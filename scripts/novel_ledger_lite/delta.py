"""The L3 delta layer: per-chapter state deltas, the projection index, the recall inverted
index, and volume/checkpoint snapshots.

五层账本（完整版架构报告 §3.1）的 lite 落地：
- L3 state_delta  每章 settle 顺路产出（引擎确定性计算，零模型）；delta 是派生数据，
  真源始终是 events/prose/headers（已入链）；delta 不新增哈希机制——每章投影哈希已
  逐章入章行 state_hash。
- delta_index     坐标→末次变更章：投影索引化的分级依据（近窗全文/远窗标题行）。
- inverted        资产→章号倒排：recall 从线性翻页降为「先查倒排定位，再取页」
  （方案三补丁 c；无匹配 O(1)——索引 miss 直接返回空）。
- checkpoint      每卷界或每 N 章冻结全量投影（报告第四刀采方案三同款
  「每卷 checkpoint 全量＋章间增量」）；中间 delta 在其后 checkpoint 被超越时可清理。
- rebuild         从最近 checkpoint 重放 events 重建缺失/损坏的 delta 段
  （报告 §5.4-B：数据零丢失——真源在链上，delta 是派生物）。
"""
from __future__ import annotations

import copy
from .contracts import digest, require
from . import facts

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
    """Rebuild the live projection from the nearest checkpoint plus committed events.

    delta 损坏/中断恢复路径（报告 §5.4-B）：从最近 checkpoint 起重放各章 events；
    无 checkpoint 时从种子状态全量重放。数据零丢失——真源在链上。返回 (state, applied_to)。
    """
    checkpoints = book.get('checkpoints') or []
    if checkpoints:
        latest = max(checkpoints, key=lambda row: row['through'])
        if through is not None and latest['through'] > through:
            latest = min((row for row in checkpoints if row['through'] <= through),
                         key=lambda row: row['through'], default=latest)
        state, start = copy.deepcopy(latest['state']), latest['through']
    else:
        state, start = facts.seed(book['contract']), 0
    for row in store.headers('main', first=start + 1, last=through):
        for event in store.read_document(row['events']):
            facts.apply_event(state, event, row['n'])
    return state, max((row['n'] for row in store.headers('main')), default=0)
