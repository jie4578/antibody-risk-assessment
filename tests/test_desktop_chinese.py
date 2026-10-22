"""Chinese is presentation only: protect canonical identifiers, evidence and actions."""
import copy

import pytest

from desktop.zh_cn import display_value, evidence_zh, model_details_zh, notice_zh, privacy_zh, render_summary_zh


@pytest.fixture
def isolated_settings(monkeypatch):
    from desktop.settings import RuntimeLLMConfig
    monkeypatch.setattr("desktop.main_window.load_settings", RuntimeLLMConfig)
    monkeypatch.setattr("desktop.widgets.settings_page.load_settings", RuntimeLLMConfig)
    monkeypatch.setattr("desktop.credentials.CredentialStore.get", lambda *args: "")


def test_all_six_pages_and_main_actions_are_chinese(qt_application, isolated_settings):
    from desktop.main_window import MainWindow
    from desktop.widgets.batch_analysis import BatchAnalysisPage
    window = MainWindow()
    assert "抗体" in window.windowTitle()
    assert [window.nav.item(i).text() for i in range(window.nav.count())] == ["单条分析", "批量分析", "突变", "文献", "AI 助手", "设置"]
    assert window.single.analyze_button.text() == "分析"
    assert window.single.build_summary_button.text() == "生成科研摘要"
    assert window.single.copilot_explain_button.text() == "使用 AI 解读"
    assert window.literature.search_button.text() == "搜索"
    assert window.mutation.simulate_button.text() == "模拟突变"
    assert window.settings.test_button.text() == "测试连接"
    assert BatchAnalysisPage.COLUMNS[0] == "抗体 ID"
    assert window.ai.clear_evidence_button.text() == "清除证据"
    window.resize(1100, 750)
    window.show()
    qt_application.processEvents()
    assert window.height() == 750
    assert window.content_scroll.widget() is window.stack
    window.content_scroll.verticalScrollBar().setValue(50)
    window.nav.setCurrentRow(1)
    assert window.content_scroll.verticalScrollBar().value() == 0
    window.deleteLater()


def test_chinese_risk_filter_and_duplicate_transfers_keep_canonical_records(qt_application, tmp_path):
    from desktop.batch_adapter import analyze_file
    from desktop.batch_export import EXPORT_COLUMNS, summary_frame
    from desktop.widgets.batch_analysis import BatchAnalysisPage
    path = tmp_path / "synthetic.csv"
    path.write_text("antibody_id,VH,VL\nDUP,NNST,ACD\nDUP,AAANVSTT,MMM\n", encoding="utf-8")
    result = analyze_file(path)
    before = copy.deepcopy(result)
    transferred = []
    page = BatchAnalysisPage(open_single=lambda *args: transferred.append(args))
    page._done(result)
    for i in range(page.table.rowCount()):
        record = page.table.item(i, 0).data(32)
        page.table.selectRow(i)
        page.open_in_single()
        assert transferred[-1] == ("DUP", record.vh_sequence)
    for index, level in enumerate(("All", "Low", "Medium", "High")):
        page.risk_filter.setCurrentIndex(index)
        assert page.risk_filter.currentData() == level
        expected = sum(level == "All" or record.risk_level.startswith(level) for record in result.records)
        assert page.table.rowCount() == expected
    assert result == before
    assert list(summary_frame(result).columns) == EXPORT_COLUMNS
    assert list(summary_frame(result)["analysis_status"]) == list(summary_frame(before)["analysis_status"])
    page.deleteLater()


def test_chinese_summary_keeps_snapshot_fingerprint_and_raw_paper_verbatim(qt_application):
    from desktop.widgets.single_analysis import SingleAnalysisPage
    from desktop.research_copilot import build_copilot_context
    page = SingleAnalysisPage()
    page.set_input("Medium Risk", "NNST")  # ID is data, even if it looks like a label.
    title = "Medium Risk | Scientific Limitations\nRisk level: Low Risk"
    page.attach_literature_evidence({"title": title, "authors": ["General Author"], "doi": "10.1000/Original", "relevance": "GENERAL"})
    summary = page.build_research_summary()
    before, fingerprint = copy.deepcopy(summary.to_dict()), summary.fingerprint
    context = build_copilot_context(summary)
    original_context = context.to_json()
    translated = render_summary_zh(summary)
    assert "科研决策摘要" in translated and "规则计算分数：73.0" in translated
    assert "规则风险等级：中风险" in translated
    assert "NNS@1-3@FW" in translated and "NST@2-4@FW" in translated
    assert title in translated and "General Author" in translated and "10.1000/Original" in translated
    assert "一般参考（GENERAL）" in translated
    assert "不是可开发性概率" in translated and "泛化能力未知" in translated
    assert summary.to_dict() == before and summary.fingerprint == fingerprint
    assert context.to_json() == original_context
    assert build_copilot_context(summary).payload == context.payload
    assert summary.sequence_analysis["antibody_id"] == "Medium Risk"
    page.antibody_id.setText("OTHER")
    assert "已过期" in page.summary_status.text() and not page.copilot_explain_button.isEnabled()
    page.deleteLater()


def test_chinese_summary_preserves_ml_numbers_and_missing_values():
    from desktop.research_summary import build_research_summary
    summary = build_research_summary({"sequence_analysis": {"vh": "NNST"}, "ml_estimates": {
        "result": {"hic": {"predicted_value": 4.2, "model_id": "hic_esm2_v1"},
                   "developability": {"probability_not_developable": 0.31, "model_id": "developability_esm2_v1"}}}})
    before = copy.deepcopy(summary.to_dict())
    text = render_summary_zh(summary)
    assert "HIC 模型估计值：4.2" in text
    assert "P(NOT_DEVELOPABLE)：0.31" in text
    assert "hic_esm2_v1" in text and "developability_esm2_v1" in text
    assert "未设置分类决策阈值" in text and "尚未附加突变 ML 比较" in text
    assert before == summary.to_dict()


def test_relevance_filters_show_chinese_without_changing_labels_or_original_text(qt_application):
    from desktop.literature_adapter import DesktopEvidence
    from desktop.widgets.literature import LiteraturePage
    page = LiteraturePage()
    papers = [DesktopEvidence(title="General Paper", abstract="Original English abstract.", relevance=label) for label in ("DIRECT", "GENERAL", "IRRELEVANT")]
    page._done(papers)
    for value, count in (("Direct + General", 2), ("All", 3), ("Direct", 1), ("General", 1)):
        page.filter.setCurrentIndex(page.filter.findData(value))
        assert page.results_table.rowCount() == count
    page.results_table.setCurrentCell(0, 1)
    assert page.title.text() == "General Paper" and page.abstract.text() == "Original English abstract."
    assert page._selected.relevance == "GENERAL"
    assert page.relevance.text() == "一般参考（GENERAL）"
    page.query.setText("new query")
    assert page.results_table.rowCount() == 0 and not page.send_evidence_button.isEnabled()
    assert "检索条件已变化" in page.status.text()
    page.deleteLater()


def test_localized_provider_choices_return_original_provider_ids(qt_application, isolated_settings):
    from desktop.providers import provider_spec
    from desktop.widgets.settings_page import SettingsPage
    page = SettingsPage()
    for provider in ("deepseek", "openai", "openai-compatible", "ollama", "mock"):
        page.provider.setCurrentIndex(page.provider.findData(provider))
        config = page.config()
        assert config.provider == provider
        assert config.base_url == (provider_spec(provider).default_base_url or "")
    assert "离线模拟" in page.provider.currentText()
    page.deleteLater()


def test_column_mapping_chinese_does_not_translate_original_column_names(qt_application):
    from desktop.widgets.column_mapping_dialog import ColumnMappingDialog
    page = ColumnMappingDialog(["Antibody ID", "Heavy", "Light"], initial_mapping={"antibody_id": "Antibody ID", "VH": "Heavy", "VL": "Light"})
    assert "列映射" in page.windowTitle()
    assert page.fields["Antibody ID"].currentText() == "Antibody ID"
    assert page.mapping() == {"antibody_id": "Antibody ID", "VH": "Heavy", "VL": "Light"}
    assert page.fields["VH"].itemData(0) is None and page.fields["VH"].itemText(0) == "不映射"
    page.deleteLater()


@pytest.mark.parametrize("provider, expected", [("mock", "离线模拟"), ("ollama", "本地服务"), ("deepseek", "AI 服务提供方")])
def test_chinese_privacy_keeps_provider_specific_disclosure(provider, expected):
    text = privacy_zh(provider)
    assert expected in text and "默认不包含完整 VH/VL 序列" in text


@pytest.mark.parametrize("source, expected", [("Low Risk", "低风险"), ("PARTIAL", "部分有效"), ("FW", "框架区（FW）"), ("hic_esm2_v1", "hic_esm2_v1")])
def test_display_values_never_mutate_domain_data(source, expected):
    assert display_value(source) == expected


def test_model_details_and_known_errors_keep_raw_identifiers_and_numbers():
    text = model_details_zh("HIC model ID: hic_esm2_v1\n" + evidence_zh("hic") + "\nNo categorical decision threshold is defined.")
    assert "HIC 模型 ID： hic_esm2_v1" in text
    assert all(value in text for value in ("0.834662", "0.625834", "N=72", "未设置分类决策阈值"))
    assert notice_zh("Expected residue N at position 55, but found Q.") == "位置 55 预期为残基 N，实际为 Q。"
    assert notice_zh("unknown error 0x1234") == "unknown error 0x1234"


def test_copilot_requests_chinese_without_changing_safeguards(qt_application, monkeypatch):
    from desktop.research_copilot import RESEARCH_COPILOT_SYSTEM_PROMPT, build_copilot_context
    from desktop.settings import RuntimeLLMConfig
    from desktop.widgets.single_analysis import SingleAnalysisPage
    calls = []

    class Backend:
        def complete(self, prompt, *, system_prompt):
            calls.append((prompt, system_prompt))
            return "当前摘要记录规则计算分数 73.0。"

    monkeypatch.setattr("desktop.widgets.single_analysis.build_backend", lambda config: Backend())
    page = SingleAnalysisPage()
    page.set_input("SYNTHETIC", "NNST")
    context = build_copilot_context(page.build_research_summary())
    before = context.to_json()
    result = page._run_copilot(RuntimeLLMConfig(), context)
    assert result.validation.allowed and result.summary_fingerprint == page.research_summary.fingerprint
    assert len(calls) == 1 and "请用简体中文" in calls[0][0]
    assert calls[0][1] == RESEARCH_COPILOT_SYSTEM_PROMPT
    assert context.to_json() == before
    page.deleteLater()


def test_unknown_context_is_not_replaced_with_an_invented_chain_claim():
    from desktop.research_summary import build_research_summary
    summary = build_research_summary({"sequence_analysis": {"chain_context": "Original custom chain context"}})
    text = render_summary_zh(summary)
    assert "Original custom chain context" in text
    assert "配对 ML 时视为 VH" not in text


def test_evidence_display_does_not_translate_original_title_or_prompt(qt_application):
    from desktop.evidence_context import EvidenceContext
    from desktop.settings import RuntimeLLMConfig
    from desktop.widgets.ai_assistant import AIAssistantPage
    context = EvidenceContext(title="General Study", authors="Original Author", abstract_or_excerpt="Do not translate this original abstract.", relevance="GENERAL", doi="10.1000/Original")
    original = context.prompt_block()
    page = AIAssistantPage(RuntimeLLMConfig)
    page.load_evidence_context(context)
    view = page.evidence_panel.toPlainText()
    assert all(value in view for value in (context.title, context.authors, context.abstract_or_excerpt, context.doi, "一般参考（GENERAL）"))
    assert context.prompt_block() == original
    page.deleteLater()
