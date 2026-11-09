"""A writer receives one complete chapter file; the host retains the ledger."""
import copy
from pathlib import Path

import pytest

import fixtures
from novel_ledger_lite import pipeline
from novel_ledger_lite.contracts import Error
from novel_ledger_lite.store import LiteStore


ARCHIVE = str(Path(__file__).parent / 'fixtures' / 'style_archive_sample.md')


def installed(**overrides):
    contract = fixtures.contract()
    contract.update(overrides)
    book = pipeline.open_book(contract, '作者确认测试输入', fixtures.world_fixture())
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(book['contract']['volumes'][0]),
                              fixtures.chapter_rows(book, with_scenes=True))
    return book, LiteStore()


def test_single_file_includes_current_chapter_and_frozen_style_and_survives_disk_roundtrip(tmp_path):
    book, store = installed(style_source=ARCHIVE)
    package = pipeline.chapter_package(book, store, 1)
    path = tmp_path / '第001章写作包.md'
    path.write_text(package['text'], encoding='utf-8')
    delivered = path.read_text(encoding='utf-8')
    assert package['chapter'] == 1
    assert delivered.startswith('#')
    assert book['plans']['1']['synopsis'] in delivered
    assert book['contract']['world_rules'][0] in delivered
    assert book['style_archive']['content'] in delivered
    assert pipeline.validate_chapter_package(book, store, delivered) is True
    with pytest.raises(Error):
        pipeline.validate_chapter_package(book, store, delivered + '额外内容')


def test_package_requires_next_chapter_and_matching_book_store_progress():
    book, store = installed()
    with pytest.raises(Error):
        pipeline.chapter_package(book, store, 2)
    inconsistent = copy.deepcopy(book)
    inconsistent['last_chapter'] = 1
    with pytest.raises(Error):
        pipeline.chapter_package(inconsistent, store, 1)


def test_missing_dependency_blocks_file_preparation_without_mutating_book():
    book, store = installed()
    coord = {'kind': 'facts', 'key': 'shen:missing-rule'}
    book['plans']['1']['scenes'][0]['reads'].append(coord)
    before = copy.deepcopy(book)
    with pytest.raises(Error) as caught:
        pipeline.chapter_package(book, store, 1)
    assert caught.value.code == 'context_dependencies'
    assert coord in caught.value.details['missing']
    assert book == before


def test_old_package_expires_after_submission_and_next_contains_actual_previous_chapter():
    book, store = installed()
    first = pipeline.chapter_package(book, store, 1)
    draft = fixtures.draft_for(book, 1)
    draft['package_ref'] = first['package_ref']
    assert fixtures.submit_reviewed(book, store, 1, draft)['ok']
    with pytest.raises(Error):
        pipeline.validate_chapter_package(book, store, first)
    second = pipeline.chapter_package(book, store, 2)
    assert draft['prose'] in second['text']
    assert book['plans']['2']['synopsis'] in second['text']
    assert pipeline.validate_chapter_package(book, store, second) is True
    with pytest.raises(Error):
        pipeline.chapter_package(book, store, 1)


def test_changing_frozen_context_invalidates_existing_package():
    book, store = installed()
    package = pipeline.chapter_package(book, store, 1)
    pipeline.recontract_patch(book, source='作者确认更换文风', style_profile='账房掌门')
    with pytest.raises(Error):
        pipeline.validate_chapter_package(book, store, package)


def test_catalog_pages_expand_to_full_values_not_only_previews():
    book, store = installed()
    # Closed hooks are chapter-related but excluded from the regular state projection.
    # More than 100 exercises pagination; the unique suffix is beyond the 80-char preview.
    for n in range(105):
        book['state']['hooks'][f'old-{n:02d}'] = {
            'subjects': ['shen'], 'status': 'resolved',
            'text': '旧线索' * 40 + f'完整尾句{n:02d}',
        }
    package = pipeline.chapter_package(book, store, 1)
    for n in range(105):
        assert f'完整尾句{n:02d}' in package['text']


def test_missing_explicit_extra_resource_cannot_be_silently_omitted():
    book, store = installed()
    with pytest.raises(Error):
        pipeline.chapter_package(book, store, 1,
                                 extra_resources=[{'kind': 'facts', 'key': 'shen:no-such-fact'}])


def test_host_can_request_an_additional_resource_and_regenerate():
    book, store = installed()
    book['state']['facts']['elsewhere:secret'] = '远方来信实际内容。'
    first = pipeline.chapter_package(book, store, 1)
    assert '远方来信实际内容。' not in first['text']
    revised = pipeline.chapter_package(
        book, store, 1, extra_resources=[{'kind': 'facts', 'key': 'elsewhere:secret'}])
    assert '远方来信实际内容。' in revised['text']
    assert pipeline.validate_chapter_package(book, store, revised) is True


def test_saved_book_and_file_validate_after_loading_in_fresh_session(tmp_path):
    book, store = installed()
    assert fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))['ok']
    package = pipeline.chapter_package(book, store, 2)
    assert package['metrics']['bytes'] == len(package['text'].encode('utf-8'))
    bundle_path = tmp_path / 'book.json'
    package_path = tmp_path / '第002章写作包.md'
    pipeline.save(book, store, bundle_path)
    package_path.write_text(package['text'], encoding='utf-8')
    restored_book, restored_store = pipeline.load(bundle_path)
    restored_text = package_path.read_text(encoding='utf-8')
    assert pipeline.validate_chapter_package(restored_book, restored_store, restored_text) is True
