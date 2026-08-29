# tests/test_agent_answer_format.py
# 最终回答格式约束（prompt 层）测试：简洁输出 / 禁止自行新增风险 / 文献规则 / 模板语禁用 等。
# 全部断言实际代码中的 SCIENTIFIC_SYSTEM_PROMPT。

from agent.llm import SCIENTIFIC_SYSTEM_PROMPT as P


def test_prompt_requires_concise_output():
    assert "150～300 字" in P
    assert "简洁" in P


def test_prompt_forbids_self_discovering_new_risks():
    assert "不得自行增加工具没有识别出的风险" in P
    assert "不得自行增加该类风险" in P
    assert "工具没有返回的信息，不得自行补充" in P


def test_prompt_no_literature_section_without_search():
    assert "本次未检索特定文献。" in P
    assert "已有研究证明" in P and "研究发现" in P  # 作为禁止对象


def test_prompt_forbids_fabricated_metadata():
    assert "PMID" in P and "DOI" in P
    assert "不得使用模型记忆自行生成" in P


def test_prompt_heuristic_must_be_labeled():
    assert "heuristic / 未经实验验证" in P


def test_prompt_forbids_experimental_data_invention():
    assert "不得编造实验数据" in P
    assert "LC-MS/MS" in P
    assert "氧化剂浓度" in P  # 作为"不得自行设计实验条件"的禁止对象


def test_prompt_ban_markdown():
    for key in ("不要使用加粗", "不要使用标题符号", "不要使用横线分隔", "禁止使用任何 Markdown", "---"):
        assert key in P


def test_prompt_ban_template_phrases():
    for key in ("我协调了多个专家智能体", "以上为多专家协同的离线演示回复",
                "接入真实 LLM 后可生成更连贯的结论", "请问有什么可以帮您",
                "让我仔细检查", "您好"):
        assert key in P


def test_prompt_simple_report_structure():
    for key in ("化学稳定性风险分析", "序列长度：XXX aa", "风险位点", "工具评分", "重点关注", "验证建议", "说明"):
        assert key in P


def test_prompt_simple_experiment_advice():
    assert "建议通过 LC-MS/MS 进一步验证。" in P
    assert "建议通过强制降解进一步验证。" in P
    assert "可使用 mutate_scan 评估候选突变" in P


def test_prompt_no_repeat_tool_log():
    assert "不要输出工具调用日志" in P
    assert "不要输出工具参数" in P


def test_prompt_keeps_fact_distinction():
    # 报告各节区分工具结果/文献/推断/建议/说明
    for key in ("工具评分", "文献证据", "重点关注", "验证建议", "说明"):
        assert key in P
