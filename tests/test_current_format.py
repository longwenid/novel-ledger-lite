"""Current formats are mandatory: reject old data instead of repairing or upgrading it."""
import copy
import json

import pytest

import fixtures
from novel_ledger_lite import compose, delta, pipeline
from novel_ledger_lite.contracts import BUNDLE_SCHEMA, SCHEMA, STORE_SCHEMA, TASK, Error
from novel_ledger_lite.envelope import validate_work
from novel_ledger_lite.store import LiteStore


def bundle(tmp_path):
    book, _, _ = fixtures.open_installed_book(with_scenes=True)
    store = LiteStore()
    group = pipeline.group(book, store, 'v1')
    assert pipeline.submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    path = tmp_path / 'book.json'
    pipeline.save(book, store, path)
    return book, store, group, path, json.loads(path.read_text(encoding='utf-8'))


def reject_load(path, raw, code):
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    before = path.read_bytes()
    with pytest.raises(Error) as caught:
        pipeline.load(path)
    assert caught.value.code == code
    assert path.read_bytes() == before


def test_current_bundle_roundtrips_without_rewriting_progress_or_groups(tmp_path):
    book, store, group, path, raw = bundle(tmp_path)
    assert raw['schema'] == BUNDLE_SCHEMA
    assert raw['book']['schema'] == SCHEMA
    assert raw['store']['schema'] == STORE_SCHEMA
    loaded, saved = pipeline.load(path)
    assert loaded == book
    assert saved.to_dict() == store.to_dict()
    assert saved.read_document(group['hash'])


@pytest.mark.parametrize('version', [None, 'novel-ledger-lite.bundle/1', 'unrelated/2'])
def test_old_or_unmarked_bundle_is_rejected(tmp_path, version):
    _, _, _, path, raw = bundle(tmp_path)
    if version is None:
        del raw['schema']
    else:
        raw['schema'] = version
    reject_load(path, raw, 'bundle_schema')


@pytest.mark.parametrize('version', [None, 'novel-ledger-lite/1', 'unrelated/2'])
def test_old_or_unmarked_book_is_rejected(tmp_path, version):
    _, _, _, path, raw = bundle(tmp_path)
    if version is None:
        del raw['book']['schema']
    else:
        raw['book']['schema'] = version
    reject_load(path, raw, 'book_schema')


@pytest.mark.parametrize('field', ['initial_contract', 'contract_changes', 'last_chapter', 'style_archive'])
def test_missing_current_book_fields_are_not_inferred(tmp_path, field):
    _, _, _, path, raw = bundle(tmp_path)
    del raw['book'][field]
    reject_load(path, raw, 'book_schema')


@pytest.mark.parametrize('version', [None, 'novel-ledger-lite.store/1', 'unrelated/2'])
def test_old_or_unmarked_store_is_rejected(tmp_path, version):
    _, _, _, path, raw = bundle(tmp_path)
    if version is None:
        del raw['store']['schema']
    else:
        raw['store']['schema'] = version
    reject_load(path, raw, 'store_schema')


def test_missing_contract_version_is_never_replaced_with_initial_contract(tmp_path):
    book, store, _, path, raw = bundle(tmp_path)
    del raw['store']['chapters']['1']['contract_hash']
    reject_load(path, raw, 'store_schema')
    store._chapters[1].pop('contract_hash')
    report = pipeline.verify_full(book, store)
    assert not report['ok']
    assert any(problem['kind'] == 'format' for problem in report['problems'])


def test_missing_shared_document_is_not_recreated_from_embedded_group(tmp_path):
    _, _, group, path, raw = bundle(tmp_path)
    del raw['store']['documents'][group['hash']]
    reject_load(path, raw, 'record')


@pytest.mark.parametrize('field', ['volume', 'pack'])
def test_partial_group_structures_are_not_upgraded(tmp_path, field):
    _, _, _, path, raw = bundle(tmp_path)
    del raw['book']['groups'][0][field]
    reject_load(path, raw, 'book_state')


def test_inconsistent_progress_is_not_automatically_fixed(tmp_path):
    _, _, _, path, raw = bundle(tmp_path)
    raw['book']['last_chapter'] = 0
    reject_load(path, raw, 'book_state')


def test_missing_frozen_archive_never_reads_external_file(tmp_path, monkeypatch):
    _, _, _, path, raw = bundle(tmp_path)
    raw['book']['contract']['style_source'] = str(tmp_path / 'old-archive.md')
    raw['book']['style_archive'] = None

    def forbidden_read(*args, **kwargs):
        raise AssertionError('load must not reconstruct an archive from disk')

    monkeypatch.setattr(compose, '_style_archive', forbidden_read)
    reject_load(path, raw, 'book_schema')


@pytest.mark.parametrize('field', ['style_anchor', 'designs'])
def test_retired_book_extensions_are_rejected(tmp_path, field):
    _, _, _, path, raw = bundle(tmp_path)
    raw['book'][field] = {}
    reject_load(path, raw, 'book_schema')


@pytest.mark.parametrize('operation', ['dispatch', 'patch', 'recover', 'catalog', 'resource', 'save'])
def test_in_memory_old_books_cannot_bypass_the_loader(tmp_path, operation):
    book, store, _, _, _ = bundle(tmp_path)
    book['schema'] = 'novel-ledger-lite/1'
    operations = {
        'dispatch': lambda: pipeline.envelope(book, store, 2),
        'patch': lambda: pipeline.recontract_patch(book, source='作者换档', style_profile='账房掌门'),
        'recover': lambda: delta.rebuild(book, store),
        'catalog': lambda: pipeline.catalog(book),
        'resource': lambda: pipeline.resource(book, 'clock', 'main'),
        'save': lambda: pipeline.save(book, store, tmp_path / 'should-not-exist.json'),
    }
    with pytest.raises(Error) as caught:
        operations[operation]()
    assert caught.value.code == 'book_schema'


@pytest.mark.parametrize('version', [None, 'novel-ledger-lite.task/1', 'unrelated/2', 2])
def test_task_requires_exact_current_schema(version):
    book, _, _ = fixtures.open_installed_book()
    work = pipeline.envelope(book, LiteStore(), 1)
    work['schema'] = version
    with pytest.raises(Error) as caught:
        validate_work(work)
    assert caught.value.code == 'envelope_schema'


@pytest.mark.parametrize('change', ['embedded_outline', 'missing_delivery', 'retired_payload', 'missing_batch_flag'])
def test_current_task_does_not_accept_older_field_shapes(change):
    book, _, _ = fixtures.open_installed_book()
    store = LiteStore()
    work = copy.deepcopy(pipeline.envelope(book, store, 1))
    assert work['schema'] == TASK
    if change == 'embedded_outline':
        work['payload']['chapter_outline'] = book['plans']['1']
    elif change == 'missing_delivery':
        del work['delivery']
    elif change == 'retired_payload':
        work['payload']['mode'] = 'redesign'
    else:
        del work['payload']['worker_batch']
    with pytest.raises(Error) as caught:
        pipeline.materialize(work, store)
    assert caught.value.code == 'envelope_input'
