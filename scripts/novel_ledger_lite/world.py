"""World-record schemas, validation and indexing for imported author material.

世界定义不自动建立人物知情或当前事实；只核对记录结构与登记引用。"""
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


TOP_KEYS = ('premise', 'story_capacity')


def validate_shape(model):
    """Validate imported world sections, record IDs and declared fields.

    只保证结构可解析，不判断内容是否足以承载整部作品。"""
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
