"""pytest 全局配置：确保项目根目录可导入"""
import sys
from pathlib import Path

# 项目根目录加入 sys.path，使测试可直接 import 根目录模块
sys.path.insert(0, str(Path(__file__).parent.parent))
