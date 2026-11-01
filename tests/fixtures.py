"""lite 冒烟夹具：小契约、种子世界、单卷章纲、正文与 drift_check 自动对齐引擎投影。

章纲行的增量选择刻意覆盖三类（clock/resources/places/knowledge）＋hooks 动作；
drift_check 由 drift_reconcile._planned 自动生成——夹具声明与引擎覆盖比对共用同一张
增量清单，一行不多一行不少。正文每句携带章号词保证跨章唯一（8 章重复窗不误伤），
时间句携带时间标记（facts 的 time_evidence 核验）。
"""
from __future__ import annotations

import copy
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/scripts')

from novel_ledger_lite import contracts, facts, planning, pipeline, store as store_module
from novel_ledger_lite.contracts import policy_default
from novel_ledger_lite.drift_reconcile import _planned

CHAPTERS = 4


def contract(chapters=CHAPTERS):
    return {
        'title': '夜班退件（lite）', 'genre': '都市生活',
        'reader_promise': '一个夜班工人查清退件来源并承担自己的选择。',
        'ending': '退件来源公开，工人承担违规开箱的后果。',
        'world_premise': '一座仓库的夜班退件纠纷。',
        'story_engine': '核对退件来源，追查签字责任。',
        'opposition': '主管担心调查影响考核。',
        'voice': '以动作、物件、对白和后果呈现夜班人情。',
        'style_traits': ['少重复解释。', '因果承接完整。'],
        'protagonist_setup': {'id': 'shen', 'name': '沈桐', 'identity': '夜班工人',
                              'desire': '查清责任。', 'limit': '不牵连无关同事。'},
        'world_rules': ['夜班退件必须登记负责人。'],
        'narrative_tracking': False, 'editorial_features': False,
        # 文风须作者显式选定（执笔前置强制）：夹具模拟作者已选定默认档的项目。
        'style_profile': '市井修仙',
        'chapter_min': 30, 'chapter_max': 200, 'chapter_aim': 60,
        'volume_outline': {'scope': 'rolling', 'words': 2500, 'tolerance': 500},
        'chapter_outline': {'scope': 'volume', 'words': 60, 'tolerance': 30},
        'volumes': [{'id': 'v1', 'purpose': '查明来源并面对后果。', 'end': chapters}],
        'entities': [{'id': 'shen', 'name': '沈桐', 'kind': 'person'}],
        'initial_resources': [{'holder': 'shen', 'asset': '车费', 'unit': '元', 'quantity': '4'}],
        'places': [{'id': 'office', 'name': '值班室'}, {'id': 'yard', 'name': '仓库后院'}],
        'placements': {'shen': 'office'},
    }


def world_fixture():
    return {
        'premise': '一座仓库的夜班退件纠纷。',
        'geography': [_place('office', '值班室'), _place('yard', '仓库后院')],
        'history': [],
        'rules': [{'id': 'r1', 'principle': '夜班退件必须登记负责人。',
                   'scope': '本仓库的夜班退件处理。', 'limits': '只约束已登记的退件。',
                   'consequences': '违反者承担登记责任。', 'links': []}],
        'factions': [], 'society': [], 'everyday': [],
        'economy': [{'id': 'asset-1', 'resource': '车费', 'production': '按班次发放。',
                     'distribution': '由主管登记后发放。', 'scarcity': '不足时需要自付。',
                     'conflict': '谁承担这笔支出。', 'links': []}],
        'characters': [{'id': 'shen', 'name': '沈桐', 'role': '夜班工人', 'desire': '查清责任。',
                        'limit': '不牵连无关同事。', 'knowledge_boundary': '只知自己经手的货物。',
                        'links': ['rules:r1']}],
        'mysteries': [], 'mechanisms': [], 'powers': [], 'cosmology': [],
    }


def _place(ident, name):
    return {'id': ident, 'name': name, 'environment': '夜间照明的作业区。',
            'resources': '退回的货物与登记册。', 'access': '夜班人员可进。',
            'story_pressure': '退件必须有人签字。', 'links': []}


HOOK_ID = 'hook-v1-required'


def volume_row(volume):
    """单卷卷纲行：登记表＋承诺声明＋时钟终值。lite 的安装门只做轻形状校验，
    逐字段机械核对在章纲门（validate_chapter_outline＋simulate）完成。"""
    return {'id': volume['id'], 'purpose': '把退件来源从个人纠纷推到制度责任。',
            'stage': '', 'arc': '本卷从一次退回的箱子写起，沈桐先被制度挡在门外，'
                                '随后用旧凭据撬开缺口，卷末由他公开来源并承担违规的代价。',
            'turns': [{'at': '卷中', 'turn': '旧凭据暴露出签字矛盾。'},
                      {'at': '卷尾', 'turn': '沈桐公开来源并接受处理。'}],
            'climax': '公开来源与签字矛盾，沈桐承担违规开箱的后果。',
            'nodes': [], 'threads': [],
            'resources': [], 'places': [], 'knowledge': [], 'characters': [],
            'clock': {'advance_days': CHAPTERS, 'to': CHAPTERS},
            'exit_state': '卷末：车费结余；沈桐在后院；对来源已确认；承诺已兑现。',
            'style': {'trend': '以短句、动作与凭据核对推进，卷末用较长段落交代责任后果。'},
            'hooks': [{'id': HOOK_ID,
                       'text': '读者看到退回凭据的来历，并要知道它最终由谁负责。',
                       'plant': [volume['first'], volume['first']],
                       'payoff': [volume['end'], volume['end']],
                       'required': True, 'continues': False}]}


REVEAL_LADDER = {1: ('null', 'hinted'), 2: ('hinted', 'suspected'), 3: ('suspected', 'confirmed')}


def chapter_rows(book, volume_outline=None, with_hook_refs=True, with_scenes=False):
    """单卷章纲行：enter/exit 链＋增量声明＋承诺动作，由同一 scratch 状态推进生成。
    with_scenes=True 时每章声明一场完整场景（依赖声明 complete → 索引化投影路径）。"""
    contract_ = book['contract']
    volume = contract_['volumes'][0]
    scratch = copy.deepcopy(book['state'])
    rows = []
    for n in range(volume['first'], volume['end'] + 1):
        rows.append(_chapter_row(scratch, contract_, volume, n, with_hook_refs, with_scenes))
    return {'volume': volume['id'], 'chapters': rows}


def _scene_row(n):
    return {'label': '核对现场', 'intent': '核对第%s批退件。' % _cn(n),
            'conflict': '签字制度挡着开箱。', 'turn': '凭据矛盾浮出。',
            'present': ['shen'], 'speakers': ['shen'],
            'dialogue_intents': [{'entity': 'shen', 'seeks': '查清来历。', 'withholds': '不提违规开箱。',
                                  'pressure': '登记制度压着。', 'tactic': '拿旧凭据对照。',
                                  'knowledge_topics': ['source']}],
            'reads': [{'kind': 'knowledge', 'key': 'shen:source'}, {'kind': 'clock', 'key': 'main'}],
            'depends_on': []}


def _chapter_row(scratch, contract_, volume, n, with_hook_refs, with_scenes=False):
    row = {'chapter': n,
           'synopsis': '沈桐核对第%s批退件的封条与签字，花掉车费并移动核对位置，'
                       '对凭据来历形成新的判断。' % _cn(n),
           'plot': {'beat': '沈桐核对封条与签字，逼出下一处矛盾。', 'nodes': [], 'threads': []},
           'resources': [], 'places': [], 'knowledge': [], 'characters': [], 'relations': [],
           'clock': {'advance_days': 1}, 'enter': [], 'exit': [],
           'disclosures': [], 'world_refs': ['rules:r1', 'geography:office', 'characters:shen'],
           'new_entities': [], 'hook_refs': [], 'hooks': [], 'reader_refs': [], 'history_refs': [],
           'scenes': [], 'pacing': {},
           'style': {'pov': '第三人称限知',
                     'rhythm': '短句交代动作，核对结果后用完整句说明后果。'}}
    if with_scenes:
        row['scenes'] = [_scene_row(n)]
        row['dependency_coverage'] = 'complete'
    deltas = []
    # clock
    deltas.append(('clock', 'clock', scratch['clock'], scratch['clock'] + 1))
    scratch['clock'] += 1
    # resources：每章花一元车费
    for key in sorted(scratch.get('resources') or {}):
        current = int(scratch['resources'][key])
        if current >= 1:
            row['resources'].append({'key': key, 'from': str(current), 'to': str(current - 1),
                                     'reason': '核对退件时花掉一趟车费。'})
            deltas.append(('resources', key, str(current), str(current - 1)))
            scratch['resources'][key] = str(current - 1)
            break
    # places：两地点间交替移动
    if scratch.get('placements') and len(scratch.get('places') or {}) >= 2:
        ident = next(iter(sorted(scratch['placements'])))
        current = scratch['placements'][ident]
        target = next(p for p in sorted(scratch['places']) if p != current)
        row['places'].append({'entity': ident, 'from': current, 'to': target,
                              'route': '从' + scratch['places'][current]['name'] + '走到'
                                       + scratch['places'][target]['name'] + '。',
                              'reason': '换到另一处核对退件。'})
        deltas.append(('places', ident, current, target))
        scratch['placements'][ident] = target
    # knowledge：揭示档位阶梯
    step = REVEAL_LADDER.get(n)
    if step:
        key = 'shen:source'
        row['knowledge'].append({'who': 'shen', 'topic': 'source', 'from': None if step[0] == 'null' else step[0],
                                 'to': step[1], 'reason': '本章核对让沈桐对来源多了一层判断。'})
        deltas.append(('knowledge', key, None if step[0] == 'null' else step[0], step[1]))
        scratch.setdefault('knowledge', {})[key] = {'status': step[1]}
    # hooks：首章 plant、末章 payoff；中间章 hook_refs 承接（内联回带的引用面）
    if n == volume['first']:
        row['hooks'].append({'hook': HOOK_ID, 'action': 'plant', 'note': '本卷开篇埋下对读者的具体承诺。'})
    if n == volume['end']:
        row['hooks'].append({'hook': HOOK_ID, 'action': 'payoff', 'note': '本卷末兑现本卷承诺。'})
    if with_hook_refs and n != volume['first'] and n != volume['end']:
        row['hook_refs'] = [HOOK_ID]
    for kind, key, before, after in deltas:
        enter_kind = 'character' if kind == 'characters' else kind
        enter_key = 'main' if kind == 'clock' else key
        row['enter'].append({'kind': enter_kind, 'key': enter_key, 'expected': before})
        row['exit'].append({'kind': enter_kind, 'key': enter_key, 'expected': after})
    return row


def _cn(number):
    digits = '零一二三四五六七八九'
    return ''.join(digits[int(d)] for d in str(number))


# --------------------------------------------------------------------------------------------------
# 正文与证据句：每句带章号词保证唯一；clock 句带时间标记；place 句含起讫地点名。
# --------------------------------------------------------------------------------------------------
PLACE_NAMES = {'office': '值班室', 'yard': '仓库后院'}


def prose_for(chapter, moves, hook_action):
    """第 chapter 章的正文与逐字证据表 {kind: quote}。moves=(from_place, to_place)。"""
    frm, to = moves
    quotes = {
        'clock': '次日清晨，沈桐开始第%s批退件的核对。' % _cn(chapter),
        'resources': '他花掉一元车费，登记第%s批核对记录。' % _cn(chapter),
        'places': '他从%s走到%s，核对第%s批封条。' % (PLACE_NAMES[frm], PLACE_NAMES[to], _cn(chapter)),
        'knowledge': '凭据来历的第%s层判断落定。' % _cn(chapter),
    }
    if hook_action == 'plant':
        quotes['hook'] = '第%s批退件凭据的来历，最终要由经手人负责交代。' % _cn(chapter)
    elif hook_action == 'payoff':
        quotes['hook'] = '第%s批退件凭据的来历由沈桐当众交代，责任就此落实。' % _cn(chapter)
    else:
        quotes['hook'] = ''
    prose = '。'.join(q for q in quotes.values() if q) + '。'
    return prose, quotes


def moves_for(chapter):
    """章纲的 places 交替：奇数章 office→yard，偶数章 yard→office。"""
    return ('office', 'yard') if chapter % 2 else ('yard', 'office')


def hook_action_for(chapter, volume):
    if chapter == volume['first']:
        return 'plant'
    if chapter == volume['end']:
        return 'payoff'
    return None


def draft_for(book, chapter):
    """一章的完整提交：正文＋drift_check（由 drift_reconcile._planned 自动生成覆盖行）。"""
    volume = book['contract']['volumes'][0]
    plan = book['plans'][str(chapter)]
    action = hook_action_for(chapter, volume)
    prose, quotes = prose_for(chapter, moves_for(chapter), action)
    items = []
    for entry in _planned(plan):
        kind, key = entry['kind'], entry['key']
        if kind == 'hook':
            items.append({'kind': 'hook', 'key': key, 'planned': entry['planned'],
                          'status': 'kept', 'actual': {'action': entry['planned']['action']},
                          'evidence': {'chapter': chapter, 'quote': quotes['hook']}})
        elif kind == 'clock':
            items.append({'kind': 'clock', 'key': key, 'planned': entry['planned'],
                          'status': 'kept', 'actual': {'advance_days': entry['planned']['advance_days']},
                          'evidence': {'chapter': chapter, 'quote': quotes['clock']}})
        elif kind == 'resources':
            items.append({'kind': 'resources', 'key': key, 'planned': entry['planned'],
                          'status': 'kept', 'actual': {'to': entry['planned']['to']},
                          'evidence': {'chapter': chapter, 'quote': quotes['resources']}})
        elif kind == 'places':
            items.append({'kind': 'places', 'key': key, 'planned': entry['planned'],
                          'status': 'kept', 'actual': {'to': entry['planned']['to']},
                          'evidence': {'chapter': chapter, 'quote': quotes['places']}})
        elif kind == 'knowledge':
            items.append({'kind': 'knowledge', 'key': key, 'planned': entry['planned'],
                          'status': 'kept', 'actual': {'to': entry['planned']['to']},
                          'evidence': {'chapter': chapter, 'quote': quotes['knowledge']}})
        else:                                  # characters/relations：夹具不声明，防御分支
            raise AssertionError('夹具未覆盖的增量种类：' + kind)
    return {'title': '第%s章 核对' % _cn(chapter),
            'summary': plan['synopsis'][:20], 'self_check': '本章按章纲完成核对与承诺载体。',
            'prose': prose, 'drift_check': {'items': items, 'unplanned': [], 'verdict': 'clean'}}


# --------------------------------------------------------------------------------------------------
# 组装：开书→安装章纲（章纲资源冻结）→后续逐章提交
# --------------------------------------------------------------------------------------------------
def open_installed_book(chapters=CHAPTERS, with_scenes=False):
    book = pipeline.open_book(contract(chapters), '夹具导入', world_fixture())
    volume = book['contract']['volumes'][0]
    outline = volume_row(volume)
    report = pipeline.install_outlines(book, volume['id'], outline,
                                       chapter_rows(book, with_scenes=with_scenes))
    return book, outline, report


def submit_chapters(book, store, through=None):
    """逐章：差量信封（冒烟组装）→提交→账本推进。返回每章结果。"""
    volume = book['contract']['volumes'][0]
    last = through or volume['end']
    results = []
    for n in range(volume['first'], last + 1):
        envelope = pipeline.envelope(book, store, n)
        assert envelope['required'], '每章信封必须有必读记录'
        results.append(pipeline.submit(book, store, n, draft_for(book, n)))
    return results
