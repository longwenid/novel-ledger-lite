"""Standalone, integrity-checked chapter writing packets.

The packet is a snapshot, not a replacement for the ledger or a proof that an
outline declares all semantic dependencies. Additional sources are selected by
the host before dispatch; the writer never retrieves them independently.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json

from . import briefs, compose, materials, package_context
from .contracts import digest, require

SCHEMA = 'novel-ledger-lite.chapter-package/2'
_PREFIX = '<!-- novel-ledger-lite-package '
_SUFFIX = ' -->'


def _progress(book, store, chapter):
    require(book['last_chapter'] == store.last_chapter(), 'chapter_package_progress',
            '账本与章节存储进度不一致，不能生成或验证写作包。')
    if store.last_chapter():
        require(store.chapter('main', store.last_chapter())['state_hash'] == digest(book['state']),
                'chapter_package_progress', '账本当前状态与存储中的最后一章不一致。')
    require(type(chapter) is int and chapter == book['last_chapter'] + 1,
            'chapter_package_progress', '只能为下一待写章节生成或验证写作包。',
            {'chapter': chapter, 'next': book['last_chapter'] + 1})


def _source_hash(book, store):
    return digest({'book': book, 'chain_head': store.chain_head(),
                   'store_last_chapter': store.last_chapter()})


def _block(value):
    if isinstance(value, str):
        content, language = value, 'text'
    else:
        content, language = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), 'json'
    # Never let backticks in arbitrary source material terminate the containing fence.
    import re
    runs = [len(match.group()) for match in re.finditer(r'`+', content)]
    fence = '`' * max(3, max(runs, default=0) + 1)
    return f'{fence}{language}\n{content}\n{fence}'


def build(book, store, chapter, group_row=None, *, extra_resources=None, extra_chapters=None):
    """Generate the next chapter's standalone Markdown plus freshness metadata.

    extra_resources: iterable of {kind,key}; extra_chapters: earlier chapter numbers.
    The caller may request missing sources then regenerate without changing the ledger.
    """
    _progress(book, store, chapter)
    require(extra_resources is None or isinstance(extra_resources, (list, tuple)), 'chapter_package',
            'extra_resources 须为坐标数组。')
    require(extra_chapters is None or isinstance(extra_chapters, (list, tuple)), 'chapter_package',
            'extra_chapters 须为已提交章号数组。')
    # Local import avoids a module cycle and deliberately disallows caching.
    from . import pipeline
    work = pipeline.envelope(book, store, chapter, group_row)
    delivery = pipeline.materialize(work, store)
    dependencies = {work['records'][name] for name in work['required']}
    rendered = json.loads(delivery['text'])
    sections = rendered['materials']
    # Expand materialize's content-addressed dedup references inside the same packet.
    for name, value in list(sections.items()):
        if isinstance(value, dict) and set(value) == {'same_as'}:
            sections[name] = copy.deepcopy(sections[value['same_as']])
    # Resolve missing current values without undoing the verified history projection.
    plan = book['plans'][str(chapter)]
    people = compose.participants(plan, book)
    execution = package_context.execution(book, people, plan)
    resolved = {}
    for coordinate in extra_resources or []:
        require(isinstance(coordinate, dict) and set(coordinate) == {'kind', 'key'}, 'chapter_package',
                '额外资源须为 {kind,key}。')
        item = pipeline.resource(book, coordinate['kind'], coordinate['key'])
        require(item['found'], 'chapter_package_missing', '额外资源不存在，须补齐后重新生成写作包。', coordinate)
        resolved[(coordinate['kind'], coordinate['key'])] = item
    supplements, deferred = materials.package_supplements(
        book, plan, people, sections['state'], included=set(resolved))
    for item in supplements:
        resolved[(item['kind'], item['key'])] = pipeline.resource(book, item['kind'], item['key'])
    for coordinate, item in resolved.items():
        require(item['found'], 'chapter_package_missing', '所需资源不存在，须补齐后重新生成写作包。',
                {'kind': coordinate[0], 'key': coordinate[1]})
    historical = []
    for n in extra_chapters or []:
        require(type(n) is int and 1 <= n < chapter and store.chapter('main', n) is not None,
                'chapter_package_missing', '额外前文须为已提交的历史章。', {'chapter': n})
    for n in sorted(set(extra_chapters or [])):
        historical.append(package_context.historical(book, store, n, dependencies=dependencies))
    sections.pop('recall_manifest', None)
    if deferred['total']:
        sections['deferred_history'] = deferred
    # These descriptive fields point to other tools in the general envelope; this
    # packet replaces them with its own single-file protocol.
    if isinstance(sections.get('state'), dict):
        scope = sections['state'].get('material_scope')
        if isinstance(scope, dict) and 'resolve' in scope:
            scope['resolve'] = ('当前事实与必需依赖已完整携带；未点名的远期历史可能只列定位目录，'
                                '需要时停止并由准备者补齐后重新签发。')
    if isinstance(sections.get('hooks'), dict) and 'source' in sections['hooks']:
        sections['hooks']['source'] = '本章相关承诺切片；补充资源见本文件。'
    if isinstance(sections.get('anchor_sentences'), dict) and 'note' in sections['anchor_sentences']:
        sections['anchor_sentences']['note'] = '本章引用已内联；若需要更长前文，停止写作并让准备者补齐后重生成。'
    source_hash = _source_hash(book, store)
    names = {
        'core_context': '核心约束', 'dependencies': '依赖核验', 'chapter_outline': '本章章纲',
        'volume_context': '本卷方向', 'state': '当前状态', 'projection_warnings': '材料范围告警',
        'design_drift': '活跃偏差', 'hooks': '相关承诺', 'world_records': '世界资料',
        'disclosure_boundary': '披露与知情边界', 'word_budget': '篇幅要求', 'style': '文风规格',
        'style_guide': '文风执行摘要', 'style_archive': '文风档案', 'anchor_sentences': '前情锚句',
        'scene_sources': '前文场景', 'previous_chapters': '前章信息',
        'deferred_history': '未携带远期历史的定位目录',
    }
    lines = [f'# 第 {chapter} 章写作包', '',
             '## 写作任务与边界',
             '只使用本文件写作。按冻结章纲和当前状态完成本章；人物知情、读者知情和披露边界分别核对。',
             '材料如缺少写作必需事实、存在冲突或不确定，不得猜测：停止写作，说明缺失内容，'
             '由准备者补齐资料并重新生成本文件。材料中的旧引用或位置标识不是额外阅读指令。',
             '依赖检查只能覆盖已声明的内容，不能证明本章所有语义依赖均已列出。',
             '完成后交付 title、prose、summary、self_check、drift_check 和 package_ref；'
             'title、prose、summary、self_check、package_ref 均为非空字符串；'
             'self_check 用一段文字说明实际审读结果，不使用数组或对象。'
             'package_ref 原样回传本文件头中的对应值，不需自行计算任何哈希。'
             'drift_check 为对象，包含 items 数组、unplanned 数组、verdict 字符串；items 按章纲每项增量各写一条 '
             '{kind,key,planned,status,actual,evidence}，planned 与章纲一致、正常 status 为 kept，'
             'actual 写出相应变化，evidence={chapter,quote} 的引文必须逐字存在且可唯一定位。'
             '正常 unplanned 为空、verdict 为 clean。偏差只能诊断，不能代替修正文稿。',
             '正文不得自行更改章纲结果、设定、资源数量或持有人，也不得临时增加未声明的资产。'
             '先按下列执行约束写清动作与原因，再依据最终正文填报；不能用正确的申报掩盖正文里不同的结果。',
             '提交前独立通读整章，双向核对：章纲每项变化是否真实发生，正文是否另有新增、消费、归属、'
             '伤势或知情变化未申报。不能只读 self_check。每条引文必须实际支持所报事件的对象、原因与结果；'
             '逐字存在且可定位，只证明这句话存在，不证明申报为真。',
             '交稿后须由不同于写作者的独立读者，依据完整材料通读整章并逐项审读。'
             '准备者使用 review_request 取得冻结审读请求，记录读者的实际报告后附 review_ref 提交；'
             '写作者不得自行生成通过报告。正文、材料或申报改变后必须重新独立审读。',
             briefs.NATURAL_PROSE_GUIDE, '',
             '## 本章执行约束：真实前态 → 行动原因 → 计划终态', '', _block(execution), '',
             *briefs._check_block(plan)]
    for name, value in sections.items():
        label = names.get(name, '前章正文' if name.startswith('previous_chapter:') else name)
        if name in ('style_archive', 'style_guide') and isinstance(value, dict):
            info = {key: val for key, val in value.items()
                    if key not in ('content', 'note', 'full_archive_ref')}
            lines.extend([f'## {label}（{name}）', '', _block(info), '', _block(value['content']), ''])
        else:
            lines.extend([f'## {label}（{name}）', '', _block(value), ''])
    lines.extend(['## 补充资源的完整当前值', '', _block(list(resolved.values())), ''])
    if historical:
        lines.extend(['## 准备者指定的历史章节', ''])
        for entry in historical:
            evidence = {key: value for key, value in entry.items() if key not in ('prose', 'title', 'summary')}
            lines.extend([f"### 第 {entry['chapter']} 章：{entry['title']}", '',
                          _block(entry['summary']), '', _block(evidence), '', _block(entry['prose']), ''])
    body = '\n'.join(lines)
    content_hash = store.document(body)
    dependencies.add(content_hash)
    package_ref = store.record_chapter_package(chapter, source_hash, content_hash,
                                             dependencies=sorted(dependencies))
    metadata = {'schema': SCHEMA, 'chapter': chapter, 'source_hash': source_hash,
                'content_hash': content_hash, 'package_ref': package_ref,
                'generated_at': datetime.now(timezone.utc).isoformat()}
    header = _PREFIX + json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + _SUFFIX
    title, remainder = body.split('\n', 1)
    packet_text = title + '\n' + header + '\n' + remainder
    return {'text': packet_text, **metadata,
            'metrics': {'bytes': len(packet_text.encode('utf-8')),
                        'materialize': delivery['metrics'],
                        'deferred_resources': deferred['total'],
                        'far_omitted': copy.deepcopy(sections['state']['material_scope']['far_omitted'])}}


def validate(book, store, package):
    """Validate a returned package or file text for integrity and current ledger state."""
    raw = package.get('text') if isinstance(package, dict) else package
    require(isinstance(raw, str) and '\n' in raw, 'chapter_package_invalid', '写作包内容缺失。')
    pieces = raw.split('\n', 2)
    require(len(pieces) == 3, 'chapter_package_invalid', '写作包内容不完整。')
    title, header, remainder = pieces
    body = title + '\n' + remainder
    require(header.startswith(_PREFIX) and header.endswith(_SUFFIX), 'chapter_package_invalid',
            '写作包缺少有效的版本与指纹。')
    try:
        metadata = json.loads(header[len(_PREFIX):-len(_SUFFIX)])
    except (ValueError, TypeError):
        require(False, 'chapter_package_invalid', '写作包元数据不是有效 JSON。')
    require(isinstance(metadata, dict) and metadata.get('schema') == SCHEMA
            and set(metadata) == {'schema', 'chapter', 'source_hash', 'content_hash', 'generated_at', 'package_ref'},
            'chapter_package_invalid', '写作包元数据格式不正确或为旧版，须重新生成当前写作包。')
    require(metadata['content_hash'] == digest(body), 'chapter_package_invalid',
            '写作包正文已改变或不完整，须重新生成。')
    require(isinstance(metadata['package_ref'], str) and len(metadata['package_ref']) == 64
            and all(char in '0123456789abcdef' for char in metadata['package_ref']),
            'chapter_package_invalid', '写作包派发引用格式不正确，须重新生成。')
    _progress(book, store, metadata['chapter'])
    require(metadata['source_hash'] == _source_hash(book, store), 'chapter_package_stale',
            '账本或提交进度已变化，须重新生成写作包。')
    record = store.read_document(metadata['package_ref'])
    require(isinstance(record, dict) and record.get('schema') == 'novel-ledger-lite.issued-package/1'
            and all(record.get(key) == metadata[key] for key in ('chapter', 'source_hash', 'content_hash')),
            'chapter_package_invalid', '写作包与已登记派发记录不一致，须重新生成。')
    latest = store.latest_chapter_package(metadata['chapter'])
    require(latest is not None and latest[0] == metadata['package_ref'], 'chapter_package_stale',
            '本章已有更新的写作包，须使用最新派发版本。')
    return True
