# 上下文组装与交付

五层账本保存契约、卷级材料、章级状态、章间增量与历史事件。每次派工从同一真源编译
四类上下文：核心约束、本章执行包、衔接材料、补读目录。账本格式与派工协议分开演进。

## 单章 Markdown 写作包

准备者在上一章通过 `submit` 后生成下一待写章，正文写作者只读生成的文件：

```python
from pathlib import Path

package = pipeline.chapter_package(book, store, chapter, group_row)
path = Path(f"第{chapter:04d}章写作包.md")
path.write_text(package["text"], encoding="utf-8")
pipeline.validate_chapter_package(book, store, path.read_text(encoding="utf-8"))
# 将 path 交给写作者；写作后由准备者使用 pipeline.submit 核账。
```

`group_row` 可省略。生成时检查账本与存储进度，仅允许下一待写章，且不使用会话缓存。
除常规必读材料外，它逐页展开本章相关目录中未携带条目的完整当前值；目录片段不作为事实。
若准备者知道还需要其他资源或更长前文，可在重生成时指定
`extra_resources=[{"kind": "facts", "key": "人物ID:事实ID"}]` 和 `extra_chapters=[已提交章号]`。
指定资源或历史章节不存在时拒绝生成。写作者发现信息缺失或冲突时停止，说明需求，由准备者
检索、核实并重新生成；禁止依据缺失信息猜测。自动检查不能证明章纲的语义依赖已完全声明。

文件内含版本、账本与章节链指纹及正文内容摘要；`validate_chapter_package` 接受文件文本或返回的
package，在正文写作和提交前校验。账本、已提交章节或文件内容变更后应重新生成，不能沿用旧包。
提交仍使用既有 `submit` 与核账，不由写作包替代。补充全部相关条目会增加输入量；人物知情、
读者知情与作者掌握的信息仍须分别遵守包内边界，不能因为资料出现在包中就直接披露。

## 每章材料

| 记录 | 交付规则 | 内容 |
|---|---|---|
| core_context | 每章必读，不缓存省略 | 作者契约的关键原文、主角限制、结局方向、声线、章长与当前卷职责 |
| chapter_outline | 每章必读 | 唯一一份冻结章纲；payload 只引用这个记录名 |
| dependencies | 每章必读 | 汇总的依赖坐标、已存在或尚未建立的状态、校验范围说明 |
| state | 每章必读 | 相关当前状态、必需知情话题、近期历史与材料范围说明 |
| volume_context | 默认必读，仅准确缓存确认后省略 | 本卷执行方向及本章节点、线路定义 |
| style | 每章必读 | 生效声线、文风档、当前滚动基线、容差与章内节奏 |
| style_guide | 内置文风时默认每章必读，仅准确缓存确认后省略 | 从所选真实档案冻结的执行摘要，附完整档案引用 |
| style_reference | 可选补读 | 内置文风完整档案及参考分析，存储一次，常规派工不重复携带全文 |
| style_archive | 外部文风时默认每章必读，仅准确缓存确认后省略 | 已冻结的完整文风档案 |
| world_records / disclosure_boundary | 有世界模型时必读 | 本章引用与人物相关记录；相关谜团的披露边界，不携带全部幕后真相 |
| hooks / design_drift / word_budget | 相关时必读 | 当前义务、活跃偏差及章节字数范围 |
| previous_chapter:N / previous_chapters | 相邻章存在时必读 | 前一章全文与章节定位 |
| anchor_sentences / scene_sources | 有引用时必读 | 已核验的历史原句、前两章首末事件与摘要、所依赖场景 |
| recall_manifest | 每章必读 | 未携带资源的名称、ID、80 字以内定位片段、总数与翻页入口 |
| contract / volume_outline / group_pack | 可选背景 | 完整契约、完整卷纲与冻结组首时点快照；当前章真值以 core_context 和 state 为准 |
| previous_deltas / style_anchor / style_volume_anchor / history_source | 可选背景 | 增量、注册锚、锚身份与历史寻址指针，不在常规派工中重复携带 |

简报列执行规则、原句与场景的记录位置、当前适用的自检种类；它不再重抄章纲、引文、
声线和整套数值规格。`style` 已带当前生效锚，注册锚只作可选背景。

## 当前状态与历史的边界

`facts/resources/relations/character_current` 是当前有效值。本章相关人物的这些条目
不因最后变更时间久远而变成标题或消失。身份、站位、持有链、相关地点拓扑也完整保留。
作者应将持续有效的限制放在当前事实中，经过与旧案材料放在 historical_assertions，
避免把每件历史事件永久堆进当前状态。

`knowledge` 是所列人物的知情切片，`reader_knowledge` 是读者知情切片。明确需要的
话题始终完整携带；其他话题按近窗选择并提供补读入口，省略不能解释为人物不知道。
`developments` 的未点名事件列表仅带近期部分；人物当前变化由 character_current 承载。

pinned 与场景显式读取项完整保留。缺少完整依赖声明时保守携带相关背景并告警；即使
回退，当前值、pinned 与明确读取项也不丢失。当前值本身过多时材料会变大，不能为满足
Token 目标裁掉必需事实。

## 依赖检查

从场景 present/speakers、人物和资源变化、关系端点、知情话题、enter/exit、preconditions、
节点前置、伏笔引用及 pinned 汇总依赖。派工前验证坐标存在、世界引用存在、章纲前态
一致；缺失或冲突返回 Error(context_dependencies)，不得写完后才发现缺少前提。

本章计划初次建立的资源或明确声明为空的前态记录为 not_established，不将它们伪造为
已存在值。新实体由章纲说明身份，实际成立仍须正文提交与结算。

complete 是声明，不是语义完整性的证明。自动检查也只能覆盖可枚举引用，无法证明作者
没有遗漏未表达的约束；这种边界必须保留给实际正文评估。

## 补读和定位

`pipeline.catalog(book, chapter=章号, kind=种类, query=关键词, page=0, per=20)` 搜索或翻页；
省略 chapter 时查询全书账本。可按稳定 ID、人物名或定位片段搜索，单页上限 100。
目录片段不替代真值，选中后调 `pipeline.resource(book, kind, key)` 取完整当前值。
地点定义使用 kind=place_records，人物站位使用 placements。需要历史证据再调 recall。
目录查询、补读和生成正文的次数由调用方记录，不能把补读视为零成本。

## 会话与缓存

没有缓存确认时，每章都能独立使用。宿主可以确认当前写作者确实已加载某些文档：

```python
cache = {"context_id": "current-writer-session", "loaded": [archive_hash, volume_context_hash]}
work = pipeline.envelope(book, store, chapter, group_row, cache=cache)
delivery = pipeline.materialize(work, store, cache=cache)
```

仅内容哈希完全一致的 style_guide、style_archive、volume_context 可以省略正文。core_context、章纲、
当前状态、依赖报告和补读目录每章仍必读。缓存确认不进入书账本，不跨会话自动继承。
新会话、重载后的新写作者或上下文压缩后应清除确认。即使复用了带缓存标记的旧任务，
materialize 没收到当前确认也会补齐相应文档。宿主对确认真实性负责，哈希本身不是模型记忆。

## 实际交付与度量

派工协议为 novel-ledger-lite.task/2；payload.chapter_outline 引用记录名，正文只在该记录
出现一次。通过 `pipeline.materialize` 得到实际交付文本，不再把整份任务卡、章纲和简报
重复拼接。可选背景只保留在存储中；相同文档内容仅渲染一次，其他记录以名称指向它。

返回 metrics 包含总 UTF-8 字节、by_record、四类材料的 category_bytes、元数据和简报字节、
缓存记录数。可传 `token_counter(text)` 与 tokenizer_id 得到真实渲染文本的 Token 数。
Token 分项的和不保证等于完整文本计数；不同分词器、缓存策略与模型的成本需另行核算。

## 账本推进与恢复

候选提交须精确覆盖章纲增量，证据逐字存在，前态、时间、资源、义务和重复门全部通过
后才推进账本。卷末保存 checkpoint 和差异单。完本验收校验章节完整性、真源内容哈希、
正文证据、逐章投影及链哈希、最终状态和未清承诺。拒绝候选不会改写书账本。

`delta.rebuild(book, store, through=n)` 选不晚于 n 的最近快照，无合适快照则从种子重放，
返回状态和实际恢复到的章号。仅接受账本 `novel-ledger-lite/2`、存储 `novel-ledger-lite.store/2`
与文件 `novel-ledger-lite.bundle/2`；派工任务必须准确匹配 task/2，不能仅凭版本后缀通过。
缺少提交时契约哈希、初始契约、进度或冻结档案的数据直接报错；进度不自动修正，
组包必须已存在于内容库，不从内嵌快照补建。没有旧版兼容或升级路径。
