"""Caller-created request documents cannot approve different source material.

Reports here are synthetic gate fixtures; they make no semantic quality claim.
"""
import copy

import pytest

from novel_ledger_lite import pipeline
from novel_ledger_lite.contracts import Error
from test_content_review import approve, installed, report_for


def _alter_request(book, store, request, change):
    manifest = copy.deepcopy(request['manifest'])
    if change in ('materials', 'materials_and_plan'):
        manifest['materials'] = store.document('这不是该章实际派发的完整写作材料。')
    if change in ('plan', 'materials_and_plan'):
        plan = copy.deepcopy(book['plans']['1'])
        # Keep exactly the same mechanical event list: the wrong synopsis must
        # still be caught before it can produce an unrestorable committed row.
        plan['synopsis'] = '这是另一份未经实际签发的章纲正文。'
        manifest['plan'] = store.document(plan)
    if change == 'contract':
        contract = copy.deepcopy(book['contract'])
        contract['title'] = '另一部作品的契约'
        manifest['contract'] = store.document(contract)
    if change in ('source_hash', 'before_state_hash', 'previous_chain'):
        manifest[change] = '0' * 64
    if change == 'event_checks':
        manifest['event_checks'].pop()
    return store.document(manifest)


@pytest.mark.parametrize('packaged', [False, True])
@pytest.mark.parametrize('change', [
    'materials', 'plan', 'materials_and_plan', 'contract', 'source_hash',
    'before_state_hash', 'previous_chain', 'event_checks',
])
def test_wrong_request_binding_cannot_replace_a_valid_approval(packaged, change):
    book, store, draft = installed(packaged=packaged)
    request, approved = approve(book, store, draft)
    forged = _alter_request(book, store, request, change)
    before = copy.deepcopy(book), copy.deepcopy(store.to_dict())

    with pytest.raises(Error):
        pipeline.record_content_review(book, store, forged, report_for(request, draft))

    assert (book, store.to_dict()) == before
    assert store.latest_content_review(1)[0] == approved
    assert pipeline.submit(book, store, 1, draft)['ok']


@pytest.mark.parametrize('packaged', [False, True])
@pytest.mark.parametrize('change', ['materials', 'plan'])
def test_submit_rechecks_bindings_even_for_a_directly_stored_review(packaged, change):
    book, store, draft = installed(packaged=packaged)
    request, approved = approve(book, store, draft)
    row = store.read_document(approved)
    row['request'] = _alter_request(book, store, request, change)
    row['report']['request_ref'] = row['request']
    row['previous'] = approved
    row['sequence'] += 1
    # The low-level public document store is not an approval boundary. Submit
    # must enforce its own invariant even when a caller inserts a complete row.
    draft['review_ref'] = store.put_content_review(row)
    before = copy.deepcopy(book), copy.deepcopy(store.to_dict())

    with pytest.raises(Error) as caught:
        pipeline.submit(book, store, 1, draft)

    assert caught.value.code == 'content_review_stale'
    assert (book, store.to_dict()) == before
    assert book['last_chapter'] == store.last_chapter() == 0
