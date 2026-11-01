# 差量信封与账本语义（lite 流程参考）

> 与完整版的差异：本文描述的组装规则只存在于 lite——完整版 novel-ledger 每次派工携带
> 整份投影与整表 design_drift（context.py 的 complete_state/complete_hooks 逐章冻结副本），
> lite 改为五层账本 L0-L4 的差量信封；机械门的判定对象与完整版逐字同源，变的只是材料
> 怎么进上下文。完整版无本文所述的 delta/checkpoint/倒排/组级共享包/锚句内联。

## 一、信封里有什么（compose.build，现编现冻）

编时点＝该章派工时（前章正文与事件已提交、哈希已在链上）。每份信封是内容寻址冻结物，
`records` 是记录名→文档键，`required` 是必读清单：

| 记录 | 层 | 必读条件 | 内容 |
|---|---|---|---|
| `contract`、`style_anchor` | L0 | 组首章（无组时每章） | 契约全文；文风卷首锚（首个 checkpoint 后冻结） |
| `volume_outline` | L1 | 组首章 | 本卷卷纲行 |
| `chapter_outline` | L2 | 每章 | 本章冻结章纲行（enter/exit 链＋增量声明＋drift_check 的核对对象） |
| `state` | L2 | 每章 | 索引化投影（见下节） |
| `design_drift` | L2 | 有活跃漂移时 | 活跃切片＋归档计数＋判定规则说明 |
| `hooks` | L2 | 每章 | 到期承诺切片（open 且本章 hook_refs/参与者关联） |
| `world_records`、`disclosure_boundary` | L2 | 有世界模型时 | 本章 world_refs＋参与者关联的世界记录（mysteries 不下发）＋幕后真相边界 |
| `word_budget` | L2 | narrative_tracking 时 | 本章字数带 |
| `style` | L2 | 每章 | 文风规格（必读）：生效文风源（内置档名或外部档案标识 source_kind）＋契约声线字段＋当前基线锚（最近 5 章滚动中位，与提交门比对同源）＋合并容差＋卷走向＋本章执行点；简报「文风规格」小节与本记录同源 |
| `style_archive` | L2 | 外部文风源时 | style-distill《文风档案.md》全文（契约 style_source 登记；与内置档二选一，此时 style_profile 保留作标识） |
| `group_pack` | 组 | 组内续章（可选读） | 组级共享包引用：契约/卷纲/投影基线/文风锚/活跃 hooks，已随组首章交付 |
| `previous_deltas` | L3 | 组内续章（可选读） | 组内前章 state_delta（重放段） |
| `anchor_sentences` | L3 | 有锚可抽时 | 前情锚句（章纲引用驱动）＋场景锚句（前窗开篇/收束句＋summary） |
| `scene_sources` | L3 | 跨章场景依赖时 | 被依赖场景的定义行＋所在章哈希 |
| `previous_chapter:N` | — | 每章 | 前文窗口（默认 1 章）全文 |
| `previous_chapters` | — | 每章 | 窗口索引＋prose 哈希＋summary |
| `history_source` | L4 | 可选读 | 页链快照＋链头哈希（recall 兜底取页用） |
| `projection_warnings` | — | 有告警时 | conservative 回退等显式告警 |

组内均摊：组首章内嵌 L0/L1 必读；续章只带引用＋差量，字节随组内章数递减，
且与书龄无关（tests/test_envelope.py::test_envelope_size_stays_flat_as_book_ages 验证：
远窗条目内容放大 10 倍，投影字节不变）。

## 二、索引化投影（scoped_state）

完整场景声明（`dependency_coverage=complete`＋逐场 `reads`/`depends_on`）时：

- 近窗（`near_window_chapters`，默认 30）内变更过的条目带全文；
- 远窗条目只带标题行 `{'_ref': True, 'last_chapter': n}`；
- 契约 `pinned` 点名的条目永远全文常驻——堵「30 章未提即失忆」；
- 章纲 `reads`/`hook_refs`/`history_refs`/`reader_refs` 点名的条目整条恢复；
- 身份登记表（entities）、站位、空间链、活跃线路与承诺是当前态，恒全文；
- 初始态（从未 settle 更新）按远窗处理，需要常驻请显式 pinned。

声明缺失时回退 **conservative 全量**（参与人相关，与完整版 partial 路径同形）并在
`projection_warnings` 显式告警——不静默裁剪。补齐声明重新冻结章纲后恢复薄投影。

## 三、design_drift 活跃切片（登记制 id 交集）

- 当前卷内未吸收 → 无条件必达；
- 更早卷未吸收 → 仅当参与者 id 交集、hook_refs 交集、或被该章 reader_refs/history_refs 点名；
- 已吸收（`absorbed_by` 有值）或已归档 → 不再出现（只剩 `archived_count`）。

吸收回写在章纲安装门核对：章纲行 `absorbs: [漂移id]` 必须存在且未吸收，通过即登记
`absorbed_by=[章号]`。误漏边界：漂移行 participants 须为登记 id（`book_state.check_book`
拦截），声明错 id 时交集失效的残余风险由作者审阅与（完整版的）continuity 兜底。

## 四、两类锚句（anchors.py，零模型抽取，逐字核验）

- **前情锚句**（引用驱动）：章纲 `hook_refs`/`history_refs`/`reader_refs` 点名的资产经
  L4 倒排定位到章，从该章冻结 events 抽 `evidence.quote` 原句——章纲点名多少抽多少；
- **场景锚句**（窗口驱动）：前窗（`scene_anchor_chapters`，默认 2）已提交章各取首/末事件
  quote＋summary 行。

两类都经 `evidence.evidence` 对冻结正文逐字核验；抽不出的（引文缺失/不一致）记入
`unmatched` 留痕，宁缺毋滥。

## 五、卷界与完本

- 卷末自动：全量 checkpoint（state＋哈希入账）＋差异单——`required_unpaid`（封线承诺
  显式点名）、`open_continues`（带入下卷的承诺）、`drift`（登记总数/已吸收/吸收率）、
  `written_han`、checkpoint 哈希；
- 非卷界每 `checkpoint_chapters`（默认 50）章同样落全量 checkpoint 兜底；
- 文风卷首锚：首个 checkpoint 冻结 `style_volume_anchor`（checkpoint 章号＋投影哈希），此后每
  `anchor_review_chapters`（默认 50）章向 `book['anchor_reviews']` 追加一条 observation
  （只登记回比时点与锚身份，不含数值偏离、不拦截、不进差异单 dict）；
- 完本验收 `pipeline.verify_full`：逐章 events 全量重放核对投影哈希＋逐章重算链哈希
  ＋未清承诺清单——不依赖 delta（delta 是派生数据，真源在链上）；分段/抽样不进 lite。
- delta 损坏恢复 `delta.rebuild(book, store)`（`from novel_ledger_lite import delta`）：从最近
  checkpoint 重放 events 重建，数据零丢失。

## 六、提交门与 draft 形状

`pipeline.submit(book, store, chapter, draft)`，draft 必须带
`{title, prose, summary, self_check, drift_check}`，`drift_check={items, unplanned, verdict}`：

- items 一行不多一行不少地覆盖章纲计划增量（含 hook 的 plant/payoff 各一行）；
- 每行带 `status: kept|deviated|skipped`、实际结果与 `evidence:{chapter, quote}`
  （quote 逐字取自本章正文）；
- deviated/skipped 必须写 reason；verdict 与实际偏差互相反证。

拒绝时返回 `{'ok': False, 'findings': [...]}`，账本不变；通过时返回
`{'ok': True, 'chapter', 'row', 'delta', 'volume_boundary'}`。findings 的
`criterion` 与完整版同一词汇表（drift_coverage/drift_before/evidence/hook_due/repetition/
style_*/substance…），同样出现在信封简报的「提交前自检」清单里——简报要求什么，
引擎就核什么。
