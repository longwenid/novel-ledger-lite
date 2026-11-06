---
name: novel-ledger-lite
description: 在作者已确认总纲、卷纲与章纲后，使用冻结资源、差量上下文和逐章核账进行长篇小说快速写作；面向约千万字体量，支持分卷接续、保存恢复和全量验收。用于按既定章纲持续执笔，不用于故事或章纲设计。
---

# novel-ledger-lite

独立的长篇写作执行技能。目标是总纲、卷纲、章纲确认后的快速执笔，控制每章材料 Token，
保持人物、资源、时间线、知情与伏笔账本一致。输入可由作者或任意工具提供，按本项目格式
校验后使用；不要求安装其他写作技能、服务或代码仓库。

## 环境与输入

- 引擎需要 Python 3.10+，仅使用标准库；从本技能目录的 `scripts/` 导入 `novel_ledger_lite`。
- 首次准备项目时读 [references/inputs.md](references/inputs.md)，核对契约、世界模型、
  卷纲、章纲与提交格式。可运行 `python3 scripts/run_example.py` 验证完整四章示例。
- 既有 Markdown 章纲可用 [导入与待核实流程](references/markdown-import.md) 建立带原文来源的
  候选清单；候选不能代替引擎账本，缺少的时序、资源和状态不得伪造为零或无变化。
- 文风必须由作者显式选择：内置档见 [references/style.md](references/style.md)，也可提供
  作者确认的 UTF-8 Markdown 文风档案。五份内置完整档案在 `references/styles/`；
  选中后冻结实际文件；单文件写作包携带本章所需文风材料，必要时由准备者补齐。
  未选定时 `envelope` 与 `submit` 会拒绝并返回选项，
  将选项交给作者选择，不代选默认档。外部档案不限定作者、文件名或生成工具。
- 实际派工与恢复时按需读 [references/architecture.md](references/architecture.md)。

## 写作流程

以下是 Python API。将本技能的 `scripts` 目录加入导入路径；相对路径须由调用方按技能
实际位置解析，避免依赖调用时的工作目录。创建 `store = LiteStore()` 后依次执行：

1. `book = pipeline.open_book(contract, source, world_model)`：导入作者确认的约束；
   `source` 说明决定来源，`world_model` 可省略。世界模型与文风档案在导入时保存冻结副本。
2. 每卷执行 `pipeline.install_outlines(book, volume_id, volume_outline, chapters_data)`。
   章纲连续覆盖该卷，增量与 enter/exit 状态链须通过模拟。失败按错误详情修正输入重交，
   不改写历史账本。此步骤核验既定章纲，不重新设计剧情。
3. `group_row = pipeline.group(book, store, volume_id, size=5)` 冻结一组共享材料。
   同卷再次调用接续下一组；已覆盖全卷会拒绝。恢复已有组用 `pipeline.group_for(book, chapter)`。
4. 上一章提交通过后，准备者调用 `package = pipeline.chapter_package(book, store, chapter, group_row)`，
   将 `package["text"]` 以 UTF-8 写为本章 Markdown 文件。写作前用
   `pipeline.validate_chapter_package(book, store, 文件内容)` 校验文件完整性和账本时效。
   正文写作者只读取这一个文件；发现缺失、冲突或不确定时停止，由准备者补齐后重新生成并校验。
   生成细节和补充资料接口见 [references/architecture.md](references/architecture.md#单章-markdown-写作包)。
   写作后用 `pipeline.submit(book, store, chapter, draft)` 提交。
   `draft` 必须含 `title/prose/summary/self_check/drift_check`。只在 `ok=True` 后推进下一章；
   拒绝时根据 `findings` 修正当前稿，不能用偏差说明代替修复，不能跳章或覆盖历史。
5. 卷末查看提交结果的 `volume_boundary`，核对未兑承诺、带入下卷项目与漂移吸收情况。
6. 阶段保存用 `pipeline.save(book, store, path)`，接续用 `pipeline.load(path)`；
   完本用 `pipeline.verify_full(book, store)`，只有 `ok=True` 才通过机械验收。

引擎不提供故事设计、自动返修调度或无人值守主机。候选被拒后的修正由当前写作会话执行；
本项目 JSON 账本用于保存恢复，其他格式的旧项目需显式转换，不直接混读。

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
依赖声明质量都会影响 Token；正文的语义与文学质量仍需实际阅读评估。
派工协议为 task/2：`payload.chapter_outline` 是记录名，章纲正文仅在该记录中出现一次。
仅支持当前格式：账本 `novel-ledger-lite/2`、存储 `novel-ledger-lite.store/2`、
持久化文件 `novel-ledger-lite.bundle/2`、派工 `novel-ledger-lite.task/2`。旧版本、缺少版本标识
或必要字段的数据直接拒绝，不补字段、不重建旧组包、不从外部文件补建档案、不自动迁移。
单文件写作应使用 `chapter_package`；其他交付方式通过 `materialize` 渲染，避免自行重复拼接任务卡和文档。
它返回总字节、分项字节和缓存命中数；可传 `token_counter` 与 `tokenizer_id` 测量实际输入 Token。
当前实现、测量口径和限制见 [DESIGN.md](DESIGN.md)。
