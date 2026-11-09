"""Run the bundled four-chapter API example using only the Python standard library."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / 'scripts'))

from novel_ledger_lite import pipeline
from novel_ledger_lite.contracts import digest
from novel_ledger_lite.store import LiteStore


def run(output):
    project = json.loads((SKILL_ROOT / 'references' / 'example_project.json').read_text(encoding='utf-8'))
    design = {key: project[key] for key in ('contract', 'world', 'volumes')}
    if project['review_design_hash'] != digest(design):
        raise RuntimeError('示例设计已改变，冻结审读报告失效。')
    book = pipeline.open_book(project['contract'], '作者确认的演示输入', project.get('world'))
    reviewed_style = {key: value for key, value in (book['style_archive'] or {}).items() if key != 'path'}
    if project['review_style_hash'] != digest(reviewed_style):
        raise RuntimeError('示例文风材料已改变，冻结审读报告失效。')
    store = LiteStore()
    dispatch_bytes = 0
    for volume in project['volumes']:
        pipeline.install_outlines(book, volume['id'], volume['outline'], volume['chapter_outline'])
        group = None
        for plan in book['chapter_outlines'][volume['id']]:
            chapter = plan['chapter']
            if group is None or chapter > group['members'][1]:
                group = pipeline.group(book, store, volume['id'])
            package = pipeline.chapter_package(book, store, chapter, group)
            pipeline.validate_chapter_package(book, store, package['text'])
            dispatch_bytes += len(package['text'].encode('utf-8'))
            draft = dict(project['drafts'][str(chapter)], package_ref=package['package_ref'])
            # These are frozen reports for the bundled, independently read sample,
            # never an automatic approval facility for arbitrary user prose.
            reviewed = project['review_reports'][str(chapter)]
            if reviewed['draft_hash'] != digest(project['drafts'][str(chapter)]):
                raise RuntimeError('示例稿件已改变，冻结审读报告失效。')
            request = pipeline.review_request(book, store, chapter, draft, writer='example-writer')
            report = dict(reviewed['report'], request_ref=request['request_ref'])
            draft['review_ref'] = pipeline.record_content_review(
                book, store, request['request_ref'], report)
            result = pipeline.submit(book, store, chapter, draft)
            if not result['ok']:
                raise RuntimeError(json.dumps(result, ensure_ascii=False))
    pipeline.save(book, store, output)
    loaded, saved_store = pipeline.load(output)
    report = pipeline.verify_full(loaded, saved_store)
    report['roundtrip'] = digest(loaded['state']) == digest(book['state'])
    report['written_han'] = loaded['written_han']
    report['dispatch_bytes'] = dispatch_bytes
    if not report['ok'] or not report['roundtrip']:
        raise RuntimeError(json.dumps(report, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional path to retain the example ledger.')
    args = parser.parse_args()
    if args.output is not None:
        report = run(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='novel-ledger-lite-') as directory:
            report = run(Path(directory) / 'example.json')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
