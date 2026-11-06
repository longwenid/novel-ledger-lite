"""The selected built-in style must have a real bundled, frozen and delivered profile."""
import json
from pathlib import Path

import pytest

import fixtures
from novel_ledger_lite import compose, pipeline
from novel_ledger_lite.contracts import STYLE_CATALOG, Error
from novel_ledger_lite.store import LiteStore


@pytest.mark.parametrize('profile', list(STYLE_CATALOG))
def test_each_builtin_style_has_a_distinct_file_and_delivers_its_execution_guide(profile):
    root = Path(__file__).resolve().parents[1]
    paths = [root / entry['file'] for entry in STYLE_CATALOG.values()]
    assert len(set(paths)) == 5
    path = root / STYLE_CATALOG[profile]['file']
    assert path.is_file() and path.resolve().is_relative_to(root)
    raw = fixtures.contract()
    raw['style_profile'] = profile
    book = pipeline.open_book(raw, '作者选择文风', fixtures.world_fixture())
    assert book['style_archive']['content'] == path.read_text(encoding='utf-8')
    assert book['style_archive']['profile'] == profile
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(book['contract']['volumes'][0]),
                              fixtures.chapter_rows(book, with_scenes=True))
    store = LiteStore()
    work = pipeline.envelope(book, store, 1)
    delivered = json.loads(pipeline.materialize(work, store)['text'])['materials']
    guide = delivered['style_guide']
    assert guide['profile'] == profile
    assert len(guide['content']) < len(book['style_archive']['content']) // 3
    assert 'style_reference' not in delivered
    assert store.read_document(guide['full_archive_ref']) == book['style_archive']
    assert guide['content'] in book['style_archive']['content']


def test_missing_builtin_file_blocks_open_instead_of_using_only_numeric_anchors(tmp_path, monkeypatch):
    monkeypatch.setattr(compose, 'STYLE_ROOT', tmp_path)
    with pytest.raises(Error) as caught:
        pipeline.open_book(fixtures.contract(), '作者选择文风')
    assert caught.value.code == 'style_profile'


def test_builtin_profile_is_frozen_and_changes_only_on_explicit_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(compose, 'STYLE_ROOT', tmp_path)
    path = tmp_path / STYLE_CATALOG['市井修仙']['file']
    path.parent.mkdir(parents=True)
    path.write_text('# 完整档案一\n<!-- dispatch:start -->第一版执行声线。<!-- dispatch:end -->\n参考一', encoding='utf-8')
    book = pipeline.open_book(fixtures.contract(), '作者选择文风', fixtures.world_fixture())
    pipeline.install_outlines(book, 'v1', fixtures.volume_row(book['contract']['volumes'][0]),
                              fixtures.chapter_rows(book))
    store = LiteStore()
    first = pipeline.envelope(book, store, 1)
    receipt = {'context_id': 'writer-A', 'loaded': [first['records']['style_guide']]}
    assert pipeline.submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    path.write_text('# 完整档案二\n<!-- dispatch:start -->第二版执行声线。<!-- dispatch:end -->\n参考二', encoding='utf-8')
    unchanged = pipeline.envelope(book, store, 2)
    assert store.read_document(unchanged['records']['style_guide'])['content'] == '第一版执行声线。'
    pipeline.recontract_patch(book, source='作者确认第二版', style_profile='市井修仙')
    changed = pipeline.envelope(book, store, 2, cache=receipt)
    assert 'style_guide' in changed['required']
    assert changed['records']['style_guide'] != first['records']['style_guide']
    assert store.read_document(changed['records']['style_guide'])['content'] == '第二版执行声线。'
    path.unlink()
    saved = tmp_path / 'book.json'
    pipeline.save(book, store, saved)
    loaded, restored = pipeline.load(saved)
    resumed = pipeline.envelope(loaded, restored, 2)
    assert restored.read_document(resumed['records']['style_guide'])['content'] == '第二版执行声线。'


def test_guide_requires_the_current_context_cache_receipt():
    book, _, _ = fixtures.open_installed_book()
    store = LiteStore()
    first = pipeline.envelope(book, store, 1)
    receipt = {'context_id': 'writer-A', 'loaded': [first['records']['style_guide']]}
    assert pipeline.submit(book, store, 1, fixtures.draft_for(book, 1))['ok']
    second = pipeline.envelope(book, store, 2, cache=receipt)
    assert 'style_guide' in second['delivery']['cached']
    warm = json.loads(pipeline.materialize(second, store, cache=receipt)['text'])['materials']
    cold = json.loads(pipeline.materialize(second, store)['text'])['materials']
    assert 'style_guide' not in warm
    assert cold['style_guide']['profile'] == '市井修仙'
