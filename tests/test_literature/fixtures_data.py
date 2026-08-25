# tests/test_literature/fixtures_data.py
# 供离线测试使用的 API 响应样本（结构参照 Europe PMC REST / PubMed E-utilities 真实响应）。

EUROPEMC_SEARCH_RESULT = {
    "hitCount": 3,
    "resultList": {
        "result": [
            {
                "id": "35921488", "source": "MED", "pmid": "35921488", "pmcid": "PMC9234567",
                "doi": "10.1016/j.xphs.2022.06.003",
                "title": "Deamidation of asparagine residues in recombinant antibodies",
                "authorString": "Zhang Y, Li W, Wang Q",
                "journalTitle": "J Pharm Sci", "pubYear": "2022",
                "abstractText": "Asn-Gly motifs are prone to deamidation in recombinant antibodies.",
                "isOpenAccess": "Y", "inPMC": "Y", "inEPMC": "Y",
            },
            {
                "id": "12345678", "source": "MED", "pmid": "12345678",
                "doi": "10.1000/abc123",
                "title": "Asn deamidation in therapeutic antibodies",
                "authorString": "Smith J",
                "journalTitle": "mAbs", "pubYear": "2020",
                "abstractText": "Deamidation of Asn affects stability of therapeutic antibodies.",
                "isOpenAccess": "N", "inPMC": "N",
            },
            {
                # 无 pmid 且无 abstract → 应被 is_valid 过滤
                "id": "999", "source": "MED",
                "title": "Paper without pmid",
                "authorString": "X Y", "journalTitle": "J", "pubYear": "2019",
                "abstractText": "", "isOpenAccess": "N", "inPMC": "N",
            },
        ]
    },
}

EUROPEMC_EMPTY_RESULT = {"hitCount": 0, "resultList": {"result": []}}

PUBMED_ESEARCH_RESULT = {"esearchresult": {"idlist": ["20000001", "20000002"]}}
PUBMED_ESEARCH_EMPTY = {"esearchresult": {"idlist": []}}

PUBMED_ESUMMARY_RESULT = {
    "result": {
        "20000001": {
            "title": "Antibody deamidation review",
            "authors": [{"name": "Li M"}],
            "fulljournalname": "Antibodies",
            "pubdate": "2021 Jan 01",
            "articleids": [
                {"idtype": "doi", "value": "10.1111/antibody.1"},
                {"idtype": "pmc", "value": "PMC7777777"},
            ],
        },
        "20000002": {
            "title": "Deamidation mechanism",
            "authors": [{"name": "Chen L"}, {"name": "Xu Z"}],
            "fulljournalname": "J Biol Chem",
            "pubdate": "2019",
            "articleids": [{"idtype": "doi", "value": "10.1111/jbc.2"}],
        },
    }
}

PUBMED_EFETCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>20000001</PMID>
      <Article>
        <Abstract>
          <AbstractText>Review of antibody deamidation in biopharmaceuticals.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>20000002</PMID>
      <Article>
        <Abstract>
          <AbstractText>Detailed mechanism of asparagine deamidation.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def fake_europepmc_request(url, params, *, timeout, retries, source, as_text=False):
    """按 URL 返回 Europe PMC 或 PubMed 的样本响应。"""
    if "europepmc" in url:
        return EUROPEMC_SEARCH_RESULT
    if "/esearch" in url:
        return PUBMED_ESEARCH_RESULT
    if "/esummary" in url:
        return PUBMED_ESUMMARY_RESULT
    if "/efetch" in url:
        return PUBMED_EFETCH_XML
    raise AssertionError(f"unexpected url: {url}")
