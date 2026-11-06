"""Shape invariants for each ledger transition.

漂移行参与者必须使用已登记实体 ID；校验增量索引、checkpoint、组记录与换档结构。"""
from __future__ import annotations

from .contracts import SCHEMA, require, text

STATUSES = ('preparing', 'running', 'paused', 'completed')
DRIFT_BASE_FIELDS = ('id', 'chapter', 'kind', 'key', 'reason')
BOOK_FIELDS = frozenset(('schema', 'contract', 'contract_source', 'initial_contract', 'contract_changes',
    'last_chapter', 'world', 'branch', 'revision', 'status', 'style_archive', 'state', 'written_han',
    'volumes_outline', 'chapter_outlines', 'plans', 'design_drift', 'deltas', 'delta_index', 'inverted',
    'checkpoints', 'groups', 'outline_protocol_checked', 'style_volume_anchor', 'anchor_reviews',
    'volume_diffs', 'style_switch'))


def require_current(book):
    """Accept only the current book shape; never infer missing fields or upgrade old data."""
    require(isinstance(book, dict) and book.get('schema') == SCHEMA, 'book_schema',
            '仅支持当前账本格式。', {'expected': SCHEMA})
    require(set(book) == BOOK_FIELDS, 'book_schema', '账本字段须符合当前格式。',
            {'missing': sorted(BOOK_FIELDS - set(book)), 'unknown': sorted(set(book) - BOOK_FIELDS)})
    require(isinstance(book['contract'], dict) and isinstance(book['initial_contract'], dict)
            and isinstance(book['state'], dict) and isinstance(book['contract_changes'], list)
            and type(book['last_chapter']) is int and book['last_chapter'] >= 0,
            'book_schema', '初始契约、变更记录与提交进度字段不符合当前格式。')
    archive = book['style_archive']
    require(archive is None or isinstance(archive, dict) and isinstance(archive.get('path'), str)
            and isinstance(archive.get('content'), str), 'book_schema', '冻结文风档案字段不符合当前格式。')
    require(not book['contract'].get('style_source') or archive is not None,
            'book_schema', '外部文风源必须已有冻结档案，不从文件补建。')
    if book['contract'].get('style_profile') and not book['contract'].get('style_source'):
        require(isinstance(archive, dict) and archive.get('profile') == book['contract']['style_profile']
                and archive.get('source_kind') == 'builtin_catalog' and text(archive.get('guide')),
                'book_schema', '所选内置文风须已有冻结档案与执行摘要，不从缺失字段补建。')
    return book


def check_book(book):
    """Shape invariants; the command that breaks them is the command that reports them."""
    require_current(book)
    status = book.get('status')
    require(status in STATUSES, 'book_state', '未知的项目状态。', {'status': status, 'known': list(STATUSES)})
    require(isinstance(book.get('state'), dict), 'book_state', '状态投影缺失。')
    require(type(book.get('written_han')) is int and book['written_han'] >= 0, 'book_state',
            '累计汉字数须为非负整数。')
    require(isinstance(book.get('plans'), dict), 'book_state', '章纲登记缺失。')
    for chapter, plan in book['plans'].items():
        require(str(chapter).isdigit() and type(plan.get('chapter')) is int,
                'book_state', '章纲登记须按章号保存。', {'chapter': chapter})
    for volume_id, outline in (book.get('volumes_outline') or {}).items():
        require(isinstance(outline, dict) and outline.get('id') == volume_id
                and isinstance(outline.get('nodes'), list) and isinstance(outline.get('threads'), list),
                'book_state', '卷纲登记须按卷 ID 保存完整行。', {'volume': volume_id})
    drift_ids = set()
    for row in book.get('design_drift') or []:
        require(isinstance(row, dict) and text(row.get('id')) and text(row.get('kind'))
                and text(row.get('key')) and text(row.get('reason'))
                and type(row.get('chapter')) is int, 'book_state',
                '与章纲不符的登记项必须带 id、章号、坐标与理由。',
                {'row': sorted(row) if isinstance(row, dict) else None})
        require(row['id'] not in drift_ids, 'book_state', '设计漂移登记 id 重复。', {'id': row['id']})
        drift_ids.add(row['id'])
        unknown = sorted(set(row.get('participants') or []) - set(book['state'].get('entities') or {}))
        require(not unknown, 'book_state',
                '设计漂移行的 participants 须为已登记实体 id；声明缺失会让活跃切片的 id 交集失效。',
                {'id': row['id'], 'unknown': unknown})
        absorbed = row.get('absorbed_by') or []
        require(isinstance(absorbed, list) and all(type(n) is int for n in absorbed),
                'book_state', '漂移吸收记录须为章号数组。', {'id': row['id']})
        require(row.get('archived') in (None, True), 'book_state', '归档标记只能是 true 或缺省。')
    require(isinstance(book.get('delta_index') or {}, dict), 'book_state', '投影索引缺失或损坏。')
    require(isinstance(book.get('inverted') or {}, dict), 'book_state', '倒排索引缺失或损坏。')
    for row in book.get('checkpoints') or []:
        require(isinstance(row, dict) and type(row.get('through')) is int
                and isinstance(row.get('state'), dict) and isinstance(row.get('state_hash'), str),
                'book_state', 'checkpoint 须为 {through, state, state_hash}。')
    for group in book.get('groups') or []:
        require(isinstance(group, dict) and set(group) == {'volume', 'members', 'hash', 'pack'}
                and isinstance(group['members'], list) and len(group['members']) == 2
                and isinstance(group['hash'], str) and isinstance(group['pack'], dict)
                and group['pack'].get('hash') == group['hash'],
                'book_state', '组冻结须使用当前 volume/members/hash/pack 完整结构。')
    switch = book.get('style_switch') or {}
    require(isinstance(switch, dict) and (not switch
                                          or (type(switch.get('at')) is int and switch['at'] >= 1
                                              and text(switch.get('profile'))
                                              and (switch.get('previous') is None
                                                   or text(switch.get('previous'))))),
            'book_state', '换档点须为 {at, profile, previous}（此前未选过档时 previous 可为空）。',
            {'switch': sorted(switch)})
    return book
