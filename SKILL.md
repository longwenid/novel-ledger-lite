---
name: novel-ledger-lite
description: 在作者已确认总纲、卷纲与章纲后，使用冻结资源、差量上下文、独立审读和逐章核账进行长篇小说快速写作；面向约千万字体量，支持分卷接续、保存恢复和全量验收。用于按既定章纲持续执笔，不用于故事或章纲设计。
---

# novel-ledger-lite

独立的长篇写作执行技能。目标是总纲、卷纲、章纲确认后的快速执笔，以不偏离作者确认内容为第一约束，
保持人物、资源、时间线、知情与伏笔账本一致，再控制材料重复。输入可由作者或任意工具提供，按本项目格式
校验后使用；不要求安装其他写作技能、服务或代码仓库。

## 环境与输入

- 引擎需要 Python 3.10+，仅使用标准库；从本技能目录的 `scripts/` 导入 `novel_ledger_lite`。
- 首次准备项目时读 [references/inputs.md](references/inputs.md)，核对契约、世界模型、
  卷纲、章纲与提交格式。可运行 `python3 scripts/run_example.py` 验证完整四章示例。
- 既有 Markdown 章纲可用 [导入与待核实流程](references/markdown-import.md) 建立带原文来源的
  候选清单；候选不能代替引擎账本，缺少的时序、资源和状态不得伪造为零或无变化。
- 输入是 outline-architect 的22文件表格大纲包时，使用[原生接入流程](references/outline-architect.md)
  和 `scripts/import_outline_architect.py`，直接保留全包原文、表格、行号及缺章范围，无需重复改写章纲。
  来源校验不代替作者确认与执行建模；完整卷章及状态链安装通过后才开始本技能的写作流程。
- 文风必须由作者显式选择：内置档见 [references/style.md](references/style.md)，也可提供
  作者确认的 UTF-8 Markdown 文风档案。五份内置完整档案在 `references/styles/`；
  选中后冻结实际文件；单文件写作包携带本章所需文风材料，必要时由准备者补齐。
  未选定时 `envelope` 与 `submit` 会拒绝并返回选项，
  将选项交给作者选择，不代选默认档。外部档案不限定作者、文件名或生成工具。
- 实际派工与恢复时按需读 [references/architecture.md](references/architecture.md)。
- 首次连续执笔、接续长篇或诊断累积漂移时，读 [章纲预检与跨章复审](references/narrative-review.md)。
  开写前实际只读剧情纲，分别核验因果可行与单元阅读驱动：具体期待、选择造成的变化、兑现后的后果及相邻单元是否同式。
  能力与归属边界始终生效，分清必须发生的动作抉择与不必反复解释的限制；有冲突退回准备者，不临时补设定。
  该核验不替代作者确认，也不将本技能扩为故事设计工具。

## 写作流程

以下是 Python API。将本技能的 `scripts` 目录加入导入路径；相对路径须由调用方按技能
实际位置解析，避免依赖调用时的工作目录。创建 `store = LiteStore()` 后依次执行：

1. `book = pipeline.open_book(contract, source, world_model)`：导入作者确认的约束；
   `source` 说明决定来源，`world_model` 可省略。世界模型与文风档案在导入时保存冻结副本。
2. 每卷执行 `pipeline.install_outlines(book, volume_id, volume_outline, chapters_data)`。
   章纲连续覆盖该卷，增量与 enter/exit 状态链须通过模拟。失败按错误详情修正输入重交，
   不改写历史账本。修纲只处理下一待写章起的尾部；重传的已写前缀必须与冻结历史相同，
   已使用的节点与伏笔定义也不能追改。此步骤核验既定章纲，不重新设计剧情。
3. `group_row = pipeline.group(book, store, volume_id, size=5)` 冻结一组共享材料。
   同卷再次调用接续下一组；已覆盖全卷会拒绝。恢复已有组用 `pipeline.group_for(book, chapter)`。
4. 上一章提交通过后，准备者调用 `package = pipeline.chapter_package(book, store, chapter, group_row)`，
   将 `package["text"]` 以 UTF-8 写为本章 Markdown 文件。写作前用
   `pipeline.validate_chapter_package(book, store, 文件内容)` 校验文件完整性和账本时效。
   正文写作者只读取这一个文件；发现缺失、冲突或不确定时停止，由准备者补齐后重新生成并校验。
   生成细节和补充资料接口见 [references/architecture.md](references/architecture.md#单章-markdown-写作包)。
   写作后调用 `review = pipeline.review_request(book, store, chapter, draft, writer=写作者标识)`，
   将 `review["text"]` 完整交给不同于写作者的独立读者。可用独立子代理或另一真实审读会话；
   无独立读者时停在待审，不由写作者替自己填通过报告。读者先读材料与整章，再逐项核对并返回包内约定的报告。
   准备者原样记录实际报告：`draft["review_ref"] = pipeline.record_content_review(book, store, review["request_ref"], report)`，
   然后用 `pipeline.submit(book, store, chapter, draft)` 提交。
   `draft` 必须含 `title/prose/summary/self_check/drift_check`；单文件包交稿还须原样回传包内
   `package_ref`，所有提交还必须带独立审读的 `review_ref`。本章一旦签发单文件包，提交不能省略引用或沿用已被补充包替换的旧引用。
   缺料、拒绝、未读完、不确定或检查未覆盖的报告均不能放行。正文、申报、材料或文风变化后重新发起审读；
   旧报告不能批准新稿。每轮请求只登记一份报告，重新审读须新请求；不能重放旧报告或沿用旧通过引用。
   只在 `ok=True` 后推进下一章；
   拒绝时根据 `findings` 修正当前稿，不能用偏差说明代替修复，不能跳章或覆盖历史。
5. 卷末查看提交结果的 `volume_boundary`，核对未兑承诺、带入下卷项目与漂移吸收情况。
   每组末及卷末还须按[跨章复审](references/narrative-review.md)实读连续正文，分列事实与动机连续性结论、
   追读判断与具体期待及剩余叙事风险；可在末章发包时补入前章全文，与该章独立审读合并。
   核账通过不替代此项阅读；具体驱动缺口先处理未写单元，不凭 `submit.ok` 连续推进，不以静章或慢热自动判失败。
6. 阶段保存用 `pipeline.save(book, store, path)`，接续用 `pipeline.load(path)`；
   完本用 `pipeline.verify_full(book, store)`，只有 `ok=True` 才通过机械验收及审读记录验链。
   保存通过同目录临时文件落盘后原子替换；失败保留上一份有效文件，不能把失败当作保存成功。

引擎不提供故事设计、自动返修调度或无人值守主机。候选被拒后的修正由当前写作会话执行；
本项目 JSON 账本用于保存恢复，其他格式的旧项目需显式转换，不直接混读。
总纲、章纲自身有问题与正文偏离章纲须分开记录：前者退回设计准备、只调整允许修订的未写部分；
不能靠严格执行有缺陷的章纲消除问题，也不能为了节奏偏好自行推翻已确认设计。

## 写作模式界面

DSH Web GUI 可开「写作模式」右栏：左边照常是会话，右边按「设定 / 章节 / 正文」三页
阅读总纲约束、人物与世界、卷章表和已写正文。界面只读，真源仍是 JSON 账本。

- 每完成一组 `submit`（或交付正文前）导出一份视图：

  ```bash
  python3 scripts/export_view.py 项目.json --out .novel-ledger
  ```

  它写 `.novel-ledger/view.json` 清单、`chunks/` 校验分片与每章一个 `chapters/chNNNN.md`，
  不改动账本；账本变了就重跑一次。保留整个导出目录，新插件会完整重组视图和正文，缺块或截断时报错。
  新导出需配套新版插件；新版仍能读取旧 view/1。旧分片保留供正在阅读的界面使用，
  可删除整个派生目录后重新导出，不要单独删 `chunks/`。
- 打开方式：会话标题栏右侧「写作模式」按钮，或右栏 guide 里的卡片；
  面板右上角「刷新」重新读取。
- 面板先找工作区根 `.novel-ledger/view.json`，再找一级子目录中的同名文件，
  多项目工作区把视图放在各自项目目录即可。
- 界面插件源码在 `ui/novel-writing-mode/`，随技能分发；在 DSH 桌面端用
  `plugin_manager install_bundle <该目录绝对路径>` 安装（需批准），装好后刷新页面即可用。

## 控制上下文并保住资源

- 前文默认只读前一章全文，结合前两章场景锚句和章纲引用的逐字历史锚句。
- `core_context` 每章必读，包含总纲核心约束、主角限制、结局方向、声线和当前卷职责。
- 本章相关人物的当前事实、余额、关系和当前人物状态不按年龄裁剪。近窗默认 30 章，
  用于近期事件和未点名知情话题；明确点名与 `contract.pinned` 值完整携带。
- 准备者可用 `pipeline.catalog`、`pipeline.resource` 与 `pipeline.recall` 检索并核实缺失资料，
  再把本章需要的材料加入写作包；写作者不直接补读。未携带不等于不存在，不杜撰或重置。
- 章纲缺少完整场景依赖声明时，引擎保守回退并发出 `projection_warnings`。材料会变大，
  可在作者已确认的内容内补齐依赖声明后重新核验；不能为了省 Token 静默删掉未知依赖。
- 派工前自动汇总场景人物、资源、知情话题、节点前置与显式引用，并检查依赖存在性和前态；
  缺失或冲突会拒绝派工。`complete` 只表示作者声明，不证明语义依赖完整。
- 单章 Markdown 写作包不依赖会话缓存。底层 `envelope` / `materialize` 的可选缓存机制仅供其他交付方式使用。
- 完整依赖声明下，未点名远期知情和历史保留定位目录，由准备者按实际需要补齐；不把目录片段当事实。
  不设固定 Token 截断线；当前状态、点名与 pinned、未兑承诺和引用原文必须完整，依赖不明时保守全量。
- 写作包显列本章起点、章纲规定的变化原因和终态，以及参与者完整当前资产。正文只能在这些
  条件内展开；缺少关键资产、需要计划外转移或消耗时，先核实、修纲、重新发包。
- 提交前独立阅读整章，对照章纲与包中当前状态，检查额外资产、数量、归属、伤势和知情变化。
  核账表不得漏报或反报；引文须支持所申报的变化，逐字存在本身不证明语义正确。
  独立读者还须双向检查正文里未申报的变化，不得只复核写作者的核账表。正文审读门槛对底层无包提交同样生效。
- 换文风必须记录作者决定，调用
  `pipeline.recontract_patch(book, source=决定来源, style_profile=档名)` 或 `style_source=路径`。
  换档从下一待写章生效；仅指定内置档时清除旧外部源，历史契约保留供验链。

## 验证与边界

在本技能目录运行 `python3 -m pytest tests -q`；测试依赖 `pytest`，引擎和四章示例不依赖它。
长程合成压测另需可选的 `tiktoken`：

```bash
python3 tests/benchmark_long_run.py --chapters 3000 --output /tmp/novel-ledger-lite-benchmark.json
```

1000 万字是目标体量，合成压测只验证机械链路与材料趋势。活跃资源、引用规模、章长和
依赖声明质量都会影响 Token；正文的语义与文学质量仍需实际阅读评估。压测合成凭证只测试协议，
不得用于实际作品，也不构成文学或语义通过证明。门禁绑定所登记的报告与材料、稿件和历史，
不把哈希或报告字段伪称为自然语言真伪判定器；宿主须实际调用独立读者并如实记录结果。
派工协议为 task/2：`payload.chapter_outline` 是记录名，章纲正文仅在该记录中出现一次。
支持账本 `novel-ledger-lite/2`；未签发单文件包的原存储为 `novel-ledger-lite.store/2`，
签发但尚无审读记录时为携带必填签发引用的 `novel-ledger-lite.store/3`；
登记独立审读后使用含 `package_heads/review_heads` 的 `novel-ledger-lite.store/4`；
持久化文件 `novel-ledger-lite.bundle/2`、派工 `novel-ledger-lite.task/2`。旧版本、缺少版本标识
或必要字段的数据直接拒绝，不补字段、不重建旧组包、不从外部文件补建档案。原有
store/2、store/3 作品可加载接续，但后续提交也必须独立审读。无审读凭证的旧历史不能通过完整审读验收；
需要保留旧历史时不得谎称它已被审读。签发或审读记录丢失不允许降级绕过门槛。
单文件写作应使用 `chapter_package`；其他交付方式通过 `materialize` 渲染，避免自行重复拼接任务卡和文档。
它返回总字节、分项字节和缓存命中数；可传 `token_counter` 与 `tokenizer_id` 测量实际输入 Token。
当前实现、测量口径和限制见 [DESIGN.md](DESIGN.md)。
