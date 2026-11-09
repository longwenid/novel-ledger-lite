"""Failure recovery and immutable history through ordinary public APIs."""
import copy
import json

import pytest

import fixtures
from novel_ledger_lite import persistence, pipeline
from novel_ledger_lite.contracts import Error
from novel_ledger_lite.store import LiteStore


def installed():
    book = pipeline.open_book(fixtures.contract(), '作者确认', fixtures.world_fixture())
    volume = fixtures.volume_row(book['contract']['volumes'][0])
    rows = fixtures.chapter_rows(book, with_scenes=True)
    pipeline.install_outlines(book, 'v1', volume, rows)
    return book, LiteStore(), volume, rows


@pytest.mark.parametrize('field', ['synopsis', 'clock', 'scene'])
def test_repair_cannot_change_a_committed_prefix(field):
    book, store, volume, rows = installed()
    assert fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))['ok']
    revised = copy.deepcopy(rows)
    first = revised['chapters'][0]
    if field == 'synopsis':
        first['synopsis'] += '他听完了另一份解释。'
    elif field == 'clock':
        first['clock']['advance_days'] = 0
    else:
        first['scenes'][0]['intent'] = '掩盖凭据的来源。'
    before = copy.deepcopy(book)
    with pytest.raises(Error) as caught:
        pipeline.install_outlines(book, 'v1', volume, revised)
    assert caught.value.code == 'outline_history'
    assert book == before


def test_tail_repair_retains_history_and_frozen_group_but_invalidates_issued_packet(tmp_path):
    book, store, volume, rows = installed()
    group = pipeline.group(book, store, 'v1')
    assert fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))['ok']
    old_packet = pipeline.chapter_package(book, store, 2, group)
    old_plan = copy.deepcopy(book['plans']['1'])
    old_group = copy.deepcopy(group)
    repaired = copy.deepcopy(rows)
    repaired['chapters'][1]['synopsis'] += '沈桐另查了交班日期。'
    changed_volume = copy.deepcopy(volume)
    changed_volume['arc'] += '后续核对加入交班日期。'
    report = pipeline.install_outlines(book, 'v1', changed_volume, repaired)
    assert report['chapters'] == [2, 3, 4]
    assert book['plans']['1'] == old_plan
    assert [row['chapter'] for row in book['chapter_outlines']['v1']] == [1, 2, 3, 4]
    assert book['chapter_outlines']['v1'][0] == old_plan
    assert book['groups'] == [old_group]
    assert store.read_document(group['hash'])['volume_outline'] == volume
    work = pipeline.envelope(book, store, 2, group)
    assert store.read_document(work['records']['chapter_outline']) == book['plans']['2']
    assert store.read_document(work['records']['volume_context'])['arc'] == changed_volume['arc']
    with pytest.raises(Error) as caught:
        pipeline.validate_chapter_package(book, store, old_packet)
    assert caught.value.code == 'chapter_package_stale'
    replacement = pipeline.chapter_package(book, store, 2, group)
    assert pipeline.validate_chapter_package(book, store, replacement)
    path = tmp_path / 'repair.json'
    pipeline.save(book, store, path)
    loaded, saved = pipeline.load(path)
    assert loaded == book
    assert saved.read_document(group['hash'])['volume_outline'] == volume


def test_tail_can_be_supplied_without_any_history():
    book, store, volume, rows = installed()
    assert fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))['ok']
    tail = {**rows, 'chapters': rows['chapters'][1:], 'from_chapter': 2}
    assert pipeline.install_outlines(book, 'v1', volume, tail)['chapters'] == [2, 3, 4]


def test_explicit_repair_anchor_cannot_point_at_history():
    book, store, volume, rows = installed()
    assert fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))['ok']
    with pytest.raises(Error) as caught:
        pipeline.install_outlines(book, 'v1', volume, {**rows, 'from_chapter': 1})
    assert caught.value.code == 'outline_history'


def test_committed_hook_definition_is_frozen_but_unwritten_definitions_can_change():
    book, store, volume, rows = installed()
    assert fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))['ok']
    revised = copy.deepcopy(volume)
    revised['hooks'][0]['text'] = '另一个读者承诺。'
    with pytest.raises(Error) as caught:
        pipeline.install_outlines(book, 'v1', revised, rows)
    assert caught.value.code == 'outline_history'
    revised = copy.deepcopy(volume)
    revised['nodes'].append({'id': 'future-node', 'line': 'main', 'depends_on': [],
                             'text': '尚未发生的新节点。'})
    assert pipeline.install_outlines(book, 'v1', revised, rows)['chapters'] == [2, 3, 4]


@pytest.mark.parametrize('registry', ['plans', 'chapter_outlines'])
def test_audit_and_load_reject_forked_historical_plan(tmp_path, registry):
    book, store, _, _ = installed()
    for n in range(1, 5):
        assert fixtures.submit_reviewed(book, store, n, fixtures.draft_for(book, n))['ok']
    if registry == 'plans':
        book['plans']['1'] = copy.deepcopy(book['plans']['1'])
        book['plans']['1']['synopsis'] += '此处历史被改写。'
    else:
        book['chapter_outlines']['v1'] = copy.deepcopy(book['chapter_outlines']['v1'])
        book['chapter_outlines']['v1'][0]['synopsis'] += '此处历史被改写。'
    report = pipeline.verify_full(book, store)
    assert not report['ok']
    assert any(row['kind'] == 'outline_history' and row['chapter'] == 1 for row in report['problems'])
    path = tmp_path / 'forked.json'
    pipeline.save(book, store, path)
    with pytest.raises(Error) as caught:
        pipeline.load(path)
    assert caught.value.code == 'outline_history'


@pytest.mark.parametrize('entrypoint', ['bundle', 'store'])
@pytest.mark.parametrize('failure', ['write', 'fsync', 'replace'])
def test_failed_atomic_save_retains_loadable_old_file_and_cleans_temp(tmp_path, monkeypatch,
                                                                    entrypoint, failure):
    book, store, _, _ = installed()
    assert fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))['ok']
    path = tmp_path / 'saved.json'
    save = (lambda: pipeline.save(book, store, path)) if entrypoint == 'bundle' else lambda: store.save(path)
    load = (lambda: pipeline.load(path)) if entrypoint == 'bundle' else lambda: LiteStore.load(path)
    save()
    old = path.read_bytes()
    assert fixtures.submit_reviewed(book, store, 2, fixtures.draft_for(book, 2))['ok']
    attempted = []
    if failure == 'write':
        real_fdopen = persistence.os.fdopen

        class FailedWriter:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.handle.close()

            def write(self, payload):
                self.handle.write(payload[:128])
                attempted.append('partial write')
                raise OSError('simulated disk-full write')

        monkeypatch.setattr(persistence.os, 'fdopen',
                            lambda *args, **kwargs: FailedWriter(real_fdopen(*args, **kwargs)))
    else:
        def fail(*args):
            attempted.append(failure)
            raise OSError('simulated ' + failure + ' failure')
        monkeypatch.setattr(persistence.os, failure, fail)
    with pytest.raises(OSError):
        save()
    assert attempted
    assert path.read_bytes() == old
    restored = load()
    restored_store = restored[1] if entrypoint == 'bundle' else restored
    assert restored_store.last_chapter() == 1
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('entrypoint', ['bundle', 'store'])
def test_atomic_save_replaces_complete_snapshot_and_flushes_before_replace(tmp_path, monkeypatch, entrypoint):
    book, store, _, _ = installed()
    path = tmp_path / 'saved.json'
    operations = []
    real_fsync, real_replace = persistence.os.fsync, persistence.os.replace

    def sync(descriptor):
        operations.append('fsync')
        real_fsync(descriptor)

    def replace(source, target):
        assert operations == ['fsync']
        assert source.startswith(str(tmp_path))
        assert json.loads(open(source, encoding='utf-8').read())
        operations.append('replace')
        real_replace(source, target)

    monkeypatch.setattr(persistence.os, 'fsync', sync)
    monkeypatch.setattr(persistence.os, 'replace', replace)
    if entrypoint == 'bundle':
        pipeline.save(book, store, path)
        assert pipeline.load(path)[0] == book
    else:
        store.save(path)
        assert LiteStore.load(path).to_dict() == store.to_dict()
    assert operations == ['fsync', 'replace']
    assert list(tmp_path.iterdir()) == [path]
