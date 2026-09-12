import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from literature import Evidence
from models import RiskItem


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def evidence(**kwargs):
    data = dict(
        evidence_id="europepmc:1", title="Antibody deamidation", authors=["A Author"],
        journal="Journal", year=2024, pmid="12345678", pmcid="PMC123", doi="10.1000/test",
        abstract="Deamidation in antibodies.", source="europepmc", is_open_access=True,
        full_text_available=True,
    )
    data.update(kwargs)
    return Evidence(**data)


def test_adapter_converts_structured_evidence_and_classifies(monkeypatch):
    import desktop.literature_adapter as adapter

    monkeypatch.setattr(adapter, "search_literature", lambda *args, **kwargs: [evidence()])
    result = adapter.search_desktop_literature("antibody deamidation")
    assert result[0].title == "Antibody deamidation"
    assert result[0].relevance == "DIRECT"
    assert result[0].doi == "10.1000/test"
    assert result[0].source_url == "https://doi.org/10.1000/test"


def test_source_url_priority_and_missing_metadata():
    from desktop.literature_adapter import source_url

    assert source_url(evidence(doi="", pmid="12345678")) == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert source_url(evidence(doi="", pmid="", pmcid="PMC123")) == "https://europepmc.org/article/PMC/123"
    assert source_url(evidence(doi="not a doi", pmid="", pmcid="")) == ""


def test_irrelevant_results_hidden_but_retained():
    from desktop.literature_adapter import DesktopEvidence, visible_results

    rows = [DesktopEvidence(title="direct", relevance="DIRECT"), DesktopEvidence(title="irrelevant", relevance="IRRELEVANT")]
    assert [r.title for r in visible_results(rows)] == ["direct"]
    assert [r.title for r in visible_results(rows, "All")] == ["direct", "irrelevant"]


def test_literature_page_has_search_controls_and_privacy_notice(qapp):
    from desktop.widgets.literature import LiteraturePage

    page = LiteraturePage()
    assert page.query is not None
    assert page.source.currentData() == "auto"
    assert page.max_results.value() == 10
    assert page.search_button.text() == "Search"
    assert page.results_table.columnCount() == 7
    assert "external providers" in page.privacy.text()


def test_empty_query_is_rejected_without_worker(qapp):
    from desktop.widgets.literature import LiteraturePage

    page = LiteraturePage(); page.query.setText("   ")
    page.search()
    assert page._worker is None
    assert page.search_button.isEnabled()


def test_page_renders_result_and_selection_detail(qapp):
    from desktop.widgets.literature import LiteraturePage
    from desktop.literature_adapter import DesktopEvidence

    page = LiteraturePage()
    result = DesktopEvidence(title="Paper", authors=["Author"], journal="Journal", year=2024, pmid="12345678", doi="10.1000/test", abstract="Abstract", relevance="GENERAL", relevance_reason="general topic", source_url="https://doi.org/10.1000/test")
    page._done([result])
    assert page.results_table.rowCount() == 1
    page.results_table.selectRow(0)
    assert page.title.text() == "Paper"
    assert page.authors.text() == "Author"
    assert page.abstract.text() == "Abstract"
    assert page.pmid.text() == "12345678"
    assert page.doi.text() == "10.1000/test"
    assert page.relevance.text() == "GENERAL"
    assert page.open_source_button.isEnabled()


@pytest.mark.parametrize(
    "message, expected",
    [
        ("timeout", "timed out"),
        ("HTTP 429 rate limit", "rate limit"),
        ("connection failed", "temporarily unavailable"),
        ("provider api error", "API error"),
    ],
)
def test_error_messages_are_user_friendly(message, expected):
    from desktop.widgets.literature import LiteraturePage

    assert expected.lower() in LiteraturePage._friendly_error(message).lower()


def test_single_context_is_topic_only():
    from desktop.literature_context import single_risk_context

    context = single_risk_context(RiskItem(category="脱酰胺", motif="NG", position="55-56", region="CDR2"))
    assert context.source == "single"
    assert all(term in context.safe_query.lower() for term in ("antibody", "deamidation", "ng", "cdr"))
    assert "120" not in context.safe_query and "project" not in context.safe_query
    assert "NG" in context.display_summary and "55-56" in context.display_summary


def test_mutation_context_is_topic_only():
    from desktop.literature_context import mutation_risk_context

    context = mutation_risk_context("N55Q", RiskItem(category="脱酰胺", motif="NG", position="55-56", region="CDR2"), "removed")
    assert context.source == "mutation" and context.change_type == "removed"
    assert all(term in context.safe_query.lower() for term in ("antibody", "deamidation", "ng", "mutation"))
    assert "n55q" not in context.safe_query.lower()


def test_context_load_clears_stale_results_and_keeps_query_editable(qapp):
    from desktop.literature_context import LiteratureContext
    from desktop.widgets.literature import LiteraturePage
    from desktop.literature_adapter import DesktopEvidence

    page = LiteraturePage(); page._done([DesktopEvidence(title="old")])
    page.load_context(LiteratureContext("single", "Deamidation", "NG", "55-56", "CDR2", safe_query="antibody deamidation NG motif CDR", display_summary="Risk: Deamidation"))
    assert page.results_table.rowCount() == 0
    assert page.query.text() == "antibody deamidation NG motif CDR"
    assert not page.context_banner.isHidden()
    page.query.setText("custom antibody deamidation")
    assert page.query.isEnabled() and page.query.text().startswith("custom")
    page.clear_context()
    assert page.context_banner.isHidden() and page._context is None


def test_single_selected_risk_navigates_without_search(qapp):
    from desktop.widgets.single_analysis import SingleAnalysisPage
    from desktop.literature_context import LiteratureContext

    calls = []
    page = SingleAnalysisPage(open_literature=calls.append)
    page.set_input("Ab-001", "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS")
    page.table.selectRow(0)
    assert page.find_literature_button.isEnabled()
    page.find_literature_button.click()
    assert len(calls) == 1 and isinstance(calls[0], LiteratureContext)
    assert "EVQL" not in calls[0].safe_query and "Ab-001" not in calls[0].safe_query


def test_mutation_removed_risk_navigates_without_search(qapp):
    from desktop.widgets.mutation import MutationPage
    from desktop.mutation_adapter import compare_mutation
    from desktop.literature_context import LiteratureContext

    seq = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
    calls = []; page = MutationPage(open_literature=calls.append); page._done(compare_mutation(seq, "N55Q", chain="VH"))
    page.removed_table.selectRow(0)
    assert page.find_removed_button.isEnabled()
    page.find_removed_button.click()
    assert len(calls) == 1 and calls[0].source == "mutation"
    assert "mutation" in calls[0].safe_query and seq not in calls[0].safe_query


def test_selected_evidence_transfers_with_bounded_provenance(qapp):
    from desktop.evidence_context import from_desktop_evidence, EvidenceContext
    from desktop.literature_adapter import DesktopEvidence

    paper = DesktopEvidence(title="Paper", authors=["Author"], pmid="12345678", doi="10.1000/test", abstract="x" * 5000, relevance="DIRECT", source="europepmc")
    context = from_desktop_evidence(paper, "antibody deamidation", "Risk: Deamidation")
    assert isinstance(context, EvidenceContext)
    assert context.title == "Paper" and context.pmid == "12345678" and context.doi == "10.1000/test"
    assert len(context.abstract_or_excerpt) == 4000
    assert "current antibody or mutation" in context.prompt_block()
    assert "x" * 4001 not in context.prompt_block()


def test_literature_send_evidence_requires_selection_and_navigates(qapp):
    from desktop.main_window import MainWindow
    from desktop.literature_adapter import DesktopEvidence

    window = MainWindow(); page = window.literature
    assert not page.send_evidence_button.isEnabled()
    page._done([DesktopEvidence(title="Selected", pmid="12345678", relevance="DIRECT", abstract="text", source="pubmed")])
    page.results_table.selectRow(0)
    assert page.send_evidence_button.isEnabled()
    page.send_evidence_button.click()
    assert window.nav.currentRow() == 4
    assert window.ai._evidence_context.title == "Selected"
    assert "12345678" in window.ai.evidence_panel.toPlainText()
    window.deleteLater(); qapp.processEvents()


def test_ai_evidence_clear_and_replace_keeps_standalone_question(qapp):
    from desktop.widgets.ai_assistant import AIAssistantPage
    from desktop.evidence_context import EvidenceContext

    page = AIAssistantPage(lambda: type("Config", (), {"provider": "mock", "api_key": ""})())
    first = EvidenceContext(title="First", pmid="11111111", relevance="GENERAL", abstract_or_excerpt="A")
    second = EvidenceContext(title="Second", pmid="22222222", relevance="DIRECT", abstract_or_excerpt="B")
    page.question.setPlainText("standalone question")
    page.load_evidence_context(first); assert "First" in page.evidence_panel.toPlainText()
    page.load_evidence_context(second); assert "Second" in page.evidence_panel.toPlainText() and "First" not in page.evidence_panel.toPlainText()
    page.clear_evidence(); assert page._evidence_context is None and page.question.toPlainText() == "standalone question"
