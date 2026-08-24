# 接入真实 LLM(DeepSeek / OpenAI)+ LangChain 端到端

本项目默认用离线 `MockLLM` 演示 Agent 循环;接入真实 LLM 只需一个 API key,即可启用
**真实函数调用(Tool Calling)+ 真实回答**,并跑通 **LangChain 端到端**。

## 1. 获取 API key

- **DeepSeek(推荐,便宜)**:https://platform.deepseek.com → 注册 → API Keys → 创建,充值几元即可。
- **OpenAI(可选)**:https://platform.openai.com → API keys。

## 2. 写入 .env(不提交)

仓库根目录执行:

```bash
copy .env.example .env
```

编辑 `.env`,填入真实 key:

```
DEEPSEEK_API_KEY=sk-你实际的key
```

> `.env` 已被 `.gitignore` 排除,不会上传;`config.py` 会自动加载它。

## 3. 验证接入

```bash
python cli.py agent-ask --q "什么是脱酰胺化？" --backend deepseek
python cli.py agent-orchestrate --q "评估这条序列的风险：<序列>" --backend deepseek
```

或者用端到端演示脚本(含 LangChain):

```bash
python examples/run_real_llm_demo.py
```

该脚本会依次:
1. 用真实 DeepSeek 跑 `Agent`(函数调用)回答一个知识问题;
2. 用真实 DeepSeek 跑 `Orchestrator` 多智能体;
3. 构建 **LangChain agent**(langgraph ReAct)并调用 `rag_search` 等工具,端到端回答。

## 4. 代码接入点

| 位置 | 作用 |
| --- | --- |
| `config.py` | 读取 `.env` / 环境变量(`get_env` / `require_env`) |
| `agent/llm.py` | `get_llm("deepseek")` / `get_llm("openai")` → 真实函数调用后端 |
| `agent/langchain_adapter.py` | `build_langchain_agent(backend="deepseek")` → LangChain/LangGraph agent |
| `cli.py` | `agent-ask` / `agent-orchestrate` 的 `--backend` 参数 |

## 5. 常见问题

- **`缺少 DEEPSEEK_API_KEY`**:`.env` 没建或没填;`copy .env.example .env` 后填入。
- **`Connection error / 401`**:key 无效或余额不足;去 DeepSeek 平台检查。
- **想换模型**:DeepSeek 可用 `deepseek-chat`、`deepseek-reasoner`(在 `agent/llm.py` 的 `DeepSeekLLM` 改 model 参数)。
