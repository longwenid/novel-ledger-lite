import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from import_markdown_outlines import import_outlines


def test_import_keeps_source_and_marks_unknowns(tmp_path):
    source = tmp_path / 'sources'
    source.mkdir()
    text = '# 本卷\n\n第0001章 起点\n\n林恩醒来。\n钩子：有人敲门。\n\n第二单元：下一段\n\n第0002章 门外\n走出屋门。\n\n## 卷末状态\n这是后续总结，不属于本章。\n'
    (source / 'v.md').write_text(text, encoding='utf-8')
    target = tmp_path / 'candidate'
    report = import_outlines(source, target)
    rows = json.loads((target / 'volumes/v01_candidate.json').read_text())['chapters']
    assert report['status'] == 'review_required' and report['chapters'] == 2
    assert rows[0]['outline_text'] == '林恩醒来。\n钩子：有人敲门。'
    assert rows[0]['source_lines'] == [3, 6]
    assert rows[1]['outline_text'] == '走出屋门。'
    assert 'timeline' in rows[0]['unresolved'] and rows[0]['review_status'] == 'unreviewed'
    assert 'clock' not in rows[0] and 'resources' not in rows[0]
    with pytest.raises(FileExistsError):
        import_outlines(source, target)
    assert (source / 'v.md').read_text(encoding='utf-8') == text


@pytest.mark.parametrize('chapters', ['第0001章 一\n内容\n第0003章 三\n内容\n',
                                       '第0001章 一\n内容\n第0001章 一\n内容\n'])
def test_import_rejects_gaps_and_duplicates_without_output(tmp_path, chapters):
    source = tmp_path / 'sources'
    source.mkdir()
    (source / 'v.md').write_text(chapters, encoding='utf-8')
    target = tmp_path / 'candidate'
    with pytest.raises(ValueError):
        import_outlines(source, target)
    assert not target.exists()
