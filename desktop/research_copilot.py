"""Controlled AI explanation layer for the deterministic research summary.

The copilot is deliberately downstream of :mod:`desktop.research_summary`.
It may explain an existing evidence snapshot, but it cannot calculate,
search, mutate, score, rank, or make a research decision.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from desktop.research_summary import ResearchDecisionSummary


RESEARCH_COPILOT_SYSTEM_PROMPT = """You are the optional explanation layer for an antibody research workbench.

The supplied Research Summary is the only source of evidence. Explain the
existing evidence; do not perform any new scientific operation. Do not call tools,
search literature, recalculate rule or ML results, infer missing
values, generate mutations, rank candidates, create scores, or issue a final research verdict or recommendation.

Use exactly these sections when useful:
Evidence Summary
Key Observations
Evidence Tensions
Evidence Gaps
Scientific Limitations

Treat every value as a reported model/rule result or literature metadata from
the supplied summary. Preserve DIRECT, GENERAL, and IRRELEVANT literature
labels. Do not promote GENERAL or IRRELEVANT literature into direct evidence.
Do not claim family-independent ML generalization, clinical success/failure
probability, causal mutation effects, or experimental validation that is not
present in the summary. Do not write a final recommendation, Go/No-Go,
best/recommended mutation, overall score, or pass/fail decision.

If the evidence is incomplete or tensions exist, say so explicitly. Cite a
PMID, PMCID, or DOI only when that exact identifier is present in the supplied
summary. Full VH/VL sequences are intentionally excluded from this context.
"""

COPILOT_INITIAL_PROMPT = """Explain the current Research Summary for a scientist.

Organize the response under these headings where applicable:
Evidence Summary
Key Observations
Evidence Tensions
Evidence Gaps
Scientific Limitations

Do not add a Final Recommendation, Go/No-Go, Best Mutation, Overall Score,
or other decision label. Do not calculate anything beyond explaining values
already present in the summary."""

REMOTE_PRIVACY_DISCLOSURE = (
    "The structured Research Summary will be sent to the configured AI provider. "
    "Full VH/VL sequences are not included by default."
)
LOCAL_PRIVACY_DISCLOSURE = (
    "The structured Research Summary will be sent to the configured local provider. "
    "Full VH/VL sequences are not included by default."
)
MOCK_PRIVACY_DISCLOSURE = (
    "The structured Research Summary will be sent to the configured offline mock provider. "
    "Full VH/VL sequences are not included by default."
)

_REMOVED_KEYS = {
    "api_key", "apikey", "authorization", "password", "secret", "token",
    "vh", "vl", "sequence", "raw_sequence", "original_sequence",
    "mutant_sequence", "sequence_input", "path", "file_path", "local_path",
}
# Match complete sequence tokens, not amino-acid-letter substrings inside prose.
# Also cover common 10-residue blocks and residue-by-residue pasted sequences.
_SEQUENCE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"[ACDEFGHIKLMNPQRSTVWY]{20,}(?:\s+[ACDEFGHIKLMNPQRSTVWY]{20,})*"
    r"|[ACDEFGHIKLMNPQRSTVWY]{10}(?:\s+[ACDEFGHIKLMNPQRSTVWY]{10})+(?:\s+[ACDEFGHIKLMNPQRSTVWY]{1,9})?"
    r"|[ACDEFGHIKLMNPQRSTVWY](?:\s+[ACDEFGHIKLMNPQRSTVWY]){19,}"
    r")(?![A-Za-z0-9_])",
    re.I,
)
_SEQUENCE_HASH_KEYS = {"vh", "vl", "sequence", "original_hash", "mutant_hash"}
_ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/etc/|/Users/|/home/)")


def _scrub_context(value: Any, key: str = "") -> Any:
    """Keep summary facts while defensively removing raw/private fields."""

    normalized_key = key.casefold().replace("-", "_")
    if normalized_key == "sequence_hashes":
        # Chain names here identify opaque SHA256 provenance, not raw sequences.
        return {
            str(name): digest
            for name, digest in value.items()
            if str(name).casefold() in _SEQUENCE_HASH_KEYS
            and isinstance(digest, str)
            and re.fullmatch(r"[0-9a-fA-F]{64}", digest)
        } if isinstance(value, Mapping) else {}
    if normalized_key in _REMOVED_KEYS or normalized_key.endswith("_api_key"):
        return None
    if isinstance(value, Mapping):
        output: Dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            child_key = str(raw_key)
            cleaned = _scrub_context(raw_value, child_key)
            if cleaned is not None:
                output[child_key] = cleaned
        return output
    if isinstance(value, (list, tuple)):
        return [_scrub_context(item, key) for item in value]
    if isinstance(value, str):
        if _ABSOLUTE_PATH_PATTERN.match(value.strip()):
            return "[LOCAL PATH OMITTED]"
        return _SEQUENCE_PATTERN.sub("[SEQUENCE OMITTED]", value)
    return value


def _redact_question(question: str) -> str:
    value = str(question or "").strip()
    return _SEQUENCE_PATTERN.sub("[SEQUENCE OMITTED]", value)[:2000]


def _literature_identifiers(payload: Mapping[str, Any]) -> set[str]:
    identifiers: set[str] = set()
    for paper in payload.get("literature_evidence", []) or []:
        if not isinstance(paper, Mapping):
            continue
        for key in ("pmid", "pmcid", "doi", "evidence_id"):
            value = str(paper.get(key) or "").strip().casefold()
            if value:
                identifiers.add(value)
    return identifiers


@dataclass(frozen=True)
class ResearchCopilotContext:
    """Provider payload derived from one deterministic summary snapshot."""

    summary_fingerprint: str
    generated_at_utc: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary_fingerprint": self.summary_fingerprint,
            "generated_at_utc": self.generated_at_utc,
            "research_summary": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2, default=str)

    def to_prompt(self, question: str = "", history: Sequence[Mapping[str, str]] = ()) -> str:
        parts = [COPILOT_INITIAL_PROMPT if not question.strip() else _redact_question(question)]
        if history:
            compact_history = list(history)[-4:]
            parts.append("Previous copilot exchange (context only; do not treat it as evidence):\n" + json.dumps(compact_history, ensure_ascii=False))
        parts.append("Structured Research Summary (唯一事实来源):\n" + self.to_json())
        return "\n\n".join(parts)


def build_copilot_context(summary: ResearchDecisionSummary) -> ResearchCopilotContext:
    """Create a safe, sequence-free context without recomputing any evidence."""

    if not isinstance(summary, ResearchDecisionSummary):
        raise TypeError("AI Research Copilot requires a ResearchDecisionSummary")
    if summary.is_stale:
        raise ValueError("Research Summary is stale; rebuild it before AI explanation")
    payload = _scrub_context(summary.to_dict())
    if not isinstance(payload, Mapping):
        raise ValueError("Research Summary could not be converted to structured context")
    payload = dict(payload)
    payload.pop("stale", None)
    payload.pop("fingerprint", None)
    payload.pop("created_at_utc", None)
    return ResearchCopilotContext(
        summary_fingerprint=summary.fingerprint,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        payload=payload,
    )


def privacy_disclosure(provider: str) -> str:
    provider_id = str(provider or "mock").casefold()
    if provider_id in {"mock"}:
        return MOCK_PRIVACY_DISCLOSURE
    if provider_id in {"ollama", "local"}:
        return LOCAL_PRIVACY_DISCLOSURE
    return REMOTE_PRIVACY_DISCLOSURE


@dataclass(frozen=True)
class CopilotValidation:
    allowed: bool
    reason: str = ""
    citations: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchCopilotResponse:
    text: str
    summary_fingerprint: str
    validation: CopilotValidation


class ResearchCopilotBoundaryError(ValueError):
    """Raised when a provider response crosses the explanation boundary."""

    def __init__(self, validation: CopilotValidation):
        super().__init__(validation.reason)
        self.validation = validation


_FORBIDDEN_PATTERNS = (
    (re.compile(r"\b(?:final\s+(?:research\s+)?verdict|final\s+recommendation|go\s*/?\s*no[- ]?go|best\s+mutation|recommended\s+mutation|should\s+(?:proceed|be\s+rejected|be\s+selected))\b", re.I), "decision or mutation recommendation"),
    (re.compile(r"\b(?:definitely\s+(?:developable|non[- ]developable)|guaranteed|clinical\s+(?:success|failure)\s+probability)\b", re.I), "unsupported certainty or clinical probability"),
    (re.compile(r"\b(?:family[- ]independent|across\s+unrelated\s+antibody\s+famil(?:y|ies))\b.{0,80}\b(?:validated|generaliz(?:e|ation)|proven|established)\b", re.I), "unsupported family-generalization claim"),
    (re.compile(r"\b(?:overall\s+(?:evidence|decision|risk)\s+score|pass\s*/?\s*fail\s+decision)\b\s*[:=]?", re.I), "invented overall decision score"),
    (re.compile(r"(?:建议|推荐|应当|应该|优先选择|最佳|最优).{0,40}(?:突变|候选|抗体|进入实验)|(?:突变|候选).{0,30}(?:最佳|最优)|(?:最终结论|综合评分|总体评分|临床.{0,8}(?:成功|失败)概率)"), "unsupported scientific decision"),
    (re.compile(r"(?:家族独立|跨家族|无关抗体家族).{0,40}(?:验证|泛化|证明)|(?:validated|proven|established).{0,60}family[- ]independent", re.I), "unsupported family-generalization claim"),
    (re.compile(r"\bbest\s+(?:candidate|antibody)\b|\b(?:recommend|choose|select|prioritize)\b.{0,40}(?:[ACDEFGHIKLMNPQRSTVWY]\d+[ACDEFGHIKLMNPQRSTVWY]|\bmutant\b|\bcandidate\b)", re.I), "decision or mutation recommendation"),
)
_PMID_PATTERN = re.compile(r"\bPMID\s*[:#]?\s*([0-9]{4,9})\b", re.I)
_PMCID_PATTERN = re.compile(r"\bPMCID\s*[:#]?\s*(PMC[0-9]+)\b", re.I)
_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def _response_citations(text: str) -> List[str]:
    values = [*(_PMID_PATTERN.findall(text)), *(_PMCID_PATTERN.findall(text)), *(_DOI_PATTERN.findall(text))]
    return [value.rstrip(".,;:)") for value in values]


def _affirmative_clauses(text: str):
    # Negated limitations are permitted; a later "but" starts a new claim.
    clauses = re.split(r"[.!?;。！？；\n]|\b(?:but|however)\b|但是|然而", text, flags=re.I)
    for clause in clauses:
        denial = re.search(r"\b(?:not|never|no|cannot|unknown|unvalidated|unsupported)\b|未|不能|不应|无法|不支持|不建议|不推荐|不是|不可|并非|无证据|尚无", clause, re.I)
        if denial and not re.search(r"\bnot\s+only\b|不仅", clause, re.I):
            continue
        yield clause


_NUMBER = r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
_CLAIM_SEPARATOR = r'''[\s"'`*_]*(?:为|是|is|[:=])?[\s"'`*_]*'''
_CLAIM_PATTERNS = (
    ("sequence_length", re.compile(r"(?:sequence[\s_]+length|序列长度)" + _CLAIM_SEPARATOR + _NUMBER, re.I)),
    ("sequence_length", re.compile(r"sequence\s+(?:is|has)\s+(?:a\s+length\s+of\s+)?" + _NUMBER + r"\s*(?:aa|amino\s+acids)", re.I)),
    ("calculated_score", re.compile(r"(?<![A-Za-z])(?:risk[\s_]+score|rule\s+score|calculated(?:\s+rule)?[\s_]+score|风险评分|风险分数|规则评分)" + _CLAIM_SEPARATOR + _NUMBER, re.I)),
    ("total_sites", re.compile(r"(?:total\s+(?:risk\s+)?sites|总风险位点数|风险位点总数)\s*(?:为|是|[:=])?\s*" + _NUMBER, re.I)),
    ("cdr_sites", re.compile(r"(?:CDR\s+(?:risk\s+)?sites|CDR风险位点数)\s*(?:为|是|[:=])?\s*" + _NUMBER, re.I)),
    ("hic_estimate", re.compile(r"(?:HIC(?:\s+model)?\s+estimate|HIC预测值|HIC估计值)\s*(?:为|是|[:=])?\s*" + _NUMBER, re.I)),
    ("probability_not_developable", re.compile(r"(?:P\(NOT_DEVELOPABLE\)|NOT_DEVELOPABLE\s+probability)\s*(?:为|是|[:=])?\s*" + _NUMBER + r"\s*(%)?", re.I)),
)


def _matches_display_value(raw, expected, *, percent=False, discrete=False):
    if expected is None or not isinstance(expected, (int, float)) or not math.isfinite(expected):
        return False
    expected = expected * 100 if percent else expected
    claimed = float(raw)
    if math.isclose(claimed, expected, rel_tol=1e-6, abs_tol=1e-6):
        return True
    if discrete or "e" in raw.lower():
        return False
    decimals = len(raw.partition(".")[2])
    return math.isclose(claimed, round(expected, decimals), rel_tol=1e-9, abs_tol=1e-9)


def _validate_numeric_claims(text, payload):
    facts = dict(payload.get("sequence_analysis") or {})
    facts.update(payload.get("ml_estimates") or {})
    mutation = payload.get("mutation_analysis") or {}
    role_names = r"(baseline|original|mutant|delta|Δ|原始|基线|突变后|突变体|差值)"
    role_pattern = re.compile(role_names + r"\s*(?:(?:calculated\s+)?(?:rule\s+|risk\s+)?score|风险评分|规则评分|分数)" + _CLAIM_SEPARATOR + _NUMBER, re.I)
    role_spans = []
    for match in role_pattern.finditer(text):
        role = match.group(1).lower()
        name = "mutant_score" if role in {"mutant", "突变后", "突变体"} else "delta_score" if role in {"delta", "δ", "差值"} else "original_score"
        expected = mutation.get(name, facts.get("calculated_score") if name == "original_score" and not mutation else None)
        if not _matches_display_value(match.group(2), expected):
            return f"Response blocked: mutation {name} does not match the current Research Summary."
        role_spans.append(match.span())
    ml_pattern = re.compile(role_names + r"\s*(HIC(?:\s+model)?(?:\s+estimate)?|P\(NOT_DEVELOPABLE\)|probability(?:\s*\(percentage points\))?|HIC估计值|概率)" + _CLAIM_SEPARATOR + _NUMBER + r"\s*(%|pp|percentage points)?", re.I)
    mutation_ml = payload.get("mutation_ml") or {}
    for match in ml_pattern.finditer(text):
        role = match.group(1).lower()
        section = "mutant" if role in {"mutant", "突变后", "突变体"} else "delta" if role in {"delta", "δ", "差值"} else "baseline"
        metric = "hic" if match.group(2).upper().startswith("HIC") else "probability"
        expected = (mutation_ml.get(section) or {}).get(metric)
        if not mutation_ml and section == "baseline":
            expected = facts.get("hic_estimate" if metric == "hic" else "probability_not_developable")
        percent = metric == "probability" and (bool(match.group(4)) or "percentage points" in match.group(2).lower())
        if not _matches_display_value(match.group(3), expected, percent=percent):
            return f"Response blocked: mutation ML {section} {metric} does not match the current Research Summary."
        role_spans.append(match.span())
    for name, pattern in _CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in role_spans):
                continue
            expected = facts.get(name)
            percent = name == "probability_not_developable" and bool(match.group(2))
            if not _matches_display_value(match.group(1), expected, percent=percent, discrete=name in {"sequence_length", "total_sites", "cdr_sites"}):
                return f"Response blocked: {name} claim does not match the current Research Summary."
    return ""


def validate_copilot_response(text: str, context: ResearchCopilotContext) -> CopilotValidation:
    """Reject unsafe decision language and identifiers absent from the summary."""

    value = str(text or "").strip()
    for clause in _affirmative_clauses(value):
        for pattern, reason in _FORBIDDEN_PATTERNS:
            if pattern.search(clause):
                return CopilotValidation(False, f"Response blocked: {reason}.")
    numeric_error = _validate_numeric_claims(value, context.payload)
    if numeric_error:
        return CopilotValidation(False, numeric_error)
    allowed_ids = _literature_identifiers(context.payload)
    citations = tuple(_response_citations(value))
    for citation in citations:
        if citation.casefold() not in allowed_ids:
            return CopilotValidation(False, f"Response blocked: citation {citation} is not present in the Research Summary.", citations)
    return CopilotValidation(True, citations=citations)


class ResearchCopilotValidator:
    """Small injectable validator facade for UI/tests."""

    def validate(self, text: str, context: ResearchCopilotContext) -> CopilotValidation:
        return validate_copilot_response(text, context)


@dataclass
class ResearchCopilotSession:
    """One pinned explanation session; it never silently follows a new snapshot."""

    context: ResearchCopilotContext
    validator: ResearchCopilotValidator = field(default_factory=ResearchCopilotValidator)
    history: List[Dict[str, str]] = field(default_factory=list)
    last_response: Optional[ResearchCopilotResponse] = None

    @property
    def summary_fingerprint(self) -> str:
        return self.context.summary_fingerprint

    def is_current(self, summary: Optional[ResearchDecisionSummary]) -> bool:
        return bool(summary and not summary.is_stale and summary.fingerprint == self.summary_fingerprint)

    def explain(self, backend: Any, question: str = "", current_summary: Optional[ResearchDecisionSummary] = None) -> ResearchCopilotResponse:
        if current_summary is not None and not self.is_current(current_summary):
            raise ValueError("Research Summary changed; rebuild and start a new explanation")
        prompt = self.context.to_prompt(question, self.history)
        text = str(backend.complete(prompt, system_prompt=RESEARCH_COPILOT_SYSTEM_PROMPT) or "").strip()
        validation = self.validator.validate(text, self.context)
        response = ResearchCopilotResponse(text, self.summary_fingerprint, validation)
        if not validation.allowed:
            raise ResearchCopilotBoundaryError(validation)
        self.last_response = response
        if question.strip():
            self.history.extend([
                {"role": "user", "content": _redact_question(question)},
                {"role": "assistant", "content": text[:4000]},
            ])
            del self.history[:-8]
        return response


__all__ = [
    "COPILOT_INITIAL_PROMPT",
    "LOCAL_PRIVACY_DISCLOSURE",
    "MOCK_PRIVACY_DISCLOSURE",
    "REMOTE_PRIVACY_DISCLOSURE",
    "RESEARCH_COPILOT_SYSTEM_PROMPT",
    "CopilotValidation",
    "ResearchCopilotBoundaryError",
    "ResearchCopilotContext",
    "ResearchCopilotResponse",
    "ResearchCopilotSession",
    "ResearchCopilotValidator",
    "build_copilot_context",
    "privacy_disclosure",
    "validate_copilot_response",
]
