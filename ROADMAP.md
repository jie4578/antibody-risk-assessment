# 项目路线图 (ROADMAP)

> 现有项目:`antibody_risk`(基于规则的抗体可变区化学稳定性风险分析工具)
> 本文件记录项目从"规则工具"升级为"规则 + ML + RAG + Agent"复合 AIDD 项目的改造过程与后续计划。

---

## 0. 现状基线(已确认)

- 纯 Python / 无外部 API / 无 LLM / 无机器学习,确定性规则打分
- 功能:单条序列扫描、CDR 标注(Kabat 手动边界)、PTM 基序扫描、虚拟突变+重扫、批量分析(CSV/FASTA/XLSX)、Rule-based Risk Score、Gradio 界面
- 工程化:模块化(`core / models / scoring / batch_analysis / input_parser / app / scan_motifs`),测试全绿(Python 3.13 / Anaconda)
- 数据模型:`RiskItem` / `AnalysisResult`(dataclass),`RiskScore`

**定位**:领域知识(抗体可开发性)+ Python 工程实践 的扎实基石;改造目标是补上 LLM / Agent / RAG / 深度学习四块能力,形成可离线运行、分层清晰的 AIDD 技术栈。

---

## 1. 能力覆盖目标(技术视角)

| 能力方向 | 目标 | 现状 |
| --- | --- | --- |
| 工程化与测试 | 模块化、CLI + Gradio 双入口、测试全绿 | ✅ 174 passed, 2 skipped |
| 蛋白/大分子序列建模 | 抗体序列表示(AAindex / k-mer)+ 可开发性/风险属性预测 | ✅ `ml/` 实现并实测 |
| 基础深度学习 | Embedding、训练/评估、Transformer 概念 | ✅ 特征+模型训练实测;Transformer 已实测(torch) |
| RAG | 向量化、检索策略、上下文构建 | ✅ `rag/` 实现并实测 |
| LLM 智能体 | Agent、Tool Calling、Memory | ✅ `agent/` 实现并实测 |
| 多智能体编排 | 任务分解、专家协同、结果汇总 | ✅ `agent/orchestrator.py` 实现并实测 |
| LangChain 集成 | 工具打包为 LangChain Tool / ReAct | ✅ `agent/langchain_adapter.py` 已实测(langchain 1.3) |

---

## 2. 目标架构(演进)

```
antibody_risk
├── core/                  # 既有规则引擎(作为 Agent 的"工具")
│   ├── motifs.py          # 风险基序库 + 扫描
│   ├── cdr.py             # CDR 标注
│   └── scoring.py         # Rule-based 打分
├── agent/                 # 智能体层
│   ├── llm.py             # LLM 后端抽象(OpenAI/DeepSeek/本地 mock,可离线)
│   ├── tools.py           # 工具注册:抗体扫描、突变、打分、ML 预测、RAG 检索
│   ├── agent.py           # ReAct/工具调用智能体
│   ├── memory.py          # 会话/长期记忆
│   ├── orchestrator.py    # 多智能体编排(任务分解+协同)
│   └── langchain_adapter.py  # 可选:LangChain 工具/Agent 集成
├── rag/                   # 检索增强生成
│   ├── chunking.py        # 文档分块
│   ├── embeddings.py      # Embedding(TF-IDF/哈希/可选模型,可离线)
│   ├── store.py           # 向量存储(内存/可选 FAISS)
│   ├── retrieval.py       # 检索策略(向量/BM25/混合 RRF)
│   ├── context.py         # 上下文构建(prompt 组装)
│   └── knowledge_base.py  # 内置示例知识库
├── ml/                    # 深度学习
│   ├── features.py        # 蛋白/序列表示(长度 + AAindex + k-mer 哈希)
│   ├── models.py          # 属性预测模型(逻辑回归/随机森林/GBDT/LightGBM)
│   ├── train.py           # 训练/交叉验证/评估/模型落盘
│   ├── evaluate.py        # 可视化(混淆矩阵/ROC/特征重要性)
│   ├── data.py            # 合成数据 + 规则弱标签
│   └── transformer.py     # 可选:最小 Transformer 编码器(需 torch)
├── app.py                 # Gradio 界面(6 Tab:扫描/突变/批量/ML/RAG/Agent)
├── cli.py                 # 命令行入口
├── examples/              # 一键演示脚本
├── tests/                 # 全绿
└── docs(README/ROADMAP)   # 文档
```

**关键设计原则**:
1. **可离线运行 / 无强制 API**:LLM 与 Embedding 均可通过"后端抽象 + 本地 hash/规则兜底"在无网络、无 key 时运行,保证演示与 CI 稳定;接入真实 API key 即启用完整能力。
2. **复用既有规则引擎为 Tool**:`core` 风险扫描、突变、打分作为 Agent 的可调用工具,体现"把既有工程成果工具化"。
3. **保持测试全绿**,新增功能都带测试;不改坏既有用例。

---

## 3. 实施阶段

### Phase 0 — 工程底座(不改变行为)  ✅ 已完成
- [x] 新增 `pyproject.toml` / 依赖分组(核心默认可跑;`ml`/`vec`/`dl`/`agent`/`all`/`dev` 可选)
- [x] 新增 CLI 入口 `cli.py`(`scan`/`ml-train`/`ml-predict`/`rag-query`/`agent-ask`/`agent-orchestrate`)
- [x] .gitignore 更新(忽略 ml/artifacts、*.png、*.joblib、.vscode、本地私有笔记等)
- [ ] 把 `core/scoring/batch_analysis/input_parser` 重构为包结构(可选优化,暂缓,保持平铺以减少破坏)

### Phase 1 — 深度学习与分子表示(`ml/`)  ✅ 已完成
- [x] 蛋白/抗体序列表示:长度 + AAindex 理化性质 + k-mer 哈希(`ml/features.py`)
- [x] 属性预测:分类(高风险)与回归(风险分数),logistic / random_forest / gbdt / lightgbm(`ml/models.py`)
- [x] 训练 / 分层切分 / 交叉验证 / 指标(AUC、R²、MAE) / 特征重要性 / 模型落盘(`ml/train.py`)
- [x] 可视化:混淆矩阵 / ROC / 特征重要性(`ml/evaluate.py`)
- [x] 合成数据 + 规则弱标签,可离线复现(`ml/data.py`)
- [x] 测试全绿 + `examples/train_ml_demo.py` 一键演示
- [x] (可选,需 torch)`ml/transformer.py`:最小 Transformer 编码器(位置编码+多头自注意力+FFN)——已实测,测试集准确率≈0.82

### Phase 2 — RAG(`rag/`)  ✅ 已完成
- [x] 文档分块:`chunk_by_heading` / `chunk_by_length`(`rag/chunking.py`)
- [x] Embedding 抽象:`TfidfEmbedder`(字符 n-gram) / `HashingEmbedder`(稠密) / 可选 sentence-transformers(`rag/embeddings.py`)
- [x] 向量存储与余弦检索(内存);可选 `FaissStore`(`rag/store.py`)
- [x] 检索策略:`vector` / `keyword`(BM25) / `hybrid`(RRF 融合)(`rag/retrieval.py`)
- [x] 上下文构建与 prompt 组装(`rag/context.py`)
- [x] 内置示例知识库(抗体可开发性 / PTM / CDR / 免疫原性)(`rag/knowledge_base.py`)
- [x] 端到端管线 `RagPipeline`(`rag/pipeline.py`);CLI `rag-query`;测试全绿

### Phase 3 — LLM/Agent(`agent/`)  ✅ 已完成
- [x] LLM 后端抽象:`MockLLM`(离线) / `OpenAILLM` / `DeepSeekLLM`(可选 drop-in),`get_llm` 工厂(`agent/llm.py`)
- [x] Tool Calling:scan_antibody / mutate_scan / risk_score / predict_risk / rag_search(`agent/tools.py`)
- [x] ReAct 工具调用智能体(plan→act→observe→answer)(`agent/agent.py`)
- [x] Memory:会话滚动上下文 + 轻量事实积累(`agent/memory.py`)
- [x] 多智能体编排:主管分解 → scan/ml/knowledge 专家协同 → 汇总(`agent/orchestrator.py`)
- [x] CLI `agent-ask` / `agent-orchestrate`;测试全绿
- [x] (可选,需 langchain)`agent/langchain_adapter.py`:把工具打包为 LangChain StructuredTool 并装配 ReAct/AgentExecutor——已实测(兼容 0.x 与 1.x/LangGraph)

### Phase 4 — 集成与展示(大部分完成)
- [x] Gradio 升级:`app.py` 现含 6 个 Tab(扫描/突变/批量 + 🔮 ML 预测 / 📚 RAG 问答 / 🤖 Agent),handler 已联调可用
- [x] CLI 演示入口:`scan` / `ml-*` / `rag-query` / `agent-ask` / `agent-orchestrate`
- [x] README 更新:四层架构、ML/RAG/Agent 章节
- [x] `examples/train_ml_demo.py` 一键演示
- [x] git 提交并推送(commit `137e840`)
- [x] 端到端 demo 一次性脚本:`examples/run_full_demo.py` 四层全跑 → `demo/DEMO_REPORT.md` + `demo/dashboard.png`(已生成)
- [x] 实测可选模块:torch Transformer(准确率≈0.82)与 langchain 适配器(工具调用验证通过)

---

## 4. 交付物

1. 一个可运行的、分层的 AIDD 项目,从"规则"到"ML"到"RAG"到"Agent"
2. 完善的测试(174 passed)与文档(README / ROADMAP)
3. CLI + Gradio 双入口,便于现场演示
4. 可离线运行;接入 API key 可启用真实 LLM / 真实向量模型

---

## 5. 待定决策

> 以下技术决策待后续确认:
> - 是否有可用的 LLM API(OpenAI/DeepSeek 等)及 key?
> - 分子方向侧重小分子还是大分子/蛋白?(当前项目天然是蛋白/抗体方向)
> - 是否允许引入较重依赖(PyTorch/LightGBM/FAISS/Chroma),还是保持轻量可离线?
> - 是否接入真实实验/文献数据(替换合成数据与内置知识库)?
