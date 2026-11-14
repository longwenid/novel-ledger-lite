"""Compile frozen writing inputs from five layers of the ledger.

L0 契约与文风；L1 卷纲；L2 章纲、相关状态与世界记录；
L3 章间增量与锚句；L4 历史事件寻址指针。完整依赖路径限制远窗标题行总量，
保留点名和常驻资源，缺少依赖声明时告警并保守携带参与人相关背景。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from .contracts import (DEFAULTS, HOOK_LINKS_CAPABILITY, READING_DEPENDENCIES_CAPABILITY,
                        SCENE_IDENTITY_CAPABILITY, SCENE_MEMORY_CAPABILITY, TASK,
                        VOLUME_OUTLINE_CAPABILITY, digest, policy_default, require,
                        resolve_style_profile, style_options_board, text, STYLE_CATALOG)
from . import anchors, briefs, delta as delta_ledger, narrative, planning, story_memory, style, world, materials, book_state
from .envelope import validate_work

STYLE_ROOT = Path(__file__).resolve().parents[2]


def json_holder(key):
    """资源坐标 [holder, asset, unit] 的持有者段；畸形键按无持有者处理。"""
    try:
        return json.loads(key)[0]
    except Exception:
        return None


def participants(plan, book):
    """Infer the cast from scenes and structured deltas, without reading narrative text."""
    plan = plan or {}
    found = set(plan.get('participants') or [])
    for scene in plan.get('scenes') or []:
        found.update(scene.get('present') or [])
        found.update(scene.get('speakers') or [])
    for row in plan.get('new_entities') or []:
        found.add(row['id'])
    for field in ('characters', 'knowledge', 'places'):
        for row in plan.get(field) or []:
            ident = row.get('who') or row.get('entity')
            if ident:
                found.add(ident)
    for row in plan.get('resources') or []:
        ident = json_holder(row.get('key', ''))
        if ident:
            found.add(ident)
    for row in plan.get('relations') or []:
        found.update(ident for ident in (row.get('source'), row.get('target')) if ident)
    for kind, key in story_memory.reads(plan):
        if kind in ('entities', 'placements', 'character_current', 'developments'):
            found.add(key)
        elif kind in ('facts', 'knowledge'):
            found.add(key.split(':', 1)[0])
        elif kind == 'resources' and json_holder(key):
            found.add(json_holder(key))
        elif kind == 'relations':
            found.update((key.split('>', 1)[0], key.split('>', 1)[-1].split(':', 1)[0]))
    return sorted(found or book['state']['entities'])

WRITING_STAGES = ('write',)


def _planned_nodes(plan):
    ids = set(plan.get('node_ids') or ())
    for row in (plan.get('plot') or {}).get('nodes') or ():
        if isinstance(row, dict) and row.get('node'):
            ids.add(row['node'])
    return ids


def _complete_dependencies(plan):
    """A flag without actual per-scene declarations does not justify dropping background."""
    scenes = plan.get('scenes') or []
    return (plan.get('dependency_coverage') == 'complete' and bool(scenes)
            and all(isinstance(scene, dict) and isinstance(scene.get('reads'), list)
                    and isinstance(scene.get('depends_on'), list) for scene in scenes))


def _spatial_scope(state, participants, plan, inputs):
    """Keep declared locations and the custody, route and parent chains that make them true.

    仅在完整依赖声明路径收窄空间背景。"""
    people = set(participants)
    people.update(key for kind, key in inputs
                  if kind in ('entities', 'placements', 'character_current', 'developments'))
    people.update(key.split(':', 1)[0] for kind, key in inputs if kind in ('facts', 'knowledge'))
    for kind, key in inputs:
        if kind == 'resources' and json_holder(key):
            people.add(json_holder(key))
        elif kind == 'relations':
            people.update((key.split('>', 1)[0], key.split('>', 1)[-1].split(':', 1)[0]))
    custody = state.get('custody', {})
    related = {ident: set() for ident in state['entities']}
    for item, holder in custody.items():
        related.setdefault(item, set()).add(holder)
        related.setdefault(holder, set()).add(item)
    todo = list(people)
    while todo:
        for ident in related.get(todo.pop(), ()):
            if ident not in people:
                people.add(ident)
                todo.append(ident)
    places = state['places']
    locations = {place for entity, place in state['placements'].items() if entity in people}
    names = {}
    for ident, row in places.items():
        names.setdefault(row.get('name'), set()).add(ident)

    def location(value):
        if isinstance(value, str):
            if value in places:
                locations.add(value)
            locations.update(names.get(value, ()))

    link_ids = set()
    for movement in plan.get('places') or []:
        location(movement.get('from'))
        location(movement.get('to'))
        link_ids.update(movement.get('links') or [])
    for row in (plan.get('enter') or []) + (plan.get('exit') or []) + (plan.get('preconditions') or []):
        if row.get('kind') in ('places', 'place', 'placements'):
            location(row.get('expected'))
    links = state.get('links', {})
    for ident in link_ids:
        link = links.get(ident, {})
        location(link.get('a'))
        location(link.get('b'))
    link_ids.update(ident for ident, link in links.items()
                    if link['a'] in locations and link['b'] in locations)
    todo = list(locations)
    while todo:
        parent = places.get(todo.pop(), {}).get('parent')
        if parent is not None and parent not in locations:
            locations.add(parent)
            todo.append(parent)
    return people, locations, link_ids


def style_spec(book, store, volume, chapter_row, chapter):
    """Build the selected style, author voice, chapter rhythm and numeric baseline for one dispatch.

    最近五章基线与提交门使用相同的指标和容差。"""
    contract = book['contract']
    volume_row_ = book.get('volumes_outline', {}).get(volume['id']) if volume else None
    volume_style = volume_row_.get('style') if isinstance(volume_row_, dict) else {}
    chapter_style = chapter_row.get('style') if isinstance(chapter_row, dict) else {}
    recent = [(row['n'], style.metrics(store.prose_page(row['n'])))
              for row in store.headers('main', first=max(1, chapter - style.STYLE_BASELINE_WINDOW),
                                       last=chapter - 1)]
    recent.sort(key=lambda pair: abs(pair[0] - chapter))
    # 外部源路径下 style_profile 可缺（锚由档案自身约定承担），锚为 None 时按空处理。
    anchor = style.current_anchor(book, recent) or {}
    external = text(contract.get('style_source') or '')
    return {'voice': contract.get('voice', ''), 'tone': contract.get('tone', ''),
            'pov': contract.get('pov', ''), 'style_traits': list(contract.get('style_traits') or []),
            'profile': resolve_style_profile(contract.get('style_profile')) or '',
            'style_source': contract.get('style_source') or '',
            'source_kind': 'external_archive' if external else 'builtin_catalog',
            'guard': contract.get('style_guard', DEFAULTS['style_guard']),
            'anchor': anchor,
            'window': style.merged_window(contract, volume_style),
            'volume': dict(volume_style), 'chapter': dict(chapter_style),
            'baseline_note': '文风基线：最近 %d 章已提交正文的滚动中位（本信封 basis=%s，origin=%s）；'
                             '尚无已提交章时回落生效档的注册锚或外部档案约定。'
                             'guard=observe 只观察形状变化，strict 才把锚点偏离判为 finding。'
                             % (style.STYLE_BASELINE_WINDOW, (anchor or {}).get('basis') or [],
                                (anchor or {}).get('origin', 'default'))}


# Current values never expire because of age. History is selected separately.
CURRENT_FIELDS = materials.CURRENT_FIELDS
HISTORY_FIELDS = materials.HISTORY_FIELDS


def scoped_state(state, delta_index, participants, plan, chapter, *, near=None, pinned=(),
                 allow_dependency_scope=True):
    """Keep relevant current state whole; window only historical detail and knowledge topics."""
    plan = plan or {}
    near = near if near is not None else policy_default('near_window_chapters')
    inputs = story_memory.reads(plan) if plan else set()
    pinned_set = {story_memory.coordinate(row) for row in pinned or ()}
    named = {(materials.field_of(kind), key) for kind, key in inputs | pinned_set}
    complete = allow_dependency_scope and _complete_dependencies(plan)
    selected, locations, link_ids = _spatial_scope(state, set(participants), plan, inputs | pinned_set)
    managed = set(CURRENT_FIELDS + HISTORY_FIELDS) | {
        'entities', 'placements', 'places', 'custody', 'arrivals', 'anchors', 'links',
        'hooks', 'thread_progress', 'story_nodes'}
    view = {key: copy.deepcopy(value) for key, value in state.items() if key not in managed}
    for field in ('entities', 'placements') + CURRENT_FIELDS:
        view[field] = {key: copy.deepcopy(value) for key, value in (state.get(field) or {}).items()
                       if materials.related(field, key, value, selected, named)}
    omitted = {}
    for field in HISTORY_FIELDS:
        rows = {}
        for key, value in (state.get(field) or {}).items():
            if not materials.related(field, key, value, selected, named):
                continue
            last = delta_ledger.last_chapter(delta_index, field, key)
            window = 2 if field == 'reader_knowledge' else near
            explicit = (field, key) in named
            if explicit or not complete:
                rows[key] = copy.deepcopy(value)
            elif field == 'developments':
                recent = [entry for entry in value
                          if (entry.get('evidence') or {}).get('chapter', entry.get('chapter', 0)) >= chapter - near]
                if recent:
                    rows[key] = copy.deepcopy(recent)
                if len(recent) < len(value):
                    omitted[field] = omitted.get(field, 0) + 1
            elif last >= chapter - window:
                rows[key] = copy.deepcopy(value)
            else:
                omitted[field] = omitted.get(field, 0) + 1
        view[field] = rows
    view['places'] = {key: copy.deepcopy(value) for key, value in state['places'].items()
                      if not complete or key in locations or ('places', key) in named}
    for field in ('custody', 'arrivals'):
        if field in state:
            view[field] = {key: copy.deepcopy(value) for key, value in state[field].items() if key in selected}
    if 'anchors' in state:
        view['anchors'] = {key: copy.deepcopy(value) for key, value in state['anchors'].items()
                           if key.split(':', 1)[0] in selected | locations}
    if 'links' in state:
        view['links'] = {key: copy.deepcopy(value) for key, value in state['links'].items()
                         if not complete or key in link_ids}
    view['hooks'] = {key: copy.deepcopy(value) for key, value in state['hooks'].items()
                     if ('hooks', key) in named or value.get('status') == 'open' and (
                         set(value.get('subjects') or []) & selected or value.get('due', chapter + 1) <= chapter)}
    if 'thread_progress' in state:
        view['thread_progress'] = {key: copy.deepcopy(value) for key, value in state['thread_progress'].items()
                                   if value.get('status') != 'resolved' or ('thread_progress', key) in named}
    if 'story_nodes' in state:
        nodes = _planned_nodes(plan) | {key for field, key in named if field == 'story_nodes'}
        view['story_nodes'] = {key: copy.deepcopy(value) for key, value in state['story_nodes'].items() if key in nodes}
    warnings = []
    if not complete:
        warnings.append({'code': 'conservative_projection', 'chapter': chapter,
                         'note': '场景依赖声明不完整，保守携带相关背景；当前状态、点名与常驻值均完整保留。',
                         'recover': '补齐 scenes[].reads/depends_on 后重新核验章纲。'})
    view['material_scope'] = {
        'mode': 'declared_dependencies' if complete else 'conservative', 'source': 'state',
        'near_window': near, 'far_omitted': omitted,
        'current_fields': list(CURRENT_FIELDS),
        'knowledge_boundary': 'knowledge 仅是所列人物的知情切片，reader_knowledge 仅是读者所知；未列话题不代表不知道。',
        'resolve': '补读目录见 recall_manifest；pipeline.catalog 可搜索和翻页，pipeline.resource 返回当前真值。'}
    if warnings:
        view['material_scope']['warnings'] = warnings
    return view, warnings


def drift_slice(book, plan, chapter, contract):
    """Select active design drift for the current chapter.

    当前卷未吸收记录必达；更早卷按参与者、钩子或显式引用匹配，已吸收或归档记录仅计数。"""
    rows = book.get('design_drift') or []
    volume = planning.volume_for(contract, chapter)
    participants = set(plan.get('participants') or [])
    hook_refs = set(plan.get('hook_refs') or [])
    named = set(plan.get('reader_refs') or []) | set(plan.get('history_refs') or [])
    active, archived, absorbing = [], 0, []
    for row in rows:
        if row.get('absorbed_by') or row.get('archived'):
            archived += 1
            continue
        row_volume = planning.volume_for(contract, row.get('chapter', 0)) if contract else None
        in_current = bool(volume and row_volume and row_volume.get('id') == volume.get('id'))
        overlap = bool(participants & set(row.get('participants') or [])
                       or hook_refs & set(row.get('hook_refs') or [])
                       or named & set(row.get('named_refs') or []))
        if in_current or overlap:
            active.append(row)
            absorbing.append(row.get('id'))
    return {'active': active, 'archived_count': archived, 'suggested_absorbs': absorbing,
            'rule': '当前卷未吸收无条件必达；更早卷未吸收按登记 id 交集或点名必达；已吸收归档不再出现。'}


def _style_archive(contract, frozen=None):
    """外部《文风档案.md》全文记录（作者提供；契约 style_source 登记）。"""
    if frozen is not None:
        return copy.deepcopy(frozen)
    with open(contract['style_source'], 'r', encoding='utf-8') as handle:
        content = handle.read()
    return {'path': contract['style_source'], 'content': content,
            'note': '外部文风档案（作者提供）：本档案是生效文风源，覆盖内置档注册锚；'
                    '档名登记仅作标识。默认每章必读，只有当前会话确认已加载此版本才可省略全文。'}


def freeze_style(contract):
    """Freeze the explicitly selected local profile or external archive, never a default."""
    if text(contract.get('style_source') or ''):
        return _style_archive(contract)
    profile = resolve_style_profile(contract.get('style_profile'))
    if profile is None:
        return None
    relative = STYLE_CATALOG[profile]['file']
    path = STYLE_ROOT / relative
    require(path.is_file(), 'style_profile', '所选内置文风档案缺失，不能仅凭数值锚执笔。', {'file': relative})
    content = path.read_text(encoding='utf-8')
    start, end = '<!-- dispatch:start -->', '<!-- dispatch:end -->'
    require(content.count(start) == 1 and content.count(end) == 1 and content.index(start) < content.index(end),
            'style_profile', '内置文风档案须包含唯一的执行摘要。', {'file': relative})
    guide = content.split(start, 1)[1].split(end, 1)[0].strip()
    require(guide, 'style_profile', '内置文风执行摘要不能为空。', {'file': relative})
    return {'path': relative, 'profile': profile, 'source_kind': 'builtin_catalog',
            'content': content, 'guide': guide}


def group_pack(book, store, volume_id, first, last):
    """Freeze shared contract, volume, style and projection material for a writing group.

    投影视角使用组首章纲，完整声明时按近窗与远窗选择，缺失时保守回退。"""
    plan0 = None
    for n in range(first, last + 1):
        candidate = (book.get('plans') or {}).get(str(n))
        if candidate is not None:
            plan0 = candidate
            break
    people = participants(plan0, book)
    near = book['contract'].get('near_window_chapters') or DEFAULTS['near_window_chapters']
    baseline, baseline_warnings = scoped_state(book['state'], book.get('delta_index') or {}, people,
                                               plan0, first, near=near,
                                               pinned=book['contract'].get('pinned') or ())
    external = text(book['contract'].get('style_source') or '')
    pack = {
        'contract': book['contract'],
        'style_volume_anchor': book.get('style_volume_anchor') or None,
        'style': {'profile': resolve_style_profile(book['contract'].get('style_profile')) or '',
                  'style_source': book['contract'].get('style_source') or '',
                  'source_kind': 'external_archive' if external else 'builtin_catalog'},
        'style_archive': _style_archive(book['contract'], book['style_archive']) if external else None,
        'style_guide': book['style_archive']['guide'] if book['style_archive'] and not external else None,
        'volume_outline': book.get('volumes_outline', {}).get(volume_id),
        'baseline_state': baseline,
        'baseline_warnings': baseline_warnings,
        'world_core': ({'premise': book['world']['premise'], 'rules': book['world']['rules']}
                       if book.get('world') else None),
        'open_hooks': {k: v for k, v in book['state'].get('hooks', {}).items() if v.get('status') == 'open'},
        'members': [first, last], 'volume': volume_id,
    }
    pack = copy.deepcopy(pack)
    pack['hash'] = store.document(pack)
    return pack


def require_style_selected(contract):
    """执笔链路的文风前置强制（2026-11-02 作者要求）：文风未显式选定（内置档名或外部档案
    路径）即拒绝，并列出可选项供主控拿去问作者——引擎不提问、不猜偏好、不用默认档放行。
    派工（build）与直提（pipeline.submit）两条路径共用本检查，绕过信封直提同样被拒。"""
    selected = text(contract.get('style_profile') or '') or text(contract.get('style_source') or '')
    require(selected, 'style_profile',
            '文风未选定：正文执笔前须作者本人显式选定文风（内置档名或外部《文风档案.md》路径），'
            '引擎不使用默认档放行。',
            {'status': 'style_not_selected', 'options': style_options_board()})


def build(book, store, chapter, group=None, *, cache=None):
    """Compile one chapter's frozen delta envelope from the ledger. Returns the validated work.

    默认每章材料自足；只有宿主明确提供当前 context_id 与已加载哈希，才省略可缓存全文。
    """
    book_state.require_current(book)
    contract = book['contract']
    plan = (book.get('plans') or {}).get(str(chapter))
    require(plan is not None, 'chapter_outline', '本章尚无已登记的章纲，不能执笔。', {'chapter': chapter})
    require_style_selected(contract)
    people = participants(plan, book)
    dependency_report = materials.dependencies(book, plan, people)
    volume = planning.volume_for(contract, chapter)
    near = contract.get('near_window_chapters') or DEFAULTS['near_window_chapters']
    pinned = contract.get('pinned') or []
    state_view, warnings = scoped_state(book['state'], book.get('delta_index') or {},
                                        people, plan, chapter,
                                        near=near, pinned=pinned,
                                        allow_dependency_scope=stage_allows_scope())
    records, required = {}, []
    context_id, loaded = materials.delivery_cache(cache)
    cached = {}

    def add(name, value, needed=True, cacheable=False):
        records[name] = store.document(value)
        if needed and cacheable and records[name] in loaded:
            cached[name] = records[name]
            return
        if needed and name not in required:
            required.append(name)

    members = (group or {}).get('members') or [chapter, chapter]
    is_group_head = chapter == members[0]
    group_hash = (group or {}).get('hash')
    if group is not None:
        require(members[0] <= chapter <= members[1] and group.get('volume') == volume['id'],
                'writing_batch', '本章不属于提供的写作组。')
        shared = store.read_document(group_hash)
        require(shared['members'] == members, 'writing_batch', '写作组范围与冻结组包不符。')
        # 组包是可寻址的可选背景，不代表当前会话已经加载了它。
        add('group_pack', {'ref': group_hash,
                           'note': '冻结组首时点背景，可按哈希补读；当前章以 core_context 和 state 为准。'}, False)
    add('core_context', materials.core(book, volume))
    add('dependencies', dependency_report)
    add('contract', contract, False)
    if book.get('style_volume_anchor'):
        add('style_volume_anchor', book['style_volume_anchor'], False)
    add('chapter_outline', plan)
    if volume is not None:
        volume_row = book.get('volumes_outline', {}).get(volume['id'])
        if volume_row is not None:
            add('volume_outline', volume_row, False)
            nodes = _planned_nodes(plan)
            threads = {row['thread'] for row in (plan.get('plot') or {}).get('threads') or []}
            volume_context = {key: volume_row[key] for key in ('id', 'purpose', 'arc', 'climax', 'exit_state', 'style')
                              if key in volume_row}
            volume_context['nodes'] = [row for row in volume_row.get('nodes') or [] if row['id'] in nodes]
            volume_context['threads'] = [row for row in volume_row.get('threads') or [] if row['id'] in threads]
            add('volume_context', volume_context, cacheable=True)
    add('state', state_view)
    add('recall_manifest', materials.catalog(book, plan, people, state_view,
                                           per=policy_default('far_reference_limit')))
    if warnings:
        add('projection_warnings', warnings)
    slice_ = drift_slice(book, plan, chapter, contract)
    if slice_['active']:
        add('design_drift', slice_)
    hook_rows = state_view.get('hooks', {})
    add('hooks', {'open': [{'id': k, 'text': v.get('text', ''), 'due': v.get('due')}
                           for k, v in sorted(hook_rows.items())],
                  'source': '到期承诺切片：open 且（本章 hook_refs 或参与者关联）；'
                            '完整承诺账由宿主经 history_source（各章 events）或 recall 倒排补读。'})
    if book.get('world') and plan:
        records_by_id = world.index(book['world'])
        selected_world = set(plan.get('world_refs', []))
        selected_world.update('characters:' + p for p in people if 'characters:' + p in records_by_id)
        todo = list(selected_world)
        while todo:
            ident = todo.pop()
            for ref in records_by_id[ident].get('links') or []:
                if ref not in selected_world:
                    selected_world.add(ref)
                    require(ref in records_by_id, 'context_dependencies', '世界依赖引用不存在。', {'key': ref})
                    todo.append(ref)
        visible = {k: records_by_id[k] for k in sorted(selected_world) if not k.startswith('mysteries:')}
        add('world_records', visible)
        topics = {row['topic'] for row in plan.get('disclosures') or []} | set(plan.get('reader_refs') or [])
        topics.update(key.split(':', 1)[-1] for kind, key in story_memory.reads(plan) if kind == 'knowledge')
        add('disclosure_boundary', {'allowed_changes': plan.get('disclosures', []),
                                    'author_secrets': [{'id': k.split(':', 1)[1], 'disclosure': v['disclosure'],
                                                        'causal_role': v['causal_role']}
                                                       for k, v in records_by_id.items()
                                                       if k.startswith('mysteries:')
                                                       and (k in selected_world or k.split(':', 1)[1] in topics)],
                                    'source': '幕后真相不下发；作者真相不能自动成为人物知情或本章披露。'})
    if contract.get('narrative_tracking') or 'word_budget' in plan:
        add('word_budget', narrative.budget_for(book, chapter))
    # 文风规格（作者要求：写章派工简报必须带所选档的文风规格）。
    # - style：每章必读的规格＋当前基线锚（与提交门比对同源）；
    # - style_anchor 是可选的注册锚背景，生效锚完整包含在 style 中；
    # - style_archive 默认每章必读，仅在明确的会话缓存确认下省略全文。
    spec = style_spec(book, store, volume, plan, chapter)
    add('style', spec)
    registered_anchor = style.baseline(book)
    if registered_anchor is not None:
        add('style_anchor', registered_anchor, False)  # 当前生效锚已完整包含在 style 中。
    if spec['source_kind'] == 'external_archive':
        add('style_archive', _style_archive(contract, book['style_archive']), cacheable=True)
    else:
        archive = book['style_archive']
        add('style_reference', archive, False)
        add('style_guide', {'profile': archive['profile'], 'file': archive['path'],
                            'content': archive['guide'],
                            'full_archive_ref': records['style_reference']}, cacheable=True)
    # L3：组内前章 delta（重放段）＋两类锚句＋跨章场景定义。
    if group is not None and not is_group_head:
        prior_deltas = []
        for n in range(members[0], chapter):
            row = store.chapter('main', n)
            if row is not None and row.get('delta'):
                prior_deltas.append({'chapter': n, 'delta': store.read_document(row['delta'])})
        if prior_deltas:
            add('previous_deltas', prior_deltas, False)
    prior = anchors.prior_anchors(book, store, plan, chapter)
    scene = anchors.scene_anchors(book, store, chapter)
    if prior['anchors'] or scene['anchors']:
        add('anchor_sentences', {'prior': prior, 'scene': scene,
                                 'note': '引用已内联、无需 recall；确需更长前文才用 recall/history_source 补读。'})
    references = {ident for scene_ in plan.get('scenes', []) for ident in scene_.get('depends_on', [])}
    local_ids = {s['id'] for s in plan.get('scenes', [])}
    external = references - local_ids
    if external:
        locations = {}
        for key, p in (book.get('plans') or {}).items():
            for s in p.get('scenes', []):
                locations[s['id']] = p['chapter']
        require(external <= set(locations), 'story_dependency', '场景依赖缺少前章来源，须补读或重新规划。')
        dependencies = []
        for n in sorted({locations[ident] for ident in external}):
            source_row = store.chapter('main', n)
            require(source_row is not None, 'context_dependencies', '依赖场景所在章节尚未提交。', {'chapter': n})
            source_plan = store.read_document(source_row['plan'])
            scenes = [s for s in source_plan.get('scenes', []) if s['id'] in external]
            dependencies.append({'chapter': n, 'scenes': scenes, 'plan_hash': store.chapter('main', n)['plan']})
        add('scene_sources', dependencies)
    # 前文窗口：默认 1 章全文（差量化降维），锚句补前窗语感。
    window = policy_default('adjacent_window_chapters')
    written = {row['n']: row for row in store.headers('main', first=max(1, chapter - window), last=chapter - 1)}
    previous = []
    for n in range(max(1, chapter - window), chapter):
        row = written.get(n)
        if row is None:
            continue
        name = 'previous_chapter:' + str(n)
        records[name] = row['prose']
        required.append(name)
        previous.append({'chapter': n, 'prose_hash': row['prose'], 'record': name, 'summary': row['summary']})
    add('previous_chapters', previous)
    add('history_source', {'head': store.chain_head(), 'chapters': store.last_chapter(),
                           'locate': '宿主按倒排定位（pipeline.recall）后取页下发；'
                                     '本记录不含页内容，Worker 不做历史翻页。'}, False)
    payload = {'chapter_outline': 'chapter_outline', 'worker_batch': bool(group is not None)}
    task = {'schema': TASK, 'stage': 'write', 'chapter': chapter, 'scope': 'chapter',
            'first': members[0], 'last': members[1], 'payload': payload, 'branch': book['branch'],
            'revision': book['revision'],
            'records': records, 'required': required,
            'narrative_tracking': bool(contract.get('narrative_tracking')),
            'capabilities': {'scene_identity': SCENE_IDENTITY_CAPABILITY,
                             'reading_dependencies': story_memory.READING_SCHEMA,
                             'volume_outline': VOLUME_OUTLINE_CAPABILITY,
                             'scene_memory': SCENE_MEMORY_CAPABILITY,
                             'hook_links': HOOK_LINKS_CAPABILITY},
            'policy': {'forbidden_terms': [], 'forbidden_name_chars': [], 'allowed_latin': [],
                       'note': '本项目未启用逐词字面约定检查。'},
            'warnings': warnings,
            'delivery': {'context_id': context_id, 'cached': cached,
                         'mode': 'acknowledged_cache' if cached else 'self_contained'}}
    if group is not None:
        task['group'] = {'hash': group_hash, 'members': members, 'head': members[0] == chapter}
    brief = briefs.write_brief(book, chapter, plan, {'prior': prior, 'scene': scene},
                               style_spec=spec)
    if brief:
        task['brief'] = brief
    return validate_work(task)


def stage_allows_scope():
    """lite 只有执笔环节：依赖声明裁剪对执笔生效。"""
    return True
