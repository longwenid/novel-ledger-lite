# 输入格式与独立示例

本项目消费作者已确认的内容，不限定内容的创作工具。可复制随包的
[example_project.json](example_project.json) 作为格式样例；它包含完整契约、世界记录、
一卷四章章纲与四份短正文提交。示例章长仅用于验证机械流程。

## 导入契约

契约是 JSON 对象。`title/genre/reader_promise/ending/world_premise/story_engine/opposition/voice`
是非空文本；`style_traits/world_rules` 是文本数组；`protagonist_setup` 包含
`id/name/identity/desire/limit`。`entities` 每条带唯一 `id/name/kind`，引用一律使用稳定 ID。

`chapter_min/chapter_aim/chapter_max` 是正整数字数范围，aim 位于上下限之间，maximum
不超过 10000。`volumes` 至少一条 `{id, purpose, end}`，卷末章号严格递增，从第一章连续划分。
`first`、总字数区间由校验推导。未知契约字段会被拒绝，完整可接受字段见
`scripts/novel_ledger_lite/contracts.py` 的 `CONTRACT_FIELDS`。

- 必须在执笔前选 `style_profile` 或 `style_source`，详见 [style.md](style.md)。
- 初始资源：`initial_resources=[{holder, asset, unit, quantity}]`；quantity 是非负十进制字符串。
- 初始事实：`initial_facts=[{entity, key, value}]`；`placements` 是人物 ID → 地点 ID。
- 常驻资源：`pinned=[{kind, key}]`，例如 `{kind: "facts", key: "shen:identity"}`。
- 章纲策略：`volume_outline={scope:"rolling",words:2500,tolerance:500}`，
  `chapter_outline={scope:"volume",words:150,tolerance:60}` 是默认形状；多卷 rolling 不能配 all 章纲。
- `narrative_tracking=false` 可用于无情节节点账的简洁项目。开启时须相应声明情节节点、
  线路与读者披露，不能将故事内变化与读者知情混为一谈。

世界模型可省略；提供时按 `world.SECTIONS` 使用记录数组，每条带唯一 ID 及该域所需字段。
例如 `world_refs=["rules:r1"]` 引用 `rules` 域的 r1。完整可运行记录见样例。

## 卷纲和章纲

`pipeline.install_outlines(book, volume_id, volume_outline, chapters_data)`：

- `volume_outline` 带本卷 `id`，`nodes/threads` 数组；以 `clock={advance_days,to}` 声明
  卷内推进天数与绝对卷末时钟。伏笔按 `{id,text,plant:[起,止],payoff:[起,止],required,continues}` 声明。
- `chapters_data={volume:卷ID, chapters:[...]}` 按章号连续覆盖到该卷末章。
- 章纲带 `chapter/synopsis`、`plot={beat,nodes,threads}`，并声明
  `resources/places/knowledge/characters/relations/clock` 等变化，`enter/exit` 使用 `{kind,key,expected}`。
  clock 的 key 为 main；资源 key 是 `[holder,asset,unit]` 的紧凑 JSON 字符串。
- `hooks` 使用 `{hook,action,note}`；正文引文引用按 `hook_refs/history_refs/reader_refs` 点名。
- `scenes` 每场带 `label/intent/conflict/turn/present/speakers/dialogue_intents`。
  完整依赖声明还需 `dependency_coverage="complete"` 与逐场 `reads:[{kind,key}]`、`depends_on:[]`。
  场景 ID 与阅读协议由安装门绑定，不自己拼接旧协议。
- 章纲 `style` 可写 `pov/rhythm`，也可明确 `dialogue_ratio`。字段、引用、长度、资源变化和
  逐章状态链都由门校验；错误的 `details.findings` 给出修正位置。
- 单章可以显式声明 `word_budget={min:1200,aim:1600,max:2000}`，三项为正整数且
  `min<=aim<=max`，max 不超过 10000。它覆盖本章的契约默认章幅；未声明的章节完全沿用
  原默认值，不向旧章纲补字段，不降低全书默认。全书可达篇幅按这些明确例外修正，短章的
  差额不转嫁后章。只通过 `install_outlines` 调整下一待写章起的尾部；已写章节的预算不可
  添加、修改或删除。预算变化使旧章包及审读失效，须重新发包、独立审读。写作包、提交与
  历史重放使用同一预算入口。情节已经自然收束时可以采用短章，不为原默认下限补回重复解释。

## 正文提交

提交对象包含非空 `title/prose/summary/self_check` 以及 `drift_check={items,unplanned,verdict}`。
使用单文件写作包时还须回传包内 `package_ref`，原样复制即可，不计算哈希。本章已签发单文件包时，
提交会核验最新签发引用和当前来源；旧引用、缺引用、来源已变均不能提交。
每项章纲增量对应一条自比：`{kind,key,planned,status,actual,evidence}`。planned 与冻结章纲
一致；正常提交 status 为 kept，actual 使用 clock.advance_days、hook.action 或资源等的 to。
`evidence={chapter,quote}` 必须逐字存在于本章正文且可唯一定位；前态由引擎投影核对。
引文还应在语义上支持所报变化；独立审读须核对整章有无计划外资产或知情变化及申报漏项，
不能只验证引文存在或沿用写手的 clean 声明。
所有提交必须先用 `review_request` 让不同于写作者的独立读者阅读完整材料和整章，
将实际报告交给 `record_content_review` 并回传得到的 `review_ref`。
审读类别、逐项事件证据、缺料停写和失效规则见 [content-review.md](content-review.md)。

`items` 须精确覆盖本章所有变化，`unplanned` 正常为空，`verdict` 为 clean。
声明偏差只用于诊断，不授权变更既定章纲；被拒时按 findings 修复正文重提。
完整写法和引用格式见样例 JSON，而不是从其他项目获取模板。

## 运行与验证

`python3 scripts/run_example.py` 不依赖 pytest、分词器或模型服务，运行内置四章稿的
完整导入、分组、冻结审读报告绑定、提交、保存重载和验收；指定 `--output 路径` 可保留示例账本。
示例仅复用已独立审读的固定稿件和报告，设计、文风材料或稿件指纹变化即拒绝，不能为任意稿件自动颁发凭证。
引擎通过 Python API 调用，示例脚本只是接入演示，不生成创作正文。

## 上下文接入

使用 task/2 时，先 envelope 编译，再 materialize 得到实际写作文本。
默认每章材料自足；新会话不要沿用上一会话的缓存确认。
具体缓存格式、补读目录与分项度量见 [architecture.md](architecture.md)。
