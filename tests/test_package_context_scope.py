"""Standalone packets keep current constraints whole without resurrecting unneeded history."""
import json
import re

import pytest

import fixtures
from novel_ledger_lite import compose, drift, package_context, pipeline
from novel_ledger_lite.contracts import Error, digest
from novel_ledger_lite.store import LiteStore


def section(packet, name):
    marker = re.search(r'^## [^\n]*（' + re.escape(name) + r'）\n\n(`{3,})json\n',
                       packet['text'], re.MULTILINE)
    assert marker, name
    return json.loads(packet['text'][marker.end():].split('\n' + marker.group(1), 1)[0])


def prepared(*, count=150, complete=True, named=False):
    raw = fixtures.contract()
    raw['narrative_tracking'] = True
    raw['near_window_chapters'] = 1
    raw['initial_facts'] = [{'entity': 'shen', 'key': 'injury', 'value': '左手旧伤不能负重。'}]
    raw['initial_resources'].append({'holder': 'shen', 'asset': '随身旧钥匙', 'unit': '把', 'quantity': '1'})
    raw['entities'].append({'id': 'li', 'name': '李青', 'kind': 'person'})
    book = pipeline.open_book(raw, '作者确认上下文回归输入', fixtures.world_fixture())
    for n in range(count):
        book['state']['knowledge'][f'shen:old-{n:04d}'] = {
            'claim': '旧批次核实细节。' * 40 + f'不可猜测的完整尾句{n:04d}', 'status': 'confirmed'}
        book['state']['reader_knowledge'][f'reader-{n:04d}'] = {
            'claim': '读者掌握的旧线索。' * 40 + f'读者完整尾句{n:04d}', 'status': 'hinted'}
    book['state']['relations']['shen>li:trust'] = '信任已经破裂。'
    book['state']['character_current']['shen'] = {'desire': '寻找旧签字人。', 'stance': '克制。'}
    book['state']['developments']['shen'] = [{'change': '旧成长经历。' * 100,
                                             'evidence': {'chapter': 0}}]
    book['state']['historical_assertions']['old-signature'] = {
        'subjects': ['shen'], 'claim': '旧签字仅能证明其当时到场，不能恢复如今的资产。' * 40}
    book['state']['hooks']['old-unpaid'] = {
        'subjects': ['shen'], 'status': 'open', 'text': '仍须归还旧钥匙。', 'due': 99}
    book['state']['hooks']['old-paid'] = {
        'subjects': ['shen'], 'status': 'resolved', 'text': '已兑现的旧承诺。'}
    chapters = fixtures.chapter_rows(book, with_scenes=True)
    target = chapters['chapters'][2]
    if not complete:
        target['dependency_coverage'] = 'partial'
    if named:
        target['scenes'][0]['reads'].append({'kind': 'knowledge', 'key': 'shen:old-0000'})
        target['reader_refs'] = ['reader-0000']
        target['history_refs'] = ['old-signature']
        book['contract']['pinned'] = [{'kind': 'knowledge', 'key': 'shen:old-0001'}]
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(book['contract']['volumes'][0]), chapters)
    store = LiteStore()
    for n in (1, 2):
        draft = fixtures.attach_synthetic_review(book, store, n, fixtures.draft_for(book, n))
        assert pipeline.submit(book, store, n, draft)['ok']
    return book, store


def test_standalone_history_growth_keeps_a_bounded_locator_and_full_current_constraints():
    sizes = []
    for count in (100, 1000):
        book, store = prepared(count=count)
        before = digest(book)
        packet = pipeline.chapter_package(book, store, 3)
        state = section(packet, 'state')
        assert state['facts']['shen:injury'] == '左手旧伤不能负重。'
        assert state['resources']['["shen","随身旧钥匙","把"]'] == '1'
        assert state['relations']['shen>li:trust'] == '信任已经破裂。'
        assert state['character_current']['shen']['desire'] == '寻找旧签字人。'
        assert 'old-unpaid' in state['hooks']
        assert not any(key.startswith('shen:old-') for key in state['knowledge'])
        assert not state['reader_knowledge']
        assert not state['developments']
        deferred = section(packet, 'deferred_history')
        assert deferred['by_kind']['knowledge'] == count
        assert deferred['by_kind']['reader_knowledge'] == count
        assert deferred['by_kind']['developments'] == 1
        assert deferred['shown'] == 20 and deferred['has_more']
        # deferred 定位行与 recall_manifest 同口径：只含 {kind,key,preview≤48}（P5）。
        assert all(set(row) == {'kind', 'key', 'preview'} and len(row['preview']) <= 48
                   for row in deferred['items'])
        assert '不可猜测的完整尾句' not in packet['text']
        assert '读者完整尾句' not in packet['text']
        assert pipeline.validate_chapter_package(book, store, packet)
        assert digest(book) == before
        sizes.append(packet['metrics']['bytes'])
    # The extra 1,800 historical values change counts, not the writer's material volume.
    assert abs(sizes[1] - sizes[0]) < 500


def test_execution_rows_point_at_chapter_outline_instead_of_copying_planned():
    """execution 行只保留引擎派生段（kind/key/opening_state/action_reason/planned_after 与
    resources 派生键），planned/details 不再逐字复抄——完整章纲声明以同包必读的
    chapter_outline 为准（declared_in 指针），opening_state/planned_after 值不变（P2 钉）。"""
    book, store = prepared(count=2)
    plan = book['plans']['3']
    execution = package_context.execution(book, compose.participants(plan, book), plan)
    assert execution['changes'], '夹具第 3 章应有计划增量行'
    for row in execution['changes']:
        assert 'planned' not in row and 'details' not in row
        assert row['declared_in'] == 'chapter_outline'
        if row['kind'] != 'hook':
            assert row['opening_state'] == drift.project(book['state'], row['kind'], row['key'])
    rows = {row['kind']: row for row in execution['changes']}
    assert rows['clock']['opening_state'] == book['state']['clock']
    assert rows['clock']['planned_after'] == book['state']['clock'] + 1
    assert rows['knowledge']['planned_after'] == 'confirmed'      # 第 3 章知情阶梯：suspected→confirmed
    assert rows['knowledge']['opening_state'] == drift.project(book['state'], 'knowledge', rows['knowledge']['key'])
    resource_row = rows['resources']
    assert {'resource_key', 'holder', 'asset', 'unit'} <= set(resource_row)
    assert 'declared_in' in execution['rule'] or '章纲为准' in execution['rule']


def test_named_and_pinned_far_knowledge_and_reader_boundary_are_fully_preserved():
    book, store = prepared(named=True)
    packet = pipeline.chapter_package(book, store, 3)
    state = section(packet, 'state')
    for key in ('shen:old-0000', 'shen:old-0001'):
        assert state['knowledge'][key] == book['state']['knowledge'][key]
    assert state['reader_knowledge']['reader-0000'] == book['state']['reader_knowledge']['reader-0000']
    assert state['historical_assertions']['old-signature'] == book['state']['historical_assertions']['old-signature']
    assert '读者完整尾句' not in json.dumps(state['knowledge'], ensure_ascii=False)
    assert section(packet, 'deferred_history')['by_kind']['knowledge'] == 148


def test_incomplete_dependencies_still_deliver_full_related_history():
    book, store = prepared(count=105, complete=False)
    packet = pipeline.chapter_package(book, store, 3)
    state = section(packet, 'state')
    assert state['material_scope']['mode'] == 'conservative'
    assert state['knowledge']['shen:old-0104'] == book['state']['knowledge']['shen:old-0104']
    assert state['reader_knowledge']['reader-0104'] == book['state']['reader_knowledge']['reader-0104']
    assert state['developments']['shen'] == book['state']['developments']['shen']
    assert packet['metrics']['deferred_resources'] == 0
    assert 'deferred_history）' not in packet['text']


def test_preparer_can_add_far_values_and_full_history_without_reviving_other_omissions():
    book, store = prepared()
    original = pipeline.chapter_package(book, store, 3)
    supplemented = pipeline.chapter_package(book, store, 3,
        extra_resources=[{'kind': 'knowledge', 'key': 'shen:old-0149'},
                         {'kind': 'reader_knowledge', 'key': 'reader-0149'}],
        extra_chapters=[1])
    assert original['package_ref'] != supplemented['package_ref']
    assert book['state']['knowledge']['shen:old-0149']['claim'] in supplemented['text']
    assert book['state']['reader_knowledge']['reader-0149']['claim'] in supplemented['text']
    assert store.prose_page(1) in supplemented['text']
    assert book['state']['knowledge']['shen:old-0148']['claim'] not in supplemented['text']
    assert supplemented['metrics']['deferred_resources'] == original['metrics']['deferred_resources'] - 2
    assert pipeline.validate_chapter_package(book, store, supplemented)
    with pytest.raises(Error):
        pipeline.validate_chapter_package(book, store, original)
