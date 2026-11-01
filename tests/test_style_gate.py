"""文风体系：内置档规格渲染进信封与简报、外部档案源、参数级换档、最近 5 章滚动
基线门可触发（提交门子集）。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

import copy

import pytest

from novel_ledger_lite import pipeline, style
from novel_ledger_lite.contracts import Error
from novel_ledger_lite.store import LiteStore

import fixtures
from fixtures import contract, draft_for, open_installed_book, prose_for, moves_for

ARCHIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'style_archive_sample.md')


def test_envelope_refused_without_author_style_and_lists_options():
    """用例一（执笔前置强制）：契约未显式选定文风 → 写章派工被引擎直接拒绝，
    返回「文风未选定」状态并列出可选项（内置五档各一句话定位＋外部档案接入方法），
    由主控拿去问作者；recontract_patch 显式选定后同章派工放行。"""
    raw = contract()
    raw.pop('style_profile', None)                             # 模拟作者未选文风
    book = pipeline.open_book(raw, '夹具导入', fixtures.world_fixture())
    volume = book['contract']['volumes'][0]
    pipeline.install_outlines(book, volume['id'], fixtures.volume_row(volume),
                              fixtures.chapter_rows(book))     # 章纲门不涉文风，放行
    store = LiteStore()
    with pytest.raises(Error) as caught:
        pipeline.envelope(book, store, 1)
    assert caught.value.code == 'style_profile'
    details = caught.value.details
    assert details['status'] == 'style_not_selected'
    board = details['options']
    assert [row['profile'] for row in board['builtin']] == \
        ['市井修仙', '账房掌门', '神秘学双声部', '宗族史传', '科幻错位幽默']
    assert all(row['line'] for row in board['builtin'])
    assert 'style-distill' in board['external'] and 'style_source' in board['external']
    assert '不使用默认档放行' in board['note']
    # 引擎自身提供同一块板面（主控随时可取，不替作者猜偏好）：
    assert pipeline.style_board() == board
    # 作者经 recontract_patch 显式选定后，同章派工放行：
    pipeline.recontract_patch(book, source='作者原话：选账房掌门', style_profile='账房掌门')
    envelope = pipeline.envelope(book, store, 1)
    assert envelope['brief'].find('文风规格') >= 0 and '账房掌门' in envelope['brief']


def test_envelope_and_brief_carry_selected_profile_spec():
    """用例二（选定后放行）：契约显式选定档名 → 写章派工放行，信封与简报必须带
    所选档的文风规格：档名、契约声线、基线说明。"""
    raw = contract()
    raw['style_profile'] = '账房掌门'
    book = pipeline.open_book(raw, '夹具导入', fixtures.world_fixture())
    volume = book['contract']['volumes'][0]
    pipeline.install_outlines(book, volume['id'], fixtures.volume_row(volume),
                              fixtures.chapter_rows(book))
    store = LiteStore()
    envelope = pipeline.envelope(book, store, 1)
    records = {name: store.read_document(key) for name, key in envelope['records'].items()}
    spec = records['style']
    assert spec['profile'] == '账房掌门' and spec['source_kind'] == 'builtin_catalog'
    assert spec['guard'] == 'observe' and spec['anchor']['origin'] == 'default'
    assert '滚动中位' in spec['baseline_note']
    assert envelope['brief'].find('文风规格') >= 0 and '账房掌门' in envelope['brief']
    # 组级共享包登记生效档（L0 的文风锚身份）。
    group_row = pipeline.group(book, store, 'v1', size=5)
    assert group_row['pack']['style']['profile'] == '账房掌门'


def test_external_style_archive_is_effective_source():
    """外部文风档案（style-distill《文风档案.md》）：契约 style_source 登记→信封
    style_archive 携带全文、source_kind 标外部、简报注明；与内置档二选一。"""
    raw = contract()
    raw['style_source'] = ARCHIVE
    book = pipeline.open_book(raw, '夹具导入', fixtures.world_fixture())
    volume = book['contract']['volumes'][0]
    pipeline.install_outlines(book, volume['id'], fixtures.volume_row(volume),
                              fixtures.chapter_rows(book))
    store = LiteStore()
    envelope = pipeline.envelope(book, store, 1)
    records = {name: store.read_document(key) for name, key in envelope['records'].items()}
    assert records['style']['source_kind'] == 'external_archive'
    assert records['style']['style_source'] == ARCHIVE
    assert '文风档案' in records['style_archive']['content']
    assert '外部档案' in envelope['brief']
    # 最小样例档案驱动基线兜底路径：外部档案时代码仍回落注册锚（样例不带量化锚时）。
    assert records['style_anchor']['origin'] in ('default', 'pilot')


def test_style_baseline_gate_triggers_on_shape_drift():
    """最近 5 章滚动基线检查（提交门子集）可触发：strict 守卫下，第 2 章句均长
    相对第 1 章基线的偏离超过容差 → style_* finding 拒绝候选。"""
    raw = contract()
    raw['style_guard'] = 'strict'
    book = pipeline.open_book(raw, '夹具导入', fixtures.world_fixture())
    volume = book['contract']['volumes'][0]
    pipeline.install_outlines(book, volume['id'], fixtures.volume_row(volume),
                              fixtures.chapter_rows(book))
    store = LiteStore()
    assert pipeline.submit(book, store, 1, draft_for(book, 1))['ok']
    # 第 2 章：同量级字数、但全部长句（3 句、句均 ~34 字 vs 基线 ~15 字）。
    sentences = ['次日清晨沈桐从仓库后院走到值班室核对第二批封条并把登记册翻到新的一页',
                 '他花掉一元车费登记第二批核对记录，凭据来历的第二层判断在他心里落定成形',
                 '第二批退件凭据的来历要由经手人负责交代，他把这句写进登记册的备注栏']
    prose = '。'.join(sentences) + '。'
    quotes = {'clock': sentences[0] + '。', 'places': sentences[0] + '。',
              'resources': sentences[1] + '。', 'knowledge': sentences[1] + '。', 'hook': ''}
    from fixtures import hook_action_for, moves_for
    assert hook_action_for(2, volume) is None                  # 中间章无 hook 动作
    plan = book['plans']['2']
    items = []
    from novel_ledger_lite.drift_reconcile import _planned
    for entry in _planned(plan):
        kind = entry['kind']
        evidence_quote = quotes[kind]
        require_quote = {'chapter': 2, 'quote': evidence_quote}
        if kind == 'clock':
            items.append({'kind': kind, 'key': entry['key'], 'planned': entry['planned'],
                          'status': 'kept', 'actual': {'advance_days': entry['planned']['advance_days']},
                          'evidence': require_quote})
        elif kind == 'hook':
            items.append({'kind': kind, 'key': entry['key'], 'planned': entry['planned'],
                          'status': 'kept', 'actual': {'action': entry['planned']['action']},
                          'evidence': require_quote})
        else:
            items.append({'kind': kind, 'key': entry['key'], 'planned': entry['planned'],
                          'status': 'kept', 'actual': {'to': entry['planned']['to']},
                          'evidence': require_quote})
    draft = {'title': '第二章 长句', 'summary': plan['synopsis'][:20],
             'self_check': '本章按章纲完成核对。', 'prose': prose,
             'drift_check': {'items': items, 'unplanned': [], 'verdict': 'clean'}}
    result = pipeline.submit(book, store, 2, draft)
    assert not result['ok']
    style_findings = [f for f in result['findings'] if f.get('criterion', '').startswith('style_')]
    assert style_findings, result['findings']
    assert any(f['metric'] == 'sentence_mean' for f in style_findings)
    # observe 档下同款偏离只观察不拒绝：形状变化记录为 observation，候选不被 style 拦。
    book2 = pipeline.open_book({**contract(), 'style_guard': 'observe'}, '夹具导入',
                               fixtures.world_fixture())
    volume2 = book2['contract']['volumes'][0]
    pipeline.install_outlines(book2, volume2['id'], fixtures.volume_row(volume2),
                              fixtures.chapter_rows(book2))
    store2 = LiteStore()
    assert pipeline.submit(book2, store2, 1, draft_for(book2, 1))['ok']
    result2 = pipeline.submit(book2, store2, 2, copy.deepcopy(draft))
    assert result2['ok']
    report = result2['row']['review']['style_report']
    assert report['observations'], 'observe 档应记录形状观察'


def test_recontract_patch_switches_profile_param_level():
    """运行中换档走参数级变更：档名校验、换档点登记、来源留档必填。"""
    book, _, _ = open_installed_book()
    with pytest.raises(Error):
        pipeline.recontract_patch(book, source='')                        # 来源必填
    with pytest.raises(Error):
        pipeline.recontract_patch(book, source='作者原话', style_profile='不存在的档')
    report = pipeline.recontract_patch(book, source='作者原话：换账房掌门', style_profile='账房掌门')
    assert book['contract']['style_profile'] == '账房掌门'                 # 逐字进契约
    assert report['switch'] == {'at': 5, 'profile': '账房掌门', 'previous': '市井修仙'}
    assert book['style_switch']['at'] == 5


def test_recontract_patch_external_source_and_baseline_cutoff():
    """外部档案换档＋换档点基线语义：at 之前的章节不进新档滚动基线，锚回落新档注册锚。"""
    book, _, _ = open_installed_book()
    with pytest.raises(Error):
        pipeline.recontract_patch(book, source='作者原话', style_source='不存在.md')
    report = pipeline.recontract_patch(book, source='作者原话：改用外部档案', style_source=ARCHIVE)
    assert book['contract']['style_source'] == ARCHIVE
    assert report['style_source'] == ARCHIVE
    # 换档点语义（style.switch_cutoff）：cutoff=5 之后 recent 里的旧章（1~4）全部被切，
    # 基线回落新生效源的注册锚（档名仍默认档、origin=default）。
    book['style_switch'] = {'at': 5, 'profile': '账房掌门', 'previous': '市井修仙'}
    book['contract']['style_profile'] = '账房掌门'
    assert style.switch_cutoff(book) == 5
    recent = [(n, style.metrics(prose_for(n, moves_for(n), 'plant')[0])) for n in range(1, 5)]
    anchor = style.current_anchor(book, recent)
    assert anchor['origin'] == 'default' and anchor['profile'] == '账房掌门'
    # 换档点之前的书（无 switch）：同窗口正常产出滚动基线。
    book['style_switch'] = {}
    anchor_before = style.current_anchor(book, recent)
    assert anchor_before['origin'] == 'rolling'
