"""Replay actual independent reader decisions against identical frozen fixtures."""
import copy
import json
from pathlib import Path

import pytest

from novel_ledger_lite import pipeline
from novel_ledger_lite.contracts import Error, digest
from novel_ledger_lite.store import LiteStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('label,accepted', [('Q', False), ('R', False), ('S', True)])
def test_real_reader_decision_controls_committing_semantic_contradictions(label, accepted, tmp_path):
    project = json.loads((ROOT / 'references/example_project.json').read_text(encoding='utf-8'))
    reviewed = json.loads((ROOT / 'tests/fixtures/independent_review_cases.json').read_text(encoding='utf-8'))
    assert digest({key: project[key] for key in ('contract', 'world', 'volumes')}) == reviewed['design_hash']
    book = pipeline.open_book(project['contract'], reviewed['source'], project['world'])
    store = LiteStore()
    volume = project['volumes'][0]
    pipeline.install_outlines(book, volume['id'], volume['outline'], volume['chapter_outline'])
    group = pipeline.group(book, store, volume['id'])
    package = pipeline.chapter_package(book, store, 1, group)
    case = reviewed['cases'][label]
    draft = copy.deepcopy(case['draft'])
    assert digest(draft) == case['manifest']['draft']
    # The real reader's semantic decision is frozen to this exact fixture design
    # and prose. Installation paths in the newly signed packet may differ after
    # relocation, so bind that fixed decision to this run's actual request.
    draft['package_ref'] = package['package_ref']
    # These drafts retain all correct writer-reported event quotations. Mechanical
    # checking alone reaches the independent review gate even for the bad endings.
    with pytest.raises(Error) as missing:
        pipeline.submit(book, store, 1, draft)
    assert missing.value.code == 'content_review_required'
    request = pipeline.review_request(book, store, 1, draft, writer='release-candidate-writer')
    report = dict(case['report'], request_ref=request['request_ref'])
    draft['review_ref'] = pipeline.record_content_review(
        book, store, request['request_ref'], report)
    before = copy.deepcopy(book), copy.deepcopy(store.to_dict())
    if accepted:
        assert pipeline.submit(book, store, 1, draft)['ok']
        assert book['state']['resources']['["shen","查单费","元"]'] == '3'
        assert book['last_chapter'] == store.last_chapter() == 1
    else:
        with pytest.raises(Error) as rejected:
            pipeline.submit(book, store, 1, draft)
        assert rejected.value.code == 'content_review_rejected'
        assert (book, store.to_dict()) == before
        assert book['last_chapter'] == store.last_chapter() == 0
    path = tmp_path / 'reviewed.json'
    pipeline.save(book, store, path)
    restored, saved = pipeline.load(path)
    assert restored == book
    assert saved.to_dict() == store.to_dict()


def test_bundled_example_rejects_changed_design_or_prose(tmp_path, monkeypatch):
    import run_example
    project = json.loads((ROOT / 'references/example_project.json').read_text(encoding='utf-8'))
    fake = tmp_path / 'skill'
    (fake / 'references').mkdir(parents=True)
    monkeypatch.setattr(run_example, 'SKILL_ROOT', fake)
    for changed in ('design', 'draft'):
        candidate = copy.deepcopy(project)
        if changed == 'design':
            candidate['contract']['ending'] += '另一种未经审读的结局。'
        else:
            candidate['drafts']['1']['prose'] += '他又得了五元。'
        (fake / 'references/example_project.json').write_text(json.dumps(candidate, ensure_ascii=False), encoding='utf-8')
        with pytest.raises(RuntimeError, match='冻结审读报告失效'):
            run_example.run(tmp_path / 'unapproved.json')
    (fake / 'references/example_project.json').write_text(json.dumps(project, ensure_ascii=False), encoding='utf-8')
    real_open = pipeline.open_book
    def changed_style(*args, **kwargs):
        book = real_open(*args, **kwargs)
        book['style_archive']['guide'] += '未经独立审读的文风约束。'
        return book
    monkeypatch.setattr(pipeline, 'open_book', changed_style)
    with pytest.raises(RuntimeError, match='文风材料已改变'):
        run_example.run(tmp_path / 'changed-style.json')


def test_real_reader_missing_material_decision_stops_incomplete_example():
    archived = json.loads((ROOT / 'tests/fixtures/example-review-before.json').read_text(encoding='utf-8'))
    project = archived['project']
    assert digest({key: project[key] for key in ('contract', 'world', 'volumes')}) == archived['design_hash']
    book = pipeline.open_book(project['contract'], '固定缺料负例', project['world'])
    store = LiteStore()
    volume = project['volumes'][0]
    pipeline.install_outlines(book, volume['id'], volume['outline'], volume['chapter_outline'])
    package = pipeline.chapter_package(book, store, 1)
    draft = copy.deepcopy(project['drafts']['1'])
    assert digest(draft) == archived['review_reports']['1']['draft_hash']
    draft['package_ref'] = package['package_ref']
    request = pipeline.review_request(book, store, 1, draft, writer='example-writer')
    # This is an archived actual reading of the identical incomplete fixture,
    # not a reader synthesized from the writer's clean declaration.
    report = dict(archived['review_reports']['1']['report'], request_ref=request['request_ref'])
    draft['review_ref'] = pipeline.record_content_review(book, store, request['request_ref'], report)
    with pytest.raises(Error) as stopped:
        pipeline.submit(book, store, 1, draft)
    assert stopped.value.code == 'content_review_rejected'
    assert book['last_chapter'] == store.last_chapter() == 0
