# literature/search.py
# 真实在线文献检索：Europe PMC(主源) + PubMed E-utilities(备源)。
#
# search_literature(query, max_results=5, source="auto") -> list[Evidence]
#   - source="auto":   先 Europe PMC，失败/无结果再试 PubMed；两者都失败 → 抛 LiteratureSearchError
#   - source="europepmc" / "pubmed": 只调对应源
#   - 网络 timeout 10s；允许 1~2 次重试；HTTP 429 遵守 Retry-After
#   - 严格区分"API 不可用/超时/限速/解析失败"(抛错) 与 "确实无相关结果"(返回 [])
#
# 所有字段直接映射自 API 响应，缺失置空；绝不填充。全文仅对 Open Access 获取，不绕过版权。

from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional

from config import get_env
from .cache import cache_key, get_cache
from .errors import LiteratureSearchError
from .evidence import Evidence

USER_AGENT = "antibody-risk/0.1 (biomedical-literature-rag)"
DEFAULT_TIMEOUT = 10  # 秒
DEFAULT_RETRIES = 2  # 最多重试次数

# Europe PMC REST
EUROPEPMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPEPMC_FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

# PubMed E-utilities
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_ESEARCH_URL = f"{PUBMED_BASE}/esearch.fcgi"
PUBMED_ESUMMARY_URL = f"{PUBMED_BASE}/esummary.fcgi"
PUBMED_EFETCH_URL = f"{PUBMED_BASE}/efetch.fcgi"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _to_int(value) -> Optional[int]:
    m = re.search(r"\d{4}", str(value or ""))
    return int(m.group(0)) if m else None


# ---------------------------------------------------------------- HTTP 层
def _ssl_context():
    """构建 SSL 上下文：优先用 certifi 的 CA 包（Windows 上常能修复证书链校验失败），
    仍失败则按标准校验（绝不静默关闭验证）。"""
    import ssl

    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _request(url: str, params: Dict[str, str], *, timeout: int, retries: int, source: str, as_text: bool = False):
    """带重试的 HTTP GET。429 遵守 Retry-After；失败抛 LiteratureSearchError。"""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last_error: Optional[LiteratureSearchError] = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
                body = resp.read()
                return body.decode("utf-8", errors="replace") if as_text else json.loads(body.decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                retry_after = e.headers.get("Retry-After")
                wait = min(float(retry_after), 10.0) if retry_after else 1.0
                time.sleep(max(wait, 0.5))
                last_error = LiteratureSearchError("rate_limited", f"[{source}] HTTP 429", status_code=429, source=source)
                continue
            raise LiteratureSearchError("api_unavailable", f"[{source}] HTTP {e.code}", status_code=e.code, source=source)
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                last_error = LiteratureSearchError("api_unavailable", f"[{source}] 网络错误: {e.reason}", source=source)
                continue
            raise LiteratureSearchError("api_unavailable", f"[{source}] 网络错误: {e.reason}", source=source)
        except (socket.timeout, TimeoutError) as e:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                last_error = LiteratureSearchError("timeout", f"[{source}] 请求超时", source=source)
                continue
            raise LiteratureSearchError("timeout", f"[{source}] 请求超时", source=source)
        except (json.JSONDecodeError, ValueError) as e:
            raise LiteratureSearchError("parsing", f"[{source}] 响应解析失败: {e}", source=source)
    raise last_error or LiteratureSearchError("api_unavailable", f"[{source}] 重试耗尽", source=source)


# ---------------------------------------------------------------- Europe PMC
def _parse_europepmc_result(r: dict) -> Evidence:
    pmid = str(r.get("pmid") or "").strip()
    pmcid = str(r.get("pmcid") or "").strip()
    doi = str(r.get("doi") or "").strip()
    title = str(r.get("title") or "").strip()
    authors = [a.strip() for a in str(r.get("authorString") or "").split(",") if a.strip()]
    journal = str(r.get("journalTitle") or "").strip()
    year = _to_int(r.get("pubYear"))
    abstract = str(r.get("abstractText") or "").strip()
    is_oa = str(r.get("isOpenAccess") or "N").upper() == "Y"
    in_pmc = str(r.get("inPMC") or "N").upper() == "Y"
    full_text_available = is_oa and bool(pmcid) and in_pmc
    eid = f"europepmc:{pmid or r.get('id') or ''}"
    partial = not (title and abstract and pmid)
    return Evidence(
        evidence_id=eid, title=title, authors=authors, journal=journal, year=year,
        pmid=pmid, pmcid=pmcid, doi=doi, abstract=abstract,
        is_open_access=is_oa, full_text_available=full_text_available,
        source="europepmc", retrieved_at=_now(), partial=partial,
    )


def _search_europepmc(query: str, max_results: int, timeout: int, retries: int) -> List[Evidence]:
    base = get_env("EUROPEPMC_BASE_URL", EUROPEPMC_SEARCH_URL)
    data = _request(
        base,
        {"query": query, "format": "json", "pageSize": str(max_results), "resultType": "core"},
        timeout=timeout, retries=retries, source="europepmc",
    )
    results = (data or {}).get("resultList", {}).get("result", [])
    evidence = [_parse_europepmc_result(r) for r in results]
    return [e for e in evidence if e.is_valid()]


def fetch_full_text(pmcid: str, *, timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES) -> str:
    """获取 Europe PMC Open Access 全文（仅应在 is_open_access=True 时调用）。返回纯文本；失败抛错。"""
    pmcid = (pmcid or "").strip()
    if not pmcid.startswith("PMC"):
        raise LiteratureSearchError("invalid_input", f"pmcid 格式无效: {pmcid}")
    base = get_env("EUROPEPMC_BASE_URL", EUROPEPMC_FULLTEXT_URL)
    url = base.format(pmcid=pmcid)
    xml_text = _request(url, {}, timeout=timeout, retries=retries, source="europepmc", as_text=True)
    return _extract_fulltext_text(xml_text)


def _extract_fulltext_text(xml_text: str) -> str:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise LiteratureSearchError("parsing", f"全文 XML 解析失败: {e}", source="europepmc")
    texts = []
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag in ("p", "title"):
            t = (node.text or "").strip()
            if t:
                texts.append(t)
    return "\n".join(texts)


# ---------------------------------------------------------------- PubMed
def _pm_params(extra: Dict[str, str]) -> Dict[str, str]:
    key = get_env("NCBI_API_KEY", "")
    p = dict(extra)
    if key:
        p["api_key"] = key
    return p


def _search_pubmed(query: str, max_results: int, timeout: int, retries: int) -> List[Evidence]:
    base = get_env("PUBMED_EUTILS_BASE_URL", PUBMED_BASE)
    # 1) esearch：拿 PMID 列表
    data = _request(
        base + "/esearch.fcgi",
        _pm_params({"db": "pubmed", "term": query, "retmode": "json", "retmax": str(max_results), "sort": "relevance"}),
        timeout=timeout, retries=retries, source="pubmed",
    )
    pmids = (data or {}).get("esearchresult", {}).get("idlist", [])
    if not pmids:
        return []
    pmids = pmids[:max_results]

    # 2) esummary：元数据(title/authors/journal/year/doi/pmc)
    summary = _request(
        base + "/esummary.fcgi",
        _pm_params({"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}),
        timeout=timeout, retries=retries, source="pubmed",
    )
    summary_map = (summary or {}).get("result", {})

    # 3) efetch：摘要（仅前若干篇，控制请求量）
    abstract_map = _fetch_pubmed_abstracts(pmids[: min(len(pmids), 5)], base, timeout, retries)

    evidence = []
    for pmid in pmids:
        r = summary_map.get(pmid, {}) or {}
        title = str(r.get("title") or "").strip()
        authors = [a.get("name", "") for a in r.get("authors", []) if a.get("name")]
        journal = str(r.get("fulljournalname") or r.get("source") or "").strip()
        year = _to_int(r.get("pubdate"))
        doi, pmcid = "", ""
        for aid in r.get("articleids", []):
            idtype = str(aid.get("idtype") or "")
            value = str(aid.get("value") or "")
            if idtype == "doi":
                doi = value
            elif idtype == "pmc":
                pmcid = value if value.startswith("PMC") else f"PMC{value}"
        abstract = abstract_map.get(pmid, "")
        eid = f"pubmed:{pmid}"
        partial = not (title and abstract and pmid)
        evidence.append(Evidence(
            evidence_id=eid, title=title, authors=authors, journal=journal, year=year,
            pmid=pmid, pmcid=pmcid, doi=doi, abstract=abstract,
            is_open_access=False, full_text_available=False, source="pubmed",
            retrieved_at=_now(), partial=partial,
        ))
    return [e for e in evidence if e.is_valid()]


def _fetch_pubmed_abstracts(pmids: List[str], base: str, timeout: int, retries: int) -> Dict[str, str]:
    if not pmids:
        return {}
    xml_text = _request(
        base + "/efetch.fcgi",
        _pm_params({"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"}),
        timeout=timeout, retries=retries, source="pubmed", as_text=True,
    )
    return _parse_pubmed_abstract_xml(xml_text)


def _parse_pubmed_abstract_xml(xml_text: str) -> Dict[str, str]:
    import xml.etree.ElementTree as ET

    def local(tag: str) -> str:
        return tag.split("}")[-1]

    out: Dict[str, str] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for article in root.iter():
        if local(article.tag) != "PubmedArticle":
            continue
        pmid = ""
        abstract_parts: List[str] = []
        for child in article.iter():
            tag = local(child.tag)
            if tag == "PMID":
                pmid = (child.text or "").strip()
            elif tag == "AbstractText":
                text = "".join(child.itertext()).strip()
                if text:
                    abstract_parts.append(text)
        if pmid:
            out[pmid] = " ".join(abstract_parts)
    return out


# ---------------------------------------------------------------- 统一入口
def search_literature(
    query: str,
    max_results: int = 5,
    source: str = "auto",
    *,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    use_cache: bool = True,
) -> List[Evidence]:
    """检索真实生物医学文献，返回 Evidence 列表。

    - 返回 []  仅表示"API 正常返回但确实没有相关结果"
    - 抛 LiteratureSearchError 表示"检索服务故障"（两者绝不混同）
    """
    if not query or not str(query).strip():
        raise LiteratureSearchError("invalid_input", "query 不能为空")
    max_results = min(max(int(max_results), 1), 10)
    source = (source or "auto").lower()
    if source not in ("auto", "europepmc", "pubmed"):
        raise LiteratureSearchError("invalid_input", f"未知 source: {source}")

    key = cache_key(query, source, max_results)
    if use_cache:
        cached = get_cache().get(key)
        if cached is not None:
            return [Evidence.from_dict(item) for item in cached]

    if source == "pubmed":
        result = _search_pubmed(query, max_results, timeout, retries)
        _maybe_cache(key, result, use_cache)
        return result

    # europepmc / auto
    euro_error: Optional[LiteratureSearchError] = None
    try:
        result = _search_europepmc(query, max_results, timeout, retries)
        if result:
            _maybe_cache(key, result, use_cache)
            return result
        euro_error = None  # europepmc 正常但无结果
    except LiteratureSearchError as e:
        euro_error = e

    if source == "europepmc":
        if euro_error is not None:
            raise euro_error
        return []

    # source == "auto"：Europe PMC 无果/失败 → 尝试 PubMed
    try:
        result = _search_pubmed(query, max_results, timeout, retries)
        if result:
            _maybe_cache(key, result, use_cache)
            return result
    except LiteratureSearchError as e:
        # 两个源都失败 → 必须明确报错，不能伪装成"无结果"
        raise euro_error if euro_error is not None else e

    return []  # 两个源都正常返回但均无结果


def _maybe_cache(key: str, result: List[Evidence], use_cache: bool) -> None:
    if use_cache:
        get_cache().set(key, [e.to_dict() for e in result])
