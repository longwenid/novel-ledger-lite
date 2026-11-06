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


def inverted_entries(events, chapter):
    """asset id → chapter for every coordinate a recall query may name.

    只索引带稳定 id 的资产类事件（承诺/读者认知/历史断言/实体/人物发展/场景登记）——
    recall 的查询域就是这些坐标；事实与资源的坐标已经活在 delta_index 里。
    """
    rows = {}
    for event in events:
        op = event.get('op')
        if op == 'hook':
            ident = event.get('id')
        elif op == 'reader_knowledge':
            ident = event.get('topic')
        elif op == 'historical_assertion':
            ident = event.get('id')
        elif op in ('entity', 'place'):
            ident = (event.get('entity') or event.get('place') or {}).get('id')
        elif op == 'alias':
            ident = event.get('entity')
        elif op == 'character_development':
            ident = event.get('entity')
        else:
            ident = None
        if isinstance(ident, str) and ident:
            rows.setdefault(ident, [])
            if chapter not in rows[ident]:
                rows[ident].append(chapter)
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
