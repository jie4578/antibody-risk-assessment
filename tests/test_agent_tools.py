# tests/test_agent_tools.py
# v3.0-A Tool Calling 基础架构测试：schema / 各工具 / 非法序列 / 异常隔离 / 结构化输出。

import json

import pytest

from agent.tools import (
    Tool,
    ToolRegistry,
    default_tools,
    tool_batch_analysis,
    tool_mutate_scan,
    tool_scan_antibody,
)

SEQ_N = "AAANVSTT"  # N@4,V,S,T → NVS = N-糖基化位点


# ---------- 1. Tool schema 正确 ----------
def test_tool_schema_valid_json():
    reg = default_tools()
    for tool in reg.list():
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == tool.name
        assert schema["function"]["description"]
        assert "parameters" in schema["function"]
        json.dumps(schema)  # 可 JSON 序列化


def test_default_tools_contains_v3_0_tools():
    names = default_tools().names()
    for expected in ("scan_antibody", "mutate_scan", "risk_score", "batch_analysis", "literature_search"):
        assert expected in names


def test_tool_schema_required_params():
    scan = default_tools().get("scan_antibody")
    schema = scan.to_schema()["function"]["parameters"]
    assert schema["required"] == ["sequence"]


# ---------- 2. sequence_analysis tool (scan_antibody) ----------
def test_scan_antibody_structured_output():
    out = tool_scan_antibody(SEQ_N)
    assert "序列长度 8 aa" in out
    assert "风险评分" in out
    assert "[N-糖基化] NVS@4-6(FW)" in out  # 类别化命中


def test_scan_antibody_o_glyco_marks_heuristic():
    out = tool_scan_antibody("SSSSSSP")
    assert "[O-糖基化]" in out
    assert "heuristic,未经实验验证" in out  # 场景 3:明确声明 heuristic


# ---------- 3. mutation tool (mutate_scan) ----------
def test_mutate_scan_before_after_comparison():
    out = tool_mutate_scan(SEQ_N, "N4Q")
    assert "突变 N4Q 成功" in out
    assert "突变前风险类别计数" in out and "突变后风险类别计数" in out
    assert "'N-糖基化': 1" in out.split("突变后风险类别计数")[0]  # 突变前有
    after = out.split("突变后风险类别计数")[1].split("\n")[0]
    assert "'N-糖基化'" not in after  # 突变后消除


# ---------- 4. batch tool (batch_analysis) ----------
def test_batch_tool_csv_text():
    csv_text = "antibody_id,VH,VL\nOG1,SSSSSSP,ACDEFGHIKLNPQRSTVWY\n"
    out = tool_batch_analysis(csv_text=csv_text)
    assert "批量分析 1 条记录" in out
    assert "OG1" in out
    assert "status=success" in out
    assert "PTM=5" in out  # O-糖基化计入 PTM


def test_batch_tool_csv_path(tmp_path):
    p = tmp_path / "ab.csv"
    p.write_text("antibody_id,VH,VL\nA1,AAANVSTT,ACDEFGHIKLNPQRSTVWY\n", encoding="utf-8")
    out = tool_batch_analysis(csv_path=str(p))
    assert "A1" in out
    assert "status=" in out


def test_batch_tool_requires_input():
    out = tool_batch_analysis()
    assert "csv_path" in out or "csv_text" in out


# ---------- 5. 非法序列 ----------
def test_scan_antibody_invalid_sequence():
    out = tool_scan_antibody("EVQLVES1GGGLV")
    assert "错误" in out


# ---------- 6. Tool 异常隔离 ----------
def test_tool_run_catches_errors():
    reg = ToolRegistry()
    def boom(**kwargs):
        raise RuntimeError("boom")

    reg.register(Tool(name="bad", description="bad", func=boom))
    out = reg.get("bad").run({})
    assert "执行异常" in out  # 不抛异常,转为可读信息


def test_tool_run_argument_error():
    scan = default_tools().get("scan_antibody")
    out = scan.run({"wrong_key": "x"})  # sequence 缺失
    assert "参数错误" in out


# ---------- 7. 结构化输出（字段化文本） ----------
def test_tool_outputs_labeled_fields():
    scan_out = tool_scan_antibody(SEQ_N)
    for label in ("序列长度", "风险评分", "命中风险基序"):
        assert label in scan_out
    batch_out = tool_batch_analysis(csv_text="antibody_id,VH,VL\nA1,AAANVSTT,ACDEFGHIKLNPQRSTVWY\n")
    for label in ("status=", "PTM=", "liability=", "risk_score="):
        assert label in batch_out
