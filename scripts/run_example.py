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
    book = pipeline.open_book(project['contract'], '作者确认的演示输入', project.get('world'))
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
            result = pipeline.submit(book, store, chapter, project['drafts'][str(chapter)])
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
