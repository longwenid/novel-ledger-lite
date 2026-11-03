"""Context sufficiency across fresh sessions, late returns, missing dependencies and recall."""
import copy
import json
from pathlib import Path

import pytest

import fixtures
from novel_ledger_lite import compose, facts, pipeline, materials
from novel_ledger_lite.contracts import Error, digest
from novel_ledger_lite.store import LiteStore


ARCHIVE = str(Path(__file__).parent / 'fixtures' / 'style_archive_sample.md')


def installed(**overrides):
    raw = fixtures.contract()
    raw.update(overrides)
    book = pipeline.open_book(raw, '作者确认测试输入', fixtures.world_fixture())
    volume = book['contract']['volumes'][0]
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(volume), fixtures.chapter_rows(book, with_scenes=True))
    return book, LiteStore()


def records(work, store):
    return json.loads(pipeline.materialize(work, store)['text'])['materials']


def test_each_chapter_is_self_contained_for_a_fresh_writer():
    book, store = installed(style_source=ARCHIVE)
    group = pipeline.group(book, store, 'v1', size=2)
    pipeline.envelope(book, store, 1, group)
    assert pipeline.submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    work = pipeline.envelope(book, store, 2, group)
    delivered = records(work, store)  # A new writer sees only this input, no earlier group input.
    assert delivered['core_context']['constraints']['world_rules'] == book['contract']['world_rules']
    assert delivered['core_context']['constraints']['protagonist_setup']['limit'] == '不牵连无关同事。'
    assert delivered['volume_context']['id'] == 'v1'
    assert delivered['style_archive']['content'] == book['style_archive']['content']
    assert work['delivery']['mode'] == 'self_contained'
    assert not work['delivery']['cached']


def test_cache_requires_explicit_current_context_and_exact_document_hash():
    book, store = installed(style_source=ARCHIVE)
    group = pipeline.group(book, store, 'v1')
    first = pipeline.envelope(book, store, 1, group)
    receipt = {'context_id': 'writer-A', 'loaded': [first['records']['style_archive'],
                                                 first['records']['volume_context']]}
    assert pipeline.submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    warm = pipeline.envelope(book, store, 2, group, cache=receipt)
    assert 'core_context' in warm['required']
    assert 'style_archive' not in warm['required']
    warmed = pipeline.materialize(warm, store, cache=receipt)
    assert warmed['metrics']['cached_records'] == 2
    assert 'style_archive' not in json.loads(warmed['text'])['materials']
    # Reusing the task in a fresh context must hydrate bodies, not inherit a stale receipt.
    cold = pipeline.materialize(warm, store)
    assert 'style_archive' in json.loads(cold['text'])['materials']
    other = pipeline.materialize(warm, store, cache={**receipt, 'context_id': 'writer-B'})
    assert 'volume_context' in json.loads(other['text'])['materials']


def test_style_switch_invalidates_the_old_cached_archive(tmp_path):
    path = tmp_path / 'voice.md'
    path.write_text('原作者声线版本一。', encoding='utf-8')
    book, store = installed(style_source=str(path))
    group = pipeline.group(book, store, 'v1')
    first = pipeline.envelope(book, store, 1, group)
    receipt = {'context_id': 'writer-A', 'loaded': [first['records']['style_archive']]}
    assert pipeline.submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    path.write_text('新作者声线版本二。', encoding='utf-8')
    pipeline.recontract_patch(book, source='作者确认版本二', style_source=str(path))
    work = pipeline.envelope(book, store, 2, group, cache=receipt)
    assert work['records']['style_archive'] not in receipt['loaded']
    assert 'style_archive' in work['required']


@pytest.mark.parametrize('cache', [{}, {'loaded': []}, {'context_id': 'A', 'loaded': ['invalid']}])
def test_invalid_cache_receipt_cannot_silently_drop_material(cache):
    book, store = installed()
    with pytest.raises(Error, match='缓存'):
        pipeline.envelope(book, store, 1, cache=cache)


def test_current_balances_traits_and_relationships_do_not_expire():
    state = facts.seed(fixtures.contract())
    state['facts']['shen:cannot-read'] = '不会识字。'
    state['relations']['shen>rival:trust'] = '信任已破裂'
    state['character_current'] = {'shen': {'value': {'desire': '寻人', 'stance': '克制'}}}
    plan = {'chapter': 3000, 'dependency_coverage': 'complete',
            'scenes': [{'present': ['shen'], 'reads': [], 'depends_on': []}]}
    view, warnings = compose.scoped_state(state, {}, ['shen'], plan, 3000)
    assert not warnings
    for field in ('facts', 'resources', 'relations', 'character_current'):
        assert view[field] == state[field]
    assert state['resources'] and all(not isinstance(v, dict) for v in view['resources'].values())


@pytest.mark.parametrize('source', ['scene', 'pinned'])
def test_missing_dependency_blocks_dispatch_even_with_complete_flag(source):
    book, store = installed()
    coord = {'kind': 'facts', 'key': 'shen:missing-rule'}
    if source == 'scene':
        book['plans']['1']['scenes'][0]['reads'].append(coord)
    else:
        book['contract']['pinned'] = [coord]
    before = copy.deepcopy(book)
    with pytest.raises(Error) as caught:
        pipeline.envelope(book, store, 1)
    assert caught.value.code == 'context_dependencies'
    assert caught.value.details['missing'] == [coord]
    assert book == before


def test_conflicting_precondition_blocks_dispatch_before_writing():
    book, store = installed()
    book['state']['facts']['shen:literacy'] = '不能识字'
    book['plans']['1']['preconditions'] = [{'kind': 'facts', 'key': 'shen:literacy', 'expected': '能识字'}]
    with pytest.raises(Error) as caught:
        pipeline.envelope(book, store, 1)
    assert caught.value.code == 'context_dependencies'
    assert caught.value.details['conflicts']


def test_planned_first_introduction_is_not_a_missing_dependency():
    book, store = installed()
    work = pipeline.envelope(book, store, 1)
    dependency = store.read_document(work['records']['dependencies'])
    assert {'kind': 'knowledge', 'key': 'shen:source', 'status': 'not_established'} in dependency['coordinates']


def test_normalized_node_dependencies_are_inferred_and_missing_predecessors_block():
    book, _ = installed(narrative_tracking=True)
    plan = {'chapter': 1, 'plot': {'nodes': [{'node': 'new-node', 'after': 'seeded',
                                             'depends_on': ['old-node'], 'line': 'main'}]}}
    with pytest.raises(Error) as caught:
        materials.dependencies(book, plan, ['shen'])
    assert {'kind': 'node', 'key': 'old-node'} in caught.value.details['missing']
    book['state']['story_nodes']['old-node'] = {'status': 'resolved'}
    report = materials.dependencies(book, plan, ['shen'])
    assert {'kind': 'node', 'key': 'old-node', 'status': 'existing'} in report['coordinates']
    assert {'kind': 'thread_progress', 'key': 'main', 'status': 'not_established'} in report['coordinates']


def test_old_development_events_do_not_reenter_as_a_full_history_list():
    state = facts.seed(fixtures.contract())
    state['developments']['shen'] = [{'change': '旧变化', 'evidence': {'chapter': n}} for n in range(1, 1000)]
    state['developments']['shen'].append({'change': '当前变化', 'evidence': {'chapter': 3000}})
    plan = {'chapter': 3001, 'dependency_coverage': 'complete',
            'scenes': [{'reads': [], 'depends_on': []}]}
    view, _ = compose.scoped_state(state, {'developments\x00shen': 3000}, ['shen'], plan, 3001)
    assert view['developments']['shen'] == [state['developments']['shen'][-1]]
    assert view['material_scope']['far_omitted']['developments'] == 1


def test_cast_is_inferred_from_scene_presence_even_without_deltas():
    raw = fixtures.contract()
    raw['entities'].append({'id': 'guest', 'name': '老赵', 'kind': 'person'})
    raw['initial_facts'] = [{'entity': 'guest', 'key': 'limit', 'value': '左手不能负重'}]
    book = pipeline.open_book(raw, '作者确认出场人物', fixtures.world_fixture())
    chapters = fixtures.chapter_rows(book, with_scenes=True)
    chapters['chapters'][0]['scenes'][0]['present'].append('guest')
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(book['contract']['volumes'][0]), chapters)
    store = LiteStore()
    work = pipeline.envelope(book, store, 1)
    view = store.read_document(work['records']['state'])
    assert view['entities']['guest']['name'] == '老赵'
    assert view['facts']['guest:limit'] == '左手不能负重'


def test_catalog_discovers_old_clues_by_name_and_supports_pagination():
    book, store = installed()
    for n in range(100):
        book['state']['historical_assertions']['clue-%03d' % n] = {
            'subjects': ['shen'], 'claim': '旧案线索%s号，铜牌留在渡口。' % n}
    work = pipeline.envelope(book, store, 1)
    # At a late chapter the old event bodies are omitted, but discoverability remains.
    plan = copy.deepcopy(book['plans']['1'])
    plan['chapter'] = 1000
    book['plans']['1000'] = plan
    view, _ = compose.scoped_state(book['state'], {}, ['shen'], plan, 1000)
    assert not view['historical_assertions']
    assert len(pipeline.catalog(book, chapter=1000, kind='historical_assertions')['items']) == 20
    page2 = pipeline.catalog(book, chapter=1000, kind='historical_assertions', page=1)
    assert page2['items'][0]['key'] == 'clue-020'
    found = pipeline.catalog(book, chapter=1000, kind='historical_assertions', query='线索99号')
    assert found['total'] == 1 and found['items'][0]['key'] == 'clue-099'
    by_person = pipeline.catalog(book, kind='historical_assertions', query='沈桐')
    assert by_person['total'] == 100
    full = pipeline.resource(book, found['items'][0]['kind'], found['items'][0]['key'])
    assert full['value']['claim'] == '旧案线索99号，铜牌留在渡口。'
    place = pipeline.catalog(book, kind='place_records', query='值班室')['items'][0]
    assert pipeline.resource(book, place['kind'], place['key'])['value']['name'] == '值班室'


def test_reader_knowledge_is_not_promoted_to_character_knowledge():
    book, store = installed(narrative_tracking=True)
    book['state']['knowledge']['shen:hidden'] = {'claim': '只看见模糊标记', 'stance': 'suspects'}
    book['state']['reader_knowledge']['hidden'] = {'claim': '读者知道幕后身份', 'status': 'confirmed'}
    plan = book['plans']['1']
    plan['scenes'][0]['reads'].append({'kind': 'knowledge', 'key': 'shen:hidden'})
    plan['reader_refs'] = ['hidden']
    delivered = records(pipeline.envelope(book, store, 1), store)
    assert delivered['state']['knowledge']['shen:hidden']['stance'] == 'suspects'
    assert delivered['state']['reader_knowledge']['hidden']['status'] == 'confirmed'
    assert '读者知道幕后身份' not in json.dumps(delivered['state']['knowledge'], ensure_ascii=False)


def test_canonical_delivery_has_one_outline_and_measures_actual_input():
    book, store = installed()
    work = pipeline.envelope(book, store, 1)
    rendered = pipeline.materialize(work, store, token_counter=len, tokenizer_id='test-character-counter')
    parsed = json.loads(rendered['text'])
    assert parsed['task']['payload']['chapter_outline'] == 'chapter_outline'
    assert isinstance(parsed['materials']['chapter_outline'], dict)
    assert 'contract' not in parsed['materials']
    encoded_plan = json.dumps(book['plans']['1'], ensure_ascii=False, separators=(',', ':'))
    assert rendered['text'].count(encoded_plan) == 1
    assert rendered['metrics']['bytes'] == len(rendered['text'].encode('utf-8'))
    assert rendered['metrics']['tokens'] == len(rendered['text'])
    assert sum(rendered['metrics']['category_bytes'].values()) == sum(
        row['bytes'] for row in rendered['metrics']['by_record'].values())
    assert '- characters：' not in work['brief']
    for quote in store.read_document(work['records'].get('anchor_sentences', work['records']['hooks'])).get('prior', {}).get('anchors', []):
        assert quote['quote'] not in work['brief']


def test_brief_references_historical_quotes_without_copying_them():
    book, store = installed()
    assert pipeline.submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    work = pipeline.envelope(book, store, 2)
    anchors = store.read_document(work['records']['anchor_sentences'])
    assert anchors['prior']['anchors']
    for quote in anchors['prior']['anchors']:
        assert quote['quote'] not in work['brief']
        assert quote['quote'] in pipeline.materialize(work, store)['text']


def test_old_actor_returns_next_volume_after_save_and_fresh_context(tmp_path):
    from benchmark_long_run import outlines, draft

    raw = fixtures.contract(60)
    raw.update(chapter_max=600, chapter_aim=500)
    raw['volumes'] = [{'id': 'v1', 'purpose': '查旧案', 'end': 30}, {'id': 'v2', 'purpose': '旧人归来', 'end': 60}]
    raw['initial_facts'] = [{'entity': 'shen', 'key': 'limit', 'value': '不会识字。'}]
    book = pipeline.open_book(raw, '作者确认两卷', fixtures.world_fixture())
    store = LiteStore()
    for volume in book['contract']['volumes']:
        outline, chapters = outlines(book, volume)
        pipeline.install_outlines(book, volume['id'], outline, chapters)
        for n in range(volume['first'], volume['end'] + 1):
            work = pipeline.envelope(book, store, n)
            if n == 31:
                delivered = records(work, store)
                assert delivered['state']['facts']['shen:limit'] == '不会识字。'
                assert delivered['state']['resources'] == book['state']['resources']
                assert delivered['core_context']['volume']['id'] == 'v2'
            outcome = pipeline.submit(book, store, n, draft(book, n, 500))
            assert outcome['ok'], outcome.get('findings')
        if volume['id'] == 'v1':
            path = tmp_path / 'volume-end.json'
            pipeline.save(book, store, path)
            book, store = pipeline.load(path)
    assert pipeline.verify_full(book, store)['ok']
