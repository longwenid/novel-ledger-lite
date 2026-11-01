"""Rich world definitions; never mutate canonical facts or character knowledge.

lite 版：从完整版裁剪——去掉开书门校验（validate/_bindings/_required_from/declared_sections，
那是完整版 creation 流程的一部分）；保留登记表（SECTIONS/LABELS）、按档域地板
（TIER_SECTIONS/required_sections）与内容寻址索引（index）——章纲 world_refs 的机械解析
（drift._world_index）与差量信封的本章世界记录切片只依赖这三件。世界模型文档本身由
完整版开书流程或作者导入，lite 不再生成或校验其完整形状。
"""
from __future__ import annotations

from .contracts import CHARACTERS, require, text

SECTIONS = {
    'geography': ('name', 'environment', 'resources', 'access', 'story_pressure'),
    'history': ('period', 'event', 'consequence', 'present_effect'),
    'rules': ('principle', 'scope', 'limits', 'consequences'),
    'factions': ('name', 'goal', 'power', 'dependencies', 'conflicts'),
    'economy': ('resource', 'production', 'distribution', 'scarcity', 'conflict'),
    'society': ('institution', 'norm', 'enforcement', 'pressure'),
    'everyday': ('practice', 'constraint', 'story_use'),
    'characters': CHARACTERS,
    'mysteries': ('truth', 'disclosure', 'causal_role'),
    'mechanisms': ('principle', 'cost', 'limits', 'failure_condition'),
    'powers': ('name', 'condition', 'gain', 'cost', 'limit'),
    'cosmology': ('name', 'inhabitant', 'law', 'entry'),
}
LABELS = {'geography': '地理与通行', 'history': '历史与当下影响', 'rules': '世界规则', 'factions': '势力与利益',
          'economy': '资源与经济', 'society': '社会制度', 'everyday': '生活日常', 'characters': '人物与关系',
          'mysteries': '隐秘信息与披露', 'mechanisms': '特殊机制与代价',
          'powers': '力量与位阶阶梯', 'cosmology': '空间与位面'}
ALL_SECTIONS = tuple(SECTIONS)
BASE_SECTIONS = ('geography', 'history', 'rules', 'factions', 'economy', 'society', 'everyday',
                 'characters', 'mysteries', 'mechanisms')
GRAND_SECTIONS = ('powers', 'cosmology')
OPTIONAL_FIELDS = {
    'history': ('epoch', 'carryover'),
    'geography': ('scale', 'counter_space'),
    'factions': ('survives_scale_up',),
    'mysteries': ('reveal_window', 'survival'),
}
# Which sections a world must fill, by scale tier. lite 的 t7 与 t6 同地板（BASE_SECTIONS）：
# 短章千万字不改变世界的域地板，只改变章数与卷数。
TIER_SECTIONS = {
    't0': ('rules', 'society', 'everyday', 'characters', 'mysteries', 'mechanisms'),
    't1': ('geography', 'rules', 'society', 'everyday', 'characters', 'mysteries', 'mechanisms'),
    't2': ('geography', 'history', 'rules', 'society', 'everyday', 'characters', 'mysteries', 'mechanisms'),
    't3': BASE_SECTIONS,
    't4': BASE_SECTIONS,
    't5': BASE_SECTIONS,
    't6': BASE_SECTIONS,
    't7': BASE_SECTIONS,
}


def _ordered(names):
    """A set of section names in the one canonical order this file declares."""
    wanted = set(names)
    return tuple(name for name in ALL_SECTIONS if name in wanted)


def required_sections(tier_id=None, choices=None):
    """The sections this tier's world must fill; lite has no opening choices, only the tier floor."""
    base = TIER_SECTIONS.get(tier_id) or ALL_SECTIONS
    return _ordered(tuple(base))


def index(model):
    return {section + ':' + row['id']: row for section in SECTIONS for row in model.get(section, [])}


# 顶层叙述键：完整版世界文档的标准结构（context 读 premise/story_capacity 组装 world_core）。
TOP_KEYS = ('premise', 'story_capacity')


def validate_shape(model):
    """Mechanical shape floor for an imported world document: sections are record arrays, each
    record carries its id and the declared fields of its section. lite 不校验域内容是否齐备
    （那是完整版开书门的事），只保证后续机械解析（index/字段读取）不会遇到畸形行。"""
    require(isinstance(model, dict), 'world_record', '世界模型须为对象。')
    unknown = sorted(set(model) - set(ALL_SECTIONS) - set(TOP_KEYS))
    require(not unknown, 'world_section', '世界模型包含未登记的域。', {'unknown': unknown})
    for section in ALL_SECTIONS:
        rows = model.get(section) or []
        require(isinstance(rows, list), 'world_section', '世界模型各域须为数组。', {'section': section})
        for row in rows:
            require(isinstance(row, dict) and text(row.get('id')), 'world_id',
                    '世界记录须带非空 id。', {'section': section})
            missing = [field for field in SECTIONS[section] if field not in row]
            require(not missing, 'world_fields', '世界记录缺少已登记字段。',
                    {'section': section, 'id': row.get('id'), 'missing': missing})
    return model
