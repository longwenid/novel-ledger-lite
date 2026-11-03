"""契约与简报：契约校验、t7 档位与窗口断言、差量化默认值、write 简报生成。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

import pytest

from novel_ledger_lite import briefs, contracts, planning
from novel_ledger_lite.contracts import DEFAULTS, SCALE_TIERS, contract_errors, policy_default, tier_of, tier_window_band


def test_contract_validates_and_derives_word_range():
    from fixtures import contract
    raw = contract()
    raw.pop('word_range', None)
    validated = planning.validate_contract(raw)
    volumes = validated['volumes']
    assert validated['word_range'] == [volumes[-1]['end'] * 30, volumes[-1]['end'] * 200]
    assert validated['near_window_chapters'] == DEFAULTS['near_window_chapters']
    assert validated['checkpoint_chapters'] == DEFAULTS['checkpoint_chapters']


def test_contract_rejects_unknown_fields_and_bad_pinned():
    from fixtures import contract
    raw = contract()
    raw['no_such_field'] = 1
    assert any('未知约定字段' in c for c in contract_errors(raw))
    raw = contract()
    raw['pinned'] = [{'kind': 'facts'}]              # 缺 key 定位键
    assert any('pinned' in c for c in contract_errors(raw))


def test_t7_tier_unlocks_thousand_chapter_serials():
    """规模档位收尾：t7 解除 t6 封顶，覆盖千万字短章写法（3000~5000 章）。"""
    t6 = tier_of({'tier': 't6'})
    t7 = tier_of({'tier': 't7'})
    assert t6 is not None and t7 is not None
    # t7 章窗覆盖 3000~5000 章；卷数 30 起步、上限可配到 100。
    assert t7['chapter_window'] == [3000, 5000]
    assert t7['volume_count'] == 30
    assert t7['volume_count_max'] == 100
    # 千万字主体落在 t7 字数区间：10M 下限与 t6 上限衔接。
    assert t7['word_range'][0] == t6['word_range'][1]
    # 短章写法（2000 字/章）下千万字 ≈ 5000 章，必须落进 t7 窗口。
    chapters_at_floor = t7['word_range'][0] // t7['chapter_min']
    assert t7['chapter_window'][0] <= chapters_at_floor <= t7['chapter_window'][1]
    # 卷数可配区间合法：百卷 rolling 路径合法（planning 只拒 rolling+all 组合）。
    policies = planning.outline_policies({'volume_outline': {'scope': 'rolling', 'words': 2500, 'tolerance': 500},
                                          'chapter_outline': {'scope': 'volume', 'words': 150, 'tolerance': 60},
                                          'volumes': [{'id': 'v%d' % i, 'purpose': 'p', 'end': i * 40}
                                                      for i in range(1, 101)]})
    assert policies['volume_outline']['scope'] == 'rolling'


def test_tier_window_band_assertion():
    """窗口无洞断言（lite 口径）：每档 chapter_window 落在该档 word_range×章长界推出的
    全域内；t6/t7 各自覆盖其体量声明下的短章写法。"""
    for row in SCALE_TIERS:
        lo, hi = tier_window_band(row)
        assert lo <= row['chapter_window'][0] and row['chapter_window'][1] <= hi, row['id']
    t6, t7 = tier_of({'tier': 't6'}), tier_of({'tier': 't7'})
    # t7 的 aim 写法（3500 字/章）章数也须落在窗口内。
    aim_chapters_lo = t7['word_range'][0] // t7['chapter_aim']
    aim_chapters_hi = t7['word_range'][1] // t7['chapter_aim']
    assert t7['chapter_window'][0] <= aim_chapters_hi
    assert aim_chapters_lo <= t7['chapter_window'][1]
    # PIPELINE_SHAPES 形状守卫：新增档位必须声明形状。
    assert contracts.PIPELINE_SHAPES.get('t7') is not None


def test_style_catalog_five_profiles_and_enum_gate():
    """内置文风档目录（五档）：档名枚举是唯一通道——杜撰拒绝。"""
    from fixtures import contract as fixtures_contract
    assert set(contracts.STYLE_CATALOG) == {'市井修仙', '账房掌门', '科幻错位幽默', '宗族史传', '神秘学双声部'}
    assert len(contracts.STYLE_CATALOG) == 5
    raw = fixtures_contract()
    raw['style_profile'] = '玄幻公馆体'                       # 杜撰档名
    assert any('style_profile' in c and '市井修仙' in c for c in contract_errors(raw))
    # 每档注册锚齐备（首章认可前的形状地板）：七项滚动指标非零。
    for name, entry in contracts.STYLE_CATALOG.items():
        for key in ('han', 'sentences', 'sentence_mean', 'sentence_short_share',
                    'paragraph_mean', 'paragraph_max', 'dialogue_share'):
            assert entry['anchor'].get(key), (name, key)


def test_style_profile_explicit_only_no_default_fallback():
    """style_profile 契约口径（2026-11-02 作者要求收紧）：选定档名逐字进契约；
    缺失＝「未选定」状态（validate 后无该字段），不落默认档——执笔派工被
    compose.build 前置检查拒绝，杜撰值仍被 choices 枚举拒绝。"""
    from fixtures import contract as fixtures_contract
    raw = fixtures_contract()
    raw.pop('style_profile', None)                     # 模拟作者未选文风的契约
    validated = planning.validate_contract(raw)
    assert 'style_profile' not in validated or not validated.get('style_profile')
    chosen = planning.validate_contract({**fixtures_contract(), 'style_profile': '宗族史传'})
    assert chosen['style_profile'] == '宗族史传'              # 选定档名逐字保留


def test_style_source_contract_field():
    """外部文风源字段：登记《文风档案.md》路径；契约层只做形状，存在性在开书校验。"""
    from fixtures import contract as fixtures_contract
    archive = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'style_archive_sample.md')
    validated = planning.validate_contract({**fixtures_contract(), 'style_source': archive})
    assert validated['style_source'] == archive
    from novel_ledger_lite import pipeline
    from novel_ledger_lite.contracts import Error
    with pytest.raises(Error):
        pipeline.open_book({**fixtures_contract(), 'style_source': '不存在.md'}, '夹具导入')


def test_delta_envelope_defaults():
    """差量化旋钮的单一来源：窗口降维 1 章全文、场景锚句 2 章、近窗 30、checkpoint 50。"""
    assert DEFAULTS['adjacent_window_chapters'] == 1
    assert DEFAULTS['scene_anchor_chapters'] == 2
    assert DEFAULTS['near_window_chapters'] == 30
    assert DEFAULTS['checkpoint_chapters'] == 50
    assert DEFAULTS['anchor_review_chapters'] == 50
    for key in ('adjacent_window_chapters', 'scene_anchor_chapters', 'near_window_chapters',
                'checkpoint_chapters', 'anchor_review_chapters'):
        assert isinstance(policy_default(key), int)


def test_write_brief_inlines_anchors_and_recalls_as_fallback():
    """内联回带的简报面：锚句清单随简报走；recall 明写为兜底通道。"""
    from fixtures import contract, open_installed_book, prose_for, moves_for
    book, outline, _ = open_installed_book()
    plan = book['plans']['2']
    anchor_pack = {'prior': {'anchors': [{'ref_kind': 'hook_ref', 'asset': 'hook-v1-required',
                                          'chapter': 1, 'op': 'hook',
                                          'quote': prose_for(1, moves_for(1), 'plant')[1]['hook'],
                                          'start': 0}],
                             'unmatched': []},
                   'scene': {'anchors': [{'chapter': 1, 'summary': '第一章摘要。',
                                          'quotes': [{'chapter': 1, 'start': 0,
                                                      'quote': prose_for(1, moves_for(1), 'plant')[1]['clock'],
                                                      'position': 'open'}]}],
                             'unmatched': []}}
    text = briefs.write_brief(book, 2, plan, anchor_pack)
    assert '前情锚句' in text and 'hook_ref#1' in text
    assert '场景锚句' in text
    assert '无需 recall' in text and '倒排定位' in text
    assert 'projection_warnings' in text or 'conservative' in text or '差量信封' in text
