# tests/conftest.py
# 确保 pytest 能导入项目根目录下的 core / batch_analysis 模块
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
