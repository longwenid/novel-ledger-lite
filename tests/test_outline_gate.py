"""章纲机械门：登记制冻结、状态链模拟、协议水位索引化、漂移吸收与形状校验。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

import copy

import pytest

from novel_ledger_lite import book_state, pipeline, story_memory
from novel_ledger_lite.contracts import Error

import fixtures
from fixtures import chapter_rows, contract, open_installed_book, volume_row


def test_install_freezes_outline_rows_and_protocols():
    """章纲资源冻结：安装门通过后 plans/chapter_outlines/volumes_outline 全部落账，
    每行绑定当前场景与阅读协议。"""
    book, outline, report = open_installed_book()
    assert report['chapters'] == [1, 2, 3, 4]
    assert set(book['plans']) == {'1', '2', '3', '4'}
    for chapter, plan in book['plans'].items():
        assert plan['scene_schema'] == story_memory.SCENE_IDENTITY_CAPABILITY
        assert plan['reading_schema'] == story_memory.READING_SCHEMA
    assert book['volumes_outline']['v1']['id'] == 'v1'
    assert book['outline_protocol_checked'] == 4


def test_gate_refuses_broken_state_chain():
    """exit ≠ enter＋增量的章纲整份被拒（状态链模拟），账本不落任何行。"""
    book, _, _ = open_installed_book()
    volume = book['contract']['volumes'][0]
    data = chapter_rows(book)
    data['chapters'][1]['exit'][0]['expected'] = 99          # clock 的 exit 改成假值
    before = dict(book['plans'])
    with pytest.raises(Error):
        pipeline.install_outlines(book, volume['id'], volume_row(volume), data)
    assert book['plans'] == before                            # 拒绝即不冻结


def test_gate_refuses_discontinuous_chapters():
    book, _, _ = open_installed_book()
    volume = book['contract']['volumes'][0]
    data = chapter_rows(book)
    data['chapters'] = [row for row in data['chapters'] if row['chapter'] != 2]
    with pytest.raises(Error):
        pipeline.install_outlines(book, volume['id'], volume_row(volume), data)


def test_bind_watermark_is_incremental():
    """协议复核按章号水位增量进行：水位之下的旧纲行跳过（bind 索引化），水位之上全复核；
    被冻结的新行自身永远过 require_current。"""
    book, _, _ = open_installed_book()
    # 新行自身协议失效 → 无论水位一律拒绝：
    stale = copy.deepcopy(book['plans']['2'])
    stale['scene_schema'] = 'scene-identity/1'
    stale['chapter'] = 99
    with pytest.raises(Error) as caught:
        story_memory.bind(stale, book['plans'], checked_through=4)
    assert caught.value.code == 'story_protocol'
    # 水位之下的旧行协议失效被跳过（增量语义本身）；水位归零则全量复核会抓到它：
    stale_old = copy.deepcopy(book['plans']['1'])
    stale_old['scene_schema'] = 'scene-identity/1'
    fresh = copy.deepcopy(book['plans']['2'])
    fresh['chapter'] = 5
    story_memory.bind(copy.deepcopy(fresh), {'1': stale_old}, checked_through=4)      # 跳过，不抛
    with pytest.raises(Error):
        story_memory.bind(copy.deepcopy(fresh), {'1': stale_old}, checked_through=0)  # 全量，抛


def test_drift_row_participants_must_be_registered():
    """设计漂移行的 participants 须为登记 id（活跃切片 id 交集的前提，安装门拦畸形）。"""
    book, _, _ = open_installed_book()
    book['design_drift'].append({'id': 'drift-1', 'chapter': 0, 'kind': 'resources',
                                 'key': '["shen","车费","元"]', 'reason': '章纲外的花费',
                                 'participants': ['ghost']})
    with pytest.raises(Error) as caught:
        book_state.check_book(book)
    assert caught.value.code == 'book_state'
    assert 'ghost' in caught.value.details['unknown']


def test_absorbs_writes_back_and_rejects_double_absorb():
    """吸收回写：章纲 absorbs 点名的漂移登记为已吸收；重复吸收与未知 id 被拒。"""
    book, _, _ = open_installed_book()
    book['design_drift'].append({'id': 'drift-1', 'chapter': 0, 'kind': 'resources',
                                 'key': '["shen","车费","元"]', 'reason': '章纲外的花费',
                                 'participants': ['shen']})
    volume = book['contract']['volumes'][0]
    data = chapter_rows(book)
    data['chapters'][1]['absorbs'] = ['drift-1']
    report = pipeline.install_outlines(book, volume['id'], volume_row(volume), data)
    assert report['absorbed'] == ['drift-1']
    assert book['design_drift'][0]['absorbed_by'] == [2]
    # 再次安装点名同一条漂移：必须被拒。
    data2 = chapter_rows(book)
    data2['chapters'][1]['absorbs'] = ['drift-1']
    with pytest.raises(Error):
        pipeline.install_outlines(book, volume['id'], volume_row(volume), data2)
