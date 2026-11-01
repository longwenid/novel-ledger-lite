"""lite 测试引导：把 lite 的 scripts 目录插到 sys.path 最前。

保证在完整版 novel-ledger 目录里跑 `python -m pytest <lite>/tests -q` 也能过：
lite 包名是 novel_ledger_lite（独立命名空间），不会与完整版 novel_ledger 冲突；
插入位置在 sys.path[0]，lite 自己的 contracts/world/envelope（裁剪版）优先于
完整版同名模块被解析——两个包各自完整，不存在半混用。
"""
import os
import sys

LITE_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts')
if LITE_SCRIPTS not in sys.path:
    sys.path.insert(0, LITE_SCRIPTS)
