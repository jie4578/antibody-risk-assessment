"""Simplified-Chinese presentation only; canonical evidence is never translated in place."""
from __future__ import annotations

import re


VALUES = {
    "Low Risk": "低风险", "Medium Risk": "中风险", "High Risk": "高风险",
    "SUCCESS": "成功", "PARTIAL": "部分有效", "INVALID": "无效", "WARNING": "警告", "ERROR": "错误",
    "DIRECT": "直接相关（DIRECT）", "GENERAL": "一般参考（GENERAL）",
    "IRRELEVANT": "不相关（IRRELEVANT）", "Unspecified": "未指定",
    "FW": "框架区（FW）", "N/A": "不适用", "None": "无", "not recorded": "未记录",
    "internal AIntibody sequence landscape": "AIntibody 内部序列空间",
}

NOTICES = {
    "Local inference; sequence ML inference runs locally and does not require DeepSeek/OpenAI. No provider API call and no sequence upload.": "本地推理：序列 ML 在本机运行，不需要 DeepSeek/OpenAI，不调用服务 API，也不上传序列。",
    "Use as research support; experimental verification remains required.": "仅供科研辅助参考，仍需实验验证。",
    "No categorical decision threshold is defined.": "未设置分类决策阈值。",
    "84/95 held-out TEST sequences had paired-min identity >=0.90 to training data. Performance on distant antibody families is unknown.": "留出 TEST 中有 84/95 条序列与训练数据的配对最小序列一致性 >=0.90；模型对远缘抗体家族的表现未知。",
    "Rule-based liability screening does not constitute broad antibody developability prediction.": "基于规则的风险筛查不等同于广泛的抗体可开发性预测。",
    "Phase 5 ML benchmark is internal and contains substantial residual sequence similarity: 84/95 held-out TEST sequences had paired-min identity >=0.90 to training data.": "Phase 5 ML 基准属于内部基准，仍存在较高序列相似性：留出 TEST 中有 84/95 条序列与训练数据的配对最小序列一致性 >=0.90。",
    "Family-independent generalization is unknown.": "跨抗体家族的独立泛化能力未知。",
    "ML estimates require experimental verification.": "ML 估计仍需实验验证。",
    "Mutation ML deltas are not validated mutation-effect measurements.": "突变 ML 差值不是经过验证的突变效应测量。",
    "Literature evidence may provide mechanism/context without validating this exact antibody or mutation.": "文献可提供机制或背景信息，但不代表已验证当前这条抗体或突变。",
    "ML Δ values are differences between model estimates and are not validated experimental mutation-effect measurements.": "ML 差值仅是模型估计值之差，不是经过实验验证的突变效应测量。",
    "The underlying models were benchmarked on antibody-level experimental properties. Single-mutation effect-size accuracy has not been independently validated.": "这些模型的基准测评对象是抗体层面的实验性质；单个突变效应量的准确性尚未经过独立验证。",
    "The models were benchmarked on antibody-level experimental properties. Single-mutation effect-size accuracy has not been independently validated.": "这些模型的基准测评对象是抗体层面的实验性质；单个突变效应量的准确性尚未经过独立验证。",
    "Experimental ML estimates have not been calculated.": "尚未计算实验性 ML 估计。",
    "No literature evidence has been attached.": "尚未附加文献证据。",
    "No mutation hypothesis is included in this summary.": "本摘要未包含突变假设。",
    "Mutation ML comparison has not been calculated.": "尚未计算突变 ML 比较。",
    "Mutation evidence excluded: baseline sequence/chain or antibody identity does not match the current analysis, or cannot be verified.": "已排除突变证据：基线序列、链类型或抗体身份与当前分析不匹配，或无法核实。",
    "Mutation ML evidence excluded: baseline sequence identity does not match the current analysis.": "已排除突变 ML 证据：基线序列身份与当前分析不匹配。",
    "Local ML model artifacts are not available.": "本地 ML 模型文件不可用。",
    "The local sequence model is not cached. Install/download it before running ML estimates.": "本地尚未缓存序列模型，请安装或下载后再运行 ML 估计。",
    "The local sequence model dependencies are not installed.": "尚未安装本地序列模型所需的依赖。",
    "Local ML estimates are unavailable because runtime status could not be determined.": "无法确定运行环境状态，本地 ML 估计暂不可用。",
    "Select VH or VL before running Experimental ML comparison.": "请先选择 VH 或 VL，再运行实验性 ML 比较。",
    "Both VH and VL are required for Experimental ML comparison.": "实验性 ML 比较需要同时提供 VH 和 VL 序列。",
    "Baseline VH does not match the validated mutation comparison.": "基线 VH 与已验证的突变比较不匹配。",
    "Baseline VL does not match the validated mutation comparison.": "基线 VL 与已验证的突变比较不匹配。",
    "Invalid mutation format; use one mutation such as N55Q.": "突变格式无效，请输入单个突变，例如 N55Q。",
    "Mutation does not change the residue.": "该突变未改变氨基酸残基。",
    "Mutation position must be 1-based and greater than zero.": "突变位置从 1 开始编号，且必须大于零。",
    "Please enter a literature query.": "请输入文献检索词。",
    "Invalid literature source.": "文献来源无效。",
    "API key is invalid or unauthorized.": "API 密钥无效或未经授权。",
    "Request rate limit reached. Try again later.": "请求频率已达上限，请稍后重试。",
    "The provider did not respond within the configured timeout.": "服务提供方未在设定的超时时间内响应。",
    "The selected model is unavailable or unsupported.": "所选模型不可用或不受支持。",
    "Invalid provider URL.": "服务提供方 URL 无效。",
    "Connection to the provider failed.": "无法连接到服务提供方。",
    "The provider returned an API error.": "服务提供方返回 API 错误。",
    "The provider request failed.": "服务请求失败。",
}


def display_value(value) -> str:
    text = str(value)
    return VALUES.get(text, text)


def notice_zh(value) -> str:
    """Translate known application notices, leaving unknown diagnostics verbatim."""
    text = str(value)
    if text in NOTICES:
        return NOTICES[text]
    match = re.fullmatch(r"Expected residue (\w) at position (\d+), but found (\w)\.", text)
    if match:
        old, position, found = match.groups()
        return f"位置 {position} 预期为残基 {old}，实际为 {found}。"
    match = re.fullmatch(r"Invalid (source|target) residue: (.+)\.", text)
    if match:
        return f"{'原始' if match[1] == 'source' else '目标'}残基无效：{match[2]}。"
    return text


def evidence_zh(task: str) -> str:
    from desktop.ml_metadata import EVIDENCE
    values = EVIDENCE[task]
    if task == "hic":
        return f"冻结 Phase 5 TEST 证据：Spearman {values['spearman']:.6f}，R² {values['r2']:.6f}，N={values['n']}。"
    return (f"冻结 Phase 5 TEST 证据：PR-AUC {values['pr_auc']:.6f}，"
            f"ROC-AUC {values['roc_auc']:.6f}，阳性比例 {values['prevalence']:.6f}，N={values['n']}。")


def privacy_zh(provider: str) -> str:
    from desktop.research_copilot import privacy_disclosure
    # Resolve via the existing provider policy; display translation has no routing role.
    original = privacy_disclosure(provider)
    destination = "已配置的 AI 服务提供方"
    if "offline mock" in original:
        destination = "已配置的离线模拟服务（Mock）"
    elif "local provider" in original:
        destination = "已配置的本地服务"
    return f"结构化科研摘要将发送至{destination}；默认不包含完整 VH/VL 序列。"


def model_details_zh(text: str) -> str:
    """Translate labels in generated model details, not arbitrary paper/user content."""
    prefixes = {
        "HIC model:": "HIC 模型：", "HIC model ID:": "HIC 模型 ID：",
        "Composite model:": "复合终点模型：", "Composite model ID:": "复合终点模型 ID：",
        "Composite:": "复合终点：", "Benchmark scope:": "基准范围：", "Benchmark:": "基准：",
        "Device:": "设备：", "Run UTC:": "运行时间（UTC）：", "Model IDs:": "模型 ID：",
        "Model version:": "模型版本：", "Model manifest:": "模型清单：",
        "VH input hash prefix:": "VH 输入哈希前缀：", "VL input hash prefix:": "VL 输入哈希前缀：",
    }
    rendered = []
    for line in text.splitlines():
        original = line
        line = notice_zh(line)
        for prefix, chinese in prefixes.items():
            if original.startswith(prefix):
                line = chinese + original[len(prefix):]
                break
        line = line.replace("Frozen Phase 5 TEST evidence:", "冻结 Phase 5 TEST 证据：")
        line = line.replace("prevalence ", "阳性比例 ")
        line = line.replace("internal AIntibody sequence landscape", VALUES["internal AIntibody sequence landscape"])
        rendered.append(line)
    return "\n".join(rendered)


def evidence_context_zh(context) -> str:
    return (f"所选文献证据（原文）\n标题：{context.title}\n作者：{context.authors}\n"
            f"期刊：{context.journal}\n年份：{context.year or ''}\nPMID：{context.pmid}\n"
            f"PMCID：{context.pmcid}\nDOI：{context.doi}\n相关性：{display_value(context.relevance)}\n"
            f"来源：{context.source}\n摘要 / 摘录（原文）：{context.abstract_or_excerpt}\n\n"
            "这是外部文献证据，本身不代表已通过实验验证当前抗体或突变。")


def render_summary_zh(summary) -> str:
    """Read the same immutable snapshot; do not translate its data or fingerprint."""
    from desktop.research_summary import MUTATION_ML_EXPANDED_LIMITATION, MUTATION_ML_WARNING
    from desktop.ml_metadata import BENCHMARK_ID, BENCHMARK_SCOPE

    lines = ["科研决策摘要", ""]

    def section(title):
        lines.extend(["", title, "-" * 24])

    if summary.is_stale:
        lines.append("摘要已过期：证据已变化，请重新生成。")
    section("序列风险筛查")
    sequence = summary.sequence_analysis
    context = sequence.get("chain_context")
    if context:
        known = "Rule screening: first input only; interpreted as VH for paired ML. VL partner is not rule-scanned."
        lines.append("规则仅扫描第一个输入框；配对 ML 时视为 VH，VL 配对链不参与规则扫描。" if context == known else str(context))
    fields = (("科学规则版本", "rule_version"), ("规则计算分数", "calculated_score"),
              ("规则风险等级", "risk_level"), ("检测到的风险位点数", "total_sites"), ("CDR 风险位点数", "cdr_sites"))
    for label, key in fields:
        if sequence.get(key) is not None:
            lines.append(f"{label}：{display_value(sequence[key])}")
    if sequence.get("calculated_score") is None and sequence.get("total_sites") is None:
        lines.append("暂无规则筛查结果。")
    else:
        if sequence.get("categories"):
            lines.append("PTM / 化学风险类别：" + "、".join(sequence["categories"]))
        sites = sequence.get("representative_sites") or []
        if sites:
            lines.append("代表性检测位点：" + "; ".join("@".join(str(site.get(key, "")) for key in ("motif", "position", "region") if site.get(key) != "") for site in sites))
        lines.append("规则计算分数越高，表示计算得到的规则惩罚越低；它不是可开发性概率。")
    section("实验性 ML 估计")
    ml = summary.ml_estimates
    if ml is None:
        lines.append("尚未计算实验性 ML 估计。")
    else:
        for label, key in (("HIC 模型估计值", "hic_estimate"), ("不可开发类别概率 P(NOT_DEVELOPABLE)", "probability_not_developable")):
            if ml.get(key) is not None:
                lines.append(f"{label}：{ml[key]}")
        lines.extend([f"HIC 模型 ID：{ml.get('hic_model_id') or '未记录'}",
                      f"复合终点模型 ID：{ml.get('developability_model_id') or '未记录'}",
                      f"基准：{ml.get('benchmark') or BENCHMARK_ID}；范围：{display_value(ml.get('scope') or BENCHMARK_SCOPE)}。"])
        for key in ("hic_evidence", "developability_evidence"):
            if ml.get(key):
                lines.append(model_details_zh(ml[key]))
        lines.extend(["仅供科研辅助参考，仍需实验验证。", "该基准为内部基准，不是跨家族独立验证。", "未设置分类决策阈值。"])
    section("突变规则比较")
    mutation = summary.mutation_analysis
    if mutation is None:
        lines.append("本摘要未包含突变假设。")
    else:
        for label, key in (("突变科学规则版本", "rule_version"), ("突变", "mutation"), ("链", "chain"),
                           ("基线规则计算分数", "original_score"), ("突变体规则计算分数", "mutant_score"), ("分数差", "delta_score")):
            if mutation.get(key) is not None:
                lines.append(f"{label}：{display_value(mutation[key])}")
        for label, key in (("已移除风险数", "removed_risks"), ("新增风险数", "added_risks"), ("未变化风险数", "unchanged_risks")):
            lines.append(f"{label}：{len(mutation.get(key) or [])}")
    section("突变 ML 比较")
    mm = summary.mutation_ml
    if mm is None:
        lines.append("尚未计算突变 ML 比较。" if mutation is not None else "尚未附加突变 ML 比较。")
    else:
        for label, key in (("基线", "baseline"), ("突变体", "mutant")):
            values = mm.get(key, {}) or {}
            lines.extend([f"{label} HIC 估计值：{values.get('hic')}", f"{label} P(NOT_DEVELOPABLE)：{values.get('probability')}"])
        delta = mm.get("delta", {}) or {}
        lines.extend([f"HIC 差值 Δ：{delta.get('hic')}", f"概率差（百分点）：{float(delta.get('probability', 0)) * 100:+.3f}",
                      notice_zh(MUTATION_ML_WARNING), notice_zh(MUTATION_ML_EXPANDED_LIMITATION)])
    section("文献证据")
    if not summary.literature_evidence:
        lines.append("尚未向本摘要附加文献证据。")
    for index, paper in enumerate(summary.literature_evidence, 1):
        # Original titles/authors/identifiers are evidence, not translatable UI text.
        authors = paper.get("authors", [])
        authors = ", ".join(authors) if isinstance(authors, list) else authors
        lines.extend([f"文献 {index}（原题）：{paper.get('title') or '无标题'}", f"  作者：{authors}",
                      f"  期刊 / 年份：{paper.get('journal') or '-'} / {paper.get('year') or '-'}",
                      f"  PMID：{paper.get('pmid') or '-'}；PMCID：{paper.get('pmcid') or '-'}；DOI：{paper.get('doi') or '-'}",
                      f"  来源：{paper.get('source') or '-'}；相关性：{display_value(paper.get('relevance') or '-')}。"])
    if summary.literature_evidence:
        lines.append(NOTICES["Literature evidence may provide mechanism/context without validating this exact antibody or mutation."])
    section("证据缺口")
    lines.extend([notice_zh(gap) for gap in summary.evidence_gaps] or ["未记录证据缺口。"])
    section("科学局限")
    lines.extend(notice_zh(limitation) for limitation in summary.limitations)
    section("溯源信息（原始技术字段）")
    lines.extend(f"{key}: {value}" for key, value in summary.provenance.items())
    lines.extend(["", "请结合这些证据层次进行人工审阅与实验规划。"])
    return "\n".join(lines)


def install_qt_chinese(app):
    """Load Qt's bundled translations for standard dialogs/context menus, if present."""
    from PySide6.QtCore import QLibraryInfo, QTranslator
    from pathlib import Path
    import sys
    import PySide6
    if getattr(app, "_antibody_zh_translator", None) is not None:
        return
    translator = QTranslator(app)
    directories = (Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath)),
                   Path(PySide6.__file__).parent / "translations",
                   Path(PySide6.__file__).parent / "Qt" / "translations",
                   Path(sys.prefix) / "Library" / "translations")
    for directory in directories:
        for filename in ("qtbase_zh_CN.qm", "qt_zh_CN.qm"):
            if translator.load(str(directory / filename)):
                app.installTranslator(translator)
                app._antibody_zh_translator = translator
                return
