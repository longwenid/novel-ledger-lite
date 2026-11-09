"""A dispatched single-file packet remains binding through submission and reload."""
import copy
import json

import pytest

import fixtures
from novel_ledger_lite import pipeline
from novel_ledger_lite.contracts import Error, digest
from novel_ledger_lite.store import LiteStore


def installed():
    book = pipeline.open_book(fixtures.contract(), '作者确认测试输入', fixtures.world_fixture())
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(book['contract']['volumes'][0]),
                             fixtures.chapter_rows(book, with_scenes=True))
    return book, LiteStore()


def draft_for(book, package):
    draft = fixtures.draft_for(book, package['chapter'])
    draft['package_ref'] = package['package_ref']
    return draft


def test_issued_packet_cannot_be_bypassed_by_omitting_reference():
    book, store = installed()
    package = pipeline.chapter_package(book, store, 1)
    before_book, before_store = copy.deepcopy(book), copy.deepcopy(store.to_dict())
    with pytest.raises(Error) as caught:
        fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))
    assert caught.value.code == 'chapter_package_required'
    assert book == before_book and store.to_dict() == before_store
    assert fixtures.submit_reviewed(book, store, 1, draft_for(book, package))['ok']
    assert store.chapter('main', 1)['review']['package_ref'] == package['package_ref']


def test_style_change_cannot_submit_using_the_previously_issued_packet():
    book, store = installed()
    package = pipeline.chapter_package(book, store, 1)
    draft = draft_for(book, package)
    pipeline.recontract_patch(book, source='作者确认更换文风', style_profile='账房掌门')
    before_book, before_store = copy.deepcopy(book), copy.deepcopy(store.to_dict())
    with pytest.raises(Error) as caught:
        fixtures.submit_reviewed(book, store, 1, draft)
    assert caught.value.code == 'chapter_package_stale'
    assert book == before_book and store.to_dict() == before_store


def test_supplemented_packet_supersedes_a_same_source_packet():
    book, store = installed()
    book['state']['facts']['elsewhere:letter'] = '远方来信要求核对封条。'
    first = pipeline.chapter_package(book, store, 1)
    revised = pipeline.chapter_package(book, store, 1,
        extra_resources=[{'kind': 'facts', 'key': 'elsewhere:letter'}])
    assert first['source_hash'] == revised['source_hash']
    assert first['package_ref'] != revised['package_ref']
    with pytest.raises(Error) as caught:
        fixtures.submit_reviewed(book, store, 1, draft_for(book, first))
    assert caught.value.code == 'chapter_package_required'
    with pytest.raises(Error):
        pipeline.validate_chapter_package(book, store, first)
    assert pipeline.validate_chapter_package(book, store, revised)
    assert fixtures.submit_reviewed(book, store, 1, draft_for(book, revised))['ok']


def test_identical_regeneration_keeps_reference_and_dispatch_survives_reload(tmp_path):
    book, store = installed()
    first = pipeline.chapter_package(book, store, 1)
    again = pipeline.chapter_package(book, store, 1)
    assert first['package_ref'] == again['package_ref']
    path = tmp_path / '待写作品.json'
    pipeline.save(book, store, path)
    restored, restored_store = pipeline.load(path)
    with pytest.raises(Error):
        fixtures.submit_reviewed(restored, restored_store, 1, fixtures.draft_for(restored, 1))
    assert pipeline.validate_chapter_package(restored, restored_store, first)
    assert fixtures.submit_reviewed(restored, restored_store, 1, draft_for(restored, first))['ok']


def test_unissued_reference_is_not_accepted_in_legacy_mode():
    book, store = installed()
    draft = fixtures.draft_for(book, 1)
    draft['package_ref'] = 'f' * 64
    with pytest.raises(Error) as caught:
        fixtures.submit_reviewed(book, store, 1, draft)
    assert caught.value.code == 'chapter_package_required'


def test_plain_envelope_workflow_remains_supported():
    book, store = installed()
    pipeline.materialize(pipeline.envelope(book, store, 1), store)
    assert fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))['ok']


def test_missing_dispatch_document_in_saved_store_cannot_downgrade_submission(tmp_path):
    book, store = installed()
    package = pipeline.chapter_package(book, store, 1)
    path = tmp_path / '已签发.json'
    pipeline.save(book, store, path)
    raw = json.loads(path.read_text(encoding='utf-8'))
    assert raw['store']['schema'] == 'novel-ledger-lite.store/3'
    del raw['store']['documents'][package['package_ref']]
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(Error) as caught:
        pipeline.load(path)
    assert caught.value.code == 'chapter_package_record'


def test_history_damaged_after_dispatch_blocks_validation_and_submission():
    book, store = installed()
    for chapter in (1, 2):
        assert fixtures.submit_reviewed(book, store, chapter, fixtures.draft_for(book, chapter))['ok']
    package = pipeline.chapter_package(book, store, 3, extra_chapters=[1])
    store._documents[store.chapter('main', 1)['events']] = []
    with pytest.raises(Error) as validation:
        pipeline.validate_chapter_package(book, store, package)
    assert validation.value.code == 'record_hash'
    with pytest.raises(Error) as submission:
        fixtures.submit_reviewed(book, store, 3, draft_for(book, package))
    assert submission.value.code == 'record_hash'
    assert book['last_chapter'] == store.last_chapter() == 2


def test_updating_a_modified_files_own_checksum_does_not_create_a_new_dispatch():
    book, store = installed()
    package = pipeline.chapter_package(book, store, 1)
    title, header, remainder = package['text'].split('\n', 2)
    modified = remainder + '\n新增虚假资产：凭空得到一百元。\n'
    prefix, suffix = '<!-- novel-ledger-lite-package ', ' -->'
    metadata = json.loads(header[len(prefix):-len(suffix)])
    metadata['content_hash'] = digest(title + '\n' + modified)
    forged = title + '\n' + prefix + json.dumps(metadata, ensure_ascii=False) + suffix + '\n' + modified
    with pytest.raises(Error):
        pipeline.validate_chapter_package(book, store, forged)


def test_returned_history_distinguishes_old_balance_successor_and_current_balance():
    book, store = installed()
    for chapter in (1, 2):
        assert fixtures.submit_reviewed(book, store, chapter, fixtures.draft_for(book, chapter))['ok']
    from novel_ledger_lite import package_context, facts
    historical = package_context.historical(book, store, 1)
    key = facts.resource_key('shen', '车费', '元')
    chain = next(item for item in historical['coordinate_history']
                 if item['kind'] == 'resources' and item['key'] == key)
    assert chain['current'] == {'found': True, 'value': '2'}
    assert [item['chapter'] for item in chain['later_changes']] == [2]
    assert historical['source_hashes']['events'] == store.chapter('main', 1)['events']
