"""Controlled AI explanation layer for the deterministic research summary.

The copilot is deliberately downstream of :mod:`desktop.research_summary`.
It may explain an existing evidence snapshot, but it cannot calculate,
search, mutate, score, rank, or make a research decision.
"""

from __future__ import annotations

import json
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
_SEQUENCE_PATTERN = re.compile(r"(?i)(?:[ACDEFGHIKLMNPQRSTVWY]\s*){20,}")
_ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/etc/|/Users/|/home/)")


def _scrub_context(value: Any, key: str = "") -> Any:
    """Keep summary facts while defensively removing raw/private fields."""

    normalized_key = key.casefold().replace("-", "_")
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
)
_PMID_PATTERN = re.compile(r"\bPMID\s*[:#]?\s*([0-9]{4,9})\b", re.I)
_PMCID_PATTERN = re.compile(r"\bPMCID\s*[:#]?\s*(PMC[0-9]+)\b", re.I)
_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def _response_citations(text: str) -> List[str]:
    values = [*(_PMID_PATTERN.findall(text)), *(_PMCID_PATTERN.findall(text)), *(_DOI_PATTERN.findall(text))]
    return [value.rstrip(".,;:)") for value in values]


def validate_copilot_response(text: str, context: ResearchCopilotContext) -> CopilotValidation:
    """Reject unsafe decision language and identifiers absent from the summary."""

    value = str(text or "").strip()
    for pattern, reason in _FORBIDDEN_PATTERNS:
        if pattern.search(value):
            return CopilotValidation(False, f"Response blocked: {reason}.")
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
