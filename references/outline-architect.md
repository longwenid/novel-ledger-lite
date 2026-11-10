# 接收 outline-architect 大纲包

何时读：输入来自 outline-architect 的 22 文件 Markdown 表格包。此接入是可选来源，不改变本技能独立消费作者或其他工具输入的能力。

## 来源接入

```bash
python3 <本技能目录>/scripts/import_outline_architect.py --source <大纲包目录> --output <新候选目录>
python3 <本技能目录>/scripts/import_outline_architect.py --verify <候选目录>
```

无需把表格改写成章节标题。工具核对源 `_manifest.json` 的 22 个文件、归一化 SHA-256 与原始字节数；完整原文放 `source/`（审计回执存在时一并保存），`tables.json` 保留所有可识别的契约表、列、行、原始行和行号。逐卷 `volumes/Vxx_candidate.json` 携带 T-VOL 原行及逐章 T-CH 原行；manifest 指明完整覆盖与缺失范围。输出既有时拒绝，来源在读取期间改变时清理本轮输出；不改源文件。

候选的 `status=review_required`、`engine_installed=false`、`delivery_acceptance=not_verified`。工具只证明来源和结构，不证明作者确认、文义质量、完整资源状态或通过上游交付门。`--verify` 在准备和恢复时核对完整快照及派生索引，不把路径或旧会话记忆当证据。

## 准备者的转换职责

先按 inputs.md 建立契约、世界模型与原 ID 对照，再把已确认内容转为真实卷纲和章纲，不重新创作剧情。建议按需读取：

- 总纲与约束：00、06、09、10 的红线，确定 promise/ending/protagonist/world_rules 等契约内容。将禁写项及人工判定要求写入冻结约束和独立审读材料，不宣称存在上游专用的章稿扫描器。
- 世界与初态：01、01a–01k、02 的人物、关系、资源、时间、知情、位置；按 world.SECTIONS 的现有格式建模，不把十八层表直接当引擎 JSON。绝对年保留年精度，转换为主时钟日数时必须有明确起点与换算依据，不把“万年”数值误读为年数或任意假定日期。
- 卷章职责：03 的 T-VOL/T-FIVE/T-UNIT-IDX/T-CH，联合04的单元与兑现、05的节奏、07的伏笔。逐章核实 scenes、reads、depends_on、resources/places/knowledge/characters/relations/clock、enter/exit 与 hooks。题材及平台章长沿作者选择，显式选风后再编包。
- 执行与证据：08、10 和审计回执。正式交付前核对上游完整校验、四道挑战、三席盲读、实际签署和 go 结论；预检候选可以先建，但不得据此声称已具备写作条件。

未知状态写进待决清单，回源核实或取得作者决定；不虚构余额、零天数、无变化、读者知情、依赖 complete 或假审读凭证。只有卷章完整且状态链通过 `pipeline.install_outlines` 才能 group/chapter_package；候选不可直接安装。滚动输出缺章时将 `missing_range` 回传上游补纲，不绕过整卷安装门。

## 衔接及恢复

实际写作完整沿用本技能：显式选风、单章包、独立整章审读、submit、save/load、verify_full。来源文档只给准备者查证，正文写作者仍只读校验过的本章包。追加和修订需先保存账本，对照新旧源快照并由作者确认；修纲只安装未写尾部，冻结历史和旧审读的绑定不变。

原 outline-architect 的 WORK/prose、META、current.md 或 roll-journal 不是本引擎存储，禁止直接当作 bundle 加载或重置历史。旧作品需要明确转换、核实已有正文与未审读历史；不能用新项目零状态接管旧正文。

上游要求的 30/60/90% P2 审计由准备者对 `_audit/T-AUDIT.md` 回填事实并取得实际签署；上游设定变更则返回原表/ID、证据与受影响范围。该回执是项目交付责任，不由引擎代签。
