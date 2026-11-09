"""Dependency checks, discoverable resource catalogs and one canonical delivery rendering."""
from __future__ import annotations

import copy
import json

from .contracts import digest, policy_default, require, text
from . import delta, drift_reconcile, narrative, story_memory, world
from .envelope import validate_work


CURRENT_FIELDS = ('facts', 'resources', 'relations', 'character_current')
HISTORY_FIELDS = ('knowledge', 'reader_knowledge', 'historical_assertions', 'developments')


def field_of(kind):
    return 'story_nodes' if kind == 'node' else kind


def core(book, volume):
    contract = book['contract']
    keys = ('title', 'genre', 'reader_promise', 'ending', 'story_engine', 'opposition', 'world_premise',
            'world_rules', 'protagonist_setup', 'voice', 'tone', 'pov', 'style_traits')
    return {'contract_hash': digest(contract),
            'constraints': {key: copy.deepcopy(contract[key]) for key in keys if key in contract},
            'chapter_band': {key: contract[key] for key in ('chapter_min', 'chapter_aim', 'chapter_max')},
            'volume': {key: volume[key] for key in ('id', 'purpose', 'first', 'end')} if volume else None,
            'rule': '以上为冻结约束；账本未携带的内容不等于不存在，人物知情与读者知情分别核对。'}


def dependencies(book, plan, people):
    """Validate concrete references and pre-state; completeness is never inferred from a flag."""
    state = book['state']
    named = story_memory.reads(plan)
    pinned = {story_memory.coordinate(row) for row in book['contract'].get('pinned') or []}
    named.update(pinned)
    named.update(('entities', ident) for ident in people)
    absent = set()
    for row in (plan.get('enter') or []) + (plan.get('preconditions') or []):
        if row.get('expected', object()) is None:
            absent.add(story_memory.coordinate(row))
    for entry in drift_reconcile._planned(plan):
        kind, key, expected = entry['kind'], entry['key'], entry['planned']
        if kind == 'hook' and expected.get('action') == 'plant':
            absent.add(('hooks', key))
        elif kind == 'knowledge' and expected.get('from') is None:
            absent.add(('knowledge', key))
        elif kind == 'resources' and str(expected.get('from')) in ('0', '0.0'):
            absent.add(('resources', key))
        elif kind in ('characters', 'relations') and expected.get('from') is None:
            absent.add(('character_current' if kind == 'characters' else 'relations', key))
        elif kind == 'node' and expected.get('after') == 'seeded':
            absent.add(('node', key))
            definition = entry.get('definition') or {}
            line = definition.get('line') or definition.get('thread') or definition.get('kind') or 'main'
            absent.add(('thread_progress', line))
        elif kind == 'thread' and expected.get('after') == 'active':
            absent.add(('thread_progress', key))
        elif kind == 'disclosure':
            # An initial reader disclosure starts from an unestablished topic.
            if expected.get('from') is None:
                absent.add(('reader_knowledge', key))
    for entry in plan.get('new_entities') or []:
        absent.add(('entities', entry['id']))
    missing, entries = [], []
    for kind, key in sorted(named):
        field = field_of(kind)
        found = kind == 'clock' or key in (state.get(field) or {})
        status = 'existing' if found else 'not_established' if (kind, key) in absent else 'missing'
        if (kind, key) in pinned and not found:
            status = 'missing'
        entries.append({'kind': kind, 'key': key, 'status': status})
        if status == 'missing':
            missing.append({'kind': kind, 'key': key})
    indexed_world = world.index(book['world']) if book.get('world') else {}
    for key in plan.get('world_refs') or []:
        if key not in indexed_world:
            missing.append({'kind': 'world_records', 'key': key})
    conflicts = drift_reconcile.state_mismatch(state, plan)
    conflicts.extend({'kind': 'precondition', 'key': row['key'], 'expected': row['expected']}
                     for row in narrative.unmet(state, plan))
    require(not missing and not conflicts, 'context_dependencies',
            '派工材料依赖缺失或前态冲突，须补齐资源或修正章纲后再写。',
            {'missing': missing, 'conflicts': conflicts})
    return {'coordinates': entries,
            'verification': '引用存在性与章纲前态已核验；不据 complete 标志宣称语义依赖完整。'}


def related(field, key, value, people, named):
    if (field, key) in named:
        return True
    if field in ('facts', 'knowledge'):
        return key.split(':', 1)[0] in people
    if field == 'resources':
        try:
            return json.loads(key)[0] in people
        except (ValueError, TypeError, IndexError):
            return False
    if field == 'relations':
        return bool({key.split('>', 1)[0], key.split('>', 1)[-1].split(':', 1)[0]} & people)
    if field in ('character_current', 'developments', 'entities', 'placements'):
        return key in people
    if field in ('historical_assertions', 'hooks'):
        return bool(set(value.get('subjects') or []) & people)
    return field == 'reader_knowledge'


def _catalog_kind(kind):
    if kind == 'place_records':
        kind = 'places'
    elif kind is not None:
        kind, _ = story_memory.coordinate({'kind': kind, 'key': 'main'})
        kind = field_of(kind)
    return kind


def _catalog_rows(book, plan, people, view, *, kind=None, query=''):
    """Collect discoverable coordinates once, without fetching their full values."""
    kind = _catalog_kind(kind)
    fields = CURRENT_FIELDS + HISTORY_FIELDS + ('entities', 'places', 'hooks')
    require(kind is None or kind in fields, 'context_catalog', '该资源种类没有补读目录。')
    people = set(people)
    named = {(field_of(k), key) for k, key in story_memory.reads(plan)} if plan else set()
    rows = []
    for field in fields:
        if kind is not None and field != kind:
            continue
        for key, value in (book['state'].get(field) or {}).items():
            if plan and not related(field, key, value, people, named):
                continue
            if view is not None and key in view.get(field, {}) and view[field][key] == value:
                continue
            holder = key.split(':', 1)[0] if field in ('facts', 'knowledge') else key
            if field == 'resources':
                holder = json.loads(key)[0]
            elif field == 'historical_assertions' and value.get('subjects'):
                holder = value['subjects'][0]
            entity = book['state']['entities'].get(holder) or {}
            label = key
            if isinstance(value, dict):
                label = value.get('name') or value.get('text') or value.get('claim') or key
            elif isinstance(value, list) and value:
                label = value[-1].get('change') or key
            else:
                label = str(value)
            label = str(label)
            if query and query.casefold() not in (key + ' ' + entity.get('name', '') + ' ' + label).casefold():
                continue
            rows.append({'kind': 'place_records' if field == 'places' else field,
                         'key': key, 'name': entity.get('name') or key,
                         'preview': label[:80],
                         'last_chapter': delta.last_chapter(book.get('delta_index') or {}, field, key)})
    rows.sort(key=lambda row: (-row['last_chapter'], row['kind'], row['key']))
    return rows


def catalog(book, plan=None, people=(), view=None, *, kind=None, query='', page=0, per=20):
    """Bounded, searchable metadata; excerpts identify entries and are never canonical values."""
    require(type(page) is int and page >= 0 and type(per) is int and 1 <= per <= 100,
            'context_catalog', '目录分页须为非负页号，每页 1～100 条。')
    require(isinstance(query, str), 'context_catalog', '目录查询须为文本。')
    rows = _catalog_rows(book, plan, people, view, kind=kind, query=query)
    kind = _catalog_kind(kind)
    start = page * per
    return {'items': rows[start:start + per], 'page': page, 'per': per, 'total': len(rows),
            'has_more': start + per < len(rows), 'query': query, 'kind': kind,
            'scope': 'chapter_related' if plan else 'all_resources',
            'resolve': '先用 pipeline.catalog 搜索/翻页，再用 pipeline.resource 按 kind/key 取真值。',
            'boundary': 'preview 只是定位片段，不是可据以写作的完整事实；knowledge 属于人物，reader_knowledge 属于读者。'}


def package_supplements(book, plan, people, view, *, included=()):
    """Preserve the verified projection; never turn its omitted history back into mandatory input.

    Current values and all explicitly named/pinned dependencies remain full. Only the history
    already excluded by a complete-dependency projection can stay deferred. Incomplete scene
    dependencies retain the conservative expansion used by standalone packets.
    """
    complete = (view.get('material_scope') or {}).get('mode') == 'declared_dependencies'
    named = {(field_of(kind), key) for kind, key in story_memory.reads(plan)}
    named.update((field_of(kind), key) for kind, key in (
        story_memory.coordinate(row) for row in book['contract'].get('pinned') or []))
    full, deferred = [], []
    counts = {}
    for row in _catalog_rows(book, plan, people, view):
        coordinate = row['kind'], row['key']
        if coordinate in included:
            continue
        if complete and row['kind'] in HISTORY_FIELDS and coordinate not in named:
            deferred.append(row)
            counts[row['kind']] = counts.get(row['kind'], 0) + 1
        else:
            full.append(row)
    return full, {
        'items': deferred[:20], 'total': len(deferred), 'by_kind': counts,
        'shown': min(20, len(deferred)), 'has_more': len(deferred) > 20,
        'scope': 'declared_dependencies' if complete else 'conservative',
        'boundary': '这里只列完整依赖声明下未点名的远期历史定位片段，不是事实正文，也不表示人物或读者不知道。'
                    '当前事实、资产、关系、人物状态及显式依赖不按年龄省略。',
        'resolve': '写作者仍只读本文件；如需任何未携带材料，停止并说明所需人物、话题或ID，'
                   '由准备者检索完整目录、核实真值后补充资源或历史章节并重新签发。'
                   '不得依据片段猜测、重置状态或自行补读。',
    }


def delivery_cache(cache):
    if cache is None:
        return None, set()
    require(isinstance(cache, dict) and text(cache.get('context_id'))
            and isinstance(cache.get('loaded'), list)
            and all(isinstance(key, str) and len(key) == 64 for key in cache['loaded']),
            'context_cache', '缓存须由宿主提供 {context_id: 当前会话ID, loaded: 已加载文档哈希数组}。')
    return cache['context_id'], set(cache['loaded'])


def render(work, store, token_counter=None, tokenizer_id=None, cache=None):
    """Render the actual model input once, excluding optional documents and cached bodies."""
    validate_work(work)
    require(token_counter is None or callable(token_counter), 'context_metrics', 'token_counter 须可调用。')
    context_id, loaded = delivery_cache(cache)
    previous = work['delivery']
    acknowledged = previous['cached']
    cached = {name: key for name, key in acknowledged.items()
              if context_id == previous.get('context_id') and key in loaded}
    required = list(work['required']) + [name for name in acknowledged if name not in cached]
    materials, seen, sizes = {}, {}, {}
    for name in required:
        key = work['records'][name]
        if key in seen:
            materials[name] = {'same_as': seen[key]}
            continue
        value = store.read_document(key)
        materials[name], seen[key] = value, name
        encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        sizes[name] = {'bytes': len(encoded.encode('utf-8'))}
        if token_counter:
            sizes[name]['tokens'] = token_counter(encoded)
    task = {key: work[key] for key in ('schema', 'stage', 'chapter', 'first', 'last', 'payload', 'delivery')
            if key in work}
    task['delivery'] = {'context_id': context_id, 'cached': cached,
                        'mode': 'acknowledged_cache' if cached else 'self_contained'}
    rendered = json.dumps({'task': task, 'brief': work.get('brief', ''), 'materials': materials},
                          ensure_ascii=False, separators=(',', ':'))
    metrics = {'bytes': len(rendered.encode('utf-8')), 'by_record': sizes,
               'required_records': len(required), 'cached_records': len(cached)}
    categories = {'core': 0, 'chapter': 0, 'continuity': 0, 'recall': 0}
    for name, size in sizes.items():
        category = ('core' if name in ('core_context', 'style', 'style_guide', 'style_archive', 'volume_context')
                    else 'recall' if name == 'recall_manifest'
                    else 'continuity' if name.startswith('previous_') or name in ('anchor_sentences', 'scene_sources')
                    else 'chapter')
        categories[category] += size['bytes']
    metrics['category_bytes'] = categories
    metrics['metadata_and_brief_bytes'] = metrics['bytes'] - sum(categories.values())
    if token_counter:
        metrics.update(tokens=token_counter(rendered), tokenizer=tokenizer_id or 'caller_provided')
    return {'text': rendered, 'metrics': metrics}
