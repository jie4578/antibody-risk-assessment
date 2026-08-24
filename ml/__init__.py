# ml/__init__.py
# 机器学习 / 蛋白表示模块：把抗体可变区序列编码为特征，并训练属性预测模型。
#
# 目标：
#   - 蛋白/抗体序列表示：one-hot、k-mer、AAindex 理化特征
#   - 属性预测：风险等级（分类）与风险分数（回归）
#   - 训练 / 交叉验证 / 指标(AUC, R2) / 特征重要性
#
# 标签来源：现有 core + scoring 的确定性规则引擎（所谓 "weak label"），
#   使整个流程可离线、可复现；说明详见 README / docs。
#
# 轻量原则：核心只用 numpy / scikit-learn / lightgbm（可选），不依赖 torch。
#   这样默认环境即可运行，重型依赖（torch / faiss / chroma / langchain）按需安装。

from .features import SequenceEncoder
from .data import build_dataset, BaseSequencePool
from .models import build_model_registry
from .train import train_pipeline

__all__ = [
    "SequenceEncoder",
    "build_dataset",
    "BaseSequencePool",
    "build_model_registry",
    "train_pipeline",
]

# 便捷版本号
__version__ = "0.1.0"
