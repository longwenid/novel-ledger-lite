"""Shared wire contracts and value utilities; no I/O or domain imports.

lite 版（novel-ledger-lite）：从完整版 novel_ledger/contracts.py 裁剪改造——
去掉开书十三门（WORLD_ARCHITECTURE/蓝图目录/CONTRACT_FIELDS 的 opening 对齐列），
契约改为「直接导入」形态；SCALE_TIERS 增 t7 解除千万字封顶；DEFAULTS 增差量化
（五层账本 L0-L4＋差量信封）所需的旋钮。判定底盘（require/Error/digest/han_count）
与完整版逐字同源，lite 与完整版对同一章纲的机械判定一致。
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

# lite 协议版本独立于完整版：引擎形状（差量信封、delta/checkpoint）是 lite 自己的协议，
# 完整版项目不经迁移不得混用（报告 §5.4-A 混合态边界由「只对新章生效」约束）。
VERSION = 'lite-1.0.0'

SCHEMA = 'novel-ledger-lite/1'

TASK = 'novel-ledger-lite.task/1'

# Frozen task capability protocols shared with the full build's vocabulary (scene/reading
# dependencies and outline protocol are the same wire shape, so an outline authored against the
# full build freezes identically here).
SCENE_IDENTITY_CAPABILITY = 'scene-identity/2'
READING_DEPENDENCIES_CAPABILITY = 'reading-dependencies/1'
VOLUME_OUTLINE_CAPABILITY = 'volume-outline/2'
SCENE_MEMORY_CAPABILITY = 'scene-memory/1'
HOOK_LINKS_CAPABILITY = 'hook-links/1'


# ----------------------------------------------------------------------------------------------
# Standard numeric settings, declared exactly once (same rule as the full build: a policy default
# has one source). lite adds the delta-envelope knobs; unchanged keys keep the full build's value.
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
    # 修订预算与连写组（与完整版同值；lite 保留必要子集的机械防线）。
    'repairs': 2,
    'revision_limit': 3,
    'fast_batch_chapters': 5,
    # 差量信封·前文窗口降维（报告机制 7 / 第五刀）：前文窗口从完整版默认 2 章全文降为
    # 1 章全文＋前窗锚句；continuity 语义在 lite 不存在，无连带声明需要保持。
    'adjacent_window_chapters': 1,
    # 场景锚句（b 类）：前窗相邻已提交章数——每章抽首/末事件 evidence.quote＋summary 行。
    'scene_anchor_chapters': 2,
    # 知情/事实投影索引化（报告第三刀）：近窗条目带全文，远窗条目只带标题行。
    'near_window_chapters': 30,
    # 状态 delta+checkpoint（报告第四刀，取方案三同款策略）：每卷界或每 N 章冻结全量
    # checkpoint，章间只留增量。这是对 storage-snapshot-stress「cumulative snapshot
    # retention remains an engineering limit」的结构性回应。
    'checkpoint_chapters': 50,
    # 文风卷首锚（方案三补丁 b）：首卷 checkpoint 冻结锚点，每 N 章回比一次（observation）。
    'anchor_review_chapters': 50,
    'chapter_max_ceiling': 10000,
}


def policy_default(key):
    """A policy's default, copied: callers must not be able to mutate the one declaration."""
    value = DEFAULTS[key]
    return copy.deepcopy(value) if isinstance(value, (dict, list)) else value


# The built-in style library: one entry per profile, 与完整版 contracts.STYLE_CATALOG 同表同源
# （五档锚点逐字复制自完整版 contracts.py:137-164）。引擎的通道是这张注册表，不是散文：
# 简报点名生效档名，anchor 是首章认可前形状比较的注册地板（style.baseline）。
# 自定义文风源不走这张表：契约 style_source 登记 style-distill 产出的《文风档案.md》路径，
# 与内置档二选一（见 pipeline.open_book 的存在性校验与 compose.build 的 style_archive 记录）。
STYLE_CATALOG = {
    # The declared default profile: the calibrated mainstream shape the single-profile era ran on.
    '市井修仙': {
        'file': 'styles/市井修仙.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 50.0, 'paragraph_max': 160.0, 'dialogue_share': 0.30},
    },
    '账房掌门': {
        'file': 'styles/账房掌门.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 47.6, 'paragraph_max': 450.0, 'dialogue_share': 0.2643},
    },
    '神秘学双声部': {
        'file': 'styles/神秘学双声部.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 36.1, 'paragraph_max': 204.0, 'dialogue_share': 0.3652},
    },
    '宗族史传': {
        'file': 'styles/宗族史传.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 35.6, 'paragraph_max': 353.0, 'dialogue_share': 0.3088},
    },
    '科幻错位幽默': {
        'file': 'styles/科幻错位幽默.md',
        'anchor': {'han': 2000, 'sentences': 180, 'sentence_mean': 18.0, 'sentence_short_share': 0.25,
                   'paragraph_mean': 49.2, 'paragraph_max': 392.0, 'dialogue_share': 0.33},
    },
}


# 给作者选的文风板面：内置五档各一句话定位＋外部档案接入方法。定位语依据各档注册锚
# 特征概括（逐档全文在完整版 references/styles/<名>.md）；引擎不提问、不猜偏好，
# 只列可选项——主控拿这块去问作者，作者显式选定后才写进契约。
STYLE_PROFILE_BOARD = (
    ('市井修仙', '校准的主流市井声线：短句与动作推进，器物、对白与烟火气承载江湖。'),
    ('账房掌门', '账房式克制：长段铺陈核对与登记流程，对白短促，凭据先行。'),
    ('神秘学双声部', '叙述与内心双声部：短段高频，规则感与悬念层层并进。'),
    ('宗族史传', '史传笔法：短段长卷，谱系感与代际纵深，收束沉稳。'),
    ('科幻错位幽默', '错位幽默：术语冷感与日常反差，中长段的节奏留白。'),
)


def style_options_board():
    """The selectable style options, for the controller to put before the author."""
    return {'builtin': [{'profile': name, 'line': line,
                         'anchor': dict(STYLE_CATALOG[name]['anchor'])}
                        for name, line in STYLE_PROFILE_BOARD],
            'external': '外部文风源：先用 style-distill 技能从参考小说产出《文风档案.md》，'
                        '再把它（绝对路径）经契约 style_source 或 recontract_patch(style_source=路径) '
                        '登记——与内置档二选一。',
            'note': '文风须作者本人显式选定（内置档名或外部档案路径）；引擎不使用默认档放行执笔，'
                    '也不替作者猜偏好。'}


def resolve_style_profile(profile=None):
    """The catalog name a contract's style_profile means; unknown or absent raises upstream.

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


# ----------------------------------------------------------------------------------------------
# Scale tiers. lite 的收尾（评审共识）：增 t7 解除 t6 封顶，支持千万字短章写法
# （2000~3333 字/章 → 3000~5000 章）。完整版报告 §2.6 登记的 1667~2999 章中章写法缺口
# 仍按完整版决策处理，lite 不覆盖；t7 的卷数按「可配」落地：volume_count 是默认起点，
# volume_count_max 声明作者可把 rolling 卷纲排到多少卷（30~100）。
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


# How the pipeline scales with the size class. 完整版 contracts.py:475 的守卫要求在这里保留：
# 新增档位必须在此声明形状，守卫测试从档位表推导该要求（test_contracts 里的形状断言）。
# lite 只有执笔环节：merge_chapter_outline 的 lite 语义是「章纲是否可随卷纲一并安装」，
# 两档都取 False——章纲门在 lite 按卷独立运行。
PIPELINE_SHAPES = {
    't6': {'merge_chapter_outline': False},
    't7': {'merge_chapter_outline': False},
}


def tier_window_band(row):
    """The chapter-count band the tier's own word range proves reachable.

    窗口无洞断言的机械口径：word_range×[chapter_min, chapter_max] 推出的章数全域
    [word_lo/chapter_max, word_hi/chapter_min]；tier 的 chapter_window 必须落在全域内
    （覆盖该档「体量声明」自身可达的写法），完整版报告 §2.6 的档间缺口登记不复制到 lite。
    """
    word_lo, word_hi = row['word_range']
    return (max(1, -(-word_lo // row['chapter_max'])), word_hi // row['chapter_min'])


# ----------------------------------------------------------------------------------------------
# The author contract: field, kind, default. lite 契约是「直接导入」形态——无开书门对齐列，
# 字段由作者/完整版开书流程产出后导入。契约层校验同一张表驱动（单表原则不变）。
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
    # 文风必须作者本人显式选定（2026-11-02 作者要求）：default=None——契约缺失该字段
    # 是合法的「未选定」状态（导入阶段放行），但执笔派工被引擎拒绝（compose.build 前置
    # 检查）；显式给出的值仍走 choices 枚举校验（杜撰拒绝）。完整版的无偏好回落默认档
    # 逻辑在 lite 不存在。
    {'key': 'style_profile', 'kind': 'text', 'default': None,
     'choices': tuple(STYLE_CATALOG), 'optional': True},
    # 外部文风源（style-distill 产出的《文风档案.md》文件路径）。与内置档二选一：
    # style_source 有值时它是生效文风源（信封 style_archive 记录携带档案全文，
    # style_profile 只保留登记）；值须指向真实文件，存在性在开书时校验
    # （contracts 层无 I/O，校验在 pipeline.open_book）。
    {'key': 'style_source', 'kind': 'text', 'default': '', 'optional': True},
    {'key': 'anchors', 'kind': 'rows', 'default': [], 'optional': True},
    {'key': 'links', 'kind': 'rows', 'default': [], 'optional': True},
    {'key': 'initial_facts', 'kind': 'rows', 'default': [], 'optional': True},
    {'key': 'places', 'kind': 'rows', 'default': [], 'optional': True},
    {'key': 'placements', 'kind': 'map', 'default': {}, 'optional': True},
    {'key': 'arcs', 'kind': 'rows', 'default': [], 'optional': True},
    # 差量化契约键（报告第三/四刀）：
    # near_window_chapters  近窗投影章数（默认 DEFAULTS['near_window_chapters']）
    # pinned                作者标记全文常驻的条目 [{kind,key}]——堵「30 章未提即失忆」
    # checkpoint_chapters   全量 checkpoint 周期上限（每卷必checkpoint，另受此上限兜底）
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
