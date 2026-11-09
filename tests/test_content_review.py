"""Exercise the real independent-review APIs and commit gate without an approval wrapper."""
import copy
import json

import pytest

import fixtures
from novel_ledger_lite import pipeline
from novel_ledger_lite.contracts import Error
from novel_ledger_lite.store import LiteStore


def installed(*, packaged=False):
    book, _, _ = fixtures.open_installed_book(with_scenes=True)
    store = LiteStore()
    draft = fixtures.draft_for(book, 1)
    if packaged:
        draft['package_ref'] = pipeline.chapter_package(book, store, 1)['package_ref']
    return book, store, draft


def request_for(book, store, draft, chapter=1):
    return pipeline.review_request(book, store, chapter, draft, writer='test-writer')


def report_for(request, draft, *, verdict='pass'):
    """Synthetic reader report for gate tests, not a semantic quality judgment."""
    items = draft['drift_check']['items']
    events = []
    for entry in request['manifest']['event_checks']:
        declared = next(item for item in items
                        if item['kind'] == entry['kind'] and item['key'] == entry['key'])
        events.append({'id': entry['id'], 'status': 'pass',
                       'notes': '机械回归中的逐项引文绑定。',
                       'evidence': copy.deepcopy(declared['evidence'])})
    return {'request_ref': request['request_ref'],
            'reviewer': 'test-independent-reader', 'verdict': verdict,
            'read_complete': True,
            'checks': [{'id': key, 'status': 'pass', 'notes': '机械回归中的全文检查覆盖。'}
                       for key in request['manifest']['checks']],
            'event_checks': events,
            'findings': [] if verdict == 'pass' else [{'reason': '测试读者指出材料不足或正文矛盾。'}]}


def approve(book, store, draft, chapter=1):
    request = request_for(book, store, draft, chapter)
    reference = pipeline.record_content_review(book, store, request['request_ref'], report_for(request, draft))
    draft['review_ref'] = reference
    return request, reference


def test_real_submit_rejects_missing_review_without_advancing_or_mutating_storage():
    book, store, draft = installed()
    before = copy.deepcopy(book), copy.deepcopy(store.to_dict())
    with pytest.raises(Error) as caught:
        pipeline.submit(book, store, 1, draft)
    assert caught.value.code == 'content_review_required'
    assert (book, store.to_dict()) == before


@pytest.mark.parametrize('reader', ['test-writer', ' test-writer '])
def test_writer_cannot_approve_its_own_request(reader):
    book, store, draft = installed()
    request = request_for(book, store, draft)
    report = report_for(request, draft)
    report['reviewer'] = reader
    before = copy.deepcopy(store.to_dict())
    with pytest.raises(Error) as caught:
        pipeline.record_content_review(book, store, request['request_ref'], report)
    assert caught.value.code == 'content_review_independence'
    assert store.to_dict() == before


def test_new_rejection_invalidates_old_approval_and_cannot_itself_authorize_submit():
    book, store, draft = installed()
    _, old = approve(book, store, draft)
    request = request_for(book, store, draft)
    rejection = pipeline.record_content_review(book, store, request['request_ref'],
                                                report_for(request, draft, verdict='reject'))
    with pytest.raises(Error) as old_error:
        pipeline.submit(book, store, 1, draft)
    assert old_error.value.code == 'content_review_required'
    draft['review_ref'] = rejection
    with pytest.raises(Error) as latest_error:
        pipeline.submit(book, store, 1, draft)
    assert latest_error.value.code == 'content_review_rejected'
    assert store.latest_content_review(1)[1]['previous'] == old
    assert store.last_chapter() == book['last_chapter'] == 0


def test_old_report_cannot_be_registered_again_on_its_original_request_after_rejection():
    book, store, draft = installed()
    original = request_for(book, store, draft)
    old_report = report_for(original, draft)
    pipeline.record_content_review(book, store, original['request_ref'], old_report)
    later = request_for(book, store, draft)
    rejected = pipeline.record_content_review(book, store, later['request_ref'],
                                              report_for(later, draft, verdict='reject'))
    before = copy.deepcopy(store.to_dict())
    with pytest.raises(Error) as caught:
        pipeline.record_content_review(book, store, original['request_ref'], old_report)
    assert caught.value.code == 'content_review_replayed'
    assert store.to_dict() == before
    assert store.latest_content_review(1)[0] == rejected


def test_old_report_cannot_replay_on_a_new_request_but_a_new_bound_report_can_proceed():
    book, store, draft = installed(packaged=True)
    original = request_for(book, store, draft)
    old_report = report_for(original, draft)
    pipeline.record_content_review(book, store, original['request_ref'], old_report)
    rejection_request = request_for(book, store, draft)
    rejected = pipeline.record_content_review(book, store, rejection_request['request_ref'],
        report_for(rejection_request, draft, verdict='reject'))
    fresh = request_for(book, store, draft)
    assert fresh['request_ref'] != original['request_ref']
    assert fresh['manifest']['attempt'] != original['manifest']['attempt']
    before = copy.deepcopy(store.to_dict())
    with pytest.raises(Error) as caught:
        pipeline.record_content_review(book, store, fresh['request_ref'], old_report)
    assert caught.value.code == 'content_review_replayed'
    assert store.to_dict() == before
    assert store.latest_content_review(1)[0] == rejected
    draft['review_ref'] = pipeline.record_content_review(book, store, fresh['request_ref'],
                                                        report_for(fresh, draft))
    assert store.latest_content_review(1)[1]['previous'] == rejected
    assert pipeline.submit(book, store, 1, draft)['ok']


@pytest.mark.parametrize('verdict', ['reject', 'needs_material'])
def test_negative_or_missing_material_review_is_retained_but_never_committed(verdict):
    book, store, draft = installed(packaged=True)
    request = request_for(book, store, draft)
    report = report_for(request, draft, verdict=verdict)
    report['checks'][0]['status'] = 'uncertain'
    draft['review_ref'] = pipeline.record_content_review(book, store, request['request_ref'], report)
    before = copy.deepcopy(book), copy.deepcopy(store.to_dict())
    with pytest.raises(Error) as caught:
        pipeline.submit(book, store, 1, draft)
    assert caught.value.code == 'content_review_rejected'
    assert (book, store.to_dict()) == before


@pytest.mark.parametrize('invalid', ['not_read', 'missing_category', 'missing_event', 'uncertain_category',
                                   'uncertain_event', 'findings', 'duplicate_category', 'bad_evidence'])
def test_pass_requires_complete_certain_checks_and_actual_event_quotes(invalid):
    book, store, draft = installed()
    request = request_for(book, store, draft)
    report = report_for(request, draft)
    if invalid == 'not_read':
        report['read_complete'] = False
    elif invalid == 'missing_category':
        report['checks'].pop()
    elif invalid == 'missing_event':
        report['event_checks'].pop()
    elif invalid == 'uncertain_category':
        report['checks'][0]['status'] = 'uncertain'
    elif invalid == 'uncertain_event':
        report['event_checks'][0]['status'] = 'uncertain'
    elif invalid == 'findings':
        report['findings'] = [{'reason': '仍有未解决的问题。'}]
    elif invalid == 'duplicate_category':
        report['checks'].append(copy.deepcopy(report['checks'][0]))
    else:
        report['event_checks'][0]['evidence']['quote'] = '这句话并不存在于待审全文。'
    before = copy.deepcopy(store.to_dict())
    with pytest.raises(Error):
        pipeline.record_content_review(book, store, request['request_ref'], report)
    assert store.to_dict() == before


@pytest.mark.parametrize('field', ['title', 'summary', 'self_check', 'prose', 'drift_check'])
def test_review_is_bound_to_the_entire_exact_candidate(field):
    book, store, draft = installed()
    approve(book, store, draft)
    if field == 'drift_check':
        ref = draft['drift_check']['items'][0]['evidence']
        ref['start'] = draft['prose'].index(ref['quote'])
    else:
        draft[field] += '复核补记。'
    before = copy.deepcopy(book), copy.deepcopy(store.to_dict())
    with pytest.raises(Error) as caught:
        pipeline.submit(book, store, 1, draft)
    assert caught.value.code == 'content_review_stale'
    assert (book, store.to_dict()) == before


def test_source_change_expires_both_pending_requests_and_previous_approvals():
    book, store, draft = installed()
    approve(book, store, draft)
    request = request_for(book, store, draft)
    pipeline.recontract_patch(book, source='作者确认更换文风。', style_profile='账房掌门')
    with pytest.raises(Error) as pending:
        pipeline.record_content_review(book, store, request['request_ref'], report_for(request, draft))
    assert pending.value.code == 'content_review_stale'
    with pytest.raises(Error) as approved:
        pipeline.submit(book, store, 1, draft)
    assert approved.value.code == 'content_review_stale'


def test_supplemented_packet_expires_old_review_even_after_candidate_updates_package_reference():
    book, store, draft = installed(packaged=True)
    book['state']['facts']['remote:letter'] = '补充的远方来信。'
    # Prepare from the final source state, then review that exact packet.
    draft['package_ref'] = pipeline.chapter_package(book, store, 1)['package_ref']
    approve(book, store, draft)
    revised = pipeline.chapter_package(book, store, 1,
        extra_resources=[{'kind': 'facts', 'key': 'remote:letter'}])
    draft['package_ref'] = revised['package_ref']
    with pytest.raises(Error) as caught:
        pipeline.submit(book, store, 1, draft)
    assert caught.value.code == 'content_review_stale'


@pytest.mark.parametrize('initial_package', [False, True])
def test_late_old_packet_report_cannot_replace_the_new_packets_approval(initial_package):
    book, store, draft = installed()
    book['state']['facts']['remote:letter'] = '准备者确认的补充来信。'
    if initial_package:
        draft['package_ref'] = pipeline.chapter_package(book, store, 1)['package_ref']
    old_request = request_for(book, store, draft)
    old_rejection = report_for(old_request, draft, verdict='needs_material')
    supplemented = pipeline.chapter_package(book, store, 1,
        extra_resources=[{'kind': 'facts', 'key': 'remote:letter'}])
    draft['package_ref'] = supplemented['package_ref']
    _, current_approval = approve(book, store, draft)
    with pytest.raises(Error):
        pipeline.record_content_review(book, store, old_request['request_ref'], old_rejection)
    assert store.latest_content_review(1)[0] == current_approval
    assert pipeline.submit(book, store, 1, draft)['ok']


def test_review_and_exact_supplemental_material_survive_save_load_before_commit(tmp_path):
    book, store, draft = installed(packaged=True)
    request, review = approve(book, store, draft)
    path = tmp_path / 'reviewed.json'
    pipeline.save(book, store, path)
    restored, saved = pipeline.load(path)
    assert saved.to_dict()['schema'] == 'novel-ledger-lite.store/4'
    assert saved.latest_content_review(1)[0] == review
    assert saved.read_document(request['manifest']['materials']) in request['text']
    assert pipeline.submit(restored, saved, 1, draft)['ok']
    assert saved.chapter('main', 1)['review']['content_review_ref'] == review


@pytest.mark.parametrize('damage', ['empty_heads', 'missing_heads', 'missing_document', 'downgrade'])
def test_saved_approval_cannot_silently_lose_its_persistent_head(tmp_path, damage):
    book, store, draft = installed()
    _, review = approve(book, store, draft)
    path = tmp_path / 'review-damaged.json'
    pipeline.save(book, store, path)
    raw = json.loads(path.read_text(encoding='utf-8'))
    if damage == 'empty_heads':
        raw['store']['review_heads'] = {}
    elif damage == 'missing_heads':
        del raw['store']['review_heads']
    elif damage == 'missing_document':
        del raw['store']['documents'][review]
    else:
        raw['store']['schema'] = 'novel-ledger-lite.store/3'
        del raw['store']['review_heads']
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(Error):
        pipeline.load(path)


def test_saved_head_cannot_roll_back_a_new_rejection_to_an_old_approval(tmp_path):
    book, store, draft = installed()
    _, approved = approve(book, store, draft)
    request = request_for(book, store, draft)
    pipeline.record_content_review(book, store, request['request_ref'],
                                   report_for(request, draft, verdict='reject'))
    path = tmp_path / 'rolled-back-head.json'
    pipeline.save(book, store, path)
    raw = json.loads(path.read_text(encoding='utf-8'))
    raw['store']['review_heads']['1'] = approved
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(Error):
        pipeline.load(path)


def test_committed_review_reference_cannot_disappear_while_its_persistent_head_remains(tmp_path):
    book, store, draft = installed(packaged=True)
    approve(book, store, draft)
    assert pipeline.submit(book, store, 1, draft)['ok']
    path = tmp_path / 'missing-committed-review-reference.json'
    pipeline.save(book, store, path)
    raw = json.loads(path.read_text(encoding='utf-8'))
    del raw['store']['chapters']['1']['review']['content_review_ref']
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(Error):
        pipeline.load(path)


def test_committed_review_chain_is_checked_by_full_audit_and_load(tmp_path):
    book, store, first = installed(packaged=True)
    for n in range(1, 5):
        draft = first if n == 1 else fixtures.draft_for(book, n)
        if n > 1:
            draft['package_ref'] = pipeline.chapter_package(book, store, n)['package_ref']
        approve(book, store, draft, n)
        assert pipeline.submit(book, store, n, draft)['ok']
    assert pipeline.verify_full(book, store)['ok']
    path = tmp_path / 'complete.json'
    pipeline.save(book, store, path)
    restored, saved = pipeline.load(path)
    assert pipeline.verify_full(restored, saved)['ok']
    review = saved.chapter('main', 2)['review']['content_review_ref']
    del saved._documents[review]
    assert not pipeline.verify_full(restored, saved)['ok']
    pipeline.save(restored, saved, path)
    with pytest.raises(Error):
        pipeline.load(path)
