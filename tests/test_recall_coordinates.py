"""Historical lookup uses committed events, canonical coordinates and complete source history."""
import copy

import pytest

import fixtures
from novel_ledger_lite import delta, facts, pipeline, spatial
from novel_ledger_lite.contracts import Error, digest, han_count
from novel_ledger_lite.store import LiteStore


RESOURCE = '["shen","车费","元"]'
RELATION = 'shen>li:trust'


def relation_book():
    contract = fixtures.contract()
    contract['entities'].append({'id': 'li', 'name': '李青', 'kind': 'person'})
    book = pipeline.open_book(contract, '作者确认的召回回归', fixtures.world_fixture())
    volume = book['contract']['volumes'][0]
    data = fixtures.chapter_rows(book)
    for row, before, after in zip(data['chapters'], (None, '信任'), ('信任', '疏离')):
        row['relations'] = [{'source': 'shen', 'target': 'li', 'key': 'trust',
                             'from': before, 'to': after, 'reason': '本次核对改变了双方信任。'}]
        row['enter'].append({'kind': 'relations', 'key': RELATION, 'expected': before})
        row['exit'].append({'kind': 'relations', 'key': RELATION, 'expected': after})
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(volume), data)
    return book, LiteStore()


def relation_draft(book, n):
    # Keep the standard fixture's real resource/clock/knowledge/hook submission, adding the
    # independent relation row that this fixture deliberately does not otherwise implement.
    base = copy.deepcopy(book)
    base['plans'][str(n)]['relations'] = []
    draft = fixtures.draft_for(base, n)
    row = book['plans'][str(n)]['relations'][0]
    quote = '沈桐与李青第%s次核对后，信任变为%s。' % (fixtures._cn(n), row['to'])
    draft['prose'] += quote
    draft['drift_check']['items'].append({
        'kind': 'relations', 'key': RELATION,
        'planned': {'from': row['from'], 'to': row['to']},
        'status': 'kept', 'actual': {'to': row['to']},
        'evidence': {'chapter': n, 'quote': quote},
    })
    return draft


def test_real_resource_consumption_and_relation_changes_are_recalled_by_standard_key():
    book, store = relation_book()
    assert pipeline.recall(book, store, RESOURCE) == {'chapters': [], 'hits': []}
    assert pipeline.resource(book, 'resources', RESOURCE)['value'] == '4'
    first = fixtures.submit_reviewed(book, store, 1, relation_draft(book, 1))
    assert first['ok'], first
    assert pipeline.resource(book, 'resources', RESOURCE)['value'] == '3'
    resource = pipeline.recall(book, store, RESOURCE)
    assert resource['chapters'] == [1]
    assert [h['event']['quantity'] for h in resource['hits']] == ['1']
    assert resource['hits'][0]['event']['from_before'] == '4'
    assert pipeline.recall(book, store, RELATION)['hits'][0]['event']['after'] == '信任'
    assert book['inverted'][RESOURCE] == [1]
    assert book['inverted'][RELATION] == [1]
    second = fixtures.submit_reviewed(book, store, 2, relation_draft(book, 2))
    assert second['ok'], second
    relations = pipeline.recall(book, store, RELATION)
    assert relations['chapters'] == [1, 2]
    assert [h['event']['after'] for h in relations['hits']] == ['信任', '疏离']
    assert [h['event']['op'] for h in pipeline.recall(book, store, 'shen:source')['hits']] \
        == ['knowledge', 'knowledge']
    assert pipeline.recall(book, store, 'source')['chapters'] == [1, 2]
    assert pipeline.recall(book, store, 'shen>li:trus') == {'chapters': [], 'hits': []}


@pytest.mark.parametrize('stale', [{}, {RESOURCE: [1], RELATION: [2, 999]}])
def test_saved_missing_or_partial_index_cannot_hide_history_or_rewrite_it(tmp_path, stale):
    book, store = relation_book()
    for n in (1, 2):
        outcome = fixtures.submit_reviewed(book, store, n, relation_draft(book, n))
        assert outcome['ok'], outcome
    book['inverted'] = copy.deepcopy(stale)
    path = tmp_path / 'partial-index.json'
    pipeline.save(book, store, path)
    loaded, saved = pipeline.load(path)
    before = copy.deepcopy(loaded), copy.deepcopy(saved.to_dict()), path.read_bytes()
    assert pipeline.recall(loaded, saved, RESOURCE)['chapters'] == [1, 2]
    assert pipeline.recall(loaded, saved, RELATION)['chapters'] == [1, 2]
    assert (loaded, saved.to_dict(), path.read_bytes()) == before


def test_recall_does_not_treat_projection_or_index_pages_as_historical_evidence():
    book, store = relation_book()
    # A seeded balance and even a stale positive index cannot manufacture a committed event.
    book['inverted'][RESOURCE] = [1]
    assert pipeline.resource(book, 'resources', RESOURCE)['found']
    assert pipeline.recall(book, store, RESOURCE) == {'chapters': [], 'hits': []}
    outcome = fixtures.submit_reviewed(book, store, 1, relation_draft(book, 1))
    assert outcome['ok'], outcome
    # A source page that fails its content hash must fail lookup rather than look like no history.
    key = store.chapter('main', 1)['events']
    store._documents[key] = []
    with pytest.raises(Error) as caught:
        pipeline.recall(book, store, RESOURCE)
    assert caught.value.code == 'record_hash'


def test_committed_state_and_transfer_are_recalled_without_an_inverted_index():
    contract = fixtures.contract()
    contract['entities'].append({'id': 'li', 'name': '李青', 'kind': 'person'})
    book = pipeline.open_book(contract, '作者确认的历史页', fixtures.world_fixture())
    store = LiteStore()
    prose = '沈桐划伤手，仍把一元车费转给李青。'
    before = book['state']
    state, events = facts.settle(before, [
        {'op': 'state', 'entity': 'shen', 'key': 'health', 'before': None, 'after': '伤',
         'evidence': {'chapter': 1, 'quote': '沈桐划伤手'}},
        {'op': 'resource', 'from': 'shen', 'to': 'li', 'asset': '车费', 'unit': '元',
         'quantity': '1', 'from_before': '4', 'to_before': '0', 'reason': '转交李青',
         'evidence': {'chapter': 1, 'quote': '把一元车费转给李青'}},
    ], prose, 1)
    # State events are a supported historical event family even though the current outline
    # form has no arbitrary-state increment. Commit the evidence-settled page through LiteStore.
    store.put_chapter({
        'n': 1, 'title': '交接', 'prose': store.document(prose),
        'events': store.document(events), 'plan': store.document({}), 'review': {},
        'state_hash': digest(state), 'summary': '受伤后交接车费', 'han': han_count(prose),
        'delta': store.document(delta.produce(before, state, events, 1)),
    }, store.document(book['contract']))
    book['state'] = state
    assert book['inverted'] == {}
    assert pipeline.recall(book, store, 'shen:health') == {
        'chapters': [1], 'hits': [{'chapter': 1, 'event': events[0]}]}
    for key in (RESOURCE, '["li","车费","元"]'):
        assert pipeline.recall(book, store, key) == {
            'chapters': [1], 'hits': [{'chapter': 1, 'event': events[1]}]}


def test_all_event_families_use_reducer_coordinates_and_transfer_both_balances():
    contract = fixtures.contract()
    contract.update(narrative_tracking=True, editorial_features=True)
    contract['entities'] += [{'id': 'li', 'name': '李青', 'kind': 'person'},
                              {'id': 'token', 'name': '凭证', 'kind': 'object'}]
    contract['placements'].update(li='office', token='office')
    state = facts.seed(contract)
    events = [
        {'op': 'entity', 'entity': {'id': 'wu', 'name': '吴戈', 'kind': 'person'}},
        {'op': 'alias', 'entity': 'wu', 'alias': '老吴'},
        {'op': 'state', 'entity': 'shen', 'key': 'health', 'before': None, 'after': '伤'},
        {'op': 'relation', 'from': 'shen', 'to': 'li', 'key': 'trust', 'before': None,
         'after': '信任'},
        {'op': 'knowledge', 'entity': 'shen', 'topic': 'source', 'before': None,
         'claim': '李青签字', 'source': '凭证', 'stance': 'knows'},
        {'op': 'resource', 'from': 'shen', 'to': 'li', 'asset': '车费', 'unit': '元',
         'quantity': '1', 'from_before': '4', 'to_before': '0', 'reason': '转交'},
        {'op': 'clock', 'before': 0, 'after': 1},
        {'op': 'clock', 'thread': 'night', 'before': 1, 'after': 2},
        {'op': 'hook', 'id': 'promise', 'before': None, 'status': 'open', 'due': 100,
         'text': '核对凭证'},
        {'op': 'place', 'place': {'id': 'gate', 'name': '门口'}},
        {'op': 'move', 'entity': 'shen', 'before': 'office', 'after': 'yard',
         'route': '走到后院', 'reason': '核对'},
        {'op': 'historical_assertion', 'id': 'old-signature', 'subjects': ['shen'],
         'claim': '曾签过字', 'source': '旧凭证',
         'occurred_at': {'basis': 'main_clock', 'start': 0, 'end': 1}},
        {'op': 'character_development', 'entity': 'shen', 'choice': '公开', 'cost': '停工',
         'change': '承担责任'},
        {'op': 'story_node', 'node': 'signature', 'line': 'main', 'depends_on': [],
         'before': None, 'after': 'seeded', 'outcome': '取得签字'},
        {'op': 'story_thread', 'thread': 'main', 'before': 'active', 'after': 'dormant',
         'reason': '等待复核', 'return_by': 100},
        {'op': 'reader_knowledge', 'topic': 'source', 'before': None, 'after': 'hinted',
         'claim': '签字可疑'},
        {'op': 'character_current', 'entity': 'shen', 'before': None,
         'after': {'desire': '核对', 'stance': '承担', 'relationship_focus': '李青'},
         'choice': '公开', 'cost': '停工', 'change': '承担责任'},
        {'op': 'anchor', 'entity': 'shen', 'key': 'height', 'value': 170, 'policy': 'eventful'},
        {'op': 'anchor_assert', 'entity': 'shen', 'key': 'height', 'value': 170},
        {'op': 'anchor_change', 'entity': 'shen', 'key': 'height', 'before': 170,
         'after': 171, 'reason': '重新测量'},
        {'op': 'link', 'id': 'road', 'a': 'office', 'b': 'yard', 'kind': 'path', 'min_days': 1},
        {'op': 'link_change', 'id': 'road', 'before': True, 'after': False, 'reason': '关闭'},
        {'op': 'link_change', 'id': 'road', 'before': False, 'after': True, 'reason': '重开'},
        {'op': 'placement', 'entity': 'token', 'before': {'place': 'office'},
         'after': {'holder': 'li'}},
        {'op': 'travel', 'entity': 'shen', 'from': 'yard', 'to': 'office', 'links': ['road'],
         'depart': 1, 'arrive': 2},
        {'op': 'perceive', 'observer': 'shen', 'target': 'li', 'from': 'office', 'to': 'office',
         'channel': 'sight'},
    ]
    for event in events:
        event['evidence'] = {'chapter': 1, 'quote': '核对凭证。'}
        before = copy.deepcopy(state)
        facts.apply_event(state, event, 1)
        # The independent reducers, rather than a duplicate op-to-key table, determine which
        # projection coordinates must be discoverable in the historical index.
        changed = {(field, key) for field in state
                   if isinstance(state[field], dict)
                   for key in set(before.get(field, {})) | set(state[field])
                   if before.get(field, {}).get(key) != state[field].get(key)}
        if before['clock'] != state['clock']:
            changed.add(('clock', 'main'))
        assert changed <= delta.event_references(event), event['op']
        assert {key for _, key in delta.event_references(event)} <= delta.event_coordinates(event)
        assert all(1 in pages for pages in delta.inverted_entries([event], 1).values())
        assert delta.event_coordinates(event), event['op']
    assert set(spatial.OPS) <= {e['op'] for e in events}
    transfer = next(e for e in events if e['op'] == 'resource')
    assert {RESOURCE, '["li","车费","元"]'} <= delta.event_coordinates(transfer)
    assert state['resources'][RESOURCE] == '3'
    assert state['resources']['["li","车费","元"]'] == '1'
    state_change = next(e for e in events if e['op'] == 'state')
    knowledge = next(e for e in events if e['op'] == 'knowledge')
    assert 'shen:health' in delta.inverted_entries([state_change], 1)
    assert 'shen:source' in delta.inverted_entries([knowledge], 1)
    assert not (delta.event_references(state_change) & delta.event_references(transfer))
