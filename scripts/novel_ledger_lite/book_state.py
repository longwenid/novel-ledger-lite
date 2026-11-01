"""Invariants every lite state transition must leave behind.

完整版 book_state.check_state 的 lite 子集，另加差量化自己的两条形状校验：
- design_drift 行的 participants 必须是登记 id（完整版报告 §4.3-2/§6.1-6：漂移行
  声明缺失或错 id 时活跃切片的 id 交集会失效、可能漏收旧漂移——安装门在这里拦住）；
- delta/checkpoint/倒排三类派生结构的形状（损坏在 rebuild/verify_full 暴露，这里拦畸形）。
"""
from __future__ import annotations

from .contracts import require, text

STATUSES = ('preparing', 'running', 'paused', 'completed')
DRIFT_BASE_FIELDS = ('id', 'chapter', 'kind', 'key', 'reason')


def check_book(book):
    """Shape invariants; the command that breaks them is the command that reports them."""
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
        require(isinstance(group, dict) and isinstance(group.get('members'), list)
                and isinstance(group.get('hash'), str),
                'book_state', '组冻结须带 members 与 hash。')
    switch = book.get('style_switch') or {}
    require(isinstance(switch, dict) and (not switch
                                          or (type(switch.get('at')) is int and switch['at'] >= 1
                                              and text(switch.get('profile'))
                                              and (switch.get('previous') is None
                                                   or text(switch.get('previous'))))),
            'book_state', '换档点须为 {at, profile, previous}（此前未选过档时 previous 可为空）。',
            {'switch': sorted(switch)})
    return book
