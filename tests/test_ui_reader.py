"""Exercise the shipped browser reader with actual Python exports and a limited host."""
from __future__ import annotations

import copy
import random
import shutil
import subprocess
from pathlib import Path

import pytest

import export_view
import fixtures
from novel_ledger_lite import pipeline
from novel_ledger_lite.store import LiteStore

ROOT = Path(__file__).resolve().parents[1]


def _large_view(work):
    raw = fixtures.contract(3000)
    raw['chapter_outline'] = {'scope': 'volume', 'words': 160, 'tolerance': 80}
    book = pipeline.open_book(raw, '导出传输回归', fixtures.world_fixture())
    volume = book['contract']['volumes'][0]
    outline = fixtures.volume_row(volume)
    outline['clock'] = {'advance_days': 3000, 'to': 3000}
    rows = fixtures.chapter_rows(book, outline, with_scenes=True)
    for row in rows['chapters']:
        row['synopsis'] = '章纲' * 80
        row['plot']['beat'] = '推进' * 80
        scene = row['scenes'][0]
        row['scenes'] = [dict(copy.deepcopy(scene), label='夜班工人在仓库核对凭据' + str(i))
                         for i in range(3)]
    rows['chapters'][0]['synopsis'] = '章纲' * 100
    rows['chapters'][0]['plot']['beat'] = '推进' * 200
    pipeline.install_outlines(book, volume['id'], outline, rows)
    bundle = work / 'large.json'
    pipeline.save(book, LiteStore(), bundle)
    export_view.build_view(str(bundle), str(work / 'large' / '.novel-ledger'))


def _long_prose(work):
    contract = fixtures.contract()
    contract['chapter_max'] = 10000
    book = pipeline.open_book(contract, '合成正文传输回归', fixtures.world_fixture())
    store = LiteStore()
    volume = book['contract']['volumes'][0]
    pipeline.install_outlines(book, volume['id'], fixtures.volume_row(volume),
                              fixtures.chapter_rows(book, with_scenes=True))
    pipeline.group(book, store, volume['id'])
    draft = fixtures.draft_for(book, 1)
    rng = random.Random(1)
    draft['prose'] += '\n\n' + '\n'.join(chr(rng.randrange(0x4e00, 0x9fa5)) for _ in range(6000))
    assert fixtures.submit_reviewed(book, store, 1, draft)['ok']
    bundle = work / 'long.json'
    pipeline.save(book, store, bundle)
    export_view.build_view(str(bundle), str(work / 'long' / '.novel-ledger'))


def test_browser_reader_roundtrips_exports_and_rejects_incomplete_transport(tmp_path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Browser transport checks require Node.js.')
    _large_view(tmp_path)
    _long_prose(tmp_path)
    result = subprocess.run(
        [node, str(ROOT / 'tests' / 'ui_reader.test.cjs'), str(tmp_path)],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
