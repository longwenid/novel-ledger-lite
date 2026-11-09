"""Shared wire contracts, scale tiers, style catalog and value utilities.

字段、策略默认值与协议标识在此统一定义；本模块仅使用标准库，不进行文件 I/O。"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

VERSION = 'lite-2.1.0'

SCHEMA = 'novel-ledger-lite/2'
STORE_SCHEMA = 'novel-ledger-lite.store/2'
BUNDLE_SCHEMA = 'novel-ledger-lite.bundle/2'

TASK = 'novel-ledger-lite.task/2'

SCENE_IDENTITY_CAPABILITY = 'scene-identity/2'
READING_DEPENDENCIES_CAPABILITY = 'reading-dependencies/1'
VOLUME_OUTLINE_CAPABILITY = 'volume-outline/2'
SCENE_MEMORY_CAPABILITY = 'scene-memory/1'
HOOK_LINKS_CAPABILITY = 'hook-links/1'


DEFAULTS = {
    # One volume outline per volume, complete in a single receipt.
    'volume_outline': {'scope': 'rolling', 'words': 2500, 'tolerance': 500},
    # One synopsis per chapter, with that chapter's drift declarations.
    'chapter_outline': {'scope': 'volume', 'words': 150, 'tolerance': 60},
    'style_window': {'sentence': 0.35, 'paragraph': 0.35, 'dialogue': 0.40, 'repetition': 0.12, 'person': 1},
    'style_guard': 'observe',
    # 注意：lite 没有 style_profile_default——文风须作者显式选定，引擎无默认档（2026-11-02）。
    'style_floor_han': 40,
    'style_min_sentences': 3,
    'style_min_ngrams': 20,
    'style_ngram': 4,
    'style_short_sentence': 10,
    'style_same_order': 3,
    'style_baseline_window': 5,
    'repairs': 2,
    'revision_limit': 3,
    'fast_batch_chapters': 5,
    'adjacent_window_chapters': 1,
    # 场景锚句（b 类）：前窗相邻已提交章数——每章抽首/末事件 evidence.quote＋summary 行。
    'scene_anchor_chapters': 2,
    'near_window_chapters': 30,
    # 补读目录每章最多列出这些定位片段，其余可搜索、翻页并按坐标补读。
    'far_reference_limit': 20,
    'checkpoint_chapters': 50,
    # 文风卷首锚（方案三补丁 b）：首卷 checkpoint 冻结锚点，每 N 章回比一次（observation）。
    'anchor_review_chapters': 50,
    'chapter_max_ceiling': 10000,
}


def policy_default(key):
    """A policy's default, copied: callers must not be able to mutate the one declaration."""
    value = DEFAULTS[key]
    return copy.deepcopy(value) if isinstance(value, (dict, list)) else value


STYLE_CATALOG = {
    # The declared default profile: the calibrated mainstream shape the single-profile era ran on.
    '市井修仙': {
        'file': 'references/styles/市井修仙.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 50.0, 'paragraph_max': 160.0, 'dialogue_share': 0.30},
    },
    '账房掌门': {
        'file': 'references/styles/账房掌门.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 47.6, 'paragraph_max': 450.0, 'dialogue_share': 0.2643},
    },
    '神秘学双声部': {
        'file': 'references/styles/神秘学双声部.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 36.1, 'paragraph_max': 204.0, 'dialogue_share': 0.3652},
    },
    '宗族史传': {
        'file': 'references/styles/宗族史传.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 35.6, 'paragraph_max': 353.0, 'dialogue_share': 0.3088},
    },
    '科幻错位幽默': {
        'file': 'references/styles/科幻错位幽默.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 49.2, 'paragraph_max': 392.0, 'dialogue_share': 0.33},
    },
}


STYLE_PROFILE_BOARD = (
    ('市井修仙', '校准的主流市井声线：短句与动作推进，器物、对白与烟火气承载江湖。'),
    ('账房掌门', '账房式克制：长段铺陈核对与登记流程，对白短促，凭据先行。'),
    ('神秘学双声部', '叙述与内心双声部：短段高频，规则感与悬念层层并进。'),
    ('宗族史传', '史传笔法：短段长卷，谱系感与代际纵深，收束沉稳。'),
    ('科幻错位幽默', '错位幽默：术语冷感与日常反差，中长段的节奏留白。'),
)


def style_options_board():
    """The selectable style options, for the controller to put before the author."""
    return {'builtin': [{'profile': name, 'line': line, 'file': STYLE_CATALOG[name]['file'],
                         'anchor': dict(STYLE_CATALOG[name]['anchor'])}
                        for name, line in STYLE_PROFILE_BOARD],
            'external': '外部文风源：提供作者确认的 UTF-8 Markdown 文风档案（可自行编写或由任意工具生成），'
                        '再把它（绝对路径）经契约 style_source 或 recontract_patch(style_source=路径) '
                        '登记——与内置档二选一。',
            'note': '文风须作者本人显式选定（内置档名或外部档案路径）；引擎不使用默认档放行执笔，'
                    '也不替作者猜偏好。'}


def resolve_style_profile(profile=None):
    """The catalog name a contract's style_profile means; unknown or absent is rejected by the caller.

    lite 口径（2026-11-02 作者要求）：未知档名返回 None 而不是悄悄落默认档——调用方
    （compose.build）对「未选定/非法」一律拒绝执笔，不存在默认档放行路径。"""
    return profile if profile in STYLE_CATALOG else None


def profile_anchor(profile=None):
    """The declared anchor of a built-in style profile, labeled for what it is.

    lite 口径（2026-11-02 作者要求）：未知或缺失档名返回 None——不静默回落默认档。
    调用方对 None 的处理是显式的：compose.build 的执笔前置检查保证到达此处时文风已
    选定（内置档名合法，或外部源路径下 style_profile 可缺、锚由档案自身约定承担）。"""
    name = resolve_style_profile(profile)
    if name is None:
        return None
    anchor = copy.deepcopy(STYLE_CATALOG[name]['anchor'])
    anchor.update({'origin': 'default', 'profile': name})
    return anchor


SCALE_TIERS = (
    {'id': 't6', 'name': '巨制', 'word_range': [4000000, 10000000], 'chapter_min': 2000, 'chapter_aim': 6500,
     'chapter_max': 10000, 'volume_count': 15, 'chapters': 1540, 'chapter_window': [1250, 1666],
     'note': '千万字级的多线长跑（按 aim 写法约 1538 章）：跨代际势力更替、世代级伏笔回收与多主角接力；'
             '对持续供给与状态管理要求最高'},
    {'id': 't7', 'name': '千字海', 'word_range': [10000000, 17500000], 'chapter_min': 2000, 'chapter_aim': 3500,
     'chapter_max': 10000, 'volume_count': 30, 'volume_count_max': 100, 'chapters': 4000,
     'chapter_window': [3000, 5000],
     'note': '千万字短章写法专档（2000~3500 字/章 → 3000~5000 章）：百卷级 rolling 卷纲（卷数 30~100 可配）。'
             '只解决章数档位与文档显式化，不引入新机制——差量信封让必读包与书龄无关，'
             '本档的成本曲线才成立'},
)


def tier_of(contract):
    """The tier row a contract's chapter band was sized to, or None for a custom band."""
    tier_id = contract.get('tier')
    if tier_id:
        return next((row for row in SCALE_TIERS if row['id'] == tier_id), None)
    return next((row for row in SCALE_TIERS
                 if row['chapter_min'] == contract.get('chapter_min')
                 and row['chapter_max'] == contract.get('chapter_max')
                 and row['chapter_aim'] == contract.get('chapter_aim')), None)


PIPELINE_SHAPES = {
    't6': {'merge_chapter_outline': False},
    't7': {'merge_chapter_outline': False},
}


def tier_window_band(row):
    """The chapter-count band the tier's own word range proves reachable.

    窗口无洞断言的机械口径：word_range×[chapter_min, chapter_max] 推出的章数全域
    [word_lo/chapter_max, word_hi/chapter_min]；tier 的 chapter_window 必须落在全域内
    每档窗口应落在自身字数与章长可达的全域内；其他章数安排可使用自定义契约。
    """
    word_lo, word_hi = row['word_range']
    return (max(1, -(-word_lo // row['chapter_max'])), word_hi // row['chapter_min'])


CONTRACT_TYPES = {
    'text': (str,),
    'int': (int,),
    'bool': (bool,),
    'band': (list,),
    'rows': (list,),
    'map': (dict,),
}


CONTRACT_FIELDS = (
    {'key': 'title', 'kind': 'text', 'default': ''},
    {'key': 'reader_promise', 'kind': 'text', 'default': ''},
    {'key': 'ending', 'kind': 'text', 'default': ''},
    {'key': 'genre', 'kind': 'text', 'default': ''},
    {'key': 'story_engine', 'kind': 'text', 'default': ''},
    {'key': 'opposition', 'kind': 'text', 'default': ''},
    {'key': 'world_premise', 'kind': 'text', 'default': ''},
    {'key': 'voice', 'kind': 'text', 'default': ''},
    {'key': 'tone', 'kind': 'text', 'default': '', 'optional': True},
    {'key': 'theme', 'kind': 'text', 'default': '', 'optional': True},
    {'key': 'pov', 'kind': 'text', 'default': '', 'optional': True},
    {'key': 'style_traits', 'kind': 'rows', 'default': []},
    {'key': 'world_rules', 'kind': 'rows', 'default': []},
    {'key': 'protagonist_setup', 'kind': 'map', 'default': '',
     'shape': ('id', 'name', 'identity', 'desire', 'limit')},
    {'key': 'entities', 'kind': 'rows', 'default': []},
    {'key': 'initial_resources', 'kind': 'rows', 'default': []},
    {'key': 'volumes', 'kind': 'rows', 'default': [],
     'shape': ('id', 'purpose', 'end'), 'blank': False, 'count': 1},
    {'key': 'word_range', 'kind': 'band', 'default': []},
    {'key': 'chapter_min', 'kind': 'int', 'default': None},
    {'key': 'chapter_max', 'kind': 'int', 'default': None},
    {'key': 'chapter_aim', 'kind': 'int', 'default': None},
    {'key': 'narrative_tracking', 'kind': 'bool', 'default': True},
    {'key': 'editorial_features', 'kind': 'bool', 'default': True},
    {'key': 'scope_append_limit', 'kind': 'int', 'default': 3},
    {'key': 'revision_limit', 'kind': 'int', 'default': DEFAULTS['revision_limit']},
    {'key': 'volume_outline', 'kind': 'map', 'default': policy_default('volume_outline'),
     'optional': True},
    {'key': 'chapter_outline', 'kind': 'map', 'default': policy_default('chapter_outline'),
     'optional': True},
    {'key': 'style_window', 'kind': 'map', 'default': policy_default('style_window'),
     'optional': True},
    {'key': 'style_guard', 'kind': 'text', 'default': DEFAULTS['style_guard'],
     'choices': ('observe', 'strict'), 'optional': True},
    {'key': 'style_profile', 'kind': 'text', 'default': None,
     'choices': tuple(STYLE_CATALOG), 'optional': True},
    {'key': 'style_source', 'kind': 'text', 'default': '', 'optional': True},
    {'key': 'anchors', 'kind': 'rows', 'default': [], 'optional': True},
    {'key': 'links', 'kind': 'rows', 'default': [], 'optional': True},
    {'key': 'initial_facts', 'kind': 'rows', 'default': [], 'optional': True},
    {'key': 'places', 'kind': 'rows', 'default': [], 'optional': True},
    {'key': 'placements', 'kind': 'map', 'default': {}, 'optional': True},
    {'key': 'arcs', 'kind': 'rows', 'default': [], 'optional': True},
    {'key': 'near_window_chapters', 'kind': 'int', 'default': DEFAULTS['near_window_chapters'],
     'optional': True},
    {'key': 'pinned', 'kind': 'rows', 'default': [], 'optional': True,
     'shape': ('kind', 'key'), 'exact': False},
    {'key': 'checkpoint_chapters', 'kind': 'int', 'default': DEFAULTS['checkpoint_chapters'],
     'optional': True},
    # 文风卷首锚回比周期（pipeline._style_anchor_review 读取）：可按书覆盖的真旋钮。
    {'key': 'anchor_review_chapters', 'kind': 'int', 'default': DEFAULTS['anchor_review_chapters'],
     'optional': True},
)


CONTRACT_KEYS = tuple(row['key'] for row in CONTRACT_FIELDS)


CHARACTERS = ('name', 'role', 'desire', 'limit', 'knowledge_boundary')
CHARACTER_KINDS = ('person', 'character')
BIOGRAPHY_FIELDS = ('past', 'contradiction', 'relationships', 'behavior')


def _placeholder(row):
    if row['kind'] in ('rows', 'band'):
        if row.get('optional'):
            return copy.deepcopy(row['default'])
        if row.get('shape'):
            entries = [{field: (0 if field == 'end' else '') for field in row['shape']}]
            return entries * row.get('count', 1)
        return copy.deepcopy(row['default'])
    if row['kind'] == 'map':
        if not row.get('shape') and isinstance(row['default'], dict):
            return copy.deepcopy(row['default'])
        return {field: '' for field in row.get('shape', ())}
    if row['kind'] == 'int':
        return row['default'] if type(row['default']) is int and row['default'] > 0 else 0
    return copy.deepcopy(row['default'])


def contract_skeleton():
    """A contract-shaped object carrying every key; never a valid contract on its own."""
    return {row['key']: _placeholder(row) for row in CONTRACT_FIELDS}


def contract_errors(raw):
    """Mechanical shape check against CONTRACT_FIELDS. Returns complaints, never raises."""
    complaints = []
    if not isinstance(raw, dict):
        return ['约定须为对象。']
    for unknown in sorted(set(raw) - set(CONTRACT_KEYS)):
        complaints.append('未知约定字段：' + unknown)
    for row in CONTRACT_FIELDS:
        key, kind = row['key'], row['kind']
        if key not in raw:
            if not row.get('optional'):
                complaints.append('缺少约定字段：' + key)
            continue
        value = raw[key]
        if kind == 'band':
            if value == []:
                continue
            if not isinstance(value, list) or len(value) != 2 or not all(type(n) is int and n > 0 for n in value) \
                    or value[0] > value[1]:
                complaints.append('word_range 须为有效总汉字区间。')
            continue
        if kind == 'rows':
            if not isinstance(value, list):
                complaints.append(key + ' 须为数组。')
            elif not value and row.get('optional'):
                pass
            elif row.get('blank') is False and len(value) < row.get('count', 1):
                complaints.append(key + ' 须提供至少 ' + str(row.get('count', 1)) + ' 条完整记录。')
            elif row.get('exact') is False and row.get('shape'):
                # pinned 行允许携带说明性附加字段，但定位键必须写实；值域不检查类型。
                if any(not isinstance(entry, dict) or not all(entry.get(f) not in ('', None)
                                                              for f in row['shape'])
                       for entry in value):
                    complaints.append(key + ' 每条记录须带定位键：' + '/'.join(row['shape']))
            elif row.get('shape') and row.get('exact'):
                allowed = set(row['shape'])
                if any(not isinstance(entry, dict) or set(entry) != allowed
                       or not all(text(entry[field]) for field in allowed) for entry in value):
                    complaints.append(key + ' 的每条记录只能有这些字段，且每项都要写实：' + '/'.join(row['shape']))
            continue
        if kind == 'map':
            if not isinstance(value, dict) or any(field not in value for field in row.get('shape', ())):
                complaints.append(key + ' 须包含字段：' + '/'.join(row.get('shape', ())))
            continue
        if kind == 'text':
            if not text(value):
                complaints.append(key + ' 须为非空文本。')
            elif row.get('choices') and value not in row['choices']:
                complaints.append(key + ' 须取 ' + '/'.join(row['choices']) + '。')
            continue
        if kind == 'bool':
            if type(value) is not bool:
                complaints.append(key + ' 须为布尔值。')
        elif type(value) is not int or value <= 0:
            complaints.append(key + ' 须为正整数。')
    return complaints


TIME_MARKERS = tuple('日天夜晨早晚午时年月春夏秋冬晓暮昏宵旬翌昨今明') + ('星期', '分钟', '秒钟')

DEFAULT_TERMS = ['ledger', 'credit', 'receipt']

DEFAULT_NAME_CHARS = []


class Error(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.message = code, message
        self.details = dict(details or {})
        self.details.setdefault('recover', '按当前任务模板修正后重提；不要改库或替换任务身份。')

    def as_dict(self):
        return {'error': self.code, 'message': self.message, 'details': self.details}


def require(ok, code, message, details=None):
    if not ok:
        raise Error(code, message, details)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(dump(value).encode('utf-8')).hexdigest()


def han_count(prose):
    return sum('\u3400' <= c <= '\u4dbf' or '\u4e00' <= c <= '\u9fff' or '\U00020000' <= c <= '\U0003134f' for c in prose)


@dataclass(frozen=True)
class Job:
    stage: str
    chapter: int
    scope: str = 'chapter'
    first: int = 0
    last: int = 0
    payload: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class Outcome:
    book: Dict[str, Any]
    chapter: Optional[Dict[str, Any]] = None
    style_report: Optional[Dict[str, Any]] = None
    findings: Optional[list] = None
