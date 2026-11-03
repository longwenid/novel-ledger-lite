"""Content-addressed immutable documents and ordered chapter rows.

写入隔离可变对象，读取校验内容哈希。章行连续提交并关联契约哈希，
headers(first,last) 用保序索引读取指定窗口。存储为内存结构，可保存为 JSON。"""
from __future__ import annotations

import bisect
import copy
import json
import os
from .contracts import STORE_SCHEMA, digest, require

CHAPTER_FIELDS = frozenset(('n', 'title', 'prose', 'events', 'plan', 'review', 'state_hash',
                            'summary', 'han', 'delta', 'contract_hash', 'chain'))


def require_current_chapter(row):
    require(isinstance(row, dict) and set(row) == CHAPTER_FIELDS, 'store_schema',
            '章行字段须符合当前格式，必须携带提交时契约哈希。')
    return row


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
        if key not in self._documents:
            self._documents[key] = copy.deepcopy(value)
        return key

    def read_document(self, key):
        require(key in self._documents, 'record', '文档不存在或已越界。', {'record': key})
        value = self._documents[key]
        require(digest(value) == key, 'record_hash', '文档内容与内容寻址哈希不符。', {'record': key})
        return copy.deepcopy(value)

    # ---------------------------------------------------------------- chapters
    def put_chapter(self, row, contract_hash):
        """Install one committed chapter row; the chain head advances only by n+1."""
        n = row['n']
        require(type(n) is int and n >= 1, 'chapter', '章号须为正整数。')
        require(n not in self._chapters, 'chapter_order', '章节已存在，不可覆盖历史。',
                {'chapter': n})
        require(n == self.last_chapter() + 1, 'chapter_order', '章节必须连续顺序提交。', {'chapter': n})
        previous = self._chain_heads.get('main')
        row = copy.deepcopy(row)
        row['contract_hash'] = contract_hash
        row['chain'] = digest({'previous': previous, 'contract': contract_hash,
                               **{k: row[k] for k in ('n', 'prose', 'events', 'plan', 'review', 'state_hash')}})
        self._chapters[n] = row
        bisect.insort(self._order, n)
        self._chain_heads['main'] = row['chain']
        return copy.deepcopy(row)

    def chapter(self, branch, n):
        require(branch == 'main', 'branch', 'lite 只保留单主线。')
        return self._chapters.get(n)

    def last_chapter(self):
        return self._order[-1] if self._order else 0

    def count(self, branch):
        require(branch == 'main', 'branch', 'lite 只保留单主线。')
        return len(self._order)

    def headers(self, branch, first=None, last=None):
        """Return chapter rows in an optional bounded window using the ordered index."""
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
        return {'schema': STORE_SCHEMA, 'documents': self._documents,
                'chapters': {str(n): row for n, row in self._chapters.items()},
                'chain_heads': dict(self._chain_heads)}

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True))

    @classmethod
    def from_dict(cls, raw):
        require(isinstance(raw, dict) and raw.get('schema') == STORE_SCHEMA, 'store_schema',
                '仅支持当前存储格式。', {'expected': STORE_SCHEMA})
        require(set(raw) == {'schema', 'documents', 'chapters', 'chain_heads'}
                and all(isinstance(raw[key], dict) for key in ('documents', 'chapters', 'chain_heads')),
                'store_schema', '存储字段须符合当前格式。')
        store = cls()
        store._documents = copy.deepcopy(raw['documents'])
        for key, row in raw['chapters'].items():
            require_current_chapter(row)
            require(type(row['n']) is int and row['n'] >= 1 and key == str(row['n']),
                    'store_schema', '存储章号与章行不符。')
            require(all(row[field] in store._documents for field in ('prose', 'events', 'plan', 'delta', 'contract_hash')),
                    'store_schema', '章行引用的当前格式文档缺失。', {'chapter': row['n']})
            store._chapters[row['n']] = copy.deepcopy(row)
        store._order = sorted(store._chapters)
        require(store._order == list(range(1, len(store._order) + 1)), 'store_schema', '存储章节须连续。')
        store._chain_heads = dict(raw['chain_heads'])
        expected = {'main': store._chapters[store.last_chapter()]['chain']} if store._order else {}
        require(store._chain_heads == expected, 'store_schema', '存储链头与章行不符。')
        return store

    @classmethod
    def load(cls, path):
        with open(path, 'r', encoding='utf-8') as handle:
            return cls.from_dict(json.loads(handle.read()))
