# novel-ledger-lite 设计定稿

日期：2026-11-02　｜　依据：《千万字级规模化架构提案》修订版 r2
（`novel-ledger/out/scaling-architecture-proposal.md`）的评审推荐要点；本文回答四件事：
推荐架构哪些机制进了 lite、哪些没进（为什么）、裁剪清单、千万字支撑与已知限制。
所有行为以 `scripts/novel_ledger_lite/` 实际代码为准；本文宣称的可验证行为均有对应测试
（`python -m pytest ../novel-ledger-lite/tests -q` → 45 passed，本轮亲跑（含文风 9 项））。

## 一、推荐架构落地情况

### 进了 lite（引擎代码＋测试在位）

| 评审推荐要点 | lite 落点 | 验证 |
|---|---|---|
| 五层账本 L0-L4＋差量信封（方案一主线） | `compose.build`：L0 契约/文风锚、L1 卷纲行、L2 章层（章纲行＋索引化投影＋活跃漂移切片＋world_records）、L3 delta＋锚句、L4 页链＋倒排；信封现编现冻、内容寻址 | test_envelope 全组；test_pipeline 全链路 |
| 内联回带（第一优先） | `anchors.prior_anchors`：章纲 hook_refs/history_refs/reader_refs → 倒排定位 → events 的 evidence.quote 逐字内联进简报「前情锚句」；简报明写 recall 只是兜底 | test_envelope::test_envelope_carries_anchors… |
| design_drift 活跃化（方案二规则＋吸收归档） | `compose.drift_slice`：当前卷未吸收无条件必达；更早卷按登记 id 交集/点名必达；已吸收归档；安装门核对 `absorbs` 回写；漂移行 participants 登记校验（`book_state.check_book`） | test_envelope::test_drift_slice_rules；test_outline_gate 两例 |
| 投影索引化＋三道保险（方案一＋方案三立场） | `compose.scoped_state`：近窗全文/远窗标题行、章纲点名整条恢复、pinned 常驻、conservative 全量＋`projection_warnings` 显式告警（不静默裁剪） | test_envelope 前三例 |
| 状态 delta+checkpoint（每卷全量＋章间增量） | `delta.produce/bump_index/checkpoint`；卷末自动全量 checkpoint＋每 50 章兜底；`rebuild` 从 checkpoint＋events 重放恢复（数据零丢失）；delta 不新增哈希（章行 state_hash＋链哈希为真源） | test_ledger::test_checkpoint…、test_rebuild…、test_verify_full… |
| 组级快照（方案二「每组一份」） | `compose.group_pack`＋`pipeline.group`：L0/L1＋投影基线＋文风锚＋活跃 hooks 每组一份；组首章内嵌必读、续章引用＋组内前章 delta；同卷重复调用自动接续下一段 | test_envelope::test_group_pack…；test_pipeline::test_group_freezing… |
| 前文窗口降维＋场景锚句（先锚句后降维） | `adjacent_window_chapters` 默认已降为 1 章全文；`anchors.scene_anchors` 取前 2 章首/末事件 quote＋summary 补语感 | test_envelope::test_envelope_carries_anchors… |
| required/sealed 通道（方案三补丁 a） | 取「卷界差异单显式列出」路径：卷末 `required_unpaid` 点名封线承诺结余（执笔侧 closed 产出通道未做，见「没进」） | test_pipeline::test_volume_diff_lists_required_sealed_channel |
| 文风卷首锚（方案三补丁 b） | 首个 checkpoint 冻结 `style_volume_anchor`，每 50 章回比（observation 级，进 `anchor_reviews`，不拦截）；堵滚动基线跟漂＋换档重置盲区 | test_ledger::test_checkpoint…（冻结断言） |
| recall 倒排（方案三补丁 c） | settle 顺路维护 asset→chapters 倒排（hook/reader_knowledge/historical/entity/development）；`pipeline.recall` 先定位后取页，miss 空返回 | test_ledger::test_recall_uses_inverted_index |
| 规模档位收尾 | SCALE_TIERS 增 t7（[3000,5000] 章、卷数 30~100 可配）＋`tier_window_band` 窗口无洞口径＋PIPELINE_SHAPES 守卫；百卷 rolling+volume 合法（planning 只拒 rolling+all）；status 分页；headers 窗口参数（store 结构性替代全表扫描） | test_contracts 四例；test_ledger::test_status_pagination |
| 审计保守 | `verify_full` 全量重放为默认验收语义（逐章 events 重放＋链哈希重算＋未清承诺清单）；分段/抽样不进 lite | test_ledger::test_verify_full…（含篡改必翻） |
| **文风体系（作者要求不裁，全量接入；选定须作者显式——2026-11-02 追加强制）** | ①内置档目录五档与完整版同表同源（contracts.STYLE_CATALOG，锚点逐字复制）；②style_profile 契约同口径收紧：选定档名逐字进契约、杜撰拒绝（choices 枚举）；**「无偏好落默认档」回落逻辑已从 lite 移除**（contracts.style_profile default=None；resolve_style_profile/profile_anchor 未知或缺失档名返回 None，不静默选档）——契约缺失该字段＝「未选定」状态；③**执笔前置机械强制**：文风未选定（无内置档名且无外部档案路径）时写章派工在 compose.build 入口被直接拒绝（Error code=style_profile，details 带 status=style_not_selected＋options 板面：内置五档各一句话定位＋外部《文风档案.md》接入方法），由主控拿去问作者（板面随时可取 pipeline.style_board()）；引擎不提问、不猜偏好、不用默认档放行，章纲安装门不受影响；④外部文风源 style_source（style-distill《文风档案.md》路径，开书校验存在，信封 style_archive 携带全文，与内置档二选一）；⑤运行中换档 pipeline.recontract_patch 参数级变更（档名校验＋来源留档必填＋style_switch={at,profile,previous} 换档点，旧章不进新档基线）；⑥写章派工简报必带所选档文风规格（briefs._style_block，与信封 style 记录同源）；⑦最近 5 章滚动基线检查保留为提交门子集（见 §二） | test_contracts 三例（五档枚举/进契约且缺失=未选定/外部源字段）；test_style_gate 六例（未选拒绝＋板面＋选定后放行闭环/显式选定简报规格/外部档案生效/基线门触发/换档/换档点基线切割） |

提案 §5.7 显式落选机制（k 路并行、章纲分批确认、设计派工世界模型切片、整套 Registry
Ledger、完本审计切片化）lite 一律未做，与提案立场一致。

### 没进 lite（如实登记，含理由）

| 机制 | 理由 |
|---|---|
| 开书十三门、契约对齐、世界/卷纲/章纲设计派工 | lite 范围是「章纲资源冻结→快速执笔」；设计流程留在完整版，lite 契约是直接导入形态 |
| 返修预算/route_repair 循环、修订链与 revision-impact 分批授权 | 提案第六刀后两件属完整版修订面；lite 提交门拒绝候选后由调用方按 findings 修正重提（账本不变），无返修额度机 |
| 独立读者 continuity=required 的引擎化 | lite 无 continuity 派工协议；制度性建议（千万字默认开）由完整版承载，lite 文档如实转述 |
| `--fresh-context`/`read --save` 主机纪律 | 完整版 runtime.md 的宿主机制，lite 无主机协议；等价物是简报「内联回带纪律」（引用已内联、recall 兜底、禁止逐条重读未变更记录） |
| 跨组缓存 | 提案 §6.2-1 未决（跨组 Worker 会话连续性协议二选一），本期不实现——与提案同进退 |
| `touches` 跨卷长线到期未触 warning | 章纲门已同源核对 hook plant/payoff 窗口落点；「跨卷到期未触报 warning」这一半未做（提案 §5.6 登记项的后半） |
| checkpoint/delta 的 prune 回收（被超越的中间产物） | 提案第四刀的可回收项未实现：lite 的 checkpoints/deltas 只增不减，靠 verify_full 与 rebuild 保证正确性；回收策略待真实压测后定 |
| 执笔侧 hook `closed` 产出通道 | 方案三补丁 a 的另一半；lite 走差异单显式列出路径（上述），结算词汇表仍 open→paid(+closed) |
| 指纹账（minhash/advisory） | 提案 §6.2-4 二选一：lite 取倒排，指纹不进 |
| t7 覆盖 1667~2999 章中章写法 | 任务口径 t7=[3000,5000]；提案 §2.6 登记的更大缺口属完整版档位决策（测试注释已声明） |
| CLI 与无人值守（watch/租约/worker-next/identity） | lite 是纯 Python API，由宿主会话逐条驱动；无人值守主机协议留完整版 |

## 二、防漂移说明：最近 5 章滚动文风基线（提交门子集）

文风机械门是提交门的一部分（`pipeline.submit` → `style.examine`，零模型），基线逻辑：

1. **基线构造**：取最近 `STYLE_BASELINE_WINDOW = 5` 章已提交正文（约一个默认连写组），
   逐章测 `style.metrics`（句均长/短句占比/段均长/最长段/对白占比/章内四字重复率/人称
   标记七项派生指标），取**逐指标中位**为当前常态基线（`style.rolling_anchor`）。中位
   吸收单章处境（安静章/爆发章），不把一章现状当下一章配额；窗口 5＝默认组大小，滑动
   窗口使每章的边际比较只面对最近的常态——基线跟着书的自然演进走，又不被单章带跑。
2. **分级回落（lite 实际形态）**：窗口内只有一章已提交 → 该章实测即锚（origin=pilot，
   lite 无单独的「认可首章」流程，首章实测就是开卷参照）→ 无已提交章（或换档点切断了
   全部近期章）→ 内置档注册锚（origin=default）→ 外部文风源且无内置档名 → 锚为空
   （首章形状比较跳过，第二章起由滚动基线接管；lite 不解析外部档案中的量化值）。
   锚的 origin/basis 随信封 style 记录与简报同源下发，写手比对的就是提交门比对的同一组数字。
3. **换档点切割**：`style_switch.at` 之前的章节被 `style.current_anchor` 切掉——旧档
   章节不拖拽新档滚动中位，窗口全旧时回落新档注册锚（test_style_gate 的换档点用例）。
4. **判定分级**：`style_guard='observe'`（默认）只记 observation 可见不拦；
   `'strict'` 把相对基线偏离超容差（默认 0.35/0.35/0.40，契约 style_window 可逐卷覆盖）
   的形状变化判为 `style_*` finding 拒绝候选（test_style_gate::test_style_baseline_gate_
   triggers_on_shape_drift 驱动两侧）。样本可比性门槛（字数量级、句数下限）防止短样
   比长章的伪发现；章纲显式 dialogue_ratio 与章内四字重复率两档下都硬判。
5. **卷首锚回比**（第三层）：首个 checkpoint 冻结 `style_volume_anchor`（锚点＝该
   checkpoint 的章号与投影哈希），此后每 `anchor_review_chapters`（默认 50）章向
   `book['anchor_reviews']` 追加一条 observation 记录（不进差异单 dict、不拦截）——滚动
   基线「跟着最近常态走」的跟漂盲区由卷首锚显式点名，作者判断是演进还是漂移。
   如实边界：当前记录只登记回比时点与锚身份，不含数值偏离报告（数值比对待后续接入）。
6. 边界（如实）：人称代词分布只是观察项，不能判定实际叙述视角；形状一致不等于文学好
   ——文学质量不在机械校验范围（完整版 verification 同款声明）。

## 三、裁剪清单（完整版 → lite）

### 逐字同源（复制未改，机械判定与完整版一致）

`evidence`(40 行)、`entities`(68)、`narrative`(180)、`spatial`(126)、`continuity`(160)、
`craft`(106)、`drift`(747)、`drift_simulation`(499)、`drift_reconcile`(457)、`lint`(266)、
`style`(351)、`facts`(268)。含义：同一章纲与 drift_check 在两个引擎得到相同机械判定。

### 裁剪/改造（复制后动刀，逐处登记）

| 模块 | 改动 |
|---|---|
| `contracts.py` | 裁开书门（WORLD_ARCHITECTURE/蓝图目录/CONTRACT_FIELDS opening 对齐列/错误路由表）；增 t7＋`tier_window_band`＋PIPELINE_SHAPES；DEFAULTS 增五个差量化旋钮；CONTRACT_FIELDS 增 pinned/near_window_chapters/checkpoint_chapters＋style_source；STYLE_CATALOG 保留五档（锚点与完整版逐字同源，档位说明见 references/style.md）；Error 精简（去主机路由分支） |
| `world.py` | 裁开书门校验（validate/_bindings/declared_sections）；保留 SECTIONS/域地板（t7 同 t6 地板）/index；新增导入文档 `validate_shape`（放行 premise/story_capacity 顶层键） |
| `story_memory.py` | `bind` 增 `checked_through` 协议校验水位（完整版每次提交全量重遍历旧纲的累计 O(N²)，提案 §5.1 第一刀登记的修复）；判定等价：水位之下跳过、归零全量复核、新行自身协议恒校验 |
| `drift_validation.py` | 唯一改动＝章纲字段白名单登记 `'absorbs'`（文件头与检查点注释登记） |
| `envelope.py` | WORK_PAYLOAD_FIELDS 裁到执笔所需；增 `warnings`/`group` 键；「信封不得静默长字段」规则不变 |
| `briefs.py` | 重写为 write 简报（材料读法/锚句小节/内联回带纪律/提交前自检）；DELTA_HINTS 逐字保留 |
| `planning.py` | 裁字面约定协议（lexical/ENFORCEMENT）与 craft 依赖；保留契约校验/阶段策略/卷定位 |

### lite 新写

`store.py`（内容寻址文档表＋章行链哈希＋headers 窗口参数）、`delta.py`（delta/索引/倒排/
checkpoint/rebuild）、`anchors.py`（两类锚句）、`compose.py`（信封编译/scoped_state/
drift_slice/group_pack/participants）、`pipeline.py`（闭环编排＋卷界差异单＋recall＋
status 分页＋verify_full＋save/load）、`book_state.py`（含漂移行 participants 登记校验）、
`planning.py` 同上。

## 四、千万字支撑机制（引擎侧，非吞吐承诺）

1. **t7 档位**：千万字短章写法（2000~3500 字/章 → 3000~5000 章）有档可落；卷数 30~100
   可配，rolling+volume 百卷路径合法（planning.outline_policies 同源校验）。
2. **信封与书龄无关**：近窗索引＋组级共享＋锚句内联，投影字节不随远窗条目内容增长
   （test_envelope_size_stays_flat_as_book_ages：内容×10、字节不变）——对完整版
   「必读包随书龄单调上涨、partial 探针数百 KB」的曲线形状反转。
3. **存储线性化结构**：每章 delta＋卷界全量 checkpoint，替代完整版「每派工冻结整份
   complete_state/complete_hooks」的二次方快照留存（storage-snapshot-stress 3.85GB/
   1667 章的明文工程上限）；lite 的 checkpoint/deltas 派生自链上真源，可 rebuild。
4. **查询路径**：倒排 recall（miss O(1)）、headers 窗口参数（无全表扫描）、status 分页、
   bind 协议水位（消累计 O(N²)）——提案第一刀四项引擎修复在 lite 全部落地。
5. **验收不随体量变质**：verify_full 全量重放为默认语义；哈希链＋投影哈希逐章入账，
   篡改必翻。

## 五、已知限制（不假装解决）

1. **全部规模结论仍是设计值**：near_window=30 / checkpoint=50 / anchor_review=50 /
   组大小 5 四个旋钮无实测标定；conservative 触发率 f 无实测分布（提案 §6.2-2/§6.2-8
   原样继承）。落地承诺前需 ≥3000 章真实样章分段压测——lite 的测试只证明机制正确，
   不证明成本曲线在真实语料上成立。
2. **存储是内存＋JSON**：LiteStore 全量驻内存，`save` 写单文件 JSON。千万字项目 GB 级
   存储量级未在 lite 演示；生产持久化仍需完整版 sqlite_store 或按 delta/checkpoint
   模式另实现分片存储。
3. **无主机协议与无人值守**：每章由宿主会话逐条调用；compress 错位、租约、
   --fresh-context 等宿主风险面在 lite 不存在也不设防。
4. **verify_full 耗时未实测**：5000 章全量重放的外推（分钟级）来自完整版压测外推，
   lite 未跑千章级基准（测试只到 4 章）。
5. **无返修预算机**：提交门拒绝后循环由调用方自担；不设 remedies/attempts 上限。
6. **1667~2999 章档位缺口**：t7 只覆盖 3000~5000 章写法；中章千万字写法无档
   （完整版报告 §2.6 已登记的更大缺口）。
7. **pinned 登记归属未决**：lite 取契约字段形态落地；提案 §6.2-3 的开书门/独立指令
   归属形态未做。
8. **字面约定（lexical）协议未复制**：契约 world_rules 不做正文逐词拦截。
9. **外部文风档案不参与数值锚**：`style_source` 档案全文随信封下发，但 lite 不解析其中
   的量化画像进锚；形状地板由内置档名（若登记）或第二章起的滚动基线提供，首章无锚时
   形状比较跳过。
10. **卷首锚回比无数值比对**：`anchor_reviews` 只登记回比时点与锚身份（checkpoint 章号
    与投影哈希），不输出与卷首形状的数值偏离；数值比对待后续接入。
11. **外部源换档不记换档点**：`recontract_patch(style_source=…)` 只改契约字段，
    `style_switch` 切割只对内置档名换档生效。

## 六、文档—代码一致性

- SKILL.md 路由七步与 `pipeline` 公开函数一一对应（open_book / install_outlines / group /
  envelope / submit / verify_full / save+load，辅以 recall/status/style_board/recontract_patch
  与 `delta.rebuild`）；
- references/architecture.md 的记录表与 `compose.build` 的 add(...) 调用逐行对应，
  必读条件与代码一致（组首章/续章分支）；
- 本文「进了」表中每行至少挂一个测试名；「没进」表中每项写明归属（完整版承载 /
  提案未决 / 提案落选 / lite 未做）。
