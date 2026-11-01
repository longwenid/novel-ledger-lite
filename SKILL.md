---
name: novel-ledger-lite
description: 千万字级精简写作引擎：按《千万字级规模化架构提案》推荐架构（五层账本 L0-L4＋差量信封）实现「章纲资源冻结→快速执笔」最小完整闭环。每章写作上下文最小充分（前 1 章全文＋锚句内联＋近窗投影）、派工简报自足（引用已内联、recall 只是兜底）、机械漂移防线保留必要子集（章纲链模拟、提交对账、引文逐字、8 章重复窗、settle 前值硬核、到期拦截、最近 5 章滚动文风基线）；文风须作者本人显式选定（内置五档或外部《文风档案.md》路径，未选定时执笔派工被引擎拒绝并返回可选项板面，无默认档放行）、规模档位解除 t6 封顶（t7 支持千万字短章写法 3000~5000 章、百卷 rolling）。当项目已有冻结的契约、世界模型、卷纲与章纲文本（完整版 novel-ledger 或作者产出），要逐章快速连写且体量指向千万字（t7、百卷级 rolling、千章以上）时使用本技能；开书十三门、世界模型/卷纲/章纲的设计派工、返修循环、修订链、独立读者 continuity 与无人值守主机协议仍属完整版 novel-ledger——两者分工见下文边界表。不用于修改本技能或完整版引擎自身。
---

# novel-ledger-lite（精简引擎）

设计定稿与裁剪依据见 **DESIGN.md**（推荐架构哪些进了 lite、哪些没进、为什么；
逐字同源/裁剪/新增的模块级清单）。本文只写引擎实际提供的行为。

## 与完整版 novel-ledger 的分工边界

| 场景 | 用谁 |
|---|---|
| 开书十三门、契约形成、世界模型派工 | novel-ledger（lite 的契约是**直接导入**形态，经 `planning.validate_contract` 校验） |
| 卷纲/章纲的**设计派工**（让 Worker 写卷纲、写章纲） | novel-ledger（lite 不派设计工；章纲文本就绪后由 lite 的**机械门**冻结） |
| 逐章快速执笔（章纲资源已冻结） | **lite**（差量信封＋提交门＋账本推进） |
| 返修预算/route_repair 循环、修订链与 revision-impact | novel-ledger（lite 提交门拒绝候选后由调用方按 findings 修正重提，无返修预算机） |
| 独立读者 continuity、无人值守 watch/租约/worker-next、host/governance | novel-ledger（lite 是纯 Python API，无主机协议；千万字项目建议照旧在完整版开 continuity=required，见 DESIGN.md「已知限制」） |
| 千章以上/t7/百卷 rolling | **lite**（完整版 SCALE_TIERS 封顶 t6=1540 章；lite 增 t7 至 5000 章） |
| 存量项目续写（旧书已在完整版账上） | novel-ledger（lite 没有旧书迁移路径：它只从 `open_book` 新建账本起步，不读完整版的 sqlite 项目） |

两个技能互不改动对方：lite 是独立包 `scripts/novel_ledger_lite/`，机械判定底盘与
完整版逐字同源（同源清单见 DESIGN.md §三）。

## 最短路由：章纲资源就绪 → 正文交付

前提（调用方备齐，lite 不生成）：契约 JSON、世界模型 JSON（可选）、每卷卷纲行、
该卷章纲数据 `{volume, chapters:[...]}`。以下为宿主会话逐条调用的 Python API
（无 CLI；`sys.path.insert(0, r'<lite>/scripts')` 后 `from novel_ledger_lite import pipeline`）：

```text
1  book = pipeline.open_book(contract, source, world_model)      # 契约校验＋账本种子；世界可选
       └─ ★作者选文风（正文前必要步骤，引擎机械强制）：contract.style_profile 点名内置
          五档之一，或 contract.style_source 登记 style-distill《文风档案.md》路径
          （与内置档二选一，开书校验存在）。契约缺失两者＝「未选定」状态：执笔派工
          被拒绝（Error code=style_profile，details 带 status=style_not_selected 与
          options 板面——内置五档各一句话定位＋外部接入方法），由主控拿去问作者；
          引擎不提问、不猜偏好、不用默认档放行。板面也可随时取：pipeline.style_board()。
          作者选定后经契约字段或 recontract_patch 写入，杜撰档名拒绝。
2  每卷一次：pipeline.install_outlines(book, volume_id, 卷纲行, {volume, chapters})
       ├─ 通过 → 章纲资源冻结落账（plans/volumes_outline/chapter_outlines）
       ├─ 抛 Error → 章纲文本不合格（链断裂/越界/协议旧），修文本重交，账本不变
       └─ 章纲行 absorbs: [漂移id] → 安装门核对回写 absorbed_by
3  每组一次：group_row = pipeline.group(book, store, volume_id, size=5)
       └─ 组级共享包（L0/L1＋投影基线＋文风锚＋活跃 hooks）每组一份；同卷再次调用自动接续下一段
4  每章循环（组内逐章）：
   envelope = pipeline.envelope(book, store, chapter, group_row)   # 现编现冻的差量信封
       ├─ 简报带「文风规格」小节（生效档名或外部档案＋契约声线＋基线说明）；
       │  外部档案时 style_archive 全文随信封下发
       → Worker 按 envelope['brief'] 写作，交 draft{title, prose, summary, self_check, drift_check}
   result = pipeline.submit(book, store, chapter, draft)           # 提交门（全机械）
       ├─ 含最近 5 章滚动文风基线检查（observe 只观察；strict 下形状偏离超容差拒绝候选）
       ├─ result['ok'] → 账本推进（状态/delta/索引/倒排/链哈希）；卷末自动出差异单＋checkpoint
       └─ result['ok']=False → 按 result['findings'][i]['criterion'] 修正 draft 重提；账本不变
5  卷界：result[-1]['volume_boundary']（差异单：required 未兑/open 带入下卷/漂移吸收率/checkpoint 哈希/累计汉字）；
       文风卷首锚回比另记于 book['anchor_reviews']（首个 checkpoint 冻结锚，之后每 50 章一条 observation）
6  完本：pipeline.verify_full(book, store)                        # 全量重放为默认验收语义
7  pipeline.save(book, store, path) / pipeline.load(path)         # 落盘/重载
```

运行中辅助入口：`pipeline.recall(book, store, asset)`（倒排定位→取页，无匹配空返回）、
`pipeline.status(book, store, page, per)`（章行分页）、`delta.rebuild(book, store)`
（`from novel_ledger_lite import delta`；delta 损坏后从 checkpoint＋events 重放恢复）、`pipeline.recontract_patch(book,
source='作者原话', style_profile=档名 或 style_source=档案路径)`（运行中换档：参数级变更，
来源留档必填；换档点 style_switch.at 之前章节保留原档、不进新档滚动基线）。

## Worker 侧读材料规则（写进派工引导）

- 必读记录以信封 `required` 清单为准；`records` 里的 `group_pack`/`history_source` 是可选补读。
- 前文只带前 1 章全文；更早前情看简报「前情锚句」（章纲点名的逐字原句）与「场景锚句」
  （前 2 章开篇/收束句＋summary）。**引用已内联、无需 recall**；确需更长前文时向宿主请求——
  宿主调 `pipeline.recall` 先查倒排定位、再取页下发（Worker 无翻页工具），禁止逐条重读未变更记录。
- 状态投影按近窗（默认 30 章）索引：远窗条目只有标题行 `{'_ref': True, 'last_chapter': n}`，
  完整值由宿主经 `group_pack`（组首章时点的投影基线）或 `history_source`（页链→各章 events）
  补读下发；标题行条目未选≠不存在。lite 信封不含完整版的 `complete_state` 全量副本。
- 信封带 `projection_warnings` 时：章纲依赖声明不完整、投影已回退 conservative 全量——
  照常写作不受影响；调用方补齐 `scenes[].reads/depends_on` 后恢复薄投影。
- `design_drift` 只带活跃切片（当前卷未吸收＋id 交集命中的更早卷漂移）；已吸收条目已归档。

## 契约与档位要点（lite 实际校验的）

- 契约直接导入：结构校验同一张 CONTRACT_FIELDS 表；差量化键 `pinned`（`[{kind,key}]`，
  作者标记全文常驻条目）、`near_window_chapters`、`checkpoint_chapters` 可覆盖默认。
- 文风：**作者本人显式选定是执笔前置条件**（契约无 style_profile/style_source 时写章
  派工被拒并返回可选项板面，无默认档放行）；`style_profile` 取内置五档（枚举校验，
  与完整版同表同源）；`style_source` 登记外部《文风档案.md》路径（style-distill 产出）
  与内置档二选一；运行中换档走 `recontract_patch` 参数级变更。档位定位、锚点差异与
  基线逻辑见 `references/style.md`，防漂移说明见 `DESIGN.md` §二。
- 档位：t6（按 aim 写法约 1538 章）之外增 t7——word_range [10M, 17.5M]、
  chapter_window [3000, 5000]、volume_count 30（可配至 100）、chapter_aim 3500；
  守卫测试断言每档窗口落在 word_range×章长界推出的全域内（1667~2999 章中章写法缺口
  仍属完整版决策，lite 不覆盖）。
- 阶段策略：rolling 卷纲＋volume 章纲合法（百卷路径）；多卷 rolling＋all 章纲拒绝。

## 测试

```bash
cd C:\Users\longwen\.zcode\skills\novel-ledger     # 完整版目录里也能跑（conftest 自带引导）
python -m pytest ../novel-ledger-lite/tests -q      # 本轮 45 passed（含文风 9 项）
```

## 详细参考

- `references/architecture.md` —— 差量信封的逐记录语义、两类锚句、告警与补读、
  卷界差异单、验收与恢复（流程必需的唯一参考文档，开头声明与完整版的差异）。
- `references/style.md` —— 内置五档目录与锚点差异、style_profile/style_source 两条
  文风源路径、换档与滚动基线说明。
- `DESIGN.md` —— 架构落地情况（含文风体系）、防漂移基线说明（§二）、裁剪清单、
  千万字支撑机制、已知限制、同源/改造/新增清单。
