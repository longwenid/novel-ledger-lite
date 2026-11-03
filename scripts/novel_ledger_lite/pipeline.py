"""Independent writing pipeline: import, freeze outlines, dispatch, settle and audit.

安装门校验字段、引用与状态链；提交门核对增量、证据、前态、重复、文风与期限；
完本验收逐章全量重放，保存与重载使用本项目 JSON 格式。"""
from __future__ import annotations

import copy
from functools import wraps
import json
import os
from .contracts import (DEFAULTS, Error, digest, han_count, policy_default, require, text)
from .store import LiteStore, require_current_chapter
from . import (anchors, book_state, briefs, compose, contracts, craft, delta as delta_ledger,
               drift_reconcile, drift_validation, facts, lint, narrative, planning, style,
               story_memory, world, materials)


def _current_book(function):
    @wraps(function)
    def checked(book, *args, **kwargs):
        book_state.require_current(book)
        return function(book, *args, **kwargs)
    return checked


def open_book(contract_raw, source, world_model=None):
    """Validate the imported contract, seed the ledger, freeze the world if one is imported.

    文风口径（2026-11-02 作者要求收紧）：style_profile 选定档名逐字进契约（杜撰档名被
    契约 choices 校验拒绝）；缺失不落默认档——validate_contract 对 default=None 的字段不
    填充，契约保持「未选定」状态，开书放行、执笔派工与直提都被 require_style_selected 拒绝；
    style_source 登记外部档案路径，contracts 层无 I/O，存在性在这里校验。"""
    contract = planning.validate_contract(contract_raw)
    if text(contract.get('style_source') or ''):
        require(os.path.isfile(contract['style_source']), 'style_source',
                '外部文风档案不存在：style_source 须指向 作者确认的 UTF-8 Markdown 文风档案真实路径。',
                {'path': contract['style_source']})
    if world_model is not None:
        world.validate_shape(world_model)
    book = {
        'schema': contracts.SCHEMA, 'contract': contract, 'contract_source': source,
        'initial_contract': copy.deepcopy(contract), 'contract_changes': [], 'last_chapter': 0,
        'world': copy.deepcopy(world_model), 'branch': 'main', 'revision': 0, 'status': 'running',
        'style_archive': compose.freeze_style(contract),
        'state': facts.seed(contract), 'written_han': 0,
        'volumes_outline': {}, 'chapter_outlines': {}, 'plans': {},
        'design_drift': [], 'deltas': {},
        'delta_index': {}, 'inverted': {}, 'checkpoints': [], 'groups': [],
        'outline_protocol_checked': 0, 'style_volume_anchor': None, 'anchor_reviews': [],
        'volume_diffs': [], 'style_switch': {},
    }
    book_state.check_book(book)
    return book


@_current_book
def recontract_patch(book, source='', style_profile=None, style_source=None):
    """Change the selected style atomically from the next unwritten chapter.

    来源必填并保存前后契约。仅指定内置档会清除外部源；指定外部源时读取并冻结档案，
    两条路径均切割旧章文风基线，历史章行继续使用提交时的契约验链。"""
    require(text(source), 'contract', '换档须说明来源（作者原话或决定出处），逐版留档。')
    next_chapter = _next_chapter_of(book)
    candidate = dict(book)
    contract = copy.deepcopy(book['contract'])
    previous = contract.get('style_profile') or contract.get('style_source')
    if style_profile is not None:
        require(style_profile in contracts.STYLE_CATALOG, 'contract',
                '文风档名须取内置目录，缺失或杜撰拒绝。',
                {'valid': sorted(contracts.STYLE_CATALOG), 'got': style_profile})
        contract['style_profile'] = style_profile
        contract.pop('style_source', None)
    if style_source is not None:
        require(isinstance(style_source, str) and os.path.isfile(style_source), 'style_source',
                '外部文风档案不存在：style_source 须指向真实档案文件。', {'path': style_source})
        contract['style_source'] = style_source
    if style_profile is not None or style_source is not None:
        candidate['contract'] = contract
        candidate['style_archive'] = compose.freeze_style(contract)
        candidate['style_switch'] = {
            'at': next_chapter, 'profile': style_profile or contract.get('style_profile') or style_source,
            'previous': previous}
        candidate['contract_changes'] = list(book['contract_changes']) + [{
            'at': next_chapter, 'source': source,
            'before': copy.deepcopy(book['contract']), 'after': copy.deepcopy(contract)}]
    book_state.check_book(candidate)
    book.update(candidate)
    return {'style_profile': book['contract'].get('style_profile'),
            'style_source': book['contract'].get('style_source') or '',
            'switch': dict(book.get('style_switch') or {})}


def style_board():
    """可选项板面（给主控拿去问作者）：内置五档各一句话定位＋外部档案接入方法。
    引擎不提问、不猜偏好；作者显式选定后经契约 style_profile/style_source 或
    recontract_patch 写入，执笔派工才放行（compose.build 前置检查）。"""
    return contracts.style_options_board()


def _next_chapter_of(book):
    """换档从当前账本记录的下一待写章生效。"""
    return book['last_chapter'] + 1


# ------------------------------------------------------------------ outline gate
@_current_book
def install_outlines(book, volume_id, volume_row_outline, chapters_data):
    """Validate and atomically freeze one volume and its chapter outlines.

    先核对字段、引用、状态链与场景协议，再核对 absorbs 声明。全部通过后回写账本，
    失败时不修改已安装章纲或漂移吸收记录。"""
    contract = book['contract']
    volume = planning.volume_for(contract, _volume_first_chapter(contract, volume_id))
    require(volume is not None and volume.get('id') == volume_id, 'volume',
            '契约里没有这一卷。', {'volume': volume_id})
    policy = planning.resolve_outline_policy(contract, 'chapter_outline')
    for entry in volume_row_outline.get('hooks') or []:
        require(isinstance(entry, dict) and text(entry.get('id')) and text(entry.get('text'))
                and isinstance(entry.get('plant'), list) and isinstance(entry.get('payoff'), list),
                'volume_outline', '卷纲 hooks 每条须带 id/text/plant/payoff 窗口。',
                {'hook': entry.get('id') if isinstance(entry, dict) else None})
    # absorbs 是作者在章纲行上的吸收声明；机械门规范化只保留已登记键（CHAPTER_FIELDS/
    # PROTOCOL_FIELDS），所以提取发生在门前、回写发生在门后——声明与引擎行分离。
    absorb_map = {}
    for row in (chapters_data or {}).get('chapters') or []:
        absorbed = row.get('absorbs') or []
        require(isinstance(absorbed, list) and all(isinstance(a, str) for a in absorbed),
                'chapter_outline', 'absorbs 须为漂移登记 id 数组。', {'chapter': row.get('chapter')})
        absorb_map[row['chapter']] = absorbed
    rows = drift_validation.validate_chapter_outline(
        chapters_data, policy, {'first': volume['first'], 'end': volume['end']},
        volume_row_outline, book.get('world'), book['state'])
    entities = copy.deepcopy(book['state'].get('entities') or {})
    checked_through = book.get('outline_protocol_checked', 0)
    previous = {key: value for key, value in book['plans'].items()}
    drift_rows = copy.deepcopy(book.get('design_drift') or [])
    drift_by_id = {row['id']: row for row in drift_rows}
    for row in rows:
        for entry in row.get('new_entities') or []:
            facts.entity({'entities': entities}, entry)
        craft.scenes(row, entities)
        story_memory.bind(row, previous, checked_through=checked_through)
        previous[str(row['chapter'])] = row
        checked_through = max(checked_through, row['chapter'])
    absorbed_ids = set()
    for row in rows:
        for ident in absorb_map.get(row['chapter'], []):
            require(ident in drift_by_id, 'design_drift', '章纲吸收了不存在的漂移登记。',
                    {'chapter': row['chapter'], 'id': ident})
            target = drift_by_id[ident]
            require(not target.get('absorbed_by'), 'design_drift', '该漂移已被吸收，不得重复登记。',
                    {'id': ident, 'absorbed_by': target.get('absorbed_by')})
            target.setdefault('absorbed_by', []).append(row['chapter'])
            absorbed_ids.add(ident)
    candidate = dict(book)
    candidate['design_drift'] = drift_rows
    candidate['volumes_outline'] = {**book['volumes_outline'], volume_id: copy.deepcopy(volume_row_outline)}
    candidate['chapter_outlines'] = {**book['chapter_outlines'], volume_id: rows}
    candidate['plans'] = dict(book['plans'])
    for row in rows:
        candidate['plans'][str(row['chapter'])] = row
    candidate['outline_protocol_checked'] = checked_through
    book_state.check_book(candidate)
    book.update(candidate)
    return {'volume': volume_id, 'chapters': [row['chapter'] for row in rows],
            'absorbed': sorted(absorbed_ids)}


def _volume_first_chapter(contract, volume_id):
    volume = next((v for v in contract['volumes'] if v['id'] == volume_id), None)
    return volume['first'] if volume else 0


# ------------------------------------------------------------------ groups & envelopes
@_current_book
def group(book, store, volume_id, size=None):
    """Freeze the next writing group and its content-addressed shared material.

    每次调用接续下一段，卷范围已覆盖则拒绝；用 group_for 复用已有组。"""
    volume = next((v for v in book['contract']['volumes'] if v['id'] == volume_id), None)
    require(volume is not None, 'volume', '契约里没有这一卷。', {'volume': volume_id})
    size = size or policy_default('fast_batch_chapters')
    covered_through = max((row['members'][1] for row in book.get('groups') or []
                           if row.get('volume') == volume_id), default=volume['first'] - 1)
    first = covered_through + 1
    require(first <= volume['end'], 'writing_batch',
            '该卷已无可冻结的组范围：全卷章节已被已冻结组覆盖，不追加重复组。',
            {'volume': volume_id, 'covered_through': covered_through, 'end': volume['end'],
             'recover': '用 group_for(book, chapter) 取该章所在的已冻结组继续派工。'})
    last = min(first + size - 1, volume['end'])
    pack = compose.group_pack(book, store, volume_id, first, last)
    group_row = {'volume': volume_id, 'members': [first, last], 'hash': pack['hash'], 'pack': pack}
    book.setdefault('groups', []).append(group_row)
    book_state.check_book(book)
    return group_row


@_current_book
def group_for(book, chapter):
    """The frozen group a chapter belongs to, or None——复用已冻结组的唯一入口。"""
    for row in book.get('groups') or []:
        first, last = row['members']
        if first <= chapter <= last:
            return row
    return None


@_current_book
def envelope(book, store, chapter, group_row=None, *, cache=None):
    """The chapter's frozen delta envelope (compose.build), validated against the wire contract."""
    return compose.build(book, store, chapter, group_row, cache=cache)


def materialize(work, store, *, token_counter=None, tokenizer_id=None, cache=None):
    """得到实际派工文本与分项度量；只渲染一次必读内容，不重复内嵌章纲或可选背景。"""
    return materials.render(work, store, token_counter, tokenizer_id, cache)


@_current_book
def catalog(book, *, chapter=None, kind=None, query='', page=0, per=20):
    """搜索/翻页发现可补读资源，chapter 指定时限于本章相关资源。"""
    plan = book['plans'].get(str(chapter)) if chapter is not None else None
    require(chapter is None or plan is not None, 'context_catalog', '目录查询章节尚无已登记章纲。')
    people = compose.participants(plan, book) if plan else ()
    return materials.catalog(book, plan, people, kind=kind, query=query, page=page, per=per)


# ------------------------------------------------------------------ submit gate
@_current_book
def submit(book, store, chapter, draft):
    """Reconcile, settle, and advance the ledger by one chapter.

    draft: {title, prose, summary, self_check, drift_check}. findings 非空即拒绝候选
    （书不变）；通过则原子推进：状态、delta、投影索引、倒排、章行链哈希、组内锚句原料、
    卷界 checkpoint＋差异单＋文风卷首锚回比。
    """
    require(type(chapter) is int and chapter == store.last_chapter() + 1,
            'chapter_order', '章节必须连续顺序提交。', {'chapter': chapter})
    require(all(text(draft.get(k)) for k in ('title', 'summary', 'self_check')), 'draft',
            '执笔需要 title/summary/self_check。')
    prose = draft.get('prose')
    require(text(prose), 'draft', '正文须非空。')
    plan = book['plans'].get(str(chapter))
    require(plan is not None, 'chapter_outline', '本章尚无已登记的章纲，不能执笔。', {'chapter': chapter})
    # 文风前置强制在直提路径同样成立：绕过 envelope 直接 submit 不能让未选定状态落账。
    compose.require_style_selected(book['contract'])
    settlement = drift_reconcile.reconcile(draft.get('drift_check'), plan, book['state'],
                                           book.get('world'), prose=prose)
    findings = list(settlement['findings'])
    contract = book['contract']
    band = (narrative.budget_for(book, chapter) if contract.get('narrative_tracking')
            else {'minimum': contract['chapter_min'], 'maximum': contract['chapter_max']})
    count = han_count(prose)
    if not band['minimum'] <= count <= band['maximum']:
        findings.append({'criterion': 'substance', 'severity': 'quality', 'target_chapter': chapter,
                         'repair_scope': 'chapter',
                         'reason': '汉字篇幅不在本章区间：用增加事件补足，不以描写或重复注水。',
                         'actual_han': count, 'allowed': [band['minimum'], band['maximum']]})
    priors = store.headers('main', first=max(1, chapter - lint.DUPLICATE_WINDOW), last=chapter - 1)
    prior_prose = [(row['n'], store.prose_page(row['n'])) for row in priors]
    findings.extend(lint.draft_findings(prose, prior_prose, chapter))
    volume = planning.volume_for(contract, chapter)
    volume_style = ((book.get('volumes_outline') or {}).get(volume['id']) or {}).get('style') \
        if volume else None
    recent = [(n, style.metrics(sample)) for n, sample in reversed(prior_prose)]
    style_report = style.examine(prose, plan.get('style'),
                                 style.current_anchor(book, recent),
                                 style.merged_window(contract, volume_style), chapter,
                                 contract=contract)
    findings.extend(style_report['findings'])
    if findings:
        return {'ok': False, 'chapter': chapter, 'findings': findings}
    raw_events = facts.prepare_hook_links(settlement['events'])
    try:
        state, events = facts.settle(book['state'], raw_events, prose, chapter)
    except Error as error:
        # settle 阶段的引擎拒绝（引文逐字、到期拦截、前值硬核）转回可读 findings：
        # 候选不通过、账本不变；错误码保留为 criterion，便于按模板修正。
        return {'ok': False, 'chapter': chapter,
                'findings': [{'criterion': error.code, 'severity': 'blocker',
                              'target_chapter': chapter, 'repair_scope': 'chapter',
                              'reason': error.message, 'details': error.details}]}
    expected_days = (plan.get('clock') or {}).get('advance_days')
    if type(expected_days) is int:
        require(state['clock'] - book['state']['clock'] == expected_days, 'elapsed_days',
                '正文推进的天数与章纲声明不一致。',
                {'planned': expected_days, 'settled': state['clock'] - book['state']['clock']})
    require(all(p in state['entities'] for p in plan.get('participants', [])), 'entity_coverage',
            '章纲参与人尚无已核验的正文身份。')
    row = {'n': chapter, 'title': draft['title'], 'prose': store.document(prose),
           'events': store.document(events), 'plan': store.document(plan),
           'review': {'drift_check': copy.deepcopy(draft.get('drift_check')),
                      'design_drift': copy.deepcopy(settlement['deviations']),
                      'self_check': draft['self_check'], 'style_report': copy.deepcopy(style_report)},
           'state_hash': digest(state), 'summary': draft['summary'], 'han': count}
    contract_hash = store.document(contract)
    delta = delta_ledger.produce(book['state'], state, events, chapter)
    # L3 delta 随章行入链（派生数据；真源 events 已入链，delta 只服务近窗分级与组内重放段）。
    row['delta'] = store.document(delta)
    row = store.put_chapter(row, contract_hash)
    book['deltas'][str(chapter)] = delta
    delta_ledger.bump_index(book['delta_index'], delta)
    for asset, pages in delta['inverted'].items():
        book['inverted'].setdefault(asset, [])
        for page in pages:
            if page not in book['inverted'][asset]:
                book['inverted'][asset].append(page)
    book['state'] = state
    book['last_chapter'] = chapter
    book['written_han'] += count
    volume_boundary = None
    if volume is not None and chapter == volume['end']:
        volume_boundary = _volume_boundary(book, volume)
    elif chapter % (contract.get('checkpoint_chapters') or DEFAULTS['checkpoint_chapters']) == 0:
        _checkpoint(book, chapter, None)
    _style_anchor_review(book, chapter)
    book_state.check_book(book)
    return {'ok': True, 'chapter': chapter, 'row': row, 'delta': delta,
            'volume_boundary': volume_boundary}


def _checkpoint(book, through, volume_id):
    book.setdefault('checkpoints', []).append(
        delta_ledger.checkpoint(book['state'], through, volume_id))
    return book['checkpoints'][-1]


def _volume_boundary(book, volume):
    """卷界：全量 checkpoint＋差异单（伏笔结余/漂移吸收率/文风锚偏离）——作者审阅面从
    「全书」压缩到「每卷一页」。required/sealed 通道（方案三补丁 a）在这里显式列出
    封线承诺的结余，不再等完本才暴露。"""
    checkpoint = _checkpoint(book, volume['end'], volume['id'])
    outline = book.get('volumes_outline', {}).get(volume['id']) or {}
    declared = {entry.get('id'): entry for entry in outline.get('hooks') or [] if isinstance(entry, dict)}
    required_unpaid, open_continues = [], []
    for ident, hook in sorted((book['state'].get('hooks') or {}).items()):
        entry = declared.get(ident) or {}
        if hook.get('status') != 'paid' and entry.get('required') and (entry.get('payoff') or [0, 0])[1] <= volume['end']:
            required_unpaid.append(ident)
        if hook.get('status') == 'open':
            open_continues.append(ident)
    drift_rows = book.get('design_drift') or []
    total = len(drift_rows)
    absorbed = len([row for row in drift_rows if row.get('absorbed_by')])
    diff = {'volume': volume['id'], 'end': volume['end'], 'checkpoint': checkpoint['state_hash'],
            'required_unpaid': required_unpaid, 'open_continues': open_continues,
            'drift': {'total': total, 'absorbed': absorbed,
                      'rate': (absorbed / total) if total else None},
            'written_han': book['written_han']}
    book.setdefault('volume_diffs', []).append(diff)
    return diff


def _style_anchor_review(book, chapter):
    """文风卷首锚（方案三补丁 b）：首个 checkpoint 冻结锚点；此后每 anchor_review_chapters
    章回比一次（observation 级，只报告不拦截）。"""
    cadence = book['contract'].get('anchor_review_chapters') or DEFAULTS['anchor_review_chapters']
    if book.get('style_volume_anchor') is None:
        if book.get('checkpoints'):
            book['style_volume_anchor'] = {'frozen_at': book['checkpoints'][0]['through'],
                                           'state_hash': book['checkpoints'][0]['state_hash']}
        return None
    if chapter - book['style_volume_anchor']['frozen_at'] < cadence:
        return None
    review = {'chapter': chapter, 'basis': '卷首锚（冻结于第 %d 章 checkpoint）' % book['style_volume_anchor']['frozen_at'],
              'note': 'observation：滚动基线与卷首锚的偏离只报告不拦截；'
                      '作者判断是自然演进还是跟漂，需要收紧时改 style_guard=strict 并重锚。'}
    book.setdefault('anchor_reviews', []).append(review)
    return review


# ------------------------------------------------------------------ recall / status / audit
@_current_book
def resource(book, kind, key):
    """按显式坐标补读当前账本真值；历史提示被省略不代表资源不存在。"""
    field, key = ('places', key) if kind == 'place_records' else story_memory.coordinate({'kind': kind, 'key': key})
    field = 'story_nodes' if field == 'node' else field
    if field == 'clock':
        found, value = True, book['state']['clock']
    else:
        rows = book['state'].get(field) or {}
        found, value = key in rows, rows.get(key)
    return {'kind': field, 'key': key, 'found': found, 'value': copy.deepcopy(value),
            'last_chapter': delta_ledger.last_chapter(book.get('delta_index') or {}, field, key)}


@_current_book
def recall(book, store, asset):
    """倒排定位→取页（方案三补丁 c）。无匹配 O(1)——索引 miss 直接空返回，不再线性翻页。"""
    pages = (book.get('inverted') or {}).get(asset) or []
    hits = []
    for n in pages:
        for event in store.events_page(n):
            entity = event.get('entity')
            ident = event.get('id') or event.get('topic') \
                or (entity.get('id') if isinstance(entity, dict) else entity)
            if asset == ident or asset == event.get('id') or asset == event.get('topic'):
                hits.append({'chapter': n, 'event': event})
    return {'chapters': list(pages), 'hits': hits}


@_current_book
def status(book, store, page=0, per=20):
    """Return ledger totals and one page of submitted chapter summaries."""
    require(page >= 0 and per > 0, 'chapter', '分页参数须为非负/正。')
    rows = store.headers('main')
    window = rows[page * per:(page + 1) * per]
    return {'status': book['status'], 'written': len(rows), 'written_han': book['written_han'],
            'chapters': [{'n': row['n'], 'title': row['title'], 'han': row['han'],
                          'state_hash': row['state_hash']} for row in window],
            'page': page, 'pages': (len(rows) + per - 1) // per,
            'drift': {'active': len([r for r in book.get('design_drift') or [] if not r.get('absorbed_by')]),
                      'archived': len([r for r in book.get('design_drift') or [] if r.get('absorbed_by')])},
            'checkpoints': len(book.get('checkpoints') or []),
            'groups': [{'members': g['members'], 'hash': g['hash']} for g in book.get('groups') or []]}


@_current_book
def verify_full(book, store):
    """完本验收＝全量重放（默认，语义不变）：逐章 events 重放核对投影哈希，逐章重算链哈希。

    核对契约章节覆盖、真源文档内容哈希、正文证据与期限、逐章投影和链哈希、最终账本
    一致性及未清承诺。每章只按明确记录的提交时契约验链；delta 不参与验收。
    """
    initial_contract = book['initial_contract']
    state = facts.seed(initial_contract)
    problems = []
    previous_chain = None
    rows = store.headers('main')
    expected_end = book['contract']['volumes'][-1]['end']
    if len(rows) != expected_end:
        problems.append({'kind': 'incomplete', 'detail': '已提交章数未覆盖契约的全部章节。',
                         'expected': expected_end, 'actual': len(rows)})
    for expected_number, row in enumerate(rows, 1):
        try:
            require_current_chapter(row)
        except Error as error:
            problems.append({'chapter': expected_number, 'kind': 'format', 'code': error.code,
                             'detail': error.message})
            break
        if row['n'] != expected_number:
            problems.append({'chapter': row['n'], 'kind': 'chapter_order', 'detail': '章节不连续。'})
        contract_hash = row['contract_hash']
        try:
            prose = store.read_document(row['prose'])
            events = store.read_document(row['events'])
            store.read_document(row['plan'])
            store.read_document(contract_hash)
        except Error as error:
            problems.append({'chapter': row['n'], 'kind': 'record', 'detail': error.message,
                             'code': error.code})
            break
        try:
            state, _ = facts.settle(state, events, prose, row['n'])
        except Error as error:
            problems.append({'chapter': row['n'], 'kind': 'replay', 'detail': error.message})
            break
        if digest(state) != row['state_hash']:
            problems.append({'chapter': row['n'], 'kind': 'state_hash',
                             'detail': '重放投影与章行 state_hash 不符。'})
        expected_chain = digest({'previous': previous_chain, 'contract': contract_hash,
                                 **{k: row[k] for k in ('n', 'prose', 'events', 'plan', 'review', 'state_hash')}})
        if row.get('chain') != expected_chain:
            problems.append({'chapter': row['n'], 'kind': 'chain', 'detail': '链哈希重算不符。'})
        previous_chain = row.get('chain')
    if previous_chain != store.chain_head():
        problems.append({'kind': 'chain_head', 'detail': '链头与已提交章节不符。'})
    matches_book = digest(state) == digest(book['state'])
    if not matches_book:
        problems.append({'kind': 'book_state', 'detail': '全量重放结果与当前账本状态不符。'})
    unpaid_required = [ident for ident, hook in (state.get('hooks') or {}).items()
                       if hook.get('status') != 'paid']
    return {'ok': not problems and not unpaid_required,
            'chapters': len(rows), 'problems': problems,
            'unpaid_hooks': unpaid_required,
            'final_state_hash': digest(state),
            'matches_book': matches_book}


# ------------------------------------------------------------------ persistence
@_current_book
def save(book, store, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(json.dumps({'schema': contracts.BUNDLE_SCHEMA, 'book': book, 'store': store.to_dict()}, ensure_ascii=False, sort_keys=True))


def load(path):
    with open(path, 'r', encoding='utf-8') as handle:
        raw = json.loads(handle.read())
    require(isinstance(raw, dict) and raw.get('schema') == contracts.BUNDLE_SCHEMA,
            'bundle_schema', '仅支持当前持久化文件格式。', {'expected': contracts.BUNDLE_SCHEMA})
    require(set(raw) == {'schema', 'book', 'store'}, 'bundle_schema', '持久化文件字段不符合当前格式。')
    book = raw['book']
    book_state.check_book(book)
    store = LiteStore.from_dict(raw['store'])
    require(book['last_chapter'] == store.last_chapter(), 'book_state',
            '账本进度与已提交章节不符，不自动修正。')
    for group_row in book['groups']:
        pack = store.read_document(group_row['hash'])
        embedded = {key: value for key, value in group_row['pack'].items() if key != 'hash'}
        require(pack == embedded and group_row['pack']['hash'] == group_row['hash'],
                'writing_batch', '冻结组包与已存文档不符，不自动补建。')
    return book, store
