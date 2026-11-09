"""将当前技能副本的 scripts 目录加入测试导入路径，支持从任意目录运行。"""
import os
import pathlib
import shutil
import sys
import tempfile
import uuid

import pytest

LITE_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts')
if LITE_SCRIPTS not in sys.path:
    sys.path.insert(0, LITE_SCRIPTS)


@pytest.fixture
def tmp_path():
    """默认的临时目录：pytest 自带夹具以 0700 建目录，在受限令牌的运行环境里
    该目录随后无法列举或删除；这里用默认权限建同名语义的独立目录并自行清理。"""
    path = tempfile.gettempdir()
    directory = os.path.join(path, 'novel-ledger-lite-test-' + uuid.uuid4().hex)
    os.makedirs(directory)
    try:
        yield pathlib.Path(directory)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
