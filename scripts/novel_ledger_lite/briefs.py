"""Writing briefs with inline verified quotes and explicit submission checks.

引用与文风规格使用信封中的相同记录；常规写作不逐条重读未变更历史。"""
from __future__ import annotations

from .contracts import policy_default
from .drift_reconcile import _planned


DELTA_HINTS = {
    'resources': '每笔资源从多少到多少与章纲一致，消耗有来源、得到有去处，数量守恒（不足会被拒）。'
                 'actual.from 由引擎投影，不要照抄章纲当既成事实。',
    'places': '人物从哪到哪与章纲一致，移动有过渡与耗时，不出现未登记地点，不瞬移。',
    'knowledge': '每个人只知道他该知道的：章纲写 hinted/suspected/confirmed 的，正文要有来源情节；'
                 '越界知情须从本章正文修掉，不能凭依据或 deviated 改变固定章纲；除 retracted 外不得无由倒退。',
    'characters': '人物变化有 choice（他选了什么）与 cost（付了什么）两个落点；'
                  '章纲声明的变化须在正文落实，漏写就返修；章纲未声明变化时保留原状态。',
    'relations': '章纲 relations 声明的关系变化逐条对上（key 形如 甲>乙:关系名）：to 用稳定短词，'
                 '上一章的 to 就是本章的 from，逐字承接；kept 申报的 to 必须与章纲逐字相同，'
                 '两端的实体须已登记。本章没有关系变化就不申报。',
    'clock': '本章推进天数与章纲一致，不倒退；章号不等于天数，同日续接不必为验收补造过夜。',
    'node': 'plot.nodes 写 seeded/advanced/resolved 的节点，正文里必须真发生：该埋的埋、该收的收；'
            '同一节点不得重复推进或已 resolved 后再推；改做或漏做须诊断并返修本章正文。',
    'thread': 'plot.threads 的线路状态（active/dormant/resolved）与正文一致；'
              '已 resolved 的线路不得重新启用，dormant 的线路要交代它为何搁置。',
    'hook': '本章声明的伏笔动作逐条对上：plant 的那一次要在正文里有读者能看见的具体载体'
            '（一件物、一句话、一个动作），payoff 的那一次是真兑现而不是再提一次；'
            '卷末 required 的必须在本卷内收（引擎在卷内状态链收尾校验），continuity 上的跨卷条目允许仍 open。',
    'disclosure': '本章声明的读者披露逐项给出实际档位和正文引文，不越过章纲，也不默认已经落实。',
}


NATURAL_PROSE_GUIDE = (
    '读材料 style 与生效文风档案，按冻结声线写，不要另外发明规则。'
    '写你知道的事：人物眼前的利益、他在意什么、他不愿明说的事，让细节从使用和忽略中自然出现。'
    '对白让人说话——直说、绕开、言不由衷或沉默都可以，动机不必说透。'
    '用动作和具体物件承载情绪，少用形容词解释感受。'
    '事实与知情边界按章纲固定，措辞和节奏自由展开。'
    '同时落实 core_context 与本章职责：关键选择有既定动机，能力运用有前提和边界，'
    '承诺兑现须有实际内容。人物可因经历改变，静章与余波可按设计承接；'
    '不能用临时新能力、无由改志或反复预约代替章纲规定的结果。'
)


def _check_block(plan):
    kinds = list(dict.fromkeys(entry['kind'] for entry in _planned(plan)))
    rows = [(kind, DELTA_HINTS[kind]) for kind in kinds if kind in DELTA_HINTS]
    if not rows:
        return []
    return ['## 提交前自检（逐项与章纲比对）',
            '本章纲声明了哪些计划增量，drift_check.items 就必须一行不多、一行不少地覆盖它们；'
            '逐项核账写入 drift_check；self_check 补充本章文风落实与实际修订依据，无需重抄核账：',
            *['- %s：%s' % (kind, hint) for kind, hint in rows], '']


def _style_block(spec):
    """文风规格小节：生效文风源（内置档名或外部档案）＋契约声线字段＋基线与守卫说明。
    spec 为空（直调简报的旧路径）时降级为一句档名提示，不空转。"""
    if not spec:
        return []
    lines = ['## 文风规格（本章生效，与材料 style 记录一致）']
    if spec.get('source_kind') == 'external_archive':
        lines.append('- 生效文风源：外部档案（UTF-8 Markdown，材料 style_archive 全文；'
                     '档名 %s 仅作标识）。' % spec.get('profile', ''))
    else:
        lines.append('- 生效文风档：%s（内置目录档；其注册锚是首章认可前的形状地板）。'
                     % spec.get('profile', ''))
        lines.append('- 内置写法读 style_guide 的冻结执行摘要；完整分析可经 style_reference 按需补读。')
    lines.append('- 声线、节奏、滚动基线与容差读 style；冻结核心约束读 core_context，不另复制规格。')
    return lines


def write_brief(book, chapter, plan, anchor_pack, style_spec=None):
    """The one page a writing dispatch needs. 锚句清单与简报同源（同一 plan 引用），因此
    「点名多少抽多少」两侧一致；文风规格小节带生效档名（或外部档案）与基线说明——
    与信封 style 记录一致，写进简报的就是提交门将比对的同一组数字。"""
    prior = (anchor_pack or {}).get('prior') or {}
    scene = (anchor_pack or {}).get('scene') or {}
    spec = style_spec if isinstance(style_spec, dict) else {}
    anchor_lines = []
    for quote in prior.get('anchors') or []:
        anchor_lines.append('- [%s#%d] %s：原句见 anchor_sentences。' % (
            quote['ref_kind'], quote['chapter'], quote['asset']))
    if not anchor_lines:
        anchor_lines.append('- 本章纲未点名可内联的历史原句；需要更早前文时用 recall 按倒排定位。')
    scene_lines = []
    for row in scene.get('anchors') or []:
        scene_lines.append('- [%d] 开篇、收束与摘要见 anchor_sentences。' % row['chapter'])
    near = policy_default('adjacent_window_chapters')
    lines = [
        '## 本阶段任务（write·第 %d 章）' % chapter,
        '按冻结章纲执笔本章正文：事实与知情边界按章纲固定；行动、阻力、选择与后果可以跨章承接，'
        '静章可停留于关系或余波。提交 {title, summary, self_check, prose, drift_check}。',
        '',
        '## 写作材料怎么读（差量信封）',
        '- 必读见 required：core_context 为核心约束，chapter_outline 是唯一章纲正文，'
        'state 为当前真值与近期历史，dependencies 说明已核验依赖。当前状态不按年龄淘汰。',
        '- recall_manifest 提供未携带资源的名称、ID 和定位片段；需要时向宿主请求 '
        'pipeline.catalog 搜索/翻页，再调 pipeline.resource 取完整值；历史证据用 recall。'
        '目录片段不能代替真值，未携带不代表不存在，人物知情与读者知情不能混用。',
        '- 前文只带前 %d 章全文；更早的前情靠下面的锚句与 scene_sources，不再整章携带。' % near,
        '- design_drift 只带活跃切片（当前卷未吸收＋登记 id 交集命中的更早卷漂移）；'
        '已吸收条目已归档，不再出现。',
        '- 若材料带 projection_warnings：章纲依赖声明不完整，投影已回退 conservative 全量'
        '；准备者核对本章必需前提，缺料或冲突则补齐并重包。告警本身不证明材料已缺失，'
        '也不保证语义依赖完整；不能为恢复薄投影而静默删料。',
        '',
        '## 前情锚句（章纲点名的历史原句，已逐字核验）',
        *anchor_lines,
        '',
        '## 场景锚句（前窗开篇/收束句＋summary）',
        *scene_lines,
        '',
        *_style_block(spec),
        '## 写作方法',
        NATURAL_PROSE_GUIDE,
        '',
        *_check_block(plan),
        '## 内联回带纪律',
        '引用已内联、无需 recall；确需更长前文时向宿主请求 recall（宿主先查倒排定位、'
        '再取页下发，Worker 不做历史翻页），禁止为「再确认」逐条重读未变更记录。',
    ]
    return '\n'.join(lines)
