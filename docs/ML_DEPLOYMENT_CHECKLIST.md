# 冻结 ML 的离线部署验收

本流程不训练、不调参、不读取 AIntibody TEST 标签、不计算实验性能。
基础 Desktop 安装通过，不能替代本流程的可选 ML 验收。CPU 与 CUDA、不同
Python/依赖版本分别记录；未测组合不宣称支持。

## 先取得可信产物

安装 `.[desktop,dl]` 只安装代码和依赖，不附带模型、ESM 缓存或训练数据。
普通用户不得为解决缺文件而运行 deployment-model builder：它会重新拟合冻结
定义。应由维护者在独立审核后提供已有可信模型和独立渠道确认的 manifest SHA256。
`joblib`/pickle 可执行代码；文件和 manifest 一起下载后自行算出的摘要不能证明信任。

必须齐备的本地产物：

- `hic_esm2_v1.joblib`、`developability_esm2_v1.joblib`、`model_manifest.json`；
- `facebook/esm2_t30_150M_UR50D` 的冻结 revision
  `a695f6045e2e32885fa60af20c13cb35398ce30c` 缓存，实际文件非空且链接有效；
- `torch`、`transformers`、`huggingface-hub`、`joblib`、`numpy`、`scikit-learn`。

检查程序位于源码/sdist 的 `tools/check_ml_deployment.py`，不是 wheel 的控制台命令。
所有输出均为环境/完整性记录，不是模型有效性指标。

```powershell
python tools/check_ml_deployment.py --artifact-dir ./artifacts/ml_models
```

默认仅检查摘要、冻结定义、依赖版本和缓存完整性，不反序列化或推理。
`PASS` 在默认模式只代表静态前提齐备，不能写成模型推理已经验收。

有独立可信 manifest 摘要后，可显式做零向量估计器 smoke：

```powershell
python tools/check_ml_deployment.py --artifact-dir ./artifacts/ml_models --synthetic-smoke --trusted-manifest-sha256 <approved-sha256>
```

完整缓存的离线 ESM 合成输入 smoke 使用 `--esm-offline-smoke` 替代
`--synthetic-smoke`，并可传 `--hf-home <cache-root>`。它验证重复输出及
1280 维/概率结构，不使用实验序列或标签。程序不下载缺失权重，不写缓存或模型；
任一 sklearn 序列化版本不匹配警告按失败处理，不能靠忽略警告获得认证。

## 安装包中的模型位置

当前运行时默认位置相对于已安装 `ml_inference` 的上一级，而不是任意当前工作目录。
源码运行的 `artifacts/ml_models` 不会自动变成 wheel 安装的模型目录。
维护者可用公开 Python API `FrozenMLPredictor(artifact_dir=...)` 显式指定可信目录；
Desktop 当前在“设置 → 可选 ML 部署检查”中提供目录和独立可信 manifest 摘要输入。
配置不复制或反序列化文件；真正发起推理前重新检查摘要和静态前提。
基础冻结 exe 不包含 torch/transformers，不能向其安装目录运行 pip；目录选择不会
补齐依赖。高级 ML 目前仍需单独验收的源码环境，不承诺公开可分发模型包。
GUI 的 READY 只代表静态前提检查通过，不代表已加载模型或完成预测/有效性验收。
显式推理使用选择的目录，并启用离线缓存模式；冻结运行时与模型定义没有修改。
因此不要把“源码开发环境能运行”写成“普通 wheel 安装已自动配置好 ML”。

## 发布记录

每种已验收环境保存 Python/架构、依赖快照、产物摘要、缓存来源、CPU/CUDA、
实际执行的 smoke 模式和退出码。环境日志/绝对路径留在忽略的本地目录。
对外只公布审阅后的无凭据记录。未执行真实 Provider 请求时，不声明其已验收。
缺模型/依赖/缓存应明确提示，不提供伪预测，不自动重建模型。

### 本轮已观察到的 CPU 组合（2026-11-05）

从现有 Anaconda Python 3.13.9 创建新的 `include-system-site-packages=false`
venv，没有向 Anaconda 安装/升级任何依赖。该 venv 安装了实际 rc2 wheel，
`pip check` 通过；不是新的官方独立 Python 或所有安全补丁的认证。
CPU PyTorch 2.13.0+cpu、transformers 4.57.6、huggingface-hub 0.36.2、
NumPy 2.3.5、scikit-learn 1.7.2、joblib 1.5.2、Gradio 5.50.0。

冻结模型加载与完整 ESM 合成输入检查通过，安装模块来源为 site-packages。
将可信现有模型副本放入该隔离安装的默认目录后，真正的 Desktop ML service
状态为 READY，合成调用/缓存重复通过，网络尝试为 0。没有实验性能计算。
源模型与 ESM 文件没有重建。CUDA、Python 3.14 的 ML 和其他依赖组合未认证。

可复现约束文件：
[基础 Desktop](environments/windows-base314-observed.txt)、
[CPU ML](environments/windows-ml-cpu313-observed.txt)。它们是已观察组合，
不是带供应链哈希的跨平台 lock，不是“永远使用旧补丁”的安全建议；升级后需复验。
通过 `pip install -c <对应约束文件> ".[desktop]"` 或 `".[desktop,dl]"` 使用。
CPU ML 的 torch 先从官方 CPU 源安装：

```powershell
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.13.0+cpu
python -m pip install -c docs/environments/windows-ml-cpu313-observed.txt ".[desktop,dl]"
```

ESM 加载保留了 `torch_dtype` 弃用提示和未使用 pooler 初始化提示。
运行时使用的是 `last_hidden_state` 的残基均值而非 pooler 输出；本轮没有依照
第三方日志的训练建议去训练，也没有为消除日志改变冻结表征或模型。
