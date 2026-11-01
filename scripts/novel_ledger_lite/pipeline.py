"""lite pipeline: contract → outline gate (frozen resources) → delta envelope → submit gate →
settle → delta/checkpoint advance → volume diff → full replay verification.

最小完整闭环「章纲资源冻结→快速执笔」的编排层。机械防线的必要子集全部保留且判定对象
不变（完整版报告 §3.0）：
- 章纲安装门＝完整版同源的 validate_chapter_outline（链模拟 simulate）＋story_memory.bind；
- 提交门＝drift_reconcile.reconcile（逐增量覆盖比对、前态引擎投影）＋引文逐字＋8 章重复
  lint＋文风代理＋settle 前值硬核＋到期拦截；
- 完本验收＝全量重放为默认（lite 不实现分段/抽样——报告 §5.7 落选机制的 lite 侧执行）。
"""
from __future__ import annotations

import copy
import json
import os
from .contracts import (DEFAULTS, Error, digest, han_count, policy_default, require, text)
from .store import LiteStore
from . import (anchors, book_state, briefs, compose, contracts, craft, delta as delta_ledger,
               drift_reconcile, drift_validation, facts, lint, narrative, planning, style,
               story_memory, world)


def open_book(contract_raw, source, world_model=None):
    """Validate the imported contract, seed the ledger, freeze the world if one is imported.

    文风口径与完整版同源：style_profile 选定档名逐字进契约（杜撰档名被契约 choices 校验拒绝，
    缺失由 validate_contract 落默认档）；style_source 登记外部档案路径，contracts 层无 I/O，
    存在性在这里校验（开书即拒绝指向不存在文件的契约）。"""
    contract = planning.validate_contract(contract_raw)
    if text(contract.get('style_source') or ''):
        require(os.path.isfile(contract['style_source']), 'style_source',
                '外部文风档案不存在：style_source 须指向 style-distill 产出的《文风档案.md》真实路径。',
                {'path': contract['style_source']})
    if world_model is not None:
        world.validate_shape(world_model)
    book = {
        'schema': contracts.SCHEMA, 'contract': contract, 'contract_source': source,
        'world': world_model, 'branch': 'main', 'revision': 0, 'status': 'running',
        'state': facts.seed(contract), 'written_han': 0,
        'volumes_outline': {}, 'chapter_outlines': {}, 'plans': {},
        'design_drift': [], 'deltas': {},
        'delta_index': {}, 'inverted': {}, 'checkpoints': [], 'groups': [],
        'outline_protocol_checked': 0, 'style_volume_anchor': None, 'anchor_reviews': [],
        'volume_diffs': [], 'style_switch': {},
    }
    book_state.check_book(book)
    return book


def recontract_patch(book, source='', style_profile=None, style_source=None):
    """参数级换档（完整版 recontract --patch 的 lite 引擎实现）。

    - style_profile：须取内置目录档名，杜撰拒绝；换档点记入 book['style_switch'] =
      {at, profile, previous}——新档自 at 章起生效，之前章节保留原档文风，既不按新档
      判定也不进新档滚动基线（style.switch_cutoff/current_anchor 的既有语义自动生效）。
    - style_source：外部文风档案路径，须真实存在；与内置档二选一，登记后生效源为外部档案
      （style_profile 保留作标识）。传 None 表示不改动该参数。
    - source 必填：换档是作者决定，决定必须留原话（逐版留档口径与完整版 lexical 同族）。
    """
    require(text(source), 'contract', '换档须说明来源（作者原话或决定出处），逐版留档。')
    next_chapter = _next_chapter_of(book)
    if style_profile is not None:
        require(style_profile in contracts.STYLE_CATALOG, 'contract',
                '文风档名须取内置目录，缺失或杜撰拒绝。',
                {'valid': sorted(contracts.STYLE_CATALOG), 'got': style_profile})
        previous = book['contract'].get('style_profile')
        book['contract']['style_profile'] = style_profile
        book['style_switch'] = {'at': next_chapter, 'profile': style_profile, 'previous': previous}
    if style_source is not None:
        require(isinstance(style_source, str) and os.path.isfile(style_source), 'style_source',
                '外部文风档案不存在：style_source 须指向真实档案文件。', {'path': style_source})
        book['contract']['style_source'] = style_source
    book_state.check_book(book)
    return {'style_profile': book['contract'].get('style_profile'),
            'style_source': book['contract'].get('style_source') or '',
            'switch': dict(book.get('style_switch') or {})}


def style_board():
    """可选项板面（给主控拿去问作者）：内置五档各一句话定位＋外部档案接入方法。
    引擎不提问、不猜偏好；作者显式选定后经契约 style_profile/style_source 或
    recontract_patch 写入，执笔派工才放行（compose.build 前置检查）。"""
    return contracts.style_options_board()


def _chapter_rows_of(book):
    rows = []
    for outlines in (book.get('chapter_outlines') or {}).values():
        rows.extend(outlines or [])
    return rows


def _next_chapter_of(book):
    """换档点的「下一章」：已冻结章纲的最大章号＋1；无章纲时从第 1 章起。"""
    numbers = [row.get('chapter') for row in _chapter_rows_of(book)]
    return max([n for n in numbers if type(n) is int] or [0]) + 1


# ------------------------------------------------------------------ outline gate
def install_outlines(book, volume_id, volume_row_outline, chapters_data):
    """The chapter-outline mechanical gate: freeze the volume's resources for writing.

    卷纲行先登记（承诺窗口形状轻校验），章纲数据过完整版同源机械门
    （drift_validation.validate_chapter_outline：章号连续覆盖、增量形状、enter/exit 链、
    simulate 全卷状态链模拟、卷末终值）→ 逐行 craft.scenes＋story_memory.bind（协议水位
    增量复核）→ plans/chapter_outlines 登记。设计漂移的吸收回写在此核对：
    章纲行 `absorbs` 点名的漂移 id 必须存在且未吸收，吸收即登记 absorbed_by。
    """
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
    drift_by_id = {row['id']: row for row in book.get('design_drift') or []}
    for row in rows:
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
    book['volumes_outline'][volume_id] = volume_row_outline
    book['chapter_outlines'][volume_id] = rows
    for row in rows:
        book['plans'][str(row['chapter'])] = row
    book['outline_protocol_checked'] = checked_through
    book_state.check_book(book)
    return {'volume': volume_id, 'chapters': [row['chapter'] for row in rows],
            'absorbed': sorted(absorbed_ids)}


def _volume_first_chapter(contract, volume_id):
    volume = next((v for v in contract['volumes'] if v['id'] == volume_id), None)
    return volume['first'] if volume else 0


# ------------------------------------------------------------------ groups & envelopes
def group(book, store, volume_id, size=None):
    """Freeze one writing group: scope, hash baseline, group-level shared pack.

    组冻结时点＝组首章派工前；组内逐章由引擎重跑组装（每章信封现编现冻——内容寻址冻结
    纪律与完整版同一性质）。同卷同范围已有活跃组则复用，不重复冻结。
    """
    volume = next((v for v in book['contract']['volumes'] if v['id'] == volume_id), None)
    require(volume is not None, 'volume', '契约里没有这一卷。', {'volume': volume_id})
    size = size or policy_default('fast_batch_chapters')
    first = volume['first']
    for existing in book.get('groups') or []:
        if existing.get('volume') == volume_id and existing['members'][1] < volume['end']:
            first = existing['members'][1] + 1
    last = min(first + size - 1, volume['end'])
    require(first <= last, 'writing_batch', '该卷已无可冻结的组范围。', {'volume': volume_id})
    pack = compose.group_pack(book, store, volume_id, first, last)
    group_row = {'volume': volume_id, 'members': [first, last], 'hash': pack['hash'], 'pack': pack}
    book.setdefault('groups', []).append(group_row)
    book_state.check_book(book)
    return group_row


def envelope(book, store, chapter, group_row=None):
    """The chapter's frozen delta envelope (compose.build), validated against the wire contract."""
    return compose.build(book, store, chapter, group_row)


# ------------------------------------------------------------------ submit gate
def submit(book, store, chapter, draft):
    """Reconcile, settle, and advance the ledger by one chapter.

    draft: {title, prose, summary, self_check, drift_check}. findings 非空即拒绝候选
    （书不变）；通过则原子推进：状态、delta、投影索引、倒排、章行链哈希、组内锚句原料、
    卷界 checkpoint＋差异单＋文风卷首锚回比。
    """
    require(all(text(draft.get(k)) for k in ('title', 'summary', 'self_check')), 'draft',
            '执笔需要 title/summary/self_check。')
    prose = draft.get('prose')
    require(text(prose), 'draft', '正文须非空。')
    plan = book['plans'].get(str(chapter))
    require(plan is not None, 'chapter_outline', '本章尚无已登记的章纲，不能执笔。', {'chapter': chapter})
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
    recent = [(n, style.metrics(sample)) for n, sample in prior_prose]
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
    contract_hash = digest(contract)
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


def status(book, store, page=0, per=20):
    """项目状态摘要＋已提交章行分页（完整版报告附带项：status --tasks 分页在 lite 落地）。"""
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


def verify_full(book, store):
    """完本验收＝全量重放（默认，语义不变）：逐章 events 重放核对投影哈希，逐章重算链哈希。

    delta 是派生数据，验收不依赖它——重放直接吃链上 events（报告 §5.4-B：数据零丢失）。
    """
    state = facts.seed(book['contract'])
    problems = []
    previous_chain = None
    contract_hash = digest(book['contract'])
    rows = store.headers('main')
    for row in rows:
        try:
            for event in store.read_document(row['events']):
                facts.apply_event(state, event, row['n'])
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
    unpaid_required = [ident for ident, hook in (state.get('hooks') or {}).items()
                       if hook.get('status') != 'paid']
    return {'ok': not problems and not unpaid_required,
            'chapters': len(rows), 'problems': problems,
            'unpaid_hooks': unpaid_required,
            'final_state_hash': digest(state),
            'matches_book': digest(state) == digest(book['state'])}


# ------------------------------------------------------------------ persistence
def save(book, store, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(json.dumps({'book': book, 'store': store.to_dict()}, ensure_ascii=False, sort_keys=True))


def load(path):
    with open(path, 'r', encoding='utf-8') as handle:
        raw = json.loads(handle.read())
    return raw['book'], LiteStore.from_dict(raw['store'])
