"""差量信封：投影索引化（近窗/远窗/pinned/点名）、conservative 告警、两类锚句、
design_drift 活跃切片、组级快照、信封尺寸与书龄无关。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

import copy

import pytest

from novel_ledger_lite import compose, delta as delta_ledger, facts, pipeline, store as store_module
from novel_ledger_lite.contracts import Error, digest

import fixtures
from fixtures import chapter_rows, contract, draft_for, open_installed_book, prose_for, volume_row, world_fixture


def test_scoped_state_near_far_pinned_named():
    """投影索引化三道保险（报告 §4.3 第三层）逐项验证：
    近窗全文、远窗标题行、pinned 常驻、点名整条恢复。"""
    state = facts.seed(contract())
    state['facts'].update({'shen:old%d' % i: '陈年旧事第%s件。' % i for i in range(50)})
    state['facts']['shen:hot'] = '近期仍在变化的事实。'
    state['facts']['shen:pinned_fact'] = '主角核心设定，作者标记常驻。'
    state['knowledge']['shen:source'] = {'claim': 'x', 'source': 's', 'stance': 'knows', 'evidence': {}}
    index = {'facts\x00shen:hot': 95}                       # 近窗条目（末次变更章 95）
    plan = {'chapter': 100, 'dependency_coverage': 'complete',
            'scenes': [{'id': 's1', 'reads': [{'kind': 'knowledge', 'key': 'shen:source'}],
                        'depends_on': []}],
            'participants': ['shen']}
    view, warnings = compose.scoped_state(
        state, index, ['shen'], plan, 100, near=30,
        pinned=[{'kind': 'facts', 'key': 'shen:pinned_fact'}])
    assert warnings == []
    assert view['material_scope']['mode'] == 'declared_dependencies'
    assert view['facts']['shen:hot'] == '近期仍在变化的事实。'           # 近窗全文
    assert view['facts']['shen:pinned_fact'].startswith('主角核心设定')  # pinned 全文常驻
    assert view['facts']['shen:old0'].get('_ref') is True              # 远窗标题行
    assert view['facts']['shen:old49']['last_chapter'] == 0
    assert view['knowledge']['shen:source']['claim'] == 'x'            # 章纲点名整条恢复
    # 初始态（从未 settle 更新）按远窗处理——作者用 pinned 堵「30 章未提即失忆」。
    assert view['facts'].get('shen:hot') is not None


def test_conservative_fallback_warns_instead_of_silent_trim():
    """声明缺失 → conservative 全量＋显式告警（方案三立场：不静默裁剪）。"""
    state = facts.seed(contract())
    state['facts']['shen:a'] = '甲'
    plan = {'chapter': 5, 'dependency_coverage': 'partial', 'scenes': [], 'participants': ['shen']}
    view, warnings = compose.scoped_state(state, {}, ['shen'], plan, 5)
    assert view['facts']['shen:a'] == '甲'
    assert any(w['code'] == 'conservative_projection' for w in warnings)


def test_drift_slice_rules():
    """design_drift 活跃切片判定（登记制 id 交集）：当前卷无条件必达；更早卷按交集；
    已吸收归档不再出现。"""
    contract_ = contract()
    contract_['volumes'] = [{'id': 'v1', 'purpose': 'p', 'first': 1, 'end': 4},
                            {'id': 'v2', 'purpose': 'q', 'first': 5, 'end': 8}]
    book = {'design_drift': [
        {'id': 'd1', 'chapter': 2, 'kind': 'resources', 'key': 'k', 'reason': 'r',
         'participants': ['shen'], 'hook_refs': []},                 # 当前卷
        {'id': 'd2', 'chapter': 0, 'kind': 'knowledge', 'key': 'k', 'reason': 'r',
         'participants': ['shen'], 'hook_refs': []},                 # 更早卷、id 交集命中
        {'id': 'd3', 'chapter': 0, 'kind': 'places', 'key': 'k', 'reason': 'r',
         'participants': ['ghost-liu'], 'hook_refs': []},            # 更早卷、无交集 → 不达
        {'id': 'd4', 'chapter': 1, 'kind': 'facts', 'key': 'k', 'reason': 'r',
         'participants': ['shen'], 'hook_refs': [], 'absorbed_by': [2]},  # 已吸收 → 归档
    ], 'state': {'entities': {'shen': {}, 'ghost-liu': {}}}}
    plan = {'chapter': 5, 'participants': ['shen'], 'hook_refs': [], 'reader_refs': [], 'history_refs': []}
    slice_ = compose.drift_slice(book, plan, 5, contract_)
    ids = {row['id'] for row in slice_['active']}
    assert ids == {'d1', 'd2'}
    assert slice_['archived_count'] == 1


def test_envelope_carries_anchors_and_previous_chapter():
    """差量信封：前 1 章全文＋前情锚句（hook_refs 引用驱动）＋场景锚句（窗口驱动）。"""
    book, _, _ = open_installed_book()
    store = store_module.LiteStore()
    assert pipeline.submit(book, store, 1, draft_for(book, 1))['ok']
    envelope = pipeline.envelope(book, store, 2)
    records = {name: store.read_document(key) for name, key in envelope['records'].items()}
    # 前文窗口降维：默认只带前 1 章全文。
    assert 'previous_chapter:1' in envelope['required']
    assert all(not name.startswith('previous_chapter:0') for name in envelope['records'])
    # 前情锚句：第 2 章 hook_refs 点名 hook-v1-required（第 1 章 plant），原句内联。
    anchors_record = records.get('anchor_sentences')
    assert anchors_record is not None
    prior_quotes = anchors_record['prior']['anchors']
    assert any(a['asset'] == fixtures.HOOK_ID and a['op'] == 'hook' for a in prior_quotes)
    # 场景锚句：前窗首/末事件 quote＋summary 行。
    assert anchors_record['scene']['anchors'][0]['chapter'] == 1
    assert anchors_record['scene']['anchors'][0]['quotes']
    # 简报与信封同源：brief 里带前情锚句小节。
    assert '前情锚句' in envelope['brief']
    # L4 历史层在场（可选读），recall 由此兜底。
    assert 'history_source' in envelope['records']
    assert 'history_source' not in envelope['required']


def test_envelope_conservative_warning_travels_with_task():
    """partial 章纲的信封携带 projection_warnings（告警随冻结输入走，不静默）。"""
    book, _, _ = open_installed_book()          # 夹具默认 scenes=[] → partial
    store = store_module.LiteStore()
    envelope = pipeline.envelope(book, store, 1)
    assert envelope['warnings']
    assert any(w['code'] == 'conservative_projection' for w in envelope['warnings'])
    assert 'projection_warnings' in envelope['records']


def test_group_pack_shared_and_chapter_delta_thinner():
    """组级快照（方案二每组一份＋方案一第四刀）：首章带 L0/L1 内嵌；组内续章带
    组包引用＋前章 delta——均摊更薄。信封时序遵守报告 §3.0：每章信封在该章派工时点
    现编（前章已提交），组尾信封的 previous_deltas 才可编译。"""
    book, _, _ = open_installed_book(with_scenes=True)
    store = store_module.LiteStore()
    group_row = pipeline.group(book, store, 'v1', size=2)
    assert group_row['members'] == [1, 2]
    head = pipeline.envelope(book, store, 1, group_row)
    assert 'contract' in head['required']                     # 组首章：L0 必读
    assert pipeline.submit(book, store, 1, draft_for(book, 1))['ok']
    tail = pipeline.envelope(book, store, 2, group_row)
    assert 'contract' not in tail['records']                  # 组内续章：L0 不重复计费
    tail_records = {name: store.read_document(key) for name, key in tail['records'].items()}
    assert tail_records['group_pack']['ref'] == group_row['hash']
    assert 'previous_deltas' in tail['records']
    assert any(row['chapter'] == 1 for row in tail_records['previous_deltas'])


def test_envelope_size_stays_flat_as_book_ages():
    """核心收益的曲线形状断言：远窗条目只携带标题行——投影尺寸与远窗条目的
    内容长度无关（完整版 partial 路径下这些条目全文进包，随书龄线性变胖）。"""
    plan = {'chapter': 100, 'dependency_coverage': 'complete',
            'scenes': [{'id': 's1', 'reads': [{'kind': 'clock', 'key': 'main'}], 'depends_on': []}],
            'participants': ['shen']}
    sizes = []
    for text_length in (20, 200):
        state = facts.seed(contract())
        state['facts'].update({'shen:legacy%d' % i: '陈年旧事' * (text_length // 4) + '。'
                               for i in range(500)})
        index = {('facts\x00shen:legacy%d' % i): 1 for i in range(500)}   # 末次变更章＝1（远窗）
        view, warnings = compose.scoped_state(state, index, ['shen'], plan, 100, near=30, pinned=[])
        assert warnings == []
        far_rows = [k for k, v in view['facts'].items() if isinstance(v, dict) and v.get('_ref')]
        assert len(far_rows) == 500                          # 远窗全部标题行
        sizes.append(len(str(view['facts'])))
    # 标题行尺寸与远窗条目内容长度无关：条目文本放大 10 倍，投影字节不变。
    assert sizes[0] == sizes[1]
    # 全文进包的对照形态（完整版行为）会随内容线性变胖：
    full_form = sum(len(v) for v in state['facts'].values())
    assert sizes[1] < full_form // 2


def test_envelope_requires_frozen_outline():
    book, _, _ = open_installed_book()
    store = store_module.LiteStore()
    with pytest.raises(Error):
        pipeline.envelope(book, store, 99)
