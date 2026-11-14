# 正文独立审读与入账

内容不漂移优先于材料大小。机械核验能验证已申报变化、前态、逐字引文和哈希，不能据此
判断正文没有额外写出资产、确认了未确认的真相，或在另一段推翻了前面的正确证据。

长篇还须执行[章纲预检与跨章复审](narrative-review.md)。每章的 `outline.notes` 说明实际章节职责、
核心承诺和生效文风；`causality.notes` 说明关键选择与已确认动机、能力前提的关系。
组末与卷末实读连续正文，可以通过末章包的 `extra_chapters` 合并到本次审读。沿用既有六类检查，
不追加报告字段，不将新增阅读要求伪称为旧历史已经完成的检查。此项需要宿主安排和读者实际执行。

## 实际流程

1. 写作者依据已校验写作包完成 `draft`，携带包内 `package_ref`。
2. 准备者调用 `pipeline.review_request(book, store, chapter, draft, writer="实际写作者标识")`。
   返回 `request_ref/manifest/text`；请求冻结完整包正文、整稿、当前前态、契约与章纲。
3. 将 `text` 原样交给不同于写作者的独立读者，可用独立子代理或另一个真实审读会话。
   没有可用读者时停在待审。不得用写作者的 self_check 或脚本自动生成通过报告。
4. 准备者将读者的实际报告原样交给 `pipeline.record_content_review(book, store, request_ref, report)`，
   返回的引用放入 `draft["review_ref"]`，再调用 `submit`。拒绝或缺料报告可以留档，但不能提交。
5. 返修、补包、修纲或换文风后重新发起请求，重新通读。每轮请求只登记一次报告，
   报告须原样回传 `request_ref`；不能重放原报告，也不能将旧报告冒充新审读。
   异步返回的旧包报告不能替代新包的审读。底层无包工作流也受相同门槛约束。

## 报告字段

```json
{
  "request_ref": "原样回传本轮请求引用",
  "reviewer": "独立读者的实际标识",
  "verdict": "pass",
  "read_complete": true,
  "checks": [
    {"id": "outline", "status": "pass", "notes": "具体说明情节与章纲的符合情况。"},
    {"id": "continuity", "status": "pass", "notes": "核对前章承接、时间与位置。"},
    {"id": "assets", "status": "pass", "notes": "核对完整资产、数量、所有权与伤势。"},
    {"id": "knowledge", "status": "pass", "notes": "区分人物、读者知情与作者真相。"},
    {"id": "causality", "status": "pass", "notes": "核对动作、原因、后果与证据含义。"},
    {"id": "unplanned", "status": "pass", "notes": "独立通读正文，检查未申报的变化及自相矛盾。"}
  ],
  "event_checks": [
    {"id": "从manifest.event_checks原样复制本项id", "status": "pass",
     "notes": "具体说明这段引文如何支持本项对象、原因和结果。",
     "evidence": {"chapter": 1, "quote": "真实正文中的逐字引文"}}
  ],
  "findings": []
}
```

`event_checks` 要逐项覆盖请求中的全部事件，不是只填一个示例。引文重复时附准确 `start`。
每次请求都有独立轮次，即使稿件未变，再审也使用新请求并实际重新阅读。
`status` 可为 pass/fail/uncertain；结论为 pass/reject/needs_material。只有已读完整章、所有
检查和事件均通过、无任何 findings 的独立报告才能放行。报告格式通过不代表其判断一定正确；
宿主须实际调用独立读者，并对读者身份和报告真实性负责，不能把协议当自然语言真伪检测器。

## 完整性与恢复

请求与报告都保存在同一内容寻址存储。每份报告绑定具体稿件（含摘要、自检、申报）、
材料、章纲、契约、前态、前章链和包引用。store/4 持久保存审读链头，丢文档、回滚链头或
从章行删审读引用均拒绝恢复。提交后全量验收核对这些绑定及历史章纲，不单检查当前余额。

旧作品可加载继续，但不会凭空拥有独立审读历史。缺凭证的旧章不能被宣布完整审读验收通过。
合成压测使用明确标记的测试凭证，仅测试协议和机械负载，不用于实际作品或文学评价。
