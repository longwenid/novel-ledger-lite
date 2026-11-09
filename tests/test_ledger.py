"""账本状态推进：settle 前值硬核、引文逐字、到期拦截、delta 产出、索引与倒排、
checkpoint、损坏重建、完本全量重放验收、recall 与分页。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

import copy

import pytest

from novel_ledger_lite import delta as delta_ledger, facts, pipeline
from novel_ledger_lite.contracts import Error, digest, han_count
from novel_ledger_lite.store import LiteStore

import fixtures
from fixtures import contract, draft_for, open_installed_book, prose_for, world_fixture


def _store():
    return LiteStore()


def test_submit_advances_ledger_and_produces_delta():
    book, _, _ = open_installed_book()
    store = _store()
    before = copy.deepcopy(book['state'])
    result = fixtures.submit_reviewed(book, store, 1, draft_for(book, 1))
    assert result['ok'], result
    row = result['row']
    assert row['han'] == han_count(draft_for(book, 1)['prose'])
    assert store.chapter('main', 1)['state_hash'] == digest(book['state'])
    # delta 是派生数据：真源 events 已入链，delta 只记 touched 坐标。
    delta = result['delta']
    assert delta['chapter'] == 1
    assert set(delta['touched']) >= {'clock', 'resources', 'placements', 'knowledge', 'hooks'}
    assert delta['after_hash'] == digest(book['state']) and delta['before_hash'] == digest(before)
    # 投影索引推进：坐标→末次变更章（clock 是标量字段，走 delta.touched 但不进条目索引）。
    assert delta_ledger.last_chapter(book['delta_index'], 'knowledge', 'shen:source') == 1
    assert delta_ledger.last_chapter(book['delta_index'], 'hooks', fixtures.HOOK_ID) == 1
    # 倒排登记：hook id → 章。
    assert fixtures.HOOK_ID in book['inverted']


def test_rejects_evidence_not_verbatim():
    """引文逐字核验（唯一子串定位）：伪造证据句整份拒绝，账本不变。"""
    book, _, _ = open_installed_book()
    store = _store()
    draft = draft_for(book, 1)
    draft['drift_check']['items'][0]['evidence']['quote'] = '这句不在正文里'
    before_state = copy.deepcopy(book['state'])
    result = fixtures.submit_reviewed(book, store, 1, draft)
    assert not result['ok']
    assert book['state'] == before_state and store.last_chapter() == 0


def test_rejects_before_value_contradicting_projection():
    """自报前态与引擎投影不符 → blocker（前态由引擎给出，不由执笔申报）。"""
    book, _, _ = open_installed_book()
    store = _store()
    draft = draft_for(book, 1)
    for item in draft['drift_check']['items']:
        if item['kind'] == 'resources':
            item['actual'] = {'from': '999', 'to': item['planned']['to']}
    result = fixtures.submit_reviewed(book, store, 1, draft)
    assert not result['ok']
    assert any(f['criterion'] == 'drift_before' for f in result['findings'])


def test_rejects_duplicate_prose_across_window():
    """8 章重复窗：与前章逐字重复的句子被机械拦截。"""
    book, _, _ = open_installed_book()
    store = _store()
    assert fixtures.submit_reviewed(book, store, 1, draft_for(book, 1))['ok']
    draft = draft_for(book, 2)
    first = draft_for(book, 1)['prose']
    draft['prose'] = draft['prose'] + '。' + first[:30]      # 搬运前章 30 字
    result = fixtures.submit_reviewed(book, store, 2, draft)
    assert not result['ok']
    assert any(f['criterion'] in ('repetition', 'language') for f in result['findings'])


def test_settle_requires_exact_before_for_facts():
    """settle 前值硬核（底盘清单）：before ≠ 投影即拒。"""
    state = facts.seed(contract())
    event = {'op': 'state', 'entity': 'shen', 'key': 'mood', 'before': 'x', 'after': 'y',
             'evidence': {'chapter': 1, 'quote': 'q'}}
    with pytest.raises(Error):
        facts.apply_event(state, event, 1)


def test_hook_deadline_intercepted():
    """到期承诺拦截：due ≤ 本章仍未兑现 → 拒绝结算。"""
    book, _, _ = open_installed_book()
    store = _store()
    fixtures.submit_reviewed(book, store, 1, draft_for(book, 1))
    book['state']['hooks'][fixtures.HOOK_ID]['due'] = 2       # 人工把期限拉到第 2 章
    result = fixtures.submit_reviewed(book, store, 2, draft_for(book, 2))
    assert not result['ok']
    assert any(f['criterion'] == 'hook_due' for f in result['findings'])


def test_checkpoint_volume_boundary_and_diff_sheet():
    """卷界：全量 checkpoint＋差异单（required 未兑/漂移吸收率/文风锚回比登记）。"""
    book, _, _ = open_installed_book()
    store = _store()
    book['design_drift'].append({'id': 'drift-x', 'chapter': 1, 'kind': 'resources',
                                 'key': '["shen","车费","元"]', 'reason': '章纲外的花费',
                                 'participants': ['shen']})
    results = fixtures.submit_chapters(book, store)
    assert all(r['ok'] for r in results)
    boundary = results[-1]['volume_boundary']
    assert boundary is not None
    assert boundary['required_unpaid'] == []                  # 卷末承诺已兑现
    assert boundary['drift']['rate'] is not None
    assert len(book['checkpoints']) == 1
    checkpoint = book['checkpoints'][0]
    assert checkpoint['through'] == 4 and checkpoint['state_hash'] == digest(book['state'])
    assert book['style_volume_anchor'] is not None            # 文风卷首锚已冻结


def test_recall_uses_inverted_index():
    """recall 倒排定位：先查索引再取页；无匹配 O(1) 空返回。"""
    book, _, _ = open_installed_book()
    store = _store()
    fixtures.submit_chapters(book, store)
    hit = pipeline.recall(book, store, fixtures.HOOK_ID)
    assert hit['chapters'] and {1, 4} <= set(hit['chapters'])
    assert hit['hits']
    miss = pipeline.recall(book, store, 'no-such-asset')
    assert miss == {'chapters': [], 'hits': []}


def test_rebuild_from_checkpoint_recovers_state():
    """delta 损坏恢复：清空 delta/索引后从 checkpoint＋events 重放，投影零丢失。"""
    book, _, _ = open_installed_book()
    store = _store()
    fixtures.submit_chapters(book, store)
    truth = digest(book['state'])
    book['deltas'] = {}
    book['delta_index'] = {}
    rebuilt, last = delta_ledger.rebuild(book, store)
    assert digest(rebuilt) == truth
    assert last == 4


def test_verify_full_replay_is_default_acceptance():
    """完本验收＝全量重放：逐章重放核对投影哈希与链哈希；不依赖 delta。"""
    book, _, _ = open_installed_book()
    store = _store()
    fixtures.submit_chapters(book, store)
    report = pipeline.verify_full(book, store)
    assert report['ok'] and report['chapters'] == 4
    assert report['matches_book'] and report['unpaid_hooks'] == []
    # 篡改一章的投影哈希 → 验收必翻。
    store._chapters[2]['state_hash'] = '0' * 64
    tampered = pipeline.verify_full(book, store)
    assert not tampered['ok']
    assert any(p['kind'] == 'state_hash' for p in tampered['problems'])


def test_status_pagination():
    """status 分页：页大小受控。"""
    book, _, _ = open_installed_book()
    store = _store()
    fixtures.submit_chapters(book, store)
    page0 = pipeline.status(book, store, page=0, per=2)
    page1 = pipeline.status(book, store, page=1, per=2)
    assert page0['written'] == 4 and page0['pages'] == 2
    assert [row['n'] for row in page0['chapters']] == [1, 2]
    assert [row['n'] for row in page1['chapters']] == [3, 4]


def test_save_load_roundtrip():
    book, _, _ = open_installed_book()
    store = _store()
    fixtures.submit_chapters(book, store)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_roundtrip.json')
    pipeline.save(book, store, path)
    book2, store2 = pipeline.load(path)
    assert digest(book2['state']) == digest(book['state'])
    assert store2.chain_head() == store.chain_head()
    os.remove(path)
