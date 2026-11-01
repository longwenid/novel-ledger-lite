"""lite storage: content-addressed documents, chapter rows, bounded header reads.

对应完整版架构报告第一刀的两处引擎修复在 lite 的落地形态：
- 章号保序索引（bisect）：headers(first, last) 是 O(log N＋窗口) 的真窗口读取，
  不做全表排序——完整版 sqlite_store.py:444-456 是无窗口全表扫描，被前文窗、
  重复窗、status 多处 O(N) 调用；lite 的调用方拿不到无界结果集（status 走
  count＋窗口分页）。
- 章行携带链哈希与投影哈希（verification.replay 的核对对象），delta/checkpoint
  （delta.py）以章行为真源重建，delta 本身不新增哈希机制。
- 无界快照不存在：完整版 context.py:934 每次派工把整份页链快照（含每章 summary）
  写进任务记录，随书龄平方增长；lite 的信封只携带 O(1) 的 L4 指针
  （compose.build 的 history_source），取页由宿主经 recall/events_page 执行。

文档按内容寻址（digest→值）一次入库不可变；同一章纲重排产生新文档键，不覆盖历史。
"""
from __future__ import annotations

import bisect
import json
import os
from .contracts import digest, require


class LiteStore:
    """In-memory repository with optional JSON persistence. Sources are immutable."""

    def __init__(self):
        self._documents = {}
        self._chapters = {}
        self._order = []            # 保序章号索引（put_chapter 经 bisect 插入，保持升序）
        self._chain_heads = {}

    # ---------------------------------------------------------------- documents
    def document(self, value):
        """Content address; storing is implicit and idempotent."""
        key = digest(value)
        self._documents.setdefault(key, value)
        return key

    def read_document(self, key):
        require(key in self._documents, 'record', '文档不存在或已越界。', {'record': key})
        return self._documents[key]

    # ---------------------------------------------------------------- chapters
    def put_chapter(self, row, contract_hash):
        """Install one committed chapter row; the chain head advances only by n+1."""
        n = row['n']
        require(type(n) is int and n >= 1, 'chapter', '章号须为正整数。')
        require(n not in self._chapters, 'chapter_order', '章节已存在，不可覆盖历史。',
                {'chapter': n})
        previous = self._chain_heads.get('main')
        row = dict(row)
        row['chain'] = digest({'previous': previous, 'contract': contract_hash,
                               **{k: row[k] for k in ('n', 'prose', 'events', 'plan', 'review', 'state_hash')}})
        self._chapters[n] = row
        bisect.insort(self._order, n)
        self._chain_heads['main'] = row['chain']
        return row

    def chapter(self, branch, n):
        require(branch == 'main', 'branch', 'lite 只保留单主线。')
        return self._chapters.get(n)

    def last_chapter(self):
        return self._order[-1] if self._order else 0

    def count(self, branch):
        require(branch == 'main', 'branch', 'lite 只保留单主线。')
        return len(self._order)

    def headers(self, branch, first=None, last=None):
        """Chapter rows in one bounded window: O(log N＋窗口) over the ordered index.

        无窗口参数的调用面不存在——status 以 count＋窗口分页取数，前文窗/重复窗
        各自带界。这是 lite 对完整版 headers 全表扫描的结构性替代。
        """
        require(branch == 'main', 'branch', 'lite 只保留单主线。')
        lo = bisect.bisect_left(self._order, first if first is not None else 1)
        hi = bisect.bisect_right(self._order, last) if last is not None else len(self._order)
        return [self._chapters[n] for n in self._order[lo:hi]]

    def chain_head(self):
        return self._chain_heads.get('main')

    def events_page(self, n):
        row = self._chapters.get(n)
        return self.read_document(row['events']) if row else []

    def prose_page(self, n):
        row = self._chapters.get(n)
        return self.read_document(row['prose']) if row else ''

    # ---------------------------------------------------------------- persistence
    def to_dict(self):
        return {'documents': self._documents,
                'chapters': {str(n): row for n, row in self._chapters.items()},
                'chain_heads': dict(self._chain_heads)}

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True))

    @classmethod
    def from_dict(cls, raw):
        store = cls()
        store._documents = {key: value for key, value in raw['documents'].items()}
        store._chapters = {int(n): row for n, row in raw['chapters'].items()}
        store._order = sorted(store._chapters)
        store._chain_heads = dict(raw['chain_heads'])
        return store

    @classmethod
    def load(cls, path):
        with open(path, 'r', encoding='utf-8') as handle:
            return cls.from_dict(json.loads(handle.read()))
