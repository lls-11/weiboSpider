# 让 tests/ 能直接 import talent_corpus（本文件夹不是 Python 包）
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
