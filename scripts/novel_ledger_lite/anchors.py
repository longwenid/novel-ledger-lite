"""Verbatim historical and adjacent-scene quotes from committed chapters.

章纲点名的资产按倒排取事件证据句；相邻章固定抽取已提交正文的首/末非空段与摘要。
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


def _paragraph_quotes(prose):
    """已提交正文的首/末非空段及其原文偏移 [(start, 段落原文), ...]；空正文返回 []。

    确定性抽取零模型：段落按换行切分、去首尾空白，start 是段落在原文中的偏移，
    供 evidence 按位置逐字核验（重复段落也可核验）。"""
    picks = []
    offset = 0
    for segment in prose.split('\n'):
        stripped = segment.strip()
        if stripped:
            picks.append((offset + (len(segment) - len(segment.lstrip())), stripped))
        offset += len(segment) + 1
    if not picks:
        return []
    return picks[0], picks[-1]


def scene_anchors(book, store, chapter):
    """窗口驱动的开篇/收束段：[{chapter, position, quote, summary}]。

    每章固定取已提交正文（store.prose_page）的首/末非空段——章界声线衔接取真实叙事段，
    不再取核账用的证据句；事件证据句只保留在 prior 引用通道（prior_anchors）。抽取结果
    仍经 evidence 逐字核验（带 start），异常留痕；2~3 章条数由 scene_anchor_chapters 决定，
    不携带窗口之外的整章正文。
    """
    window = policy_default('scene_anchor_chapters')
    rows = []
    findings = []
    for n in range(max(1, chapter - window), chapter):
        row = store.chapter('main', n)
        if row is None:
            continue
        prose = store.prose_page(n)
        picks = []
        for position, (start, quote) in zip(('open', 'close'), _paragraph_quotes(prose)):
            try:
                checked = verify_quote({'chapter': n, 'quote': quote, 'start': start}, {n: prose})
            except Exception as error:      # 引文与冻结正文不一致：锚句宁缺毋滥，但必须留痕。
                findings.append({'asset': 'chapter:%d' % n, 'reason': str(error)})
                continue
            picks.append({'chapter': n, 'start': checked['start'], 'quote': checked['quote'],
                          'position': position})
        rows.append({'chapter': n, 'summary': row.get('summary', ''), 'quotes': picks})
    return {'anchors': rows, 'unmatched': findings}


def aggregate(prior, scene, *, full_chapters=()):
    """按引文文本聚合信封锚句：一条唯一引文携带全部角色，同一原句只下发一次。

    角色写作 prior.<ref_kind>#<asset>（章纲点名的历史证据句）与 scene.<position>
    （前窗开篇/收束段）；被 previous_chapter:N 全文携带的章（full_chapters）不再重复
    摘要，其余窗口章保留一行。unmatched 留痕原样合并。"""
    quotes, index = [], {}

    def carry(quote, role):
        entry = index.get(quote['quote'])
        if entry is None:
            entry = {'chapter': quote['chapter'], 'start': quote['start'],
                     'quote': quote['quote'], 'roles': []}
            index[quote['quote']] = entry
            quotes.append(entry)
        entry['roles'].append(role)

    for quote in prior.get('anchors') or []:
        carry(quote, 'prior.%s#%s' % (quote['ref_kind'], quote['asset']))
    for row in scene.get('anchors') or []:
        for quote in row.get('quotes') or []:
            carry(quote, 'scene.%s' % quote['position'])
    return {'quotes': quotes,
            'summaries': [{'chapter': row['chapter'], 'summary': row.get('summary', '')}
                          for row in scene.get('anchors') or []
                          if row['chapter'] not in full_chapters and row.get('summary')],
            'unmatched': [*(prior.get('unmatched') or []), *(scene.get('unmatched') or [])],
            'note': '引用已内联、无需 recall；确需更长前文才用 recall/history_source 补读。'}
