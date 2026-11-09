"""写作视图导出：账本仍是真源，派生产物必须完整、可重现且不碰账本。"""
from __future__ import annotations

import json
from pathlib import Path
import sys

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / 'scripts'))

import export_view  # noqa: E402
from run_example import run  # noqa: E402
from novel_ledger_lite import pipeline  # noqa: E402


def _bundle(work):
    path = work / 'project.json'
    run(path)
    return path


def test_view_covers_book_volumes_and_chapters(tmp_path):
    bundle = _bundle(tmp_path)
    out = tmp_path / 'view'
    result = export_view.build_view(str(bundle), str(out))
    view = json.loads((out / 'view.json').read_text(encoding='utf-8'))

    assert result['chapters'] == 4
    assert view['schema'] == export_view.VIEW_SCHEMA
    assert view['book']['chapter_count'] == 4
    assert view['book']['written'] == 4
    assert view['book']['title']
    assert [row['n'] for row in view['chapters']] == [1, 2, 3, 4]
    assert all(row['state'] == 'written' for row in view['chapters'])
    assert all(row['file'] == 'chapters/ch%04d.md' % row['n'] for row in view['chapters'])
    assert view['volumes'] and view['volumes'][0]['end'] == 4
    assert view['characters'] and view['characters'][0]['name']
    assert view['facets'] and all('label' in facet for facet in view['facets'])
    assert view['premise']['world_premise']
    for row in view['chapters']:
        body = (out / row['file']).read_text(encoding='utf-8')
        assert body.startswith('# ')
        assert row['title'] in body


def test_view_export_does_not_touch_the_bundle(tmp_path):
    bundle = _bundle(tmp_path)
    before = bundle.read_bytes()
    export_view.build_view(str(bundle), str(tmp_path / 'view'))
    assert bundle.read_bytes() == before
    loaded, _ = pipeline.load(str(bundle))
    assert loaded['last_chapter'] == 4


def test_cli_reports_missing_bundle(tmp_path, capsys):
    code = export_view.main([str(tmp_path / 'absent.json'), '--quiet'])
    assert code == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload['ok'] is False
