# Antibody AI Research Assistant

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Gradio](https://img.shields.io/badge/Gradio-4.x-orange)](https://gradio.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个面向 **AIDD（AI 药物研发）** 的复合型抗体可开发性分析项目，将三条技术线整合在一个可运行仓库里：

1. **规则引擎**（`core/`，既有）：扫描脱酰胺、异构化、氧化、N-糖基化等风险基序，标注 CDR / FW 区域，支持虚拟突变模拟、批量分析（CSV / FASTA / XLSX）与 Rule-based Computational Risk Score。
2. **机器学习属性预测**（`ml/`，新增）：把抗体可变区序列编码为数值特征（长度 + AAindex 理化性质 + k-mer 哈希），训练**风险等级分类**与**风险分数回归**模型，含交叉验证、AUC / R²、特征重要性、可视化，覆盖"序列→特征→模型→验证"的完整 ML 流程。
3. **检索增强生成 RAG**（`rag/`，新增）：内置抗体可开发性 / PTM 知识库，文档分块 → Embedding → 检索（向量 / BM25 / 混合 RRF）→ 上下文构建 → prompt 组装。
4. **LLM 智能体**（`agent/`，新增）：工具调用(scan / mutate / score / predict / rag)、Memory、ReAct 智能体循环、多智能体编排（任务分解 + 专家协同），默认用可离线的 MockLLM，接入 key 可启用真实 LLM。

核心设计原则：**可离线运行、无强制外部 API**。ML 采用 `numpy + scikit-learn + lightgbm`（可选）；LLM / Embedding 通过"后端抽象 + 本地兜底"实现，无 key 也能跑通演示，接入 key 即启用完整能力。

> **关于 ML 标签的诚实说明**：`ml/` 里用"规则引擎打标签"生成可复现的合成数据集（weak label），因此模型学到的是规则引擎的**平滑/可泛化替身**，用于展示完整 ML 工程流程与可开发性相对排序，**未经实验验证**、不构成实验/临床结论。

## 1. Project Overview

本工具基于规则扫描抗体可变区序列中的常见翻译后修饰（PTM）与化学不稳定（Chemical Liability）风险基序，并按 CDR / Framework 区域定位。适用于抗体药物发现早期的可开发性初筛。

支持：

- 单条抗体序列分析
- CDR 区域标注（Kabat 手动边界，可在界面中调整）
- Chemical Liability motif 扫描（脱酰胺化 NG/NS/NN、异构化 DG/DS/DA、氧化 M）
- PTM motif 扫描（N-糖基化 N-x-S/T）
- 虚拟突变 + 重扫（如 `N55Q`）
- 批量分析
- 三种输入格式：CSV / FASTA / XLSX
- Rule-based computational risk score

**本项目不是实验验证平台**，不是：

- 实验数据预测器
- 临床风险预测器
- 结构预测器
- LLM 自动科研结论系统

所有输出仅用于候选序列的**相对优先级排序**，不构成任何实验或临床结论。

## 2. Architecture

```
Gradio UI (app.py)            CLI (cli.py)
    │                              │
    ├── 序列扫描（Single Sequence）─┘
    │       ↓
    │   core.scan_sequence()          ← 旧 API 入口
    │       ↓
    │   core.analyze_sequence()       ← 统一分析入口
    │       ↓
    │   AnalysisResult (models.py)
    │       ↓
    │   to_legacy_tuple()             ← 兼容 UI 旧 schema
    │
    ├── 虚拟突变（Mutation）
    │       ↓
    │   core.mutate_and_rescan()
    │       ↓
    │   core.mutate_sequence() → core.analyze_sequence()
    │
    ├── 批量分析（Batch Analysis）
    │       ↓
    │   input_parser.load_batch_input()    ← CSV / FASTA / XLSX
    │       ↓
    │   DataFrame (antibody_id, VH, VL)
    │       ↓
    │   batch_analysis.batch_analysis()
    │       ↓
    │   core.analyze_sequence()            ← 逐条、逐链
    │       ↓
    │   scoring.compute_risk_score()
    │       ↓
    │   DataFrame（14 列结果）
    │       ↓
    │   write_result_csv()                 ← 下载临时 CSV
    │
    └── ML 属性预测（ml/）           ← 新增
            ↓
        ml.data.build_dataset()       合成抗体序列 + 规则弱标签
            ↓
        ml.features.SequenceEncoder   序列 → 数值特征（长度 + AAindex + k-mer 哈希）
            ↓
        ml.models.make_model          分类 / 回归模型
            ↓
        ml.train.train_pipeline       训练 / 交叉验证 / 指标(AUC,R²) / 特征重要性 / 保存
            ↓
        ml.evaluate                   可视化（混淆矩阵 / ROC / 特征重要性）
```

各模块职责：

| 模块 | 职责 |
| --- | --- |
| `core.py` | 单条序列分析核心：风险基序库（RISK_MOTIFS）、氨基酸校验（validate_sequence）、CDR 标注、motif 扫描、突变模拟 |
| `models.py` | 统一数据模型：RiskItem / AnalysisResult，以及旧 API（tuple / 中文键 dict）的兼容适配 |
| `scoring.py` | Rule-based Computational Risk Score 计算 |
| `batch_analysis.py` | 批量调度：逐条复用 analyze_sequence，单条异常隔离，14 列结果输出，下载用临时 CSV 生命周期管理 |
| `input_parser.py` | 统一输入解析：CSV / FASTA / XLSX → 统一 DataFrame（antibody_id, VH, VL） |
| `app.py` | Gradio 界面：序列扫描 / 虚拟突变 / 批量分析 三个 Tab |
| `cli.py` | 命令行入口：`scan` / `ml-train` / `ml-predict`（后续加 `batch` / `rag` / `agent`） |
| `ml/` | ML 属性预测：数据合成（data.py）、序列表示（features.py）、模型（models.py）、训练（train.py）、可视化（evaluate.py） |

## 3. Installation

环境要求：

- Python 3.8 或以上

基础安装（规则引擎 + ML + CLI + Gradio，默认即可运行）：

```bash
pip install -r requirements.txt        # 或 pip install .（读取 pyproject.toml 依赖）
```

可选增强（按需安装）：

```bash
pip install ".[ml]"     # lightgbm（额外树模型）
pip install ".[all]"    # lightgbm + faiss + chromadb + langchain（RAG/Agent 用）
pip install ".[dev]"    # pytest 等测试工具
```

使用入口（两种）：

1. **Gradio 界面**（推荐演示）：

```bash
python app.py
```

（`app.py` 默认以 `demo.launch(theme=gr.themes.Soft(), share=True)` 启动，会生成一个可分享的临时链接，也可直接访问本地地址。）

`app.py` 现含 **6 个 Tab**：🔍 序列扫描 / 🧪 虚拟突变 / 📊 批量分析（原有）+ 🔮 **ML 风险预测** / 📚 **RAG 知识问答** / 🤖 **智能体 Agent**（新增，分别对接 `ml/`、`rag/`、`agent/` 三层能力）。

2. **命令行**：

```bash
python cli.py scan --seq "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
python cli.py ml-train --n 800 --task classification --model logistic --save ml/artifacts/cls.joblib
python cli.py ml-predict --model ml/artifacts/cls.joblib --seq "<待预测序列>"
```

## 4. Input Formats

批量分析支持三种输入格式，统一解析为 `antibody_id` / `VH` / `VL` 三列 DataFrame 后交给 `batch_analysis()`。**相同序列无论以哪种格式输入，分析结果（risk_score / risk_level / analysis_status / 风险计数）完全一致。**

### CSV

每行一条抗体，包含三列（列名必须完全一致，列顺序不限）：

| 列名 | 说明 |
| --- | --- |
| `antibody_id` | 抗体唯一标识 |
| `VH` | 重链可变区序列（单字母氨基酸） |
| `VL` | 轻链可变区序列（单字母氨基酸） |

示例见仓库根目录 `example_antibodies.csv`。

### FASTA

推荐使用 `>抗体ID_VH` / `>抗体ID_VL` 的 header 命名，也支持 `>` 加 `|` 分隔（`>抗体ID|VH` / `>抗体ID|VL`），链标记大小写不敏感。VH 与 VL 按抗体 ID 自动配对；某条抗体缺少一条链时，该链在结果中记为空值，由现有分析逻辑处理。

- 支持多条序列。
- 序列可跨多行书写，解析时自动合并为单行。
- 序列自动转为大写，并去除行首尾空白。

示例：

```
>AB001_VH
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS

>AB001_VL
DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVEIK
```

（`>AB001|VH` / `>AB001|VL` 是等价的 header 写法。）

### Excel

- 仅支持 `.xlsx` 文件。
- 默认读取第一个 sheet。
- 列名与 CSV 相同：`antibody_id`、`VH`、`VL`，列顺序不限。
- 存在重复的 `antibody_id` 会报错。

> 当前**不支持** `.xls` / `.xlsm` 格式。

## 5. Rule-based Computational Risk Score

批量分析输出中的 `risk_score`（0–100）与 `risk_level`（Low / Medium / High Risk）由纯 Python 确定性规则计算。

公式：

```
score = 100 − total_penalty
```

- baseline = 100
- score 被 clamp 到 0–100
- 风险等级：

| 区间 | 等级 |
| --- | --- |
| 80–100 | Low Risk |
| 60–79 | Medium Risk |
| 0–59 | High Risk |

CDR 区域使用启发式权重（heuristic weighting）：

- CDR = 1.3
- Framework = 1.0

同一基序重复出现：第 1 次全额罚分，后续 ×0.5（递减惩罚）。

> **This score is a rule-based computational prioritization score and has not been experimentally validated.**
>
> **The CDR region weighting is a heuristic used for computational prioritization and has not been experimentally validated.**

该评分是基于规则的计算优先级评分，未经实验验证；CDR 区域权重属于计算优先级排序中的启发式设计，未经实验验证。该评分仅用于候选序列的相对优先级排序，**不代表**真实药物稳定性、真实糖基化发生、PK / 活性 / 免疫原性结果，也不是机器学习模型或实验数据校准结论。

## 6. Risk Score Examples

使用当前 `example_antibodies.csv` 的真实分析结果：

| antibody_id | risk_score | risk_level |
| --- | --- | --- |
| AB001 | 64.30 | Medium Risk |
| AB002 | 74.00 | Medium Risk |
| AB006_RISK | 48.95 | High Risk |

这些结果仅用于展示当前规则系统如何对候选序列排序，**不能**解释为：

- "AB001 有 64% 安全性"
- "64 分意味着实验成功率 64%"
- "High Risk = 实验一定失败"

## 7. ML 属性预测（AIDD，新增）

`ml/` 提供一个**完整、可复现**的抗体序列属性预测流程，用于把"序列"变成"可排序的判断"，并展示端到端机器学习工程实践。

### 7.1 数据（弱标签）

`ml/data.py` 用现有确定性**规则引擎**给合成的抗体样序列打标签（`risk_score` / `risk_level` / `high_risk`），得到一份可离线复现的数据集。这样做是出于两点考虑：

- 项目只有少量真实抗体序列，不足以训练，合成数据让流程自洽；
- 用规则引擎打标签（weak label）可保证**无需外部数据集、无需网络、结果确定**。

```python
from ml.data import build_dataset
df = build_dataset(n=800, seed=42)
print(df.head())
```

> 诚实说明：模型学到的是规则引擎的**平滑/可泛化替身**，用于可开发性相对排序；不是真实实验/临床预测。

### 7.2 序列特征

`ml/features.py` 的 `SequenceEncoder` 把序列编码为定长向量，特征包括：

- 长度（归一化）
- **AAindex 理化性质统计**（mean/std/min/max）：疏水性（Kyte-Doolittle）、体积、电荷、极性
- **k-mer 计数的哈希特征**（feature hashing，固定维度、长度无关）

```python
from ml.features import SequenceEncoder
enc = SequenceEncoder(k_max=3, kmer_dim=256)
X = enc.transform(df["sequence"].tolist())   # (n, n_features)
```

### 7.3 模型

`ml/models.py` 提供分类与回归两类模型，默认用 scikit-learn，安装 `lightgbm` 后额外提供梯度提升树：

- 分类（高风险与否）：`logistic` / `random_forest` / `gbdt` / `lightgbm`
- 回归（风险分数）：`ridge` / `random_forest` / `gbdt` / `lightgbm`

**（可选）Transformer 分类器**：`ml/transformer.py` 用 PyTorch 实现"位置编码 + 多头自注意力 + 前馈网络"的**最小 Transformer 编码器**（`build_transformer_classifier`），把序列当 token 处理，对应岗位要求的"Transformer 基础"。需 `pip install '.[dl]'`（torch）后启用；未装 torch 时该模块可导入但调用会给出提示。

### 7.4 训练与评估

`ml/train.py` 的 `train_pipeline` 完成分层切分、训练、测试集评估（分类：accuracy / precision / recall / f1 / roc_auc；回归：R² / MAE / RMSE）、可选 5 折交叉验证、特征重要性，并可落盘模型供复用。

```python
from ml.train import train_pipeline
result = train_pipeline(df, task="classification", model_name="logistic")
print(result.report)
```

`ml/evaluate.py` 生成混淆矩阵 / ROC / 特征重要性图：

```python
from ml.evaluate import roc_curve_plot, feature_importance_plot
roc_curve_plot(y_true, proba, "ml/artifacts/roc.png")
```

### 7.5 直接跑通（里含示例输出）

```bash
python cli.py ml-train --n 800 --task classification --model logistic --save ml/artifacts/cls.joblib
```

示例输出（`n=300, logistic`，实测）：accuracy 0.85、roc_auc 0.8542，Top 特征为 `hydropathy_KD_mean`、`volume_std` 等理化性质——提示模型主要利用疏水性/体积信息判断风险。

## 8. RAG 检索增强生成（新增）

`rag/` 实现一个**可离线运行**的 RAG 管线，覆盖岗位要求的"向量化 / 检索策略 / 上下文构建"，并对接（下一步）Agent 工具调用。

```
rag/
├── knowledge_base.py  内置抗体可开发性 / PTM / CDR / 免疫原性知识片段（教材式摘要）
├── chunking.py        文档分块：按标题(chunk_by_heading) / 按长度滑窗(chunk_by_length)
├── embeddings.py      Embedding 抽象：TfidfEmbedder(稀疏) / HashingEmbedder(稠密) / 可选 sentence-transformers
├── store.py           内存向量库 + 余弦检索；可选 FaissStore(faiss-cpu)
├── retrieval.py       检索策略：vector / keyword(BM25) / hybrid(RRF 融合)
├── context.py         上下文构建 + prompt 组装（带引用溯源）
└── pipeline.py        RagPipeline：文档→分块→向量化→检索→上下文→prompt
```

### 8.1 一条命令跑通

```bash
python cli.py rag-query --q "抗体可变区出现非保守糖基化位点有什么风险？" --show-prompt
```

### 8.2 代码用法

```python
from rag import RagPipeline
from rag.knowledge_base import KNOWLEDGE_BASE

pipe = RagPipeline(embedder="tfidf", strategy="hybrid", top_k=4)
pipe.index(KNOWLEDGE_BASE)                 # 推荐：内置知识库
result = pipe.query("抗体的脱酰胺化主要发生在哪里？")
print(result["context"])                   # 组装好的上下文（带 [n] 引用）
print(result["prompt"])                    # 可交给 LLM 的 prompt
```

### 8.3 设计要点（对应当前岗位要求）

- **向量化**：默认用 TF-IDF（字符 n-gram，兼容中英文）与 n-gram 哈希（稠密）；安装 `sentence-transformers` 可升级为真实语义向量。
- **检索策略**：`vector`（余弦）/ `keyword`（自实现 BM25，无额外依赖）/ `hybrid`（Reciprocal Rank Fusion 融合两路，兼顾语义与精确词）。
- **上下文构建**：`build_context` 把命中块拼成带 `[n]` 引用的上下文；`assemble_prompt` 用模板组装，提示模型"基于资料回答、不足则说明、不要编造"。
- **可离线**：全程无外部 API / 无网络；中文按字符 n-gram 处理，避免中文分词问题。

> 说明：内置知识库为教材/综述式摘要，用于技术演示 RAG 能力，**非真实文献引用**；接入真实文献库只需替换 `KNOWLEDGE_BASE` 或换成文档路径。

## 9. LLM / Agent 智能体（新增）

`agent/` 实现一个**可离线运行**的工具调用智能体与多智能体编排器，覆盖岗位要求的"LLM 应用与智能体开发 / Agent / Tool Calling / Memory / 多智能体协作"。

```
agent/
├── llm.py           LLM 后端抽象:MockLLM(离线) + OpenAILLM / DeepSeekLLM(可选,drop-in);ToolCall / Observation
├── tools.py         工具注册:scan_antibody / mutate_scan / risk_score / predict_risk / rag_search
├── memory.py        会话记忆(滚动上下文 + 轻量事实积累)
├── agent.py         ReAct 智能体:plan → act(调用工具) → observe → answer
└── orchestrator.py  多智能体编排:主管分解任务 → scan_agent / ml_agent / knowledge_agent 协同 → 汇总
```

### 9.1 一条命令跑通

```bash
# 单智能体（知识问答，自动走 RAG）
python cli.py agent-ask --q "什么是脱酰胺化？"
# 多智能体（评估序列 + 知识问答，分解给 scan_agent + knowledge_agent）
python cli.py agent-orchestrate --q "评估这条序列的风险并告诉我脱酰胺化为什么重要：<序列>"
```

### 9.2 代码用法

```python
from agent import Agent, Orchestrator

# 单智能体：自动识别问题并调用工具（扫描/突变/打分/ML预测/RAG）
agent = Agent()
agent.ask("请评估这条序列的风险：" + SEQ)

# 多智能体：主管分解任务，专家协同执行后汇总
orchestrator = Orchestrator()
result = orchestrator.run("评估这条序列的风险并告诉我脱酰胺化为什么重要：" + SEQ)
print(result["answer"])
```

### 9.3 设计要点

- **可离线**：默认 `MockLLM`（关键词意图规划工具调用 + 模板作答），无 key / 无网络也能演示完整 Agent 循环；`OpenAILLM` / `DeepSeekLLM` 是 drop-in，接入 key 即启用真实函数调用。
- **Tool Calling**：工具带 schema（`to_schema()` 生成 OpenAI tools 格式），能被 LLM 函数调用。
- **Memory**：`ConversationMemory` 记录对话与工具观察，跨轮共享上下文。
- **多智能体**：`Orchestrator` 依据问题把任务分解给专家智能体（规则扫描 / ML 预测 / 知识检索），共享记忆协同，再聚合。
- **工程成果工具化**：把既有规则引擎 / ML / RAG 全部封装为可调用工具，体现"把工程能力做成 Agent 的武器"。
- **（可选）LangChain 集成**：`agent/langchain_adapter.py` 把默认工具打包成 LangChain `StructuredTool` 并装配 `create_react_agent` / `AgentExecutor`，复用 LangChain 生态；需 `pip install '.[agent]'`（langchain）后启用，未安装则给出提示。

## 10. Limitations

当前工具存在以下限制：

1. 核心风险评估基于规则（rule-based）；新增 `ml/` 的机器学习模型以规则引擎为弱标签（rule-supervised surrogate），并非真实实验数据集训练
2. 未经实验验证
3. CDR 使用当前编号 / 索引近似（Kabat 手动边界）
4. VH / VL 当前共用同一套 CDR 参数（未按链独立）
5. 无结构信息
6. 无表达量数据
7. 无 PK 数据
8. 无免疫原性数据
9. N-糖基化是序列 motif 预测，不代表真实糖基化发生
10. score 不是概率
11. score 不是临床指标
12. score 不是实验结果

## 11. Testing

```bash
python -m pytest -q
```

所有测试应全部通过（当前 **174** 个：既有 122 + `ml/` 20 + `rag/` 17 + `agent/` 15）。新增测试时请保持全绿。

## 12. 应用场景

- 杂交瘤 / 噬菌体展示筛选后，对候选抗体序列进行快速成药性初筛
- 人源化改造后，检测是否引入新的化学降解风险
- 理性设计突变，去除高风险基序，指导湿实验
- 生物信息学入门项目，展示"领域知识 + Python 实战"能力
- 求职展示：作为 AIDD 岗位的**工程 + ML** 作品集（下一步接入 RAG / Agent）

## 13. 岗位要求映射（求职展示）

本项目按 **睿智医药 · 高级 AI 研发工程师（AIDD）** 岗位要求逐条对齐，映射表见完整版 `ROADMAP.md`。现状（已完成 Phase 0 - 3）：

| 岗位要求 | 本项目对应产出 |
| --- | --- |
| 扎实 Python 与工程实现 | 模块化、dataclass、异常隔离、**174 个测试**、Gradio + CLI 双入口 |
| 蛋白/大分子（序列建模方向） | 抗体序列特征化（k-mer / AAindex）+ 风险属性预测 |
| 基础深度学习（Embedding、训练/推理、Transformer/微调思路） | `ml/features.py` 表示学习、`ml/train.py` 训练与交叉验证、`ml/transformer.py` 最小编码器（可选 torch） |
| **RAG 基础实现（向量化 / 检索 / 上下文）** | `rag/`：文档分块、TF-IDF/哈希 Embedding、BM25+向量混合检索、上下文与 prompt 组装 |
| **LangChain/LlamaIndex 智能体、Agent / Tool Calling / Memory** | `agent/`：LLM 后端抽象、5 个可调用工具、ReAct 循环、会话记忆；`agent/langchain_adapter.py` 可选 LangChain 工具/Agent 集成 |
| **多智能体协作与编排（分工 / 任务分解 / 协同）** | `agent/orchestrator.py`：主管分解 → scan/ml/knowledge 专家协同 → 汇总 |
| 结合 AI 工具与工程实践，独立完成需求→方案→实现→验证 | `ml/`、`rag/`、`agent/` 端到端流程：数据→特征→模型→评估→检索→工具调用 |
| 加分：AIDD | 抗体可开发性、CDR 风险、PTM、虚拟突变分析、知识库问答、可对话研发助手 |
