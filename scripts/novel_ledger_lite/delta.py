"""State deltas, projection indexes, asset inverted indexes and checkpoint replay.

正文与 events 是真源，delta 和索引是派生数据。checkpoint 保存当前全量状态，
恢复时选目标章之前的最近快照，再按章重放事件；无合适快照则从种子状态开始。"""
from __future__ import annotations

import copy
from .contracts import digest, require
from . import facts, book_state

# 状态条目类字段：条目级 diff 分级；标量字段（clock 等）整字段记 touched。
ENTRY_FIELDS = ('entities', 'facts', 'knowledge', 'resources', 'relations', 'hooks', 'places',
                'placements', 'historical_assertions', 'developments', 'custody', 'arrivals',
                'anchors', 'links', 'story_nodes', 'thread_progress', 'reader_knowledge',
                'character_current', 'clock_threads')


def produce(before, after, events, chapter):
    """One chapter's state delta, plus its inverted-index entries. Pure; no side effects."""
    touched = {}
    for field in set(before) | set(after):
        old, new = before.get(field), after.get(field)
        if isinstance(old, dict) and isinstance(new, dict):
            keys = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
            if keys:
                touched[field] = keys
        elif old != new:
            touched[field] = new if field == 'clock' else 'changed'
    delta = {'chapter': chapter,
             'touched': touched,
             'before_hash': digest(before),
             'after_hash': digest(after),
             'inverted': inverted_entries(events, chapter)}
    return delta


def _event_addresses(event):
    """Extract projection coordinates and searchable identities together, without live state."""
    references, coordinates = set(), set()

    def name(value):
        if isinstance(value, str) and value:
            coordinates.add(value)

    def reference(kind, key):
        if isinstance(key, str) and key:
            references.add((kind, key))
            name(key)

    def compound(kind, entity, key):
        if isinstance(entity, str) and entity and isinstance(key, str) and key:
            reference(kind, entity + ':' + key)

    op = event.get('op')
    entity = event.get('entity')
    ident = entity.get('id') if isinstance(entity, dict) else entity
    for value in (ident, event.get('id'), event.get('topic')):
        name(value)

    if op in ('entity', 'alias'):
        reference('entities', ident)
    elif op == 'state':
        compound('facts', ident, event.get('key'))
    elif op == 'relation':
        source, target, key = event.get('from'), event.get('to'), event.get('key')
        for value in (source, target):
            name(value)
        if all(isinstance(v, str) and v for v in (source, target, key)):
            reference('relations', source + '>' + target + ':' + key)
    elif op == 'knowledge':
        compound('knowledge', ident, event.get('topic'))
    elif op == 'resource':
        asset, unit = event.get('asset'), event.get('unit')
        for holder in (event.get('from'), event.get('to')):
            name(holder)
            if all(isinstance(v, str) and v for v in (holder, asset, unit)):
                reference('resources', facts.resource_key(holder, asset, unit))
    elif op == 'clock':
        thread = event.get('thread')
        reference('clock_threads' if thread else 'clock', thread or 'main')
        if not thread:
            name('clock')              # Chapter outlines also call the main clock `clock`.
    elif op == 'hook':
        reference('hooks', event.get('id'))
    elif op == 'place':
        place = event.get('place')
        reference('places', place.get('id') if isinstance(place, dict) else None)
    elif op == 'move':
        reference('placements', ident)
    elif op == 'historical_assertion':
        reference('historical_assertions', event.get('id'))
    elif op == 'character_development':
        reference('developments', ident)
    elif op == 'story_node':
        reference('story_nodes', event.get('node'))
        reference('thread_progress', event.get('line'))
    elif op == 'story_thread':
        reference('thread_progress', event.get('thread'))
    elif op == 'reader_knowledge':
        reference('reader_knowledge', event.get('topic'))
    elif op == 'character_current':
        reference('character_current', ident)
    elif op in ('anchor', 'anchor_assert', 'anchor_change'):
        compound('anchors', ident, event.get('key'))
    elif op in ('link', 'link_change'):
        reference('links', event.get('id'))
    elif op == 'placement':
        # A handoff can remove one representation while establishing the other.
        reference('placements', ident)
        reference('custody', ident)
        if isinstance(event.get('after'), dict) and 'holder' in event['after']:
            reference('arrivals', ident)
    elif op == 'travel':
        reference('placements', ident)
        if 'arrive' in event:
            reference('arrivals', ident)
    elif op == 'perceive':
        # Perception has no implicit knowledge/state mutation; its recorded participants
        # and path remain searchable without presenting them as changed projections.
        for field in ('observer', 'target', 'from', 'to', 'link'):
            name(event.get(field))
    return references, coordinates


def event_references(event) -> set[tuple[str, str]]:
    """Direct projection coordinates an event records, preserving field identity.

    These are primary coordinates, suitable for following a coordinate's history. Searchable
    participants/topics are deliberately separate: a resource flow and a state change involving
    the same person must not become each other's successors. Derived effects requiring live
    state (such as arrival times of carried objects) are not invented from an event alone.
    """
    return _event_addresses(event)[0]


def event_coordinates(event) -> set[str]:
    """Canonical searchable keys, including entity/topic/id queries and both transfer holders."""
    return _event_addresses(event)[1]


def inverted_entries(events, chapter):
    """Searchable event coordinate → committed chapter; the index never substitutes for history."""
    rows = {}
    for event in events:
        for coordinate in sorted(event_coordinates(event)):
            pages = rows.setdefault(coordinate, [])
            if chapter not in pages:
                pages.append(chapter)
    return rows


def bump_index(delta_index, delta):
    """Advance the projection index: coordinate → last chapter that moved it."""
    chapter = delta['chapter']
    for field, keys in delta['touched'].items():
        if not isinstance(keys, list):
            continue
        for key in keys:
            delta_index['%s\x00%s' % (field, key)] = chapter
    return delta_index


def last_chapter(delta_index, field, key):
    """0 means「从未变更」——近窗判定视为远窗；点名条目仍可整条恢复。"""
    return delta_index.get('%s\x00%s' % (field, key), 0)


def checkpoint(state, through, volume=None):
    """Freeze one full projection snapshot. 每卷必落，另受 checkpoint_chapters 上限兜底。"""
    return {'through': through, 'volume': volume, 'state': copy.deepcopy(state),
            'state_hash': digest(state)}


def rebuild(book, store, through=None):
    """Rebuild the live projection through a requested chapter from a checkpoint and committed events.

    无可用快照时从种子状态开始；返回状态与实际恢复到的章号。"""
    book_state.require_current(book)
    require(through is None or type(through) is int and through >= 0,
            'chapter', '恢复章号须为非负整数。')
    target = store.last_chapter() if through is None else min(through, store.last_chapter())
    checkpoints = [row for row in book.get('checkpoints') or [] if row['through'] <= target]
    if checkpoints:
        latest = max(checkpoints, key=lambda row: row['through'])
        require(digest(latest['state']) == latest['state_hash'], 'checkpoint_hash',
                'checkpoint 状态与哈希不符。')
        state, start = copy.deepcopy(latest['state']), latest['through']
    else:
        state, start = facts.seed(book['initial_contract']), 0
    applied_to = start
    for row in store.headers('main', first=start + 1, last=target):
        for event in store.read_document(row['events']):
            facts.apply_event(state, event, row['n'])
        applied_to = row['n']
    return state, applied_to
