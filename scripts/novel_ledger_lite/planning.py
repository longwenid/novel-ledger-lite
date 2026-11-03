"""Validate imported author constraints, outline policies and volume ranges.

rolling 卷纲可配 volume 章纲；多卷 rolling 不可配 all 章纲。"""
from __future__ import annotations

import copy
import math
from . import contracts
from .contracts import CONTRACT_FIELDS, contract_errors, digest, require, text


def resolve_outline_policy(contract, key):
    """Required pipeline policies: absence defaults, explicit invalid values never do."""
    scopes = ('all', 'rolling') if key == 'volume_outline' else ('volume', 'all')
    policy = contract[key] if key in contract else contracts.policy_default(key)
    require(isinstance(policy, dict) and set(policy) == {'scope', 'words', 'tolerance'}
            and policy.get('scope') in scopes and type(policy.get('words')) is int and policy['words'] > 0
            and type(policy.get('tolerance')) is int and 0 <= policy['tolerance'] < policy['words'],
            key, key + ' 是必选阶段，不能用空对象或 null 关闭；须为 {scope:' + '|'.join(scopes)
            + ',words:正整数,tolerance:非负整数且小于 words}。',
            {'recover': '通过明确改约填写完整策略；缺省字段可使用默认值。',
             'default': contracts.policy_default(key)})
    return copy.deepcopy(policy)


def outline_policies(contract):
    policies = {key: resolve_outline_policy(contract, key)
                for key in ('volume_outline', 'chapter_outline')}
    require(not (policies['volume_outline']['scope'] == 'rolling'
                 and policies['chapter_outline']['scope'] == 'all'
                 and len(contract.get('volumes') or []) > 1),
            'outline_policy', '多卷 rolling 卷纲须搭配 volume 章纲；全书章纲须先有 all 卷纲。',
            {'recover': '明确改约选择 all/volume、all/all 或 rolling/volume。'})
    return policies


def validate_contract(raw):
    """Direct-import contract validation. lite 契约无开书门对齐；缺省字段按 CONTRACT_FIELDS
    补默认（结构性默认，不发明作者决定）。"""
    contract = copy.deepcopy(raw) if isinstance(raw, dict) else raw
    if isinstance(contract, dict):
        for row in CONTRACT_FIELDS:
            if row['key'] in contract:
                continue
            default = row['default']
            if default in ('', None):
                continue
            if default == [] and row.get('blank') is False and row.get('count', 1) > 0:
                continue
            contract[row['key']] = copy.deepcopy(default)
    complaints = contract_errors(contract)
    require(not complaints, 'contract', '约定结构不成立：' + '；'.join(complaints[:6]))
    contract.setdefault('chapter_aim', min(contract['chapter_max'], max(contract['chapter_min'], 3500)))
    require(all(type(contract[k]) is int and contract[k] > 0
                for k in ('chapter_min', 'chapter_max', 'chapter_aim', 'revision_limit')),
            'contract', '章幅与修订窗口须为正整数。')
    require(contract['chapter_min'] <= contract['chapter_aim'] <= contract['chapter_max'], 'contract',
            '章目标须在上下限之间。')
    require(contract['chapter_max'] <= contracts.policy_default('chapter_max_ceiling'), 'contract',
            '章字数上限不得高于策略上限 %d。' % contracts.policy_default('chapter_max_ceiling'))
    require(type(contract['narrative_tracking']) is bool, 'contract', 'narrative_tracking 须为布尔值。')
    contract.update(outline_policies(contract))
    volumes = contract['volumes']
    seen, last = set(), 0
    for volume in volumes:
        require(isinstance(volume, dict) and text(volume.get('id')) and text(volume.get('purpose'))
                and volume['id'] not in seen, 'volume', '卷需要唯一 id 和职责。')
        seen.add(volume['id'])
        if 'end' not in volume:
            require(type(volume.get('word_budget')) is int and volume['word_budget'] > 0, 'volume',
                    '卷需要 end 或 word_budget。')
            volume['end'] = last + max(1, math.ceil(volume['word_budget'] / contract['chapter_aim']))
        require(type(volume['end']) is int and volume['end'] > last, 'volume', '卷末章号须严格递增。')
        volume['first'] = last + 1
        last = volume['end']
    contract['word_range'] = [last * contract['chapter_min'], last * contract['chapter_max']]
    for key in ('world_rules', 'red_lines', 'arcs'):
        value = contract.get(key)
        if value is not None:
            require(isinstance(value, list) and all(text(v) for v in value), 'contract',
                    key + ' 须为字符串数组。')
    for row in contract.get('pinned') or []:
        require(isinstance(row, dict) and text(row.get('kind')) and text(row.get('key')),
                'contract', 'pinned 条目须带 {kind,key} 定位键。')
    return contract


def volume_for(contract, chapter):
    return next((v for v in contract['volumes'] if v['first'] <= chapter <= v['end']), None)


def world_hash(model):
    return digest(model) if model else None
