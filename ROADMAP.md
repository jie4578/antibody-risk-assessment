# AIDD 岗位匹配路线图 (ROADMAP)

> 目标岗位:睿智医药(ChemPartner)· 高级 AI 研发工程师(AIDD)
> 现有项目:`antibody_risk`(基于规则的抗体可变区化学稳定性风险分析工具)
> 本文件用于把岗位要求映射为可执行的项目增强项,指导逐步改造。

---

## 0. 现状基线(已确认)

- 纯 Python / 无外部 API / 无 LLM / 无机器学习,确定性规则打分
- 功能:单条序列扫描、CDR 标注(Kabat 手动边界)、PTM 基序扫描、虚拟突变+重扫、批量分析(CSV/FASTA/XLSX)、Rule-based Risk Score、Gradio 界面
- 工程化:模块化(`core / models / scoring / batch_analysis / input_parser / app / scan_motifs`),122 个测试全绿(Python 3.13 / Anaconda)
- 数据模型:`RiskItem` / `AnalysisResult`(dataclass),`RiskScore`

**定位**:领域知识(抗体可开发性)+ Python 工程实践 的扎实基石,但**缺少**岗位核心要求的 LLM / Agent / RAG / 深度学习部分。

---

## 1. 岗位要求 → 现状差距矩阵

| # | 岗位要求(原文要点) | 现状 | 目标 | 优先级 |
|---|---|---|---|---|
| 1 | 扎实 Python,工程实现与调试 | ✅ 良好(模块化/测试/类型/边界处理) | 保持,补类型注解与 CLI | 基础 |
| 2 | 熟悉 LangChain / LlamaIndex 的 LLM 应用与智能体开发;理解 Agent / Tool Calling / Memory | ❌ 无 LLM | 新增 `agent/` 模块:LLM 后端抽象、Agent、Tool Calling、Memory | 🔴 高 |
| 3 | 理解并具备 RAG 基础实现经验(向量化、检索、上下文构建) | ❌ 无 | 新增 `rag/` 模块:文档分块、Embedding、向量检索、上下文组装 | 🔴 高 |
| 4 | 多智能体协作与编排(分工、任务分解、协同执行),关注并快速上手新框架 | ❌ 无 | 新增多智能体编排(主管/推理/工具智能体 + 任务分解) | 🟠 中高 |
| 5 | 基础深度学习:常见模型结构与训练/推理(Transformer、Embedding、简单微调) | ❌ 无(纯规则) | 新增 `ml/` 模块:蛋白/序列 Embedding、属性预测、微调、Transformer 基础 | 🟠 中高 |
| 6 | 分子设计 AI 至少熟悉一个方向:小分子(表征/性质预测/虚拟筛选) 或 大分子(序列/结构建模、蛋白/核酸应用) | ⚠️ 仅序列基序规则 | 大分子方向:抗体/蛋白序列 Embedding + 可开发性/风险属性预测 | 🟠 中高 |
| 7 | 结合 AI 工具与工程实践,独立完成需求理解→方案→实现→验证 | ✅ 已有 | 强化:完整 pipeline + 可复现实验 + 结果可视化 | 贯穿 |
| 8 | 加分:AIDD/CADD、大模型应用(Agent / RAG) | ⚠️ 部分 | 显式补齐 RAG + Agent + 属性预测 | 加分 |

**结论**:现有项目满足"领域知识 + 工程实践"(#1、#7),严重缺口集中在 **LLM/Agent/RAG(#2/#3/#4)** 与 **深度学习/分子建模(#5/#6)**。

---

## 2. 目标架构(演进)

```
antibody_risk
├── core/                  # 既有规则引擎(重构为包,作为"工具")
│   ├── motifs.py          # 风险基序库 + 扫描
│   ├── cdr.py             # CDR 标注
│   └── scoring.py         # Rule-based 打分
├── agent/                 # 新增:LangChain/LlamaIndex 风格的智能体层
│   ├── llm.py             # LLM 后端抽象(OpenAI/DeepSeek/本地 mock,可离线)
│   ├── tools.py           # 工具注册:抗体扫描、突变、打分、RAG 检索
│   ├── agent.py           # ReAct/工具调用智能体
│   ├── memory.py          # 会话/长期记忆
│   └── orchestrator.py    # 多智能体编排(任务分解+协同)
├── rag/                   # 新增:检索增强生成
│   ├── chunking.py        # 文档分块
│   ├── embeddings.py      # Embedding(模型或 hash 兜底,可离线)
│   ├── store.py           # 向量存储(内存/可选 FAISS/Chroma)
│   ├── retrieval.py       # 检索策略(相似度/混合/rerank)
│   └── context.py         # 上下文构建(prompt 组装)
├── ml/                    # 新增:深度学习
│   ├── encoding.py        # 蛋白/序列表示(one-hot, k-mer, AAindex, Embedding)
│   ├── models.py          # 属性预测模型(逻辑回归/GBDT/简单 Transformer)
│   └── train.py           # 训练/评估/微调脚本
├── app.py                 # Gradio 界面(接入 Agent / RAG / ML)
├── cli.py                 # 新增:命令行入口
├── tests/                 # 全绿
└── docs/                  # 文档
```

**关键设计原则**:
1. **可离线运行 / 无强制 API**:LLM 与 Embedding 均可通过"后端抽象 + 本地 hash/规则兜底"在无网络、无 key 时运行,保证演示与 CI 稳定;接入真实 API key 即启用完整能力。这同时满足 README 现有"无外部依赖"哲学到岗位"LLM/RAG"要求的平滑过渡。
2. **复用既有规则引擎为 Tool**:`core` 风险扫描、突变、打分作为 Agent 的可调用工具,体现"把既有工程成果工具化"。
3. **保持测试全绿**,新增功能都带测试;不改坏既有 122 个用例。

---

## 3. 实施阶段

### Phase 0 — 工程底座(不改变行为)  ✅ 已完成
- [x] 新增 `pyproject.toml` / 依赖分组(核心默认可跑;`ml`/`vec`/`agent`/`all`/`dev` 可选)
- [x] 新增 CLI 入口 `cli.py`(`scan`/`ml-train`/`ml-predict`/`rag-query`)
- [x] .gitignore 更新(忽略 ml/artifacts、*.png、*.joblib 等产物)
- [ ] 把 `core/scoring/batch_analysis/input_parser` 重构为包结构(可选优化,暂缓,保持平铺以减少破坏)

### Phase 1 — 深度学习与分子表示(`ml/`)  ✅ 已完成
- [x] 蛋白/抗体序列表示:长度 + AAindex 理化性质 + k-mer 哈希(`ml/features.py`)
- [x] 属性预测:分类(高风险)与回归(风险分数),logistic / random_forest / gbdt / lightgbm(`ml/models.py`)
- [x] 训练 / 分层切分 / 交叉验证 / 指标(AUC、R²、MAE) / 特征重要性 / 模型落盘(`ml/train.py`)
- [x] 可视化:混淆矩阵 / ROC / 特征重要性(`ml/evaluate.py`)
- [x] 合成数据 + 规则弱标签,可离线复现(`ml/data.py`)
- [x] 测试全绿 + `examples/train_ml_demo.py` 一键演示
- [x] (可选,需 torch)`ml/transformer.py`:最小 Transformer 编码器(位置编码+多头自注意力+FFN),对应"Transformer 基础"

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
- [x] (可选,需 langchain)`agent/langchain_adapter.py`:把工具打包为 LangChain StructuredTool 并装配 ReAct/AgentExecutor

### Phase 4 — 集成与展示(大部分完成)
- [x] Gradio 升级:`app.py` 现含 6 个 Tab(扫描/突变/批量 + 🔮 ML 预测 / 📚 RAG 问答 / 🤖 Agent),handler 已联调可用
- [x] CLI 演示入口:`scan` / `ml-*` / `rag-query` / `agent-ask` / `agent-orchestrate`
- [x] README 更新:四层架构、ML/RAG/Agent 章节、岗位技能映射表
- [x] `examples/train_ml_demo.py` 一键演示
- [ ] 端到端 demo 一次性脚本与截图(可选,用于作品集展示)
- [ ] git 初始提交(存底;需更高权限运行 git 命令)

---

## 4. 交付物(面向求职展示)

1. 一个可运行的、分层的 AIDD 项目,从"规则"到"ML"到"RAG"到"Agent"
2. 完善的测试与文档
3. 清晰的 README 岗位技能映射表(证明覆盖 LangChain/LlamaIndex、RAG、Agent、DL、分子设计)
4. CLI + Gradio 双入口,便于现场演示

---

## 5. 使用方式(待补)
> 关键决策待与需求方确认后再填充:
> - 是否有可用的 LLM API(OpenAI/DeepSeek 等)及 key?
> - 分子方向侧重小分子还是大分子/蛋白?(当前项目天然是蛋白/抗体方向)
> - 是否允许引入较重依赖(PyTorch/LightGBM/FAISS/Chroma),还是保持轻量可离线?
