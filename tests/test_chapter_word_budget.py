"""Chapter exceptions preserve frozen history, review bindings and global defaults."""
import copy

import pytest

import fixtures
from novel_ledger_lite import narrative, pipeline
from novel_ledger_lite.contracts import Error, han_count
from novel_ledger_lite.store import LiteStore
from test_content_review import report_for


def installed(*, tracking=False, budget=None):
    raw = fixtures.contract()
    raw.update(narrative_tracking=tracking, chapter_min=80, chapter_aim=90, chapter_max=100)
    book = pipeline.open_book(raw, '作者确认各章默认篇幅与一个短章。', fixtures.world_fixture())
    volume = fixtures.volume_row(book['contract']['volumes'][0])
    rows = fixtures.chapter_rows(book, with_scenes=True)
    if budget is not None:
        rows['chapters'][1]['word_budget'] = copy.deepcopy(budget)
    pipeline.install_outlines(book, 'v1', volume, rows)
    return book, LiteStore(), volume, rows


def review_and_submit(book, store, chapter, draft):
    """Synthetic distinct-reader protocol receipt, not a literary approval."""
    request = pipeline.review_request(book, store, chapter, draft, writer='budget-test-writer')
    draft['review_ref'] = pipeline.record_content_review(
        book, store, request['request_ref'], report_for(request, draft))
    return pipeline.submit(book, store, chapter, draft)


def test_absent_budget_keeps_old_outline_shape_and_budget_calculation():
    book, store, _, _ = installed(tracking=True)
    assert all('word_budget' not in row for row in book['plans'].values())
    assert narrative.budget_for(book, 1) == narrative.word_budget(book['contract'], 0, 1)
    draft = fixtures.draft_for(book, 1)
    assert review_and_submit(book, store, 1, draft)['ok']
    report = pipeline.verify_full(book, store)
    assert report['matches_book']
    assert [p['kind'] for p in report['problems']] == ['incomplete']


@pytest.mark.parametrize('tracking', [False, True])
def test_only_declared_short_chapter_changes_budget_and_survives_review_replay(tmp_path, tracking):
    exception = {'min': 50, 'aim': 60, 'max': 65}
    book, store, _, _ = installed(tracking=tracking, budget=exception)
    original_contract = copy.deepcopy(book['contract'])
    for chapter in range(1, 5):
        draft = fixtures.draft_for(book, chapter)
        if chapter == 3:
            draft['prose'] += '他在灯下按住旧表，等主管把经手日期说完。'
        band = narrative.budget_for(book, chapter)
        assert band['minimum'] == (50 if chapter == 2 else 80)
        packet = pipeline.chapter_package(book, store, chapter)
        assert pipeline.validate_chapter_package(book, store, packet)
        if chapter == 2:
            assert han_count(draft['prose']) < original_contract['chapter_min']
            work = pipeline.envelope(book, store, chapter)
            delivered = store.read_document(work['records']['word_budget'])
            assert [delivered[k] for k in ('minimum', 'aim', 'maximum')] == [50, 60, 65]
            assert book['plans']['2']['word_budget'] == exception
        draft['package_ref'] = packet['package_ref']
        assert review_and_submit(book, store, chapter, draft)['ok']
    # The short chapter's allowance is not silently recovered by padding a later chapter.
    assert book['written_han'] < 4 * original_contract['chapter_min']
    assert book['contract'] == original_contract
    assert all('word_budget' not in book['plans'][str(n)] for n in (1, 3, 4))
    assert pipeline.verify_full(book, store)['ok']
    path = tmp_path / 'short-chapter.json'
    pipeline.save(book, store, path)
    restored, saved = pipeline.load(path)
    assert pipeline.verify_full(restored, saved)['ok']
    assert restored == book and saved.to_dict() == store.to_dict()


@pytest.mark.parametrize('invalid', [None, {}, [], {'min': 1, 'aim': 2},
    {'min': True, 'aim': 2, 'max': 3}, {'min': 0, 'aim': 2, 'max': 3},
    {'min': -1, 'aim': 2, 'max': 3}, {'min': 1.0, 'aim': 2, 'max': 3},
    {'min': 1, 'aim': '2', 'max': 3}, {'min': 3, 'aim': 2, 'max': 4},
    {'min': 1, 'aim': 4, 'max': 3}, {'min': 1, 'aim': 2, 'max': 10001},
    {'min': 1, 'aim': 2, 'max': 3, 'extra': 4}])
def test_invalid_budget_is_rejected_atomically(invalid):
    book, _, volume, rows = installed()
    rows['chapters'][1]['word_budget'] = invalid
    before = copy.deepcopy(book)
    with pytest.raises(Error) as caught:
        pipeline.install_outlines(book, 'v1', volume, rows)
    assert caught.value.code == 'word_budget'
    assert book == before


@pytest.mark.parametrize('exception', [
    {'min': 50, 'aim': 55, 'max': 60}, {'min': 64, 'aim': 66, 'max': 70}])
def test_short_chapter_still_has_to_meet_its_own_limits(exception):
    book, store, _, _ = installed(budget=exception)
    assert review_and_submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    result = review_and_submit(book, store, 2, fixtures.draft_for(book, 2))
    assert not result['ok']
    assert any(f['criterion'] == 'substance'
               and f['allowed'] == [exception['min'], exception['max']]
               for f in result['findings'])
    assert book['last_chapter'] == store.last_chapter() == 1


@pytest.mark.parametrize('change', ['add', 'edit', 'remove'])
def test_committed_chapter_budget_cannot_be_added_edited_or_removed(change):
    book, store, volume, rows = installed()
    if change != 'add':
        rows['chapters'][0]['word_budget'] = {'min': 80, 'aim': 90, 'max': 100}
        pipeline.install_outlines(book, 'v1', volume, rows)
    assert review_and_submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    if change == 'remove':
        del rows['chapters'][0]['word_budget']
    else:
        rows['chapters'][0]['word_budget'] = {'min': 70, 'aim': 80, 'max': 100}
    before = copy.deepcopy(book)
    with pytest.raises(Error) as caught:
        pipeline.install_outlines(book, 'v1', volume, rows)
    assert caught.value.code == 'outline_history'
    assert book == before


def test_tail_budget_change_expires_packet_request_and_approval():
    book, store, volume, rows = installed()
    assert review_and_submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    original_row = copy.deepcopy(store.chapter('main', 1))
    old_packet = pipeline.chapter_package(book, store, 2)
    draft = fixtures.draft_for(book, 2)
    draft['package_ref'] = old_packet['package_ref']
    request = pipeline.review_request(book, store, 2, draft, writer='budget-test-writer')
    old_report = report_for(request, draft)
    draft['review_ref'] = pipeline.record_content_review(book, store, request['request_ref'], old_report)
    rows['chapters'][1]['word_budget'] = {'min': 50, 'aim': 60, 'max': 65}
    pipeline.install_outlines(book, 'v1', volume, rows)
    with pytest.raises(Error) as stale_packet:
        pipeline.validate_chapter_package(book, store, old_packet)
    assert stale_packet.value.code == 'chapter_package_stale'
    with pytest.raises(Error) as stale_request:
        pipeline.record_content_review(book, store, request['request_ref'], old_report)
    assert stale_request.value.code == 'content_review_stale'
    fresh_packet = pipeline.chapter_package(book, store, 2)
    draft['package_ref'] = fresh_packet['package_ref']
    with pytest.raises(Error) as stale_approval:
        pipeline.submit(book, store, 2, draft)
    assert stale_approval.value.code == 'content_review_stale'
    assert review_and_submit(book, store, 2, draft)['ok']
    assert store.chapter('main', 1) == original_row


def test_replay_detects_inaccurate_recorded_han_with_the_shared_budget_resolver():
    book, store, _, _ = installed()
    assert review_and_submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    store.chapter('main', 1)['han'] += 1
    report = pipeline.verify_full(book, store)
    assert any(p['kind'] == 'word_budget' and p['chapter'] == 1 for p in report['problems'])
