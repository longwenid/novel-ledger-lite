"""将当前技能副本的 scripts 目录加入测试导入路径，支持从任意目录运行。"""
import os
import sys

LITE_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts')
if LITE_SCRIPTS not in sys.path:
    sys.path.insert(0, LITE_SCRIPTS)
