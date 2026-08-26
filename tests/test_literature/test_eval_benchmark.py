# tests/test_literature/test_eval_benchmark.py
# 评估体系：指标正确性 + 离线基准确定性（不联网）。

from literature.eval_benchmark import (
    OFFLINE_CORPUS,
    hit_at_k,
    mrr_at_k,
    retrieval_metrics,
    run_offline_benchmark,
)


def test_hit_at_k():
    assert hit_at_k(["a", "b", "c"], {"b"}, 2) == 1.0
    assert hit_at_k(["a", "b", "c"], {"z"}, 2) == 0.0
    assert hit_at_k(["a"], {"a"}, 5) == 1.0


def test_mrr_at_k():
    assert mrr_at_k(["a", "b"], {"b"}, 2) == 0.5
    assert mrr_at_k(["a", "b"], {"a"}, 2) == 1.0
    assert mrr_at_k(["a", "b"], {"z"}, 2) == 0.0


def test_retrieval_metrics_dict():
    ranked = OFFLINE_CORPUS[:3]
    m = retrieval_metrics(ranked, {"100001"}, k=5)
    assert set(m.keys()) == {"hit@k", "mrr@k"}


def test_offline_benchmark_deterministic():
    r1 = run_offline_benchmark(k=5)
    r2 = run_offline_benchmark(k=5)
    assert r1 == r2  # 确定性：相同输入相同结果
    assert r1["n_queries"] == 4
    # 语料是人工构造的，rerank 应能把每类查询的相关文献排进 top-5
    assert r1["avg_hit@k"] == 1.0
    assert r1["avg_mrr@k"] > 0.0


def test_offline_benchmark_per_query():
    r = run_offline_benchmark(k=5)
    queries = {q["query"] for q in r["per_query"]}
    assert queries == {"antibody deamidation", "antibody glycosylation", "methionine oxidation antibody", "antibody aggregation"}
