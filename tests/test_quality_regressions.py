"""质检回归：内容完整性、完本验收、换档历史、安装原子性与按章恢复。"""
import copy
from pathlib import Path

import pytest

import fixtures
from novel_ledger_lite import delta, facts, pipeline, style
from novel_ledger_lite.contracts import Error, digest
from novel_ledger_lite.store import LiteStore


ARCHIVE = str(Path(__file__).parent / 'fixtures' / 'style_archive_sample.md')


def completed_book():
    book, _, _ = fixtures.open_installed_book()
    store = LiteStore()
    assert all(r['ok'] for r in fixtures.submit_chapters(book, store))
    return book, store


@pytest.mark.parametrize('field', ['prose', 'plan', 'events', 'contract_hash'])
@pytest.mark.parametrize('missing', [False, True])
def test_audit_rejects_corrupt_or_missing_source_documents(field, missing):
    book, store = completed_book()
    key = store.chapter('main', 1)[field]
    if missing:
        del store._documents[key]
    else:
        store._documents[key] = '被替换的内容'
    report = pipeline.verify_full(book, store)
    assert not report['ok']
    assert any(p['kind'] == 'record' and p['chapter'] == 1 for p in report['problems'])


def test_frozen_documents_do_not_share_mutable_references():
    store = LiteStore()
    value = {'rows': [{'text': '原文'}]}
    original = copy.deepcopy(value)
    key = store.document(value)
    value['rows'][0]['text'] = '输入被修改'
    read = store.read_document(key)
    read['rows'].append({'text': '读取结果被修改'})
    assert store.read_document(key) == original
    assert digest(store.read_document(key)) == key


@pytest.mark.parametrize('through', [0, 1, 3])
def test_audit_requires_all_contracted_chapters(through):
    book, _, _ = fixtures.open_installed_book()
    store = LiteStore()
    for n in range(1, through + 1):
        assert fixtures.submit_reviewed(book, store, n, fixtures.draft_for(book, n))['ok']
    report = pipeline.verify_full(book, store)
    assert not report['ok']
    assert any(p['kind'] == 'incomplete' for p in report['problems'])


def test_audit_rejects_live_state_mismatch():
    book, store = completed_book()
    book['state']['clock'] += 1
    report = pipeline.verify_full(book, store)
    assert not report['ok'] and not report['matches_book']
    assert any(p['kind'] == 'book_state' for p in report['problems'])


def test_style_changes_preserve_historical_chains_across_save_load(tmp_path):
    book, _, _ = fixtures.open_installed_book()
    store = LiteStore()
    assert fixtures.submit_reviewed(book, store, 1, fixtures.draft_for(book, 1))['ok']
    first_chain = store.chain_head()
    pipeline.recontract_patch(book, source='作者：换账房掌门', style_profile='账房掌门')
    assert book['style_switch']['at'] == 2
    assert fixtures.submit_reviewed(book, store, 2, fixtures.draft_for(book, 2))['ok']
    pipeline.recontract_patch(book, source='作者：换外部档案', style_source=ARCHIVE)
    assert book['style_switch']['at'] == 3
    for n in (3, 4):
        assert fixtures.submit_reviewed(book, store, n, fixtures.draft_for(book, n))['ok']
    # 写完后再次换档也不能使已提交历史失效。
    pipeline.recontract_patch(book, source='作者：改回内置档', style_profile='市井修仙')
    path = tmp_path / 'book.json'
    pipeline.save(book, store, path)
    loaded, saved = pipeline.load(path)
    assert pipeline.verify_full(loaded, saved)['ok']
    assert saved.chapter('main', 1)['chain'] == first_chain
    assert [r['source'] for r in loaded['contract_changes']] == [
        '作者：换账房掌门', '作者：换外部档案', '作者：改回内置档']
    assert saved.chapter('main', 1)['contract_hash'] != saved.chapter('main', 2)['contract_hash']



def test_external_style_can_switch_back_to_builtin():
    book, _, _ = fixtures.open_installed_book()
    store = LiteStore()
    pipeline.recontract_patch(book, source='作者：外部档案', style_source=ARCHIVE)
    pipeline.recontract_patch(book, source='作者：账房掌门', style_profile='账房掌门')
    envelope = pipeline.envelope(book, store, 1)
    spec = store.read_document(envelope['records']['style'])
    assert spec['source_kind'] == 'builtin_catalog'
    assert spec['profile'] == '账房掌门'
    assert not spec['style_source']
    assert 'style_archive' not in envelope['records']


def test_invalid_style_change_leaves_book_unchanged():
    book, _, _ = fixtures.open_installed_book()
    before = copy.deepcopy(book)
    with pytest.raises(Error):
        pipeline.recontract_patch(book, source='作者换档', style_profile='账房掌门',
                                  style_source='不存在的文风档案.md')
    assert book == before


@pytest.mark.parametrize('bad_id', ['missing', 'drift-1'])
def test_failed_absorption_leaves_entire_book_unchanged(bad_id):
    book, _, _ = fixtures.open_installed_book()
    book['design_drift'] = [{'id': 'drift-1', 'chapter': 0, 'kind': 'resources',
                             'key': 'x', 'reason': '变更', 'participants': ['shen']}]
    data = fixtures.chapter_rows(book)
    data['chapters'][1]['absorbs'] = ['drift-1', bad_id]
    before = copy.deepcopy(book)
    volume = book['contract']['volumes'][0]
    with pytest.raises(Error):
        pipeline.install_outlines(book, 'v1', fixtures.volume_row(volume), data)
    assert book == before
    data['chapters'][1]['absorbs'] = ['drift-1']
    assert pipeline.install_outlines(book, 'v1', fixtures.volume_row(volume), data)['absorbed'] == ['drift-1']


def test_final_outline_invariant_failure_is_atomic():
    book, _, _ = fixtures.open_installed_book()
    volume = book['contract']['volumes'][0]
    outline = fixtures.volume_row(volume)
    outline['id'] = 'wrong-volume'
    before = copy.deepcopy(book)
    with pytest.raises(Error):
        pipeline.install_outlines(book, 'v1', outline, fixtures.chapter_rows(book))
    assert book == before


def test_submit_and_envelope_use_same_nearest_five_chapters(monkeypatch):
    monkeypatch.setattr(fixtures, 'CHAPTERS', 10)
    book, _, _ = fixtures.open_installed_book(chapters=10)
    store = LiteStore()
    for n in range(1, 9):
        assert fixtures.submit_reviewed(book, store, n, fixtures.draft_for(book, n))['ok']
    envelope = pipeline.envelope(book, store, 9)
    expected = store.read_document(envelope['records']['style'])['anchor']
    observed = []
    examine = style.examine

    def capture(prose, declared, anchor, *args, **kwargs):
        observed.append(anchor)
        return examine(prose, declared, anchor, *args, **kwargs)

    monkeypatch.setattr(style, 'examine', capture)
    assert fixtures.submit_reviewed(book, store, 9, fixtures.draft_for(book, 9))['ok']
    assert observed == [expected]
    assert observed[0]['basis'] == [4, 5, 6, 7, 8]


@pytest.mark.parametrize('with_checkpoints', [False, True])
@pytest.mark.parametrize('through', [0, 1, 2, 3, 4, 10, None])
def test_rebuild_respects_requested_chapter(through, with_checkpoints):
    book, _, _ = fixtures.open_installed_book()
    store = LiteStore()
    states = {0: copy.deepcopy(book['state'])}
    for n in range(1, 5):
        assert fixtures.submit_reviewed(book, store, n, fixtures.draft_for(book, n))['ok']
        states[n] = copy.deepcopy(book['state'])
        if with_checkpoints and n in (1, 2):
            pipeline._checkpoint(book, n, None)
    if not with_checkpoints:
        book['checkpoints'] = []
    target = 4 if through is None else min(through, 4)
    rebuilt, last = delta.rebuild(book, store, through=through)
    assert rebuilt == states[target]
    assert last == target
    assert book['state'] == states[4]


def test_rebuild_before_first_checkpoint_uses_seed():
    book, store = completed_book()  # 只有第 4 章 checkpoint
    rebuilt, last = delta.rebuild(book, store, through=2)
    expected = facts.seed(book['initial_contract'])
    for n in (1, 2):
        for event in store.events_page(n):
            facts.apply_event(expected, event, n)
    assert rebuilt == expected and last == 2
