"""长篇上下文的大小边界和资源真源：历史不全带，但点名可精确取回。"""
import copy
import json

from novel_ledger_lite import compose, facts, pipeline
from novel_ledger_lite.contracts import digest, policy_default
from novel_ledger_lite.store import LiteStore

import fixtures


def complete_plan():
    return {'chapter': 4000, 'dependency_coverage': 'complete', 'participants': ['shen'],
            'scenes': [{'id': 's', 'reads': [], 'depends_on': []}]}


def test_history_growth_does_not_expand_worker_material_linearly():
    sizes = []
    for count in (100, 1000, 3000):
        state = facts.seed(fixtures.contract())
        state['historical_assertions'].update({'history-%04d' % n:
            {'subjects': ['shen'], 'claim': '完整的历史事实。' * 100} for n in range(count)})
        before = digest(state)
        view, warnings = compose.scoped_state(state, {}, ['shen'], complete_plan(), 4000)
        assert not warnings
        assert not view['historical_assertions']
        assert view['material_scope']['far_omitted']['historical_assertions'] == count
        sizes.append(len(json.dumps(view, ensure_ascii=False).encode()))
        assert digest(state) == before
    assert max(sizes) - min(sizes) < 100


def test_named_pinned_and_recent_values_survive_history_cap_and_are_retrievable():
    book = pipeline.open_book(fixtures.contract(), '测试')
    state = book['state']
    state['historical_assertions'].update({'history-%04d' % n: {'value': n, 'subjects': ['shen']}
                                           for n in range(3000)})
    state['facts']['shen:recent'] = '近期状态'
    index = {'facts\x00shen:recent': 3999}
    plan = complete_plan()
    plan['scenes'][0]['reads'] = [{'kind': 'historical_assertions', 'key': 'history-2998'}]
    view, _ = compose.scoped_state(state, index, ['shen'], plan, 4000,
                                    pinned=[{'kind': 'historical_assertions', 'key': 'history-2999'}])
    assert view['historical_assertions']['history-2998']['value'] == 2998
    assert view['historical_assertions']['history-2999']['value'] == 2999
    assert view['facts']['shen:recent'] == '近期状态'
    assert 'history-2997' not in view['historical_assertions']
    restored = pipeline.resource(book, 'historical_assertions', 'history-2997')
    assert restored['found'] and restored['value']['value'] == 2997
    restored['value']['value'] = -1
    assert state['historical_assertions']['history-2997']['value'] == 2997
    assert not pipeline.resource(book, 'facts', 'shen:missing')['found']


def test_far_limit_is_shared_by_all_history_fields():
    state = facts.seed(fixtures.contract())
    state['facts'].update({'shen:f%d' % n: '事实' for n in range(50)})
    state['knowledge'].update({'shen:k%d' % n: {'claim': '认知'} for n in range(50)})
    state['historical_assertions'].update({'h%d' % n: {'subjects': ['shen'], 'claim': '历史'}
                                          for n in range(50)})
    view, _ = compose.scoped_state(state, {}, ['shen'], complete_plan(), 4000)
    refs = sum(isinstance(value, dict) and value.get('_ref') is True
               for field in compose.HISTORY_FIELDS for value in view[field].values())
    assert refs == 0
    assert len(view['facts']) == 50
    assert sum(view['material_scope']['far_omitted'].values()) == 100


def test_incomplete_dependencies_keep_conservative_material():
    state = facts.seed(fixtures.contract())
    state['facts'].update({'shen:f%d' % n: '历史事实' for n in range(3000)})
    view, warnings = compose.scoped_state(state, {}, ['shen'], {'scenes': []}, 4000)
    assert len(view['facts']) == 3000
    assert warnings and view['material_scope']['mode'] == 'conservative'


def test_partial_projection_preserves_explicit_background_and_pinned_values():
    state = facts.seed(fixtures.contract())
    state['facts'].update({'other:rule': '作者指定的常驻规则', 'other:clue': '本章明确需要的线索'})
    plan = {'scenes': [{'reads': [{'kind': 'facts', 'key': 'other:clue'}], 'depends_on': []}]}
    view, warnings = compose.scoped_state(state, {}, ['shen'], plan, 4000,
                                        pinned=[{'kind': 'facts', 'key': 'other:rule'}])
    assert warnings
    assert view['facts']['other:rule'] == '作者指定的常驻规则'
    assert view['facts']['other:clue'] == '本章明确需要的线索'


def test_frozen_world_and_shared_group_do_not_follow_input_mutations():
    world = fixtures.world_fixture()
    book = pipeline.open_book(fixtures.contract(), '测试', world)
    world['rules'][0]['principle'] = '意外改动'
    assert book['world']['rules'][0]['principle'] != '意外改动'
    volume = book['contract']['volumes'][0]
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(volume), fixtures.chapter_rows(book))
    store = LiteStore()
    group = pipeline.group(book, store, 'v1')
    frozen = store.read_document(group['hash'])
    assert digest(frozen) == group['hash']
    before = copy.deepcopy(group['pack'])
    book['contract']['voice'] = '后来变动的声线'
    book['volumes_outline']['v1']['purpose'] = '后来变动的卷纲'
    assert group['pack'] == before
    assert store.read_document(group['hash']) == frozen


def test_external_style_is_frozen_until_explicit_recontract_even_mid_group(tmp_path):
    path = tmp_path / '文风档案.md'
    path.write_text('作者确认的第一版文风。', encoding='utf-8')
    raw = fixtures.contract()
    raw['style_source'] = str(path)
    book = pipeline.open_book(raw, '测试', fixtures.world_fixture())
    volume = book['contract']['volumes'][0]
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(volume), fixtures.chapter_rows(book))
    store = LiteStore()
    group = pipeline.group(book, store, 'v1')
    assert pipeline.submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    path.write_text('作者确认的第二版文风。', encoding='utf-8')
    # 文件被外部改写不能改变本书冻结材料。
    solo = pipeline.envelope(book, store, 2)
    assert store.read_document(solo['records']['style_archive'])['content'] == '作者确认的第一版文风。'
    pipeline.recontract_patch(book, source='作者：换用第二版', style_source=str(path))
    refreshed = pipeline.envelope(book, store, 2, group)
    assert 'style_archive' in refreshed['required']
    assert store.read_document(refreshed['records']['style_archive'])['content'] == '作者确认的第二版文风。'
    saved = tmp_path / 'saved.json'
    pipeline.save(book, store, saved)
    path.unlink()
    loaded, saved_store = pipeline.load(saved)
    after_reload = pipeline.envelope(loaded, saved_store, 2)
    assert saved_store.read_document(after_reload['records']['style_archive'])['content'] == '作者确认的第二版文风。'



def test_synthetic_chapter_tags_do_not_trigger_duplicate_gate_above_1000():
    from benchmark_long_run import draft
    from novel_ledger_lite import lint

    book, _, _ = fixtures.open_installed_book()
    for n in (1000, 1002):
        book['plans'][str(n)] = copy.deepcopy(book['plans']['2'])
    first, second = draft(book, 1000, 3500), draft(book, 1002, 3500)
    assert lint.cross_chapter_duplicates(second['prose'], [(1000, first['prose'])], 1002) == []
