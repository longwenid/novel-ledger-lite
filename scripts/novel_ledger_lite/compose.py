"""The delta-envelope compiler: every chapter's writing context assembled from the five-layer
ledger (L0-L4), as a frozen, content-addressed work input.

五层账本（完整版架构报告 §3.1）在 lite 的组装规则——这是组装规则，不是新存储引擎：
- L0 恒定层   契约＋文风锚（内置档锚/卷首锚）；全书冻结一次，组级共享包携带。
- L1 卷层     本卷卷纲行＋活跃 hooks 切片；每卷一次。
- L2 章层     章纲行＋索引化状态投影（近窗全文/远窗标题行/pinned/点名整条恢复）＋
              design_drift 活跃切片＋本章 world_records 切片；每章差量信封主体。
- L3 差量层   组内前章 state_delta＋两类锚句＋scene_sources；下章组装原料。
- L4 历史层   页链 history_source＋倒排指针；recall 降为兜底通道。

信封在该章派工时点现编现冻（前章正文与事件已提交、哈希已在链上）；每份信封仍是
内容寻址冻结物。差量化不改变任何机械门的判定对象——省的是材料搬运字节，不是校验强度。
"""
from __future__ import annotations

import copy
import json
from .contracts import (DEFAULTS, HOOK_LINKS_CAPABILITY, READING_DEPENDENCIES_CAPABILITY,
                        SCENE_IDENTITY_CAPABILITY, SCENE_MEMORY_CAPABILITY, TASK,
                        VOLUME_OUTLINE_CAPABILITY, digest, policy_default, require,
                        resolve_style_profile, style_options_board, text)
from . import anchors, briefs, delta as delta_ledger, narrative, planning, story_memory, style, world
from .envelope import validate_work


def json_holder(key):
    """资源坐标 [holder, asset, unit] 的持有者段；畸形键按无持有者处理。"""
    try:
        return json.loads(key)[0]
    except Exception:
        return None


def participants(plan, book):
    """Who is on stage this chapter, from the row itself rather than a profile table
    （完整版 context._participants 的 lite 同源实现）。

    章纲未声明参与者时保守回落全实体——保守方向必须是「多带材料」，绝不静默收窄。"""
    if plan:
        named = plan.get('participants')
        if isinstance(named, list) and named:
            return list(named)
        found = []
        for row in plan.get('characters') or []:
            if isinstance(row, dict) and text(row.get('entity')) and row['entity'] not in found:
                found.append(row['entity'])
        for row in plan.get('new_entities') or []:
            if isinstance(row, dict) and text(row.get('id')) and row['id'] not in found:
                found.append(row['id'])
        for row in (plan.get('knowledge') or []) + (plan.get('places') or []):
            if isinstance(row, dict):
                ident = row.get('who') or row.get('entity')
                if text(ident) and ident not in found:
                    found.append(ident)
        if found:
            return found
    return list(book['state']['entities'])

# Stages lite freezes. lite 的范围是「章纲资源冻结→快速执笔」：章纲经安装门直接冻结进
# 账本（机械门＝完整版同源的 validate_chapter_outline/bind/链模拟），设计派工不在 lite。
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
    """Keep declared locations plus the custody, route and parent chains that make them true.

    与完整版 context._spatial_scope 同一实现语义：仅在完整依赖声明下调用；
    partial 声明保留全部空间背景——缺席不证明无关。
    """
    people = set(participants)
    people.update(key for kind, key in inputs
                  if kind in ('entities', 'placements', 'character_current', 'developments'))
    people.update(key.split(':', 1)[0] for kind, key in inputs if kind in ('facts', 'knowledge'))
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
    """The style specification one dispatch writes against（完整版 context.style_material 的
    lite 同口径渲染）：契约声线字段＋生效档名（或外部档案源）＋当前基线锚＋合并容差
    ＋卷走向＋本章执行点。基线是最近 5 章已提交正文的滚动中位（style.STYLE_BASELINE_WINDOW，
    引擎自己重算——信封里写进的就是提交门将比对的同一组数字）。"""
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


# 历史态条目字段：按「近窗全文 / 远窗标题行」分级（投影索引化）。
HISTORY_FIELDS = ('facts', 'knowledge', 'resources', 'relations', 'historical_assertions',
                  'developments', 'reader_knowledge', 'character_current')
# 身份与当前态字段：恒全文——身份登记表是登记制引用的基础；站位/持有/拓扑是当前态
# 不是历史；活跃线路与承诺是活义务。分级只对历史态条目生效。
PRESENT_FIELDS = ('entities', 'placements', 'places', 'hooks', 'thread_progress', 'story_nodes',
                  'custody', 'arrivals', 'anchors', 'links', 'clock_threads')


def _title_row(field, key, value, last_chapter):
    """远窗标题行：一行坐标与末次变更章，不携带值——完整值仍可按 L4 补读。"""
    return {'_ref': True, 'last_chapter': last_chapter}


def scoped_state(state, delta_index, participants, plan, chapter, *, near=None, pinned=(),
                 allow_dependency_scope=True):
    """The indexed projection: near-window full entries, far-window title rows, pinned and
    named entries restored whole, conservative fallback with an explicit warning.

    三道保险（完整版报告 §4.3 第三层）在此逐字落地：
    - 点名整条恢复：章纲 reads/hook_refs/history_refs/reader_refs 点名的条目永远带全文；
    - pinned 常驻：作者标记的条目（契约 pinned 行 {kind,key}）永远带全文；
    - 声明缺失时保留 conservative 全量并显式告警（采完整版报告方案三立场，不静默裁剪）：
      漏标从「多付 token」退回「多付 token＋被看见」，成本上界＝完整版 partial 路径本身。
    """
    plan = plan or {}
    near = near if near is not None else policy_default('near_window_chapters')
    inputs = story_memory.reads(plan) if plan else set()
    named = set(inputs)
    named.update(('hooks', ident) for ident in plan.get('hook_refs', []))
    named.update(('reader_knowledge', ident) for ident in plan.get('reader_refs', []))
    named.update(('historical_assertions', ident) for ident in plan.get('history_refs', []))
    pinned_set = {(row.get('kind'), row.get('key')) for row in pinned or ()}
    warnings = []
    complete = allow_dependency_scope and _complete_dependencies(plan)
    if not complete:
        # conservative：参与人相关全量（＝完整版 partial 路径），另加显式告警。
        selected = set(participants)
        view = copy.deepcopy(state)
        for field in ('entities', 'placements', 'developments'):
            view[field] = {k: v for k, v in state[field].items() if k in selected}
        view['facts'] = {k: v for k, v in state['facts'].items() if k.split(':', 1)[0] in selected}
        view['knowledge'] = {k: v for k, v in state['knowledge'].items() if k.split(':', 1)[0] in selected}
        view['resources'] = {k: v for k, v in state['resources'].items()
                             if k.startswith('[') and k and json_holder(k) in selected}
        view['relations'] = {k: v for k, v in state['relations'].items()
                             if k.split('>')[0] in selected or k.split('>')[1].split(':')[0] in selected}
        view['hooks'] = {k: v for k, v in state['hooks'].items()
                         if v.get('status') == 'open' and (k in plan.get('hook_refs', [])
                                                           or selected.intersection(v.get('subjects', [])))}
        view['material_scope'] = {'mode': 'conservative', 'source': 'state',
                                  'note': '场景依赖声明不完整，参与人的全部知情与状态资料已随本 state 记录全量携带；'
                                          '未声明不视为无关。'}
        warnings.append({'code': 'conservative_projection',
                         'chapter': chapter,
                         'note': '章纲未给完整场景依赖声明（dependency_coverage=complete＋逐场 reads），'
                                 '状态投影回退 conservative 全量——补齐声明可恢复差量信封的薄投影。',
                         'recover': '补写本章 scenes[].reads/depends_on 后重新冻结章纲。'})
        view['material_scope']['warnings'] = list(warnings)
        return view, warnings
    view = copy.deepcopy(state)
    selected, locations, link_ids = _spatial_scope(state, set(participants), plan, inputs)
    # 身份与当前态：参与人相关恒全文。
    for field in ('entities', 'placements', 'developments'):
        view[field] = {k: v for k, v in state[field].items() if k in selected}
    # 历史态条目：近窗全文 / 远窗标题行 / pinned 与点名整条恢复。
    for field in HISTORY_FIELDS:
        source = state.get(field, {})
        rows = {}
        for key, value in source.items():
            holder = key.split(':', 1)[0] if field in ('facts', 'knowledge') else None
            if field in ('facts', 'knowledge') and holder not in selected \
                    and (field, key) not in named and (field, key) not in pinned_set:
                continue
            if field == 'reader_knowledge' and key not in named:
                last = delta_ledger.last_chapter(delta_index, field, key)
                if last < chapter - 2 and (field, key) not in pinned_set:
                    rows[key] = _title_row(field, key, value, last)
                    continue
            if field == 'historical_assertions' and key not in named:
                subjects = set(value.get('subjects') or [])
                if not subjects & selected and (field, key) not in pinned_set:
                    continue
            if field in ('facts', 'knowledge', 'resources', 'relations', 'developments', 'reader_knowledge',
                         'character_current'):
                last = delta_ledger.last_chapter(delta_index, field, key)
                # last==0（从未被 settle 更新的初始态）按远窗处理：初始设定若被远窗裁成
                # 标题行，作者应以 pinned 显式常驻——「30 章未提即失忆」的机械堵法。
                if last >= chapter - near or (field, key) in pinned_set or (field, key) in named:
                    rows[key] = copy.deepcopy(value)
                else:
                    rows[key] = _title_row(field, key, value, last)
            else:
                rows[key] = copy.deepcopy(value)
        view[field] = rows
    # 空间完整保留（完整声明路径），与完整版一致。
    view['places'] = {k: v for k, v in state['places'].items() if k in locations}
    for field in ('custody', 'arrivals'):
        if field in state:
            view[field] = {k: v for k, v in state[field].items() if k in selected}
    if 'anchors' in state:
        view['anchors'] = {k: v for k, v in state['anchors'].items()
                           if k.split(':', 1)[0] in selected | locations}
    if 'links' in state:
        view['links'] = {k: v for k, v in state['links'].items() if k in link_ids}
    view['hooks'] = {k: v for k, v in state['hooks'].items()
                     if v.get('status') == 'open' and (k in plan.get('hook_refs', [])
                                                       or selected.intersection(v.get('subjects', [])))}
    if 'thread_progress' in state:
        view['thread_progress'] = {k: v for k, v in state['thread_progress'].items()
                                   if v.get('status') != 'resolved'}
    if 'story_nodes' in state:
        nodes = _planned_nodes(plan)
        view['story_nodes'] = {k: v for k, v in state['story_nodes'].items() if k in nodes}
    view['material_scope'] = {
        'mode': 'declared_dependencies', 'source': 'state',
        'near_window': near,
        'note': '知情与事实按近窗索引选择：近窗条目全文、远窗标题行、pinned 与章纲点名条目整条恢复；'
                '站位、持有链、移动路径及父地点完整保留。标题行条目的完整值由宿主经 group_pack（组基线投影）'
                '或 history_source（页链→各章 events）/recall 补读下发，未选不代表不存在。'}
    return view, warnings


def drift_slice(book, plan, chapter, contract):
    """design_drift 活跃切片（完整版报告 §4.3-2 判定规则，登记制 id 交集）：

    ①当前卷内未吸收 → 无条件必达；
    ②更早卷未吸收 → 仅当 id 交集（参与者/钩子引用），或被该章 reader_refs/history_refs
      点名 → 必达；
    ③已吸收（absorbed_by）或已归档（archived）→ 归档，切片不再出现（只有计数指针）。
    误漏边界：漂移行 participants 声明缺失/错 id 时交集失效可能漏收旧漂移——安装门
    已对 participants 做登记 id 形状校验（book_state.check_book），残余归声明质量风险。
    """
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


def _style_archive(contract):
    """外部《文风档案.md》全文记录（style-distill 产出；契约 style_source 登记）。"""
    with open(contract['style_source'], 'r', encoding='utf-8') as handle:
        content = handle.read()
    return {'path': contract['style_source'], 'content': content,
            'note': '外部文风档案（style-distill 产出）：本档案是生效文风源，覆盖内置档注册锚；'
                    '档名登记仅作标识。组内续章经组包引用补读，不每章重复携带。'}


def group_pack(book, store, volume_id, first, last):
    """组级共享包（完整版报告第五刀，方案二「每组一份」）：L0/L1＋投影基线＋文风卷首锚
    ＋外部文风档案全文（外部源时）＋世界核心＋活跃 hooks 基线。组冻结时点＝组首章派工前；
    组内其余章差量引用本包。基线投影以组首章的章纲为视角：首章声明完整则走索引化
    （近窗/远窗/pinned/点名），声明缺失则 conservative 全量（与该章自己的信封同口径）。"""
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
        'style_archive': _style_archive(book['contract']) if external else None,
        'volume_outline': book.get('volumes_outline', {}).get(volume_id),
        'baseline_state': baseline,
        'baseline_warnings': baseline_warnings,
        'world_core': ({'premise': book['world']['premise'], 'rules': book['world']['rules']}
                       if book.get('world') else None),
        'open_hooks': {k: v for k, v in book['state'].get('hooks', {}).items() if v.get('status') == 'open'},
        'members': [first, last], 'volume': volume_id,
    }
    pack['hash'] = digest(pack)
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


def build(book, store, chapter, group=None):
    """Compile one chapter's frozen delta envelope from the ledger. Returns the validated work.

    组语义：group 为 None 或组内首章 → L0/L1/基线内嵌信封（必读）；组内非首章 → 只带
    组包引用（可选读）＋组内前章 delta＋L2 章层差量——组内均摊随章数递减，字节与书龄无关。
    """
    contract = book['contract']
    plan = (book.get('plans') or {}).get(str(chapter))
    require(plan is not None, 'chapter_outline', '本章尚无已登记的章纲，不能执笔。', {'chapter': chapter})
    require_style_selected(contract)
    volume = planning.volume_for(contract, chapter)
    near = contract.get('near_window_chapters') or DEFAULTS['near_window_chapters']
    pinned = contract.get('pinned') or []
    state_view, warnings = scoped_state(book['state'], book.get('delta_index') or {},
                                        participants(plan, book), plan, chapter,
                                        near=near, pinned=pinned,
                                        allow_dependency_scope=stage_allows_scope())
    records, required = {}, []

    def add(name, value, needed=True):
        records[name] = store.document(value)
        if needed and name not in required:
            required.append(name)

    members = (group or {}).get('members') or [chapter, chapter]
    is_group_head = chapter == members[0]
    group_hash = (group or {}).get('hash')
    head_or_solo = group is None or is_group_head
    if not head_or_solo:
        # 组内续章：L0/L1 以组包引用形式在场（可选读，不重复计费）；章层照常全带。
        add('group_pack', {'ref': group_hash,
                           'note': '组级共享包（契约/卷纲/投影基线/文风卷首锚/外部文风档案全文）已随组首章交付；'
                                   '本章上下文只带差量。需要完整基线或档案全文时按此引用补读。'}, False)
    else:
        add('contract', contract)
        if book.get('style_volume_anchor'):
            # 文风卷首锚（首个 checkpoint 后冻结）：L0 件，组首章随契约一并交付。
            add('style_volume_anchor', book['style_volume_anchor'])
    add('chapter_outline', plan)
    if volume is not None:
        volume_row = book.get('volumes_outline', {}).get(volume['id'])
        if volume_row is not None:
            add('volume_outline', volume_row, is_group_head or group is None)
    add('state', state_view)
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
        people = plan.get('participants') or []
        selected_world.update('characters:' + p for p in people if 'characters:' + p in records_by_id)
        todo = list(selected_world)
        while todo:
            ident = todo.pop()
            for ref in records_by_id[ident].get('links') or []:
                if ref not in selected_world:
                    selected_world.add(ref)
                    if not contract.get('narrative_tracking'):
                        todo.append(ref)
        visible = {k: records_by_id[k] for k in sorted(selected_world) if not k.startswith('mysteries:')}
        add('world_records', visible)
        add('disclosure_boundary', {'allowed_changes': plan.get('disclosures', []),
                                    'author_secrets': [{'id': k.split(':', 1)[1], 'disclosure': v['disclosure'],
                                                        'causal_role': v['causal_role']}
                                                       for k, v in records_by_id.items()
                                                       if k.startswith('mysteries:')],
                                    'source': '幕后真相不下发；作者真相不能自动成为人物知情或本章披露。'})
    if contract.get('narrative_tracking'):
        add('word_budget', narrative.budget_for(book, chapter))
    # 文风规格（作者要求：写章派工简报必须带所选档的文风规格）。
    # - style：每章必读的规格＋当前基线锚（与提交门比对同源）；
    # - style_anchor：内置档注册锚（style.baseline；外部源且无档名时为 None 则不登记）；
    # - style_archive：外部《文风档案.md》全文只在组首章（或无组时）内嵌必读，组内续章经
    #   组包引用补读——与 L0 的组级均摊纪律一致，不每章重复携带整份档案。
    spec = style_spec(book, store, volume, plan, chapter)
    add('style', spec)
    registered_anchor = style.baseline(book)
    if registered_anchor is not None:
        add('style_anchor', registered_anchor)
    if spec['source_kind'] == 'external_archive' and head_or_solo:
        add('style_archive', _style_archive(contract))
    # L3：组内前章 delta（重放段）＋两类锚句＋跨章场景定义。
    if group is not None and not is_group_head:
        prior_deltas = []
        for n in range(members[0], chapter):
            row = store.chapter('main', n)
            if row is not None and row.get('delta'):
                prior_deltas.append({'chapter': n, 'delta': store.read_document(row['delta'])})
        if prior_deltas:
            add('previous_deltas', prior_deltas)
    prior = anchors.prior_anchors(book, store, plan, chapter)
    scene = anchors.scene_anchors(book, store, chapter)
    if prior['anchors'] or scene['anchors']:
        add('anchor_sentences', {'prior': prior, 'scene': scene,
                                 'note': '引用已内联、无需 recall；确需更长前文才用 recall/history_source 补读。'})
    # scene_sources：跨章场景定义整条携带（完整版同语义：从已提交章纲中取被依赖场景行）。
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
            source_plan = store.read_document(store.chapter('main', n)['plan'])
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
    # L4 只进指针，不进页内容：完整版 context.py:934 每次派工把整份页链快照
    # （含每章 summary）写进任务记录，随书龄平方增长（500 章逐章冻结累计百 MB 级）。
    # lite 的信封携带 O(1) 寻址头；取页由宿主按倒排定位后经 store 取页下发
    # （pipeline.recall），Worker 不翻历史页。
    add('history_source', {'head': store.chain_head(), 'chapters': store.last_chapter(),
                           'locate': '宿主按倒排定位（pipeline.recall）后取页下发；'
                                     '本记录不含页内容，Worker 不做历史翻页。'}, False)
    payload = {'chapter_outline': plan, 'worker_batch': bool(group is not None)}
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
                       'note': 'lite 项目不设字面约定门；完整版 lexical 协议不复制。'},
            'warnings': warnings}
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
