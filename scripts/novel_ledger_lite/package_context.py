"""Writer-facing execution constraints derived from the existing plan and ledger."""
from __future__ import annotations

import copy
import json

from . import delta, drift, drift_reconcile


def execution(book, people, plan):
    """Make the declared before/reason/after chain visible without a second reducer."""
    state = book['state']
    changes = []
    for entry in drift_reconcile._planned(plan):
        kind, key = entry['kind'], entry['key']
        planned, detail = entry['planned'], entry.get('detail') or {}
        opening = (copy.deepcopy(state.get('hooks', {}).get(key)) if kind == 'hook'
                   else drift.project(state, kind, key))
        row = {'kind': kind, 'key': key, 'opening_state': opening,
               'action_reason': detail.get('reason') or detail.get('choice') or detail.get('change')
                                or detail.get('outcome') or detail.get('note'),
               'planned_after': copy.deepcopy(planned.get('to', planned.get('after', planned.get('action')))),
               'planned': copy.deepcopy(planned), 'details': copy.deepcopy(detail)}
        if kind == 'clock':
            row['planned_after'] = opening + planned['advance_days']
        if kind == 'resources':
            coordinate = drift._resource_coordinate(state, key, detail.get('asset'))
            try:
                holder, asset, unit = json.loads(coordinate or key)
            except (ValueError, TypeError):
                holder, asset, unit = (detail.get(name) for name in ('holder', 'asset', 'unit'))
            row.update(resource_key=coordinate or key, holder=holder, asset=asset, unit=unit)
        changes.append(row)
    current_assets = []
    people = set(people)
    planned_assets = {row.get('resource_key') for row in changes if row['kind'] == 'resources'}
    for key, quantity in sorted(state.get('resources', {}).items()):
        holder, asset, unit = json.loads(key)
        if holder in people or key in planned_assets:
            current_assets.append({'key': key, 'holder': holder,
                                   'holder_name': state['entities'].get(holder, {}).get('name', holder),
                                   'asset': asset, 'unit': unit, 'quantity': copy.deepcopy(quantity)})
    return {'chapter': plan['chapter'], 'changes': changes, 'current_assets': current_assets,
            'rule': 'opening_state 是本章开写前真实状态，不冒充同章每一步之前的状态；planned_after 是章纲要求的结果。'
                    'changes 按核账接口分组，正文顺序遵循场景和章纲因果；'
                    '同章先 plant 后 payoff 时须先写埋设再兑现，不能跳过中间动作。'
                    '按行动原因在正文中完成变化，未列变化的已有资产保持原状。'
                    '正文不得临时新增资产、转移归属、消费数量或改人物知情来迁就情节。'
                    '确需新变化时停止写作，由准备者核实并修订章纲后重新发包。'}


def historical(book, store, chapter, *, dependencies=None):
    """Return verified source text, exact-coordinate later events and current truth."""
    row = store.chapter('main', chapter)
    dependencies = dependencies if dependencies is not None else set()
    dependencies.update(row[name] for name in ('prose', 'events', 'plan'))
    events, prose = store.events_page(chapter), store.prose_page(chapter)
    store.read_document(row['plan'])  # Verify the referenced plan as well as prose and events.
    coordinates = set().union(*(delta.event_references(event) for event in events)) if events else set()
    # Every chapter advances the global clock. It is already present in the current
    # state; replaying every later tick would obscure the actual historical dependency.
    coordinates = {coordinate for coordinate in coordinates if coordinate[0] not in ('clock', 'clock_threads')}
    later = {coordinate: [] for coordinate in coordinates}
    for source in store.headers('main', first=chapter + 1):
        verified = False
        dependencies.add(source['events'])
        for event in store.events_page(source['n']):
            shared = coordinates & delta.event_references(event)
            if not shared:
                continue
            if not verified:
                store.prose_page(source['n'])
                store.read_document(source['plan'])
                dependencies.update(source[name] for name in ('prose', 'plan'))
                verified = True
            item = {'chapter': source['n'], 'event': event,
                    'source_hashes': {name: source[name] for name in ('prose', 'events', 'plan')}}
            for coordinate in shared:
                later[coordinate].append(copy.deepcopy(item))
    histories = []
    for kind, key in sorted(coordinates):
        rows = book['state'].get(kind) or {}
        histories.append({'kind': kind, 'key': key, 'later_changes': later[(kind, key)],
                          'current': {'found': key in rows, 'value': copy.deepcopy(rows.get(key))}})
    return {'chapter': chapter, 'title': row['title'], 'summary': row['summary'], 'prose': prose,
            'events': events, 'source_hashes': {name: row[name] for name in ('prose', 'events', 'plan')},
            'coordinate_history': histories,
            'boundary': '本章正文与事件是当时记录；同坐标的后续变化另列，当前真值见 current 和本包当前状态。'
                        '不能把当时的余额、归属、关系或认知重新当作当前状态。'
                        '全局与支线时钟读本包当前状态，不逐章重复列出后续时钟推进。'}
