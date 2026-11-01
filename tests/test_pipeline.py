"""最小完整闭环冒烟：开书→章纲机械门冻结→冻结组→逐章差量信封→提交→账本推进
→卷界差异单→完本全量重放验收→落盘重载。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

import pytest

from novel_ledger_lite import pipeline
from novel_ledger_lite.contracts import digest
from novel_ledger_lite.store import LiteStore

import fixtures
from fixtures import chapter_rows, contract, draft_for, open_installed_book, volume_row, world_fixture


def test_full_loop_smoke():
    """「章纲资源冻结→快速执笔」全链路：四章一本书，逐章信封现编现冻、提交门全绿、
    卷界 checkpoint＋差异单、完本验收通过。"""
    book, outline, report = open_installed_book()
    assert report['chapters'] == [1, 2, 3, 4]
    store = LiteStore()
    group_row = pipeline.group(book, store, 'v1', size=5)
    results = []
    for n in range(1, 5):
        envelope = pipeline.envelope(book, store, n, group_row)
        assert envelope['required']
        assert envelope['stage'] == 'write'
        outcome = pipeline.submit(book, store, n, draft_for(book, n))
        assert outcome['ok'], [f for f in outcome.get('findings', [])]
        results.append(outcome)
    assert book['written_han'] > 0 and book['status'] == 'running'
    boundary = results[-1]['volume_boundary']
    assert boundary['volume'] == 'v1'
    assert boundary['open_continues'] == []                   # 单卷无跨卷承诺
    final = pipeline.verify_full(book, store)
    assert final['ok'] and final['matches_book']
    assert pipeline.status(book, store)['written'] == 4


def test_group_freezing_refuses_overflow_and_reuses_active():
    """组冻结：同卷再次调用接续下一段；全卷覆盖后再调被拒（不追加重复组）；
    已冻结组经 group_for 复用。"""
    book, _, _ = open_installed_book()
    store = LiteStore()
    first = pipeline.group(book, store, 'v1', size=3)
    assert first['members'] == [1, 3]
    second = pipeline.group(book, store, 'v1', size=3)
    assert second['members'] == [4, 4]
    assert first['hash'] != second['hash']
    # 验收员场景：4 章卷 size=2 连调三次——第三次必须拒绝，组表不增长。
    book2, _, _ = open_installed_book()
    store2 = LiteStore()
    assert pipeline.group(book2, store2, 'v1', size=2)['members'] == [1, 2]
    assert pipeline.group(book2, store2, 'v1', size=2)['members'] == [3, 4]
    with pytest.raises(Exception) as caught:
        pipeline.group(book2, store2, 'v1', size=2)
    assert getattr(caught.value, 'code', None) == 'writing_batch'
    assert [g['members'] for g in book2['groups']] == [[1, 2], [3, 4]]
    # 复用：取章所在的已冻结组。
    assert pipeline.group_for(book2, 3)['members'] == [3, 4]
    assert pipeline.group_for(book2, 99) is None


def test_loop_rejects_writing_without_frozen_outline():
    """未冻结章纲不可执笔：机械门的「资源冻结」是执笔的前置事实。"""
    book = pipeline.open_book(contract(), '夹具导入', world_fixture())
    store = LiteStore()
    with pytest.raises(Exception):
        pipeline.envelope(book, store, 1)
    with pytest.raises(Exception):
        pipeline.submit(book, store, 1, {'title': 't', 'summary': 's', 'self_check': 'c',
                                         'prose': '正文', 'drift_check': {'items': [], 'unplanned': [],
                                                                          'verdict': 'clean'}})


def test_volume_diff_lists_required_sealed_channel():
    """required/sealed 通道（方案三补丁 a）：封线承诺未兑现时，卷界差异单显式点名。"""
    book, _, _ = open_installed_book()
    store = LiteStore()
    assert pipeline.submit(book, store, 1, draft_for(book, 1))['ok']
    assert pipeline.submit(book, store, 2, draft_for(book, 2))['ok']
    assert pipeline.submit(book, store, 3, draft_for(book, 3))['ok']
    # 第 4 章本应 payoff；用第 3 章的稿子顶替第 4 章会被章纲对账拒绝——
    # 这里直接伪造「卷末承诺仍 open」的状态来看差异单的点名行为。
    pipeline._checkpoint(book, 4, 'v1')
    boundary = pipeline._volume_boundary(book, book['contract']['volumes'][0])
    assert fixtures.HOOK_ID in boundary['required_unpaid']
    assert boundary['drift'] is not None
