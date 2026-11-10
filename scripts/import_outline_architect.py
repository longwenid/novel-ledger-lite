#!/usr/bin/env python3
"""Snapshot an outline-architect package as source-backed preparation candidates.

This adapter does not create a book, approve an outline or invent state deltas.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

DOCS = ('00', '01', '01a', '01b', '01c', '01d', '01e', '01f', '01g',
        '01h', '01i', '01j', '01k', '02', '03', '04', '05', '06', '07', '08', '09', '10')
UNRESOLVED = ['author_confirmation', 'delivery_acceptance', 'contract', 'world_model',
              'scene_dependencies', 'resource_changes', 'character_states', 'knowledge',
              'timeline', 'hooks', 'enter_exit', 'style_selection']


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'重复 JSON 键：{key}')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique)


def cells(line: str) -> list[str]:
    parts, buf, slashes = [], [], 0
    for char in line.strip():
        if char == '|' and slashes % 2 == 0:
            parts.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(char)
        slashes = slashes + 1 if char == '\\' else 0
    parts.append(''.join(buf).strip())
    if parts and not parts[0]:
        parts.pop(0)
    if parts and not parts[-1]:
        parts.pop()
    return [part.replace('\\|', '|') for part in parts]


def tables(raw: bytes, filename: str) -> dict:
    lines = raw.decode('utf-8-sig').splitlines()
    result, pending, fence, i = {}, None, None, 0
    while i < len(lines):
        line = lines[i]
        mark = re.match(r'^\s*(`{3,}|~{3,})', line)
        if mark:
            token = mark.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            i += 1
            continue
        if fence:
            i += 1
            continue
        if re.match(r'^#{1,6}\s', line):
            # Only a heading beginning with the table ID declares a data table.
            # Explanations such as "§3 地图主表（T-REG）" are not declarations.
            match = re.match(r'^#{1,6}\s+(T-[A-Z0-9-]+)\b', line)
            pending = match.group(1) if match else None
        if pending and line.strip().startswith('|') and i + 1 < len(lines):
            header, divider = cells(line), cells(lines[i + 1])
            if divider and all(re.fullmatch(r':?-{2,}:?', x) for x in divider):
                # Existing packages may have an extra separator dash cell. It
                # carries no data; actual header and data rows must match exactly.
                if pending in result or len(set(header)) != len(header):
                    raise ValueError(f'{filename}:{i + 1}: 重复表、重复列或无效表头 {pending}')
                rows = []
                i += 2
                while i < len(lines) and lines[i].strip().startswith('|'):
                    values = cells(lines[i])
                    if len(values) != len(header):
                        raise ValueError(f'{filename}:{i + 1}: {pending} 列数不符')
                    rows.append({'values': dict(zip(header, values)), 'source_lines': [i + 1, i + 1],
                                 'raw': lines[i]})
                    i += 1
                result[pending] = {'header': header, 'rows': rows}
                pending = None
                continue
        i += 1
    return result


def source_snapshot(source: Path):
    manifest_path = source / '_manifest.json'
    if manifest_path.is_symlink():
        raise ValueError('manifest 不得为符号链接')
    manifest_raw = manifest_path.read_bytes()
    manifest = read_json(manifest_raw)
    if not isinstance(manifest, dict):
        raise ValueError('manifest 顶层必须为对象')
    entries = manifest.get('files')
    if not isinstance(entries, list) or len(entries) != len(DOCS):
        raise ValueError('manifest 必须列出22个大纲文件')
    docs, frozen = {}, {'_manifest.json': manifest_raw}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('manifest 文件项必须为对象')
        name = entry.get('name', '')
        match = re.fullmatch(r'(\d{2}[a-k]?)-[^/\\]+\.md', name)
        if not match or match.group(1) not in DOCS or match.group(1) in docs or Path(name).name != name:
            raise ValueError(f'无效、重复或越界文件：{name}')
        path = source / name
        if path.is_symlink():
            raise ValueError(f'源文件不得为符号链接：{name}')
        raw = path.read_bytes()
        normalized = raw.decode('utf-8-sig').replace('\r\n', '\n').encode('utf-8')
        if entry.get('sha256') != sha(normalized) or entry.get('bytes') != len(raw):
            raise ValueError(f'manifest 指纹或字节数失配：{name}；先核实源变更，不能自动重算洗白')
        docs[match.group(1)] = {'name': name, 'tables': tables(raw, name)}
        frozen[name] = raw
    if set(docs) != set(DOCS):
        raise ValueError('源文档不齐')
    audit = source / '_audit/T-AUDIT.md'
    if audit.exists():
        if audit.is_symlink() or not audit.resolve().is_relative_to(source.resolve()):
            raise ValueError('审计回执不得链接到包外')
        frozen['_audit/T-AUDIT.md'] = audit.read_bytes()
    return docs, frozen


def rows(docs, did, tid):
    try:
        return docs[did]['tables'][tid]['rows']
    except KeyError:
        raise ValueError(f'缺少 {did}#{tid}') from None


def number(value, prefix):
    match = re.fullmatch(prefix + r'(\d{4,})', value)
    if not match:
        raise ValueError(f'无效 ID：{value}')
    return int(match.group(1))


def chapter_range(value):
    match = re.fullmatch(r'CH(\d{4,})\s*[-–—~～至]\s*(?:CH)?(\d{4,})', value)
    if not match or int(match.group(1)) > int(match.group(2)):
        raise ValueError(f'无效章范围：{value}')
    return int(match.group(1)), int(match.group(2))


def prepare(docs, frozen):
    volumes, units = [], {}
    last = 0
    for row in rows(docs, '03', 'T-VOL'):
        value = row['values']
        vid = value.get('volume_id', '')
        if not re.fullmatch(r'V\d{2,}', vid) or any(v['volume_id'] == vid for v in volumes):
            raise ValueError('卷 ID 无效或重复')
        first, end = chapter_range(value.get('章范围', ''))
        if first != last + 1:
            raise ValueError('卷范围必须从第1章连续')
        volumes.append({'volume_id': vid, 'first': first, 'end': end, 'source_row': row, 'chapters': []})
        last = end
    if not volumes:
        raise ValueError('没有卷纲')
    for row in rows(docs, '03', 'T-UNIT-IDX'):
        value = row['values']
        uid = value.get('unit_id', '')
        if not uid or uid in units:
            raise ValueError('单元 ID 为空或重复')
        units[uid] = value
    last_ch = 0
    for row in rows(docs, '03', 'T-CH'):
        value = row['values']
        ch = number(value.get('章号', ''), 'CH')
        if ch != last_ch + 1:
            raise ValueError('已有章卡必须从第1章连续且不重复')
        volume = next((v for v in volumes if v['first'] <= ch <= v['end']), None)
        unit = units.get(value.get('unit_id'))
        if volume is None or unit is None or unit.get('卷') != volume['volume_id']:
            raise ValueError(f'第{ch}章卷/单元归属不符')
        uf, ue = chapter_range(unit.get('章范围', ''))
        if not uf <= ch <= ue:
            raise ValueError(f'第{ch}章不在所属单元范围')
        for field in ('章目标', '阻碍', '不可逆变化'):
            if value.get(field, '').strip() in ('', '—', 'TBD', '待定'):
                raise ValueError(f'第{ch}章缺少{field}')
        volume['chapters'].append({'chapter': ch, 'outline_fields': value,
            'outline_text': row['raw'], 'source_file': docs['03']['name'],
            'source_lines': row['source_lines'], 'source_sha256': sha(frozen[docs['03']['name']]),
            'review_status': 'unreviewed', 'unresolved': list(UNRESOLVED)})
        last_ch = ch
    if not last_ch:
        raise ValueError('没有逐章章纲，不能创建执行候选')
    for volume in volumes:
        volume['coverage_complete'] = len(volume['chapters']) == volume['end'] - volume['first'] + 1
        volume['missing_range'] = None if volume['coverage_complete'] else [
            volume['first'] + len(volume['chapters']), volume['end']]
        volume['status'] = 'review_required' if volume['coverage_complete'] else 'outline_incomplete'
    return volumes, last_ch


def import_outline_architect(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.absolute()
    resolved_output = output.resolve()
    if source == resolved_output or source in resolved_output.parents or resolved_output in source.parents:
        raise ValueError('候选与源目录不得相互包含')
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'目标已存在，未覆盖：{output}')
    docs, frozen = source_snapshot(source)
    volumes, count = prepare(docs, frozen)
    manifest = {'schema': 'novel-ledger-lite.outline-candidates/1',
        'source_format': 'outline-architect/1', 'status': 'review_required',
        'source_directory': str(source), 'source_manifest_sha256': sha(frozen['_manifest.json']),
        'chapters': count, 'delivery_acceptance': 'not_verified', 'engine_installed': False,
        'unresolved': list(UNRESOLVED), 'volumes': [], 'files': [],
        'warning': '已完成来源校验与原文快照，未完成作者确认、交付验收或执行建模。候选不是写作账本。'}
    payloads = {'source/' + name: raw for name, raw in frozen.items()}
    payloads['tables.json'] = (json.dumps(docs, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    for volume in volumes:
        name = f"volumes/{volume['volume_id']}_candidate.json"
        payloads[name] = (json.dumps(volume, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        manifest['volumes'].append({k: value for k, value in volume.items() if k not in ('chapters', 'source_row')} | {'candidate': name})
    manifest['files'] = [{'name': name, 'sha256': sha(raw), 'bytes': len(raw)} for name, raw in payloads.items()]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()  # Exclusive reservation: an existing empty directory is never replaced.
    try:
        for name, raw in payloads.items():
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        # Refuse a source change during extraction; never publish a mixed snapshot.
        if source_snapshot(source)[1] != frozen:
            raise ValueError('读取期间源包发生变化，未发布候选')
        (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


def verify_import(output: Path) -> dict:
    output = output.resolve()
    manifest = read_json((output / 'manifest.json').read_bytes())
    if (manifest.get('schema') != 'novel-ledger-lite.outline-candidates/1'
            or manifest.get('source_format') != 'outline-architect/1'
            or manifest.get('status') != 'review_required' or manifest.get('engine_installed') is not False
            or manifest.get('unresolved') != UNRESOLVED):
        raise ValueError('候选格式或状态无效；不能将候选标为已安装')
    seen = set()
    for entry in manifest['files']:
        name = entry['name']
        path = output / name
        if (name in seen or path.is_symlink() or path.resolve().is_relative_to(output) is False
                or '..' in Path(name).parts or Path(name).is_absolute()):
            raise ValueError('候选文件路径无效或重复')
        seen.add(name)
        raw = path.read_bytes()
        if len(raw) != entry['bytes'] or sha(raw) != entry['sha256']:
            raise ValueError(f'候选指纹失配：{name}')
    docs, frozen = source_snapshot(output / 'source')
    volumes, count = prepare(docs, frozen)
    expected = {'source/' + name for name in frozen} | {'tables.json'}
    expected |= {f"volumes/{v['volume_id']}_candidate.json" for v in volumes}
    if seen != expected or manifest['source_manifest_sha256'] != sha(frozen['_manifest.json']):
        raise ValueError('候选文件清单或来源 manifest 指纹不符')
    if read_json((output / 'tables.json').read_bytes()) != docs or manifest['chapters'] != count:
        raise ValueError('候选索引与冻结原文不符')
    for volume in volumes:
        if read_json((output / f"volumes/{volume['volume_id']}_candidate.json").read_bytes()) != volume:
            raise ValueError('卷候选与冻结原文不符')
    expected_volumes = [{k: value for k, value in volume.items() if k not in ('chapters', 'source_row')}
                        | {'candidate': f"volumes/{volume['volume_id']}_candidate.json"} for volume in volumes]
    if manifest['volumes'] != expected_volumes or manifest['delivery_acceptance'] != 'not_verified':
        raise ValueError('候选覆盖或验收声明不符')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path, help='只读核对候选及全部冻结来源')
    args = parser.parse_args()
    try:
        if args.verify:
            if args.source or args.output:
                raise ValueError('--verify 不与 --source/--output 混用')
            result = verify_import(args.verify)
        else:
            if args.source is None or args.output is None:
                raise ValueError('需要 --source 与 --output')
            result = import_outline_architect(args.source, args.output)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f'接入失败：{exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
