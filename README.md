# 抗体序列化学稳定性风险评估工具

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Gradio](https://img.shields.io/badge/Gradio-3.x-orange)](https://gradio.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个基于 Python 的抗体可变区序列分析工具，用于快速扫描脱酰胺、异构化、氧化等翻译后修饰（PTM）风险基序，并自动标注其在 CDR 或骨架区（FW）中的位置。适用于抗体药物发现早期的可开发性评估。

👉 **在线体验**：[Gradio Demo 链接]（临时链接，72小时有效，也可本地运行）

![工具截图](screenshot.png)

## ✨ 功能特性

- **PTM 风险基序扫描**：内置脱酰胺化（NG, NS, NN）、异构化（DG, DS, DA）、甲硫氨酸氧化（M）以及 N-糖基化（N-x-S/T）检测规则
- **手动 CDR 注释**：基于 Kabat 编号规则，支持自定义 CDR1、CDR2、CDR3 边界，灵活适配不同抗体
- **虚拟突变模拟**：输入点突变（如 `N55Q`），即时验证突变对风险的消除效果
- **风险区域定位**：明确报告每个风险位点位于 CDR 或骨架区，按风险等级排序
- **可视化界面**：使用 Gradio 构建交互式 Web 界面，支持一键导出报告
- **模块化设计**：核心分析逻辑与界面分离，可轻松集成到其他流程或命令行工具中

## 🧬 应用场景

- 杂交瘤 / 噬菌体展示筛选后，对候选抗体序列进行快速成药性初筛
- 人源化改造后，检测是否引入新的化学降解风险
- 理性设计突变，去除高风险基序，指导湿实验
- 生物信息学入门项目，展示“领域知识 + Python 实战”能力

## 🚀 快速开始

### 环境要求
- Python 3.8 或以上
- 推荐使用 Anaconda 管理环境

### 安装依赖
```bash
pip install gradio