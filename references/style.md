# 文风体系（lite）

> 与完整版的差异：测量/基线/容差/守卫逻辑与五档目录和完整版逐字同源（`style.py` 未改
> 一行、`STYLE_CATALOG` 锚点同表）；lite 独有的三处——①文风须作者显式选定，无「无偏好
> 落默认档」回落（完整版有）；②外部文风源经契约 `style_source` 接入，档案全文随信封
> 下发但不解析其量化值（完整版无此通道）；③无「认可首章」流程与 `references/styles/`
> 档案正文随包（lite 只消费注册锚，档案正文从完整版取）。

lite 的文风能力说明：档位、两条文风源路径、换档与基线门。

## 一、内置文风档目录（五档，与完整版同表同源）

`contracts.STYLE_CATALOG` 五档，每档带注册锚（七项滚动指标：句均长/短句占比/段均长/
最长段/对白占比等），是首章认可前形状比较的地板：

| 档名 | 定位 | 锚点差异（段落/对白） |
|---|---|---|
| 市井修仙（校准基准档） | 校准的主流形状，单档时代的基线 | 段均 50 / 对白 0.30 |
| 账房掌门 | 账房式克制，长段铺陈 | 段均 47.6（上限 450）/ 对白 0.264 |
| 神秘学双声部 | 叙述与内心双声部，短段高频 | 段均 36.1 / 对白 0.365 |
| 宗族史传 | 史传笔法，短段长卷 | 段均 35.6（上限 353）/ 对白 0.309 |
| 科幻错位幽默 | 错位幽默节奏，中长段 | 段均 49.2（上限 392）/ 对白 0.33 |

档位语义（完整版同口径）：

- **选定档名逐字进契约**：契约 `style_profile` 字段保存档名原文，信封/简报按它渲染。
- **杜撰拒绝**：契约校验 `choices=tuple(STYLE_CATALOG)`，杜撰档名报错并列有效五档。
- **无默认档放行（2026-11-02 作者要求收紧）**：「无偏好落默认档」回落逻辑已从 lite 移除——`style_profile` 缺省＝「未选定」状态（validate_contract 不填充），执笔派工被 compose.build 前置检查机械拒绝，返回 status=style_not_selected＋可选项板面（内置五档一句话定位＋外部档案接入方法，主控拿去问作者；也可随时取 pipeline.style_board()）。引擎不提问、不猜偏好；「市井修仙」的锚点只作为校准基准数据保留，不再代表任何自动选择。
- 内置档的完整档案文本在完整版 `references/styles/<名>.md`；lite 引擎只消费注册锚，
  档案正文随需要从完整版取。

## 二、两条文风源路径（二选一）

1. **内置档**：契约 `style_profile` 点名目录档名（作者显式选定）。信封 `style` 记录带
   `source_kind='builtin_catalog'`；`style_anchor` 记录是该档注册锚。
2. **外部档案**：契约 `style_source` 登记 style-distill 产出的《文风档案.md》文件路径
   （绝对路径）。开书时校验文件存在（contracts 层无 I/O，校验在 `pipeline.open_book`）；
   信封 `style_archive` 记录在组首章（或无组时）携带档案全文下发 Worker，`source_kind='external_archive'`，
   `style_profile` 保留作标识。最小样例档案在 `tests/fixtures/style_archive_sample.md`
   驱动测试。

两条路径共用同一套机械测量与基线逻辑——换源不换门。

## 三、执笔链路中的文风

- **派工简报**：`briefs.write_brief` 增「文风规格」小节——生效文风源（内置档名或外部
  档案）、契约声线（voice/tone/pov）、声线特质、基线说明、本卷走向（卷纲 style.trend）、
  本章执行点（章纲 style.rhythm）。与信封 `style` 记录同源：写进简报的就是提交门将
  比对的同一组数字。
- **信封记录**：`style`（规格＋当前基线锚＋合并容差，每章必读）、`style_anchor`（内置档
  注册锚＝`style.baseline(book)`，lite 无「认可首章」流程；外部源且无档名时为 None 则不
  登记）、`style_archive`（外部档案全文：只在组首章或无组时内嵌必读，组内续章经组包引用
  补读，不每章重复携带）、`style_volume_anchor`（文风卷首锚，首个 checkpoint 后冻结，组首章随
  契约交付）。
- **组级共享包**：登记生效档标识（profile/style_source/source_kind）、卷首锚、外部档案全文。

## 四、运行中换档（参数级变更）

`pipeline.recontract_patch(book, source='作者原话', style_profile=档名 或 style_source=路径)`：

- 档名杜撰拒绝（须在目录内）；外部档案须真实存在；`source` 必填（作者决定留原话）。
- 换档点记入 `book['style_switch'] = {at, profile, previous}`：新档自 `at` 章（已冻结
  章纲最大章号＋1）起生效；之前章节保留原档文风，既不按新档判定也不进新档滚动基线
  （`style.switch_cutoff`/`current_anchor` 的完整版既有语义自动生效）。
- 外部档案换档：`style_source` 参数级变更只改契约字段（校验文件存在），**不**登记
  `style_switch`——换档点切割只对内置档名换档生效（代码实际行为，如实登记）。

## 五、滚动基线与守卫（防漂移，详见 DESIGN.md §二）

- 基线＝**最近 5 章已提交正文的滚动中位**（`style.STYLE_BASELINE_WINDOW=5`，约一个
  默认连写组），中位吸收单章波动而不把它当下一章目标；只有一章时该章实测即锚
  （origin=pilot）；无已提交章时回落内置档注册锚，外部源且无档名时锚为空（首章形状
  比较跳过，第二章起由滚动基线接管）。
- `style_guard='observe'`（默认）：形状偏离只记录 observation，不拦候选；
  `'strict'`：句均长/短句占比/段均长/最长段/对白占比相对基线偏离超容差 → `style_*`
  finding，候选拒绝。章纲显式 `dialogue_ratio` 目标与章内高重复率检查在两档下都生效。
- 测试入口：`tests/test_style_gate.py::test_style_baseline_gate_triggers_on_shape_drift`
  驱动 strict 下基线门真实触发与 observe 下只观察不拒绝。
