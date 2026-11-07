# Markdown 章纲接入与未核实状态

适用于每卷一个 Markdown 文件，章标题为 `第0001章 标题` 的既有章纲。使用：

```bash
python3 <技能目录>/scripts/import_markdown_outlines.py --source <逐章细纲目录> --output <不存在的候选目录>
```

脚本逐章保存原文、来源文件、行号、文件 SHA-256 及需核实的字段；检查从第1章起连续、无重号及原文不为空，目标存在时拒绝覆盖。`manifest.json` 和每卷候选是**只供人工核查的中间格式**，不是引擎章纲或写作账本，不能直接传 `install_outlines` 或称为已完成导入。

对每卷依照 inputs.md 转为真实卷纲与章纲，逐章从原文和设定确认 `resources/places/knowledge/characters/relations/clock/enter/exit/hooks/scenes`。未说明不等于零、空或当天，不应猜测时间、余额、人物位置、货物所有权。不可用 `narrative_tracking=false` 和空数组掩盖真实状态变化。时间或库存缺乏确定依据时登记待决，先解决，再安装该卷；章纲变化应保留出处及作者允许范围。

仅在相应卷完整建模并通过 `pipeline.install_outlines` 后建立组、派工和提交；文风仍须作者明确选择。当前引擎要求整卷安装和可模拟的状态链，不能只凭候选文档或通过结构校验就保证全部语义已核实。如作者希望从第1章开写但整卷仍缺信息，应说明阻塞和需要补全的范围，不使用伪造的数据绕过。
