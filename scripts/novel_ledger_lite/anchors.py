"""Verbatim historical and adjacent-scene quotes from committed events.

章纲点名的资产按倒排取证据；相邻场景固定抽取首末事件原句与摘要。
抽取结果核对冻结正文，异常留痕，减少重复读取整章历史。"""
from __future__ import annotations

from .contracts import DEFAULTS, policy_default, require
from .evidence import evidence as verify_quote
from . import delta as delta_ledger


def _event_quote(event, store, chapter_n, findings):
    """One verbatim quote from a committed event; unreadable pages are skipped with a note,
    never silently."""
    ref = event.get('evidence')
    if not isinstance(ref, dict) or ref.get('chapter') is None:
        findings.append({'asset': event.get('id') or event.get('topic'), 'reason': '事件缺少可核验引文。'})
        return None
    try:
        checked = verify_quote(ref, {chapter_n: store.prose_page(chapter_n)})
    except Exception as error:              # 引文与冻结正文不一致：锚句宁缺毋滥，但必须留痕。
        findings.append({'asset': event.get('id') or event.get('topic'), 'reason': str(error)})
        return None
    return {'chapter': chapter_n, 'start': checked['start'], 'quote': checked['quote']}


def prior_anchors(book, store, plan, chapter):
    """引用驱动的原句清单：[{ref_kind, asset, chapter, quote, start}]。

    定位次序（报告机制 7 的 lite 版）：先查倒排（L4），命中才取该章 events 过滤；
    倒排 miss 即无锚句（recall 的兜底通道仍可用，信封不承载全文）。
    """
    inverted = book.get('inverted') or {}
    findings = []
    anchors = []
    wanted = [('hook_ref', 'hook_refs', 'hook'),
              ('history_ref', 'history_refs', 'historical_assertion'),
              ('reader_ref', 'reader_refs', 'reader_knowledge')]
    for ref_kind, field, op in wanted:
        for asset in plan.get(field) or []:
            pages = inverted.get(asset) or []
            for page_n in sorted(pages):
                if page_n >= chapter:
                    break
                for event in store.events_page(page_n):
                    if event.get('op') != op:
                        continue
                    if op == 'hook' and event.get('id') != asset:
                        continue
                    if op == 'historical_assertion' and event.get('id') != asset:
                        continue
                    if op == 'reader_knowledge' and event.get('topic') != asset:
                        continue
                    quote = _event_quote(event, store, page_n, findings)
                    if quote:
                        quote.update({'ref_kind': ref_kind, 'asset': asset, 'op': op})
                        anchors.append(quote)
                    break                           # 每个引用取首次登记的原句一句。
    return {'anchors': anchors, 'unmatched': findings}


def scene_anchors(book, store, chapter):
    """窗口驱动的开篇/收束句：[{chapter, position, quote, summary}]。

    每章固定首/末事件各一句（选取规则可调，引擎确定性抽取零模型）；2~3 章约
    具体条数由 scene_anchor_chapters 决定，不携带窗口之外的整章正文。
    """
    window = policy_default('scene_anchor_chapters')
    rows = []
    findings = []
    for n in range(max(1, chapter - window), chapter):
        row = store.chapter('main', n)
        if row is None:
            continue
        events = store.events_page(n)
        picks = []
        if events:
            for position, event in (('open', events[0]), ('close', events[-1])):
                quote = _event_quote(event, store, n, findings)
                if quote:
                    quote['position'] = position
                    picks.append(quote)
        rows.append({'chapter': n, 'summary': row.get('summary', ''), 'quotes': picks})
    return {'anchors': rows, 'unmatched': findings}
