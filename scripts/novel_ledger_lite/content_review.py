"""Bind independent prose review to the exact draft and frozen writing materials.

This is an enforced review protocol, not a natural-language truth detector. The
host must give the request to a different reader and faithfully record its report.
"""
from __future__ import annotations

import copy
import json
import uuid

from .contracts import digest, require, text
from .drift_reconcile import _planned
from .evidence import evidence

REQUEST_SCHEMA = 'novel-ledger-lite.review-request/1'
REVIEW_SCHEMA = 'novel-ledger-lite.content-review/1'
CHECKS = ('outline', 'continuity', 'assets', 'knowledge', 'causality', 'unplanned')
STATUSES = ('pass', 'fail', 'uncertain')


def _manifest(value):
    fields = {'schema', 'attempt', 'chapter', 'writer', 'source_hash', 'draft', 'materials', 'package_ref',
              'plan', 'contract', 'before_state_hash', 'previous_chain', 'checks', 'event_checks'}
    def fingerprint(item):
        return isinstance(item, str) and len(item) == 64 and all(c in '0123456789abcdef' for c in item)
    require(isinstance(value, dict) and set(value) == fields
            and value['schema'] == REQUEST_SCHEMA and type(value['chapter']) is int
            and isinstance(value['attempt'], str) and len(value['attempt']) == 32
            and all(c in '0123456789abcdef' for c in value['attempt'])
            and value['chapter'] >= 1 and text(value['writer'])
            and all(fingerprint(value[key]) for key in
                    ('source_hash', 'draft', 'materials', 'plan', 'contract', 'before_state_hash'))
            and (value['package_ref'] is None or fingerprint(value['package_ref']))
            and (value['previous_chain'] is None or fingerprint(value['previous_chain']))
            and value['checks'] == list(CHECKS) and isinstance(value['event_checks'], list),
            'content_review_record', '审读请求格式不完整或指纹损坏。')
    return value


def payload(draft):
    require(isinstance(draft, dict), 'content_review', '待审稿须为对象。')
    return {key: copy.deepcopy(value) for key, value in draft.items() if key != 'review_ref'}


def request(book, store, chapter, draft, *, writer):
    from . import chapter_package, pipeline
    chapter_package._progress(book, store, chapter)
    require(text(writer), 'content_review', '须登记实际写作者身份或会话标识。')
    candidate = payload(draft)
    require(all(text(candidate.get(key)) for key in ('title', 'prose', 'summary', 'self_check')),
            'content_review', '审读需要完整的 title/prose/summary/self_check。')
    plan = book['plans'].get(str(chapter))
    require(plan is not None, 'content_review', '待审章节尚无已确认章纲。')
    current_source = chapter_package._source_hash(book, store)
    issued = store.latest_chapter_package(chapter)
    if issued is not None:
        require(candidate.get('package_ref') == issued[0], 'chapter_package_required',
                '审读必须使用本章最新写作包引用。')
        require(issued[1]['source_hash'] == current_source,
                'chapter_package_stale', '材料已变化，先重新生成写作包。')
        materials_ref = issued[1]['content_hash']
        require(materials_ref in store._documents, 'content_review_materials',
                '旧签发记录未保存完整包正文，须重新生成当前写作包再独立审读。')
        context = store.read_document(materials_ref)
    else:
        require(candidate.get('package_ref') is None, 'chapter_package_required',
                '未签发的写作包引用不能用于审读。')
        work = pipeline.envelope(book, store, chapter)
        context = pipeline.materialize(work, store)['text']
        materials_ref = store.document(context)
    manifest = {
        'schema': REQUEST_SCHEMA, 'attempt': uuid.uuid4().hex,
        'chapter': chapter, 'writer': writer.strip(),
        'source_hash': current_source,
        'draft': store.document(candidate), 'materials': materials_ref,
        'package_ref': candidate.get('package_ref'),
        'plan': store.document(plan), 'contract': store.document(book['contract']),
        'before_state_hash': digest(book['state']), 'previous_chain': store.chain_head(),
        'checks': list(CHECKS),
        'event_checks': [{'id': digest(entry), **entry} for entry in _planned(plan)],
    }
    reference = store.document(manifest)
    from .chapter_package import _block
    instructions = (
        '# 独立正文审读\n\n'
        '你须是不同于写作者的独立读者。先通读下列完整材料和整章正文，再核对申报；'
        '不能把 self_check、clean 或逐字引文当成语义通过证明。\n'
        '双向检查每项计划是否实际发生，以及正文是否另有新增资产、消费、归属、伤势、'
        '事实、规则、时序、人物或读者知情变化。区分作者真相、人物推测与读者获知。'
        '逐项引文必须真实支持对象、原因、结果；全章前后矛盾也须列出。\n'
        '材料缺失、矛盾或无法确认时 verdict=needs_material；有漂移时 verdict=reject。'
        '没有把握不得通过。不得修改稿件或替写作者补造设定。\n'
        '返回报告：request_ref（原样回传本请求引用）、reviewer（独立读者标识）、verdict（pass/reject/needs_material）、'
        'read_complete（布尔）、checks（每类 {id,status,notes}）、event_checks'
        '（逐项 {id,status,notes,evidence:{chapter,quote,start?}}）、findings（问题数组）。'
        'status 为 pass/fail/uncertain；每条 notes 说明实际核对结果。'
        'pass 须完整覆盖全部检查与事件，findings 为空。\n\n'
    )
    rendered = instructions + '## 请求引用\n' + reference + '\n\n'
    rendered += '## 核对清单\n' + _block(manifest) + '\n\n'
    rendered += '## 完整写作材料\n' + _block(context) + '\n\n'
    rendered += '## 待审完整稿件\n' + _block(candidate) + '\n'
    return {'request_ref': reference, 'manifest': copy.deepcopy(manifest), 'text': rendered}


def _check_report(report, manifest, candidate):
    require(isinstance(report, dict) and set(report) == {
        'request_ref', 'reviewer', 'verdict', 'read_complete', 'checks', 'event_checks', 'findings'},
        'content_review', '审读报告字段不完整。')
    require(report['request_ref'] == digest(manifest), 'content_review_replayed',
            '报告必须回传实际审读请求引用，不能复用另一轮的旧报告。')
    require(text(report['reviewer']) and report['reviewer'].strip() != manifest['writer'],
            'content_review_independence', '正文须由不同于写作者的独立读者审读。')
    require(report['verdict'] in ('pass', 'reject', 'needs_material')
            and type(report['read_complete']) is bool and isinstance(report['findings'], list)
            and isinstance(report['checks'], list) and isinstance(report['event_checks'], list),
            'content_review', '审读结论、全文阅读状态或检查列表格式错误。')
    for rows in (report['checks'], report['event_checks']):
        ids = []
        for item in rows:
            require(isinstance(item, dict) and text(item.get('id'))
                    and item.get('status') in STATUSES and text(item.get('notes')),
                    'content_review', '审读每项须有 id/status/notes，不能只勾选通过。')
            ids.append(item['id'])
        require(len(ids) == len(set(ids)), 'content_review', '审读条目不能重复。')
    if report['verdict'] == 'pass':
        require(report['read_complete'] and not report['findings']
                and {row['id'] for row in report['checks']} == set(CHECKS)
                and {row['id'] for row in report['event_checks']} ==
                    {row['id'] for row in manifest['event_checks']}
                and all(row['status'] == 'pass'
                        for row in report['checks'] + report['event_checks']),
                'content_review_incomplete', '通过报告必须完整审读、逐项覆盖且无问题或不确定项。')
        for row in report['event_checks']:
            evidence(row.get('evidence'), {manifest['chapter']: candidate['prose']})


def _current_manifest(book, store, manifest, *, source_hash=None):
    """Do not accept a caller-created request merely because its source hash matches."""
    from . import pipeline
    from .chapter_package import _source_hash
    require(manifest['chapter'] == book['last_chapter'] + 1 == store.last_chapter() + 1
            and manifest['source_hash'] == (source_hash if source_hash is not None else _source_hash(book, store))
            and manifest['plan'] == digest(book['plans'].get(str(manifest['chapter'])))
            and manifest['contract'] == digest(book['contract'])
            and manifest['before_state_hash'] == digest(book['state'])
            and manifest['previous_chain'] == store.chain_head()
            and manifest['event_checks'] == [{'id': digest(entry), **entry}
                                           for entry in _planned(book['plans'][str(manifest['chapter'])])],
            'content_review_stale', '审读请求的章纲、契约、前态或提交链与当前来源不一致。')
    issued = store.latest_chapter_package(manifest['chapter'])
    require(manifest['package_ref'] == (issued[0] if issued else None),
            'content_review_stale', '独立审读期间写作包已更新，旧报告不能替代新包的审读。')
    if issued is not None:
        expected = issued[1]['content_hash']
    else:
        work = pipeline.envelope(book, store, manifest['chapter'])
        expected = digest(pipeline.materialize(work, store)['text'])
    require(manifest['materials'] == expected, 'content_review_stale',
            '审读材料必须是实际签发的完整包或当前规范派工文本，不能替换成其他文档。')


def record(book, store, request_ref, report):
    manifest = _manifest(store.read_document(request_ref))
    _current_manifest(book, store, manifest)
    require(not any(isinstance(value, dict) and value.get('schema') == REVIEW_SCHEMA
                    and value.get('request') == request_ref for value in store._documents.values()),
            'content_review_replayed', '本轮审读请求已有报告；再次审读须重新发起请求，不能重放旧报告。')
    candidate = store.read_document(manifest['draft'])
    store.read_document(manifest['materials'])
    _check_report(report, manifest, candidate)
    latest = store.latest_content_review(manifest['chapter'])
    row = {'schema': REVIEW_SCHEMA, 'chapter': manifest['chapter'], 'request': request_ref,
           'report': copy.deepcopy(report), 'previous': latest[0] if latest else None,
           'sequence': latest[1]['sequence'] + 1 if latest else 1}
    return store.put_content_review(row)


def read_record(store, reference):
    row = store.read_document(reference)
    require(isinstance(row, dict) and set(row) == {
        'schema', 'chapter', 'request', 'report', 'previous', 'sequence'}
        and row['schema'] == REVIEW_SCHEMA and type(row['chapter']) is int
        and row['chapter'] >= 1 and type(row['sequence']) is int and row['sequence'] >= 1,
        'content_review_record', '审读记录格式损坏。')
    manifest = _manifest(store.read_document(row['request']))
    require(manifest['chapter'] == row['chapter'],
            'content_review_record', '审读记录与请求不一致。')
    candidate = store.read_document(manifest['draft'])
    store.read_document(manifest['materials'])
    plan = store.read_document(manifest['plan'])
    require(manifest['event_checks'] == [{'id': digest(entry), **entry} for entry in _planned(plan)],
            'content_review_record', '审读逐项清单与冻结章纲不一致。')
    store.read_document(manifest['contract'])
    _check_report(row['report'], manifest, candidate)
    return row, manifest, candidate


def require_approved(book, store, chapter, draft, *, source_hash=None):
    reference = draft.get('review_ref')
    require(text(reference), 'content_review_required', '提交前必须完成独立全文审读并回传 review_ref。')
    latest = store.latest_content_review(chapter)
    require(latest is not None and latest[0] == reference, 'content_review_required',
            '须使用本章最新的独立审读记录，不能沿用被替代的通过记录。')
    row, manifest, candidate = read_record(store, reference)
    require(row['report']['verdict'] == 'pass', 'content_review_rejected',
            '独立审读未通过；须修正正文或补齐材料后重新审读。')
    _current_manifest(book, store, manifest, source_hash=source_hash)
    require(manifest['draft'] == digest(payload(draft))
            and manifest['package_ref'] == draft.get('package_ref'),
            'content_review_stale', '稿件或材料已改变，原审读不能继续放行。')
    return reference


def verify_committed(store, row, *, before_state_hash=None, previous_chain=None):
    reference = row['review'].get('content_review_ref')
    require(text(reference), 'content_review_required', '该历史章缺少独立正文审读记录，不能声称完整验收。')
    latest = store.latest_content_review(row['n'])
    require(latest is not None and latest[0] == reference,
            'content_review_record', '已提交章与审读持久引用不一致。')
    review, manifest, candidate = read_record(store, reference)
    expected = {'title': row['title'], 'prose': store.read_document(row['prose']),
                'summary': row['summary'], 'self_check': row['review']['self_check'],
                'drift_check': row['review']['drift_check']}
    require(review['report']['verdict'] == 'pass'
            and all(candidate.get(key) == value for key, value in expected.items())
            and candidate.get('package_ref') == row['review'].get('package_ref')
            and manifest['plan'] == row['plan'] and manifest['contract'] == row['contract_hash'],
            'content_review_record', '提交正文、章纲、契约或申报与独立审读对象不一致。')
    if manifest['package_ref'] is not None:
        packet = store.read_document(manifest['package_ref'])
        require(packet.get('schema') == 'novel-ledger-lite.issued-package/1'
                and packet.get('source_hash') == manifest['source_hash']
                and packet.get('content_hash') == manifest['materials'],
                'content_review_record', '审读材料不是该章实际签发的写作包。')
    if before_state_hash is not None:
        require(manifest['before_state_hash'] == before_state_hash
                and manifest['previous_chain'] == previous_chain,
                'content_review_record', '审读前态与真实提交链不一致。')
    return True
