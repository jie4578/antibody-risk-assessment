# examples/train_ml_demo.py
# 一键演示 ML 属性预测：构建数据集 → 训练分类+回归 → 打印报告 → 生成可视化图。
#
# 运行：
#   python examples/train_ml_demo.py
#
# 产物写入 ml/artifacts/：模型 cls.joblib / reg.joblib、roc.png、cm.png、feature_importance.png

import os
import sys

# 把仓库根目录加到 sys.path，使脚本可从任何位置直接运行（避免 'No module named ml'）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml", "artifacts")


def main() -> None:
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    from ml.data import build_dataset
    from ml.evaluate import confusion_matrix_plot, feature_importance_plot, roc_curve_plot
    from ml.features import SequenceEncoder
    from ml.train import load_bundle, train_pipeline

    print("== 1/4 构造数据集（规则弱标签）==")
    df = build_dataset(n=800, seed=42)
    print(df["risk_level"].value_counts().to_string())

    print("\n== 2/4 训练分类模型（high_risk）==")
    cls = train_pipeline(
        df, task="classification", model_name="logistic",
        save_path=os.path.join(ARTIFACT_DIR, "cls.joblib"),
    )
    print(cls.report)

    print("\n== 3/4 训练回归模型（risk_score）==")
    reg = train_pipeline(
        df, task="regression", model_name="ridge",
        save_path=os.path.join(ARTIFACT_DIR, "reg.joblib"),
    )
    print(reg.report)

    print("\n== 4/4 生成可视化 ==")
    encoder = SequenceEncoder()
    X = encoder.transform(df["sequence"].tolist())
    y = df["high_risk"].astype(int).to_numpy()
    model = cls.model
    y_pred = model.predict(X)
    proba = model.predict_proba(X)[:, 1]
    cm_path = confusion_matrix_plot(y, y_pred, ["Low", "High"], os.path.join(ARTIFACT_DIR, "cm.png"))
    roc_path = roc_curve_plot(y, proba, os.path.join(ARTIFACT_DIR, "roc.png"))
    fi_path = feature_importance_plot(cls.feature_importance, top_n=15, save_path=os.path.join(ARTIFACT_DIR, "feature_importance.png"))
    print(f"已生成:\n  {cm_path}\n  {roc_path}\n  {fi_path}")

    # 示例：对新序列预测
    print("\n== 示例预测 ==")
    model_cls, enc_cls = load_bundle(os.path.join(ARTIFACT_DIR, "cls.joblib"))
    demo_seq = df["sequence"].iloc[0]
    prob = model_cls.predict_proba(enc_cls.transform([demo_seq]))[:, 1][0]
    print(f"序列(前40): {demo_seq[:40]}...")
    print(f"高风险概率: {prob:.4f}")


if __name__ == "__main__":
    main()
