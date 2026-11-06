#!/usr/bin/env python3
"""Archive existing chapter outlines for review; never invent a ledger or install plans."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

HEADER = re.compile(r'^第(\d{1,6})章\s+(.+?)\s*$')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract(path: Path) -> list[dict]:
    raw = path.read_bytes()
    lines = raw.decode('utf-8-sig').splitlines()
    headings = [(i, HEADER.fullmatch(line)) for i, line in enumerate(lines)]
    headings = [(i, m) for i, m in headings if m]
    if not headings:
        raise ValueError(f'{path}: 未发现“第0001章 标题”格式的章节')
    digest = sha(raw)
    rows = []
    for pos, (line, m) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        start, stop = line + 1, end
        for index in range(start, end):
            item = lines[index].strip()
            if re.match(r'^#{1,6}\s+', item) or re.fullmatch(r'第[一二三四五六七八九十百\d]+单元[：:].*', item):
                stop = index
                break
        while start < stop and not lines[start].strip():
            start += 1
        while stop > start and not lines[stop - 1].strip():
            stop -= 1
        # A standalone unit heading between chapters is catalogue metadata, not prior chapter text.
        while stop > start and re.fullmatch(r'第[一二三四五六七八九十百\d]+单元[：:].*', lines[stop - 1].strip()):
            stop -= 1
            while stop > start and not lines[stop - 1].strip():
                stop -= 1
        contents = lines[start:stop]
        if not contents:
            raise ValueError(f'{path}:{line + 1}: 章节内容为空')
        rows.append({'chapter': int(m.group(1)), 'title': m.group(2),
                     'source_lines': [line + 1, stop],
                     'source_file': path.name, 'source_sha256': digest,
                     'outline_text': '\n'.join(contents),
                     'review_status': 'unreviewed',
                     'unresolved': ['scene_dependencies', 'resource_changes', 'character_states',
                                    'knowledge', 'timeline', 'hooks', 'enter_exit']})
    return rows


def import_outlines(source: Path, output: Path) -> dict:
    files = sorted(source.glob('*.md'))
    if not files:
        raise ValueError(f'{source}: 无 Markdown 章纲文件')
    parsed = [(f, extract(f)) for f in files]
    parsed.sort(key=lambda item: item[1][0]['chapter'])
    nums = [row['chapter'] for _, rows in parsed for row in rows]
    if nums != list(range(1, len(nums) + 1)):
        raise ValueError('章号必须从 1 连续，且不得重复、缺失或文件交叉')
    if output.exists():
        raise FileExistsError(f'目标已存在，未覆盖：{output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.outline-import-', dir=output.parent) as temp:
        tmp = Path(temp) / 'ready'
        tmp.mkdir()
        (tmp / 'volumes').mkdir()
        volumes = []
        for i, (f, rows) in enumerate(parsed, 1):
            item = {'volume_id': f'v{i}', 'source_file': f.name,
                    'source_sha256': sha(f.read_bytes()),
                    'first': rows[0]['chapter'], 'end': rows[-1]['chapter'],
                    'chapters': rows}
            name = f'v{i:02d}_candidate.json'
            (tmp / 'volumes' / name).write_text(json.dumps(item, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            volumes.append({k: item[k] for k in ('volume_id', 'source_file', 'source_sha256', 'first', 'end')}
                           | {'candidate': f'volumes/{name}'})
        manifest = {'schema': 'novel-ledger-lite.outline-candidates/1',
                    'status': 'review_required', 'source_directory': str(source.resolve()),
                    'chapters': len(nums), 'volumes': volumes,
                    'warning': '候选不是引擎已冻结章纲；空字段不代表没有变化。必须逐卷核实并转为正式契约格式。'}
        (tmp / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        shutil.move(str(tmp), str(output))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='含按卷 Markdown 章纲的目录')
    parser.add_argument('--output', type=Path, required=True, help='必须不存在的候选目录')
    args = parser.parse_args()
    print(json.dumps(import_outlines(args.source, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
