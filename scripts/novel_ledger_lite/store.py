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
PACKAGED_STORE_SCHEMA = 'novel-ledger-lite.store/3'
REVIEWED_STORE_SCHEMA = 'novel-ledger-lite.store/4'


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
        self._package_heads = {}
        self._review_heads = {}

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

    def latest_chapter_package(self, chapter):
        """Return the last issued single-file packet, retained in ordinary documents.

        These preparation records survive save/load without changing ledger or
        chapter schemas. A regenerated identical packet keeps its reference.
        """
        records = [(key, value) for key, value in self._documents.items()
                   if isinstance(value, dict)
                   and value.get('schema') == 'novel-ledger-lite.issued-package/1'
                   and value.get('chapter') == chapter]
        head = self._package_heads.get(chapter)
        require(bool(records) == (head is not None), 'chapter_package_record',
                '写作包签发记录或持久引用已丢失；拒绝退回无包提交。')
        checked = []
        for key, _ in records:
            record = self.read_document(key)
            require(set(record) == {'schema', 'chapter', 'source_hash', 'content_hash', 'previous', 'sequence', 'dependencies'}
                    and type(record['chapter']) is int and record['chapter'] >= 1
                    and type(record['sequence']) is int and record['sequence'] >= 1
                    and all(isinstance(record[field], str) and len(record[field]) == 64
                            and all(char in '0123456789abcdef' for char in record[field])
                            for field in ('source_hash', 'content_hash')),
                    'chapter_package_record', '写作包签发记录不完整或版本链断裂。')
            dependencies = record['dependencies']
            require(isinstance(dependencies, list)
                    and all(isinstance(item, str) for item in dependencies)
                    and dependencies == sorted(set(dependencies)),
                    'chapter_package_record', '写作包来源依赖记录损坏。')
            for reference in dependencies:
                self.read_document(reference)
            checked.append((key, record))
        previous = None
        for number, (key, record) in enumerate(sorted(checked, key=lambda item: item[1]['sequence']), 1):
            require(record['sequence'] == number
                    and record['previous'] == (previous[0] if previous else None),
                    'chapter_package_record', '写作包签发记录不完整或版本链断裂。')
            previous = (key, record)
        require(previous is None or previous[0] == head, 'chapter_package_record',
                '写作包签发引用与版本链不一致。')
        return previous

    def record_chapter_package(self, chapter, source_hash, content_hash, *, dependencies=None):
        """Bind a dispatch to this store before a writer receives its text."""
        latest = self.latest_chapter_package(chapter)
        dependencies = sorted(set(dependencies or []))
        for reference in dependencies:
            self.read_document(reference)
        if latest and all(latest[1][field] == value for field, value in
                          (('source_hash', source_hash), ('content_hash', content_hash),
                           ('dependencies', dependencies))):
            return latest[0]
        record = {'schema': 'novel-ledger-lite.issued-package/1', 'chapter': chapter,
                  'source_hash': source_hash, 'content_hash': content_hash, 'dependencies': dependencies,
                  'previous': latest[0] if latest else None,
                  'sequence': latest[1]['sequence'] + 1 if latest else 1}
        reference = self.document(record)
        self._package_heads[chapter] = reference
        return reference

    def latest_content_review(self, chapter):
        """Read the retained review chain, including rejection of an older approval."""
        from .content_review import read_record
        reference = self._review_heads.get(chapter)
        latest, seen = None, set()
        expected_sequence = None
        while reference is not None:
            require(reference not in seen, 'content_review_record', '审读记录链循环。')
            seen.add(reference)
            row, _, _ = read_record(self, reference)
            require(row['chapter'] == chapter and
                    (expected_sequence is None or row['sequence'] == expected_sequence),
                    'content_review_record', '审读版本链不连续或章号不符。')
            if latest is None:
                latest = (reference, row)
            expected_sequence = row['sequence'] - 1
            reference = row['previous']
        require(expected_sequence in (None, 0), 'content_review_record', '审读版本链前缀丢失。')
        retained = {key for key, value in self._documents.items() if isinstance(value, dict)
                    and value.get('schema') == 'novel-ledger-lite.content-review/1'
                    and value.get('chapter') == chapter}
        require(retained == seen, 'content_review_record',
                '审读持久引用遗漏或回退了已登记报告，不能沿用旧通过结论。')
        return latest

    def put_content_review(self, row):
        reference = self.document(row)
        self._review_heads[row['chapter']] = reference
        return reference

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
        schema = REVIEWED_STORE_SCHEMA if self._review_heads else PACKAGED_STORE_SCHEMA if self._package_heads else STORE_SCHEMA
        result = {'schema': schema, 'documents': self._documents,
                'chapters': {str(n): row for n, row in self._chapters.items()},
                'chain_heads': dict(self._chain_heads)}
        if self._package_heads or self._review_heads:
            result['package_heads'] = {str(n): key for n, key in self._package_heads.items()}
        if self._review_heads:
            result['review_heads'] = {str(n): key for n, key in self._review_heads.items()}
        return result

    def save(self, path):
        from .persistence import save_json
        save_json(self.to_dict(), path)

    @classmethod
    def from_dict(cls, raw):
        require(isinstance(raw, dict) and raw.get('schema') in (STORE_SCHEMA, PACKAGED_STORE_SCHEMA, REVIEWED_STORE_SCHEMA), 'store_schema',
                '不支持的存储格式。', {'expected': [STORE_SCHEMA, PACKAGED_STORE_SCHEMA, REVIEWED_STORE_SCHEMA]})
        reviewed = raw['schema'] == REVIEWED_STORE_SCHEMA
        packaged = raw['schema'] in (PACKAGED_STORE_SCHEMA, REVIEWED_STORE_SCHEMA)
        expected_fields = ({'schema', 'documents', 'chapters', 'chain_heads'}
                           | ({'package_heads'} if packaged else set())
                           | ({'review_heads'} if reviewed else set()))
        require(set(raw) == expected_fields
                and all(isinstance(raw[key], dict) for key in ('documents', 'chapters', 'chain_heads')),
                'store_schema', '存储字段须符合当前格式。')
        store = cls()
        store._documents = copy.deepcopy(raw['documents'])
        issued_chapters = {value.get('chapter') for value in store._documents.values()
                           if isinstance(value, dict) and value.get('schema') == 'novel-ledger-lite.issued-package/1'}
        if packaged:
            require(isinstance(raw['package_heads'], dict) and (raw['package_heads'] or reviewed),
                    'store_schema', '已签发写作包的存储必须保留非空 package_heads。')
            for number, reference in raw['package_heads'].items():
                require(isinstance(number, str) and number.isdecimal() and int(number) >= 1
                        and str(int(number)) == number and isinstance(reference, str),
                        'store_schema', '写作包持久引用格式损坏。')
                store._package_heads[int(number)] = reference
            require(issued_chapters == set(store._package_heads), 'chapter_package_record',
                    '写作包持久引用与签发文档不一致，拒绝猜测或降级。')
            for number in store._package_heads:
                store.latest_chapter_package(number)
        else:
            require(not issued_chapters, 'chapter_package_record',
                    '旧存储含签发文档却无持久引用；拒绝静默降级，请保留现场恢复可信副本。')
        review_chapters = {value.get('chapter') for value in store._documents.values()
                           if isinstance(value, dict) and value.get('schema') == 'novel-ledger-lite.content-review/1'}
        if reviewed:
            require(isinstance(raw['review_heads'], dict) and raw['review_heads'],
                    'content_review_record', '审读持久引用缺失。')
            for number, reference in raw['review_heads'].items():
                require(isinstance(number, str) and number.isdecimal() and str(int(number)) == number
                        and int(number) >= 1 and isinstance(reference, str),
                        'content_review_record', '审读持久引用格式损坏。')
                store._review_heads[int(number)] = reference
            require(review_chapters == set(store._review_heads), 'content_review_record',
                    '审读记录与持久引用不一致，不允许降级。')
            for number in store._review_heads:
                store.latest_content_review(number)
        else:
            require(not review_chapters, 'content_review_record', '存储含审读记录却丢失持久引用。')
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
