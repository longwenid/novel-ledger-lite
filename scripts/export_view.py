#!/usr/bin/env python3
"""Export a read-only writing view from a saved bundle for the GUI writing mode.

引擎账本仍是唯一真源：这里只把 bundle 里的设定、卷章信息和正文投影成
GUI 右栏可逐文件读取的派生产物（`.novel-ledger/view.json` 与每章 Markdown）。
删除或重新生成派生产物不影响账本，也不会被 `pipeline.load` 读取。

用法（在小说项目目录执行）：

    python3 <skill>/scripts/export_view.py <bundle.json> [--out .novel-ledger]

产物：

    <out>/view.json            小型版本清单，引用完整写作视图分片
    <out>/chunks/<sha>.json    单行 UTF-8 分片（含正文，逐片及重组后验 SHA-256）
    <out>/chapters/ch0001.md   每章正文（标题行 + 正文段落）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from novel_ledger_lite import pipeline, world  # noqa: E402

VIEW_SCHEMA = 'novel-writing-view/2'
MANIFEST_SCHEMA = 'novel-writing-manifest/1'
CONTENT_SCHEMA = 'novel-writing-content/1'
CHUNK_SCHEMA = 'novel-writing-chunk/1'
# Each transport file is one physical line and stays comfortably below the
# workspace reader's byte ceiling, independently of prose line lengths.
MAX_TRANSPORT_BYTES = 128 * 1024

WORLD_FIELD_LABELS = {
    'name': '名称', 'environment': '环境', 'resources': '资源', 'access': '进出', 'story_pressure': '叙事压力',
    'period': '时期', 'event': '事件', 'consequence': '后果', 'present_effect': '当下影响', 'epoch': '纪元',
    'carryover': '遗产', 'scale': '尺度', 'counter_space': '对立空间',
    'principle': '原理', 'scope': '作用范围', 'limits': '限制', 'consequences': '代价', 'cost': '代价',
    'goal': '目标', 'power': '力量', 'dependencies': '依赖', 'conflicts': '冲突', 'survives_scale_up': '放量后是否成立',
    'resource': '资源', 'production': '生产', 'distribution': '分配', 'scarcity': '稀缺', 'conflict': '冲突点',
    'institution': '制度', 'norm': '规范', 'enforcement': '执行', 'pressure': '压力',
    'practice': '日常实践', 'constraint': '约束', 'story_use': '叙事用途',
    'truth': '真相', 'disclosure': '披露时机', 'causal_role': '因果作用', 'reveal_window': '披露窗口',
    'survival': '存续', 'mechanism': '机制', 'failure_condition': '失效条件',
    'condition': '触发条件', 'gain': '所得', 'limit': '限制',
    'inhabitant': '居民', 'law': '法则', 'entry': '入口',
    'role': '角色', 'desire': '欲望', 'knowledge_boundary': '认知边界', 'links': '关联',
}

FACET_LABELS = (
    ('world_premise', '世界前提'),
    ('story_engine', '故事引擎'),
    ('opposition', '对抗'),
    ('reader_promise', '读者承诺'),
    ('ending', '结局方向'),
    ('voice', '叙事声音'),
)


def _scalar(value):
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return ' '.join(value.split())
    if isinstance(value, list):
        return '、'.join(_scalar(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return '' if value is None else str(value)


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _json_character_bytes(char):
    """Bytes occupied by one character inside an ensure_ascii=False string."""
    if char in ('"', '\\', '\b', '\f', '\n', '\r', '\t'):
        return 2
    code = ord(char)
    if code < 32:
        return 6
    return len(char.encode('utf-8'))


def _atomic_bytes(path, raw):
    descriptor, temporary = tempfile.mkstemp(prefix='.export-', dir=os.path.dirname(path) or '.')
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(raw)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _content(out_dir, text):
    """Write lossless, content-addressed JSON chunks and return their manifest."""
    chunks_dir = os.path.join(out_dir, 'chunks')
    os.makedirs(chunks_dir, exist_ok=True)
    pieces, start, size = [], 0, 0
    # Leave room for schema, index and punctuation in the serialized envelope.
    budget = MAX_TRANSPORT_BYTES - 256
    for position, char in enumerate(text):
        cost = _json_character_bytes(char)
        if size + cost > budget:
            pieces.append(text[start:position])
            start, size = position, 0
        size += cost
    pieces.append(text[start:])
    references = []
    for index, piece in enumerate(pieces):
        raw = _json_bytes({'schema': CHUNK_SCHEMA, 'index': index, 'text': piece})
        if len(raw) > MAX_TRANSPORT_BYTES:
            raise ValueError('写作视图分片超过传输预算。')
        checksum = hashlib.sha256(raw).hexdigest()
        name = 'chunks/%s.json' % checksum
        _atomic_bytes(os.path.join(out_dir, name), raw)
        references.append({'file': name, 'bytes': len(raw), 'sha256': checksum})
    raw_text = text.encode('utf-8')
    return {'schema': CONTENT_SCHEMA, 'bytes': len(raw_text),
            'sha256': hashlib.sha256(raw_text).hexdigest(), 'chunks': references}


def _documents(store_raw):
    documents = store_raw.get('documents') or {}
    return documents if isinstance(documents, dict) else {}


def _prose_of(store_raw, row, documents):
    key = row.get('prose')
    value = documents.get(key) if isinstance(key, str) else None
    return value if isinstance(value, str) else ''


def _world_view(book):
    model = book.get('world') or {}
    sections = []
    for section in world.ALL_SECTIONS:
        rows = model.get(section)
        if not isinstance(rows, list) or not rows:
            continue
        fields = list(world.SECTIONS[section]) + list(world.OPTIONAL_FIELDS.get(section, ()))
        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = _scalar(row.get('name') or row.get('institution') or row.get('resource')
                            or row.get('period') or row.get('principle') or row.get('practice')
                            or row.get('truth') or row.get('event') or row.get('id') or '')
            lines = []
            for field in fields:
                if field in ('name', 'id') or field not in row:
                    continue
                value = _scalar(row.get(field))
                if value:
                    lines.append({'label': WORLD_FIELD_LABELS.get(field, field), 'value': value})
            items.append({'id': _scalar(row.get('id') or ''), 'title': title or _scalar(row.get('id') or ''),
                          'lines': lines})
        sections.append({'key': section, 'title': world.LABELS.get(section, section), 'items': items})
    return sections


def _characters(book, contract):
    state = book.get('state') or {}
    entities = state.get('entities') or {}
    world_people = {}
    for row in (book.get('world') or {}).get('characters') or []:
        if isinstance(row, dict) and row.get('id'):
            world_people[row['id']] = row
    facts = {}
    for key, value in (state.get('facts') or {}).items():
        if not isinstance(key, str) or ':' not in key:
            continue
        who, _, name = key.partition(':')
        facts.setdefault(who, []).append({'key': name, 'value': _scalar(value)})
    knowledge = {}
    for key, value in (state.get('knowledge') or {}).items():
        if not isinstance(key, str) or ':' not in key or not isinstance(value, dict):
            continue
        who, _, topic = key.partition(':')
        knowledge.setdefault(who, []).append({
            'topic': topic,
            'stance': _scalar(value.get('stance')),
            'claim': _scalar(value.get('claim')),
        })
    places = state.get('places') or {}
    placements = state.get('placements') or {}
    people = []
    for ident, entity in entities.items():
        if not isinstance(entity, dict):
            continue
        if entity.get('kind') not in (None, 'person', 'character'):
            continue
        profile = world_people.get(ident) or {}
        place_id = placements.get(ident)
        people.append({
            'id': ident,
            'name': _scalar(entity.get('name') or ident),
            'kind': _scalar(entity.get('kind') or ''),
            'role': _scalar(profile.get('role') or ''),
            'desire': _scalar(profile.get('desire') or ''),
            'limit': _scalar(profile.get('limit') or ''),
            'place': _scalar((places.get(place_id) or {}).get('name') or place_id or ''),
            'facts': facts.get(ident, []),
            'knowledge': knowledge.get(ident, []),
        })
    protagonist = contract.get('protagonist_setup') or {}
    head = people[0]['id'] if people else None
    return people, protagonist, head


def _resources(book):
    state = book.get('state') or {}
    places = state.get('places') or {}
    rows = []
    for key, value in (state.get('resources') or {}).items():
        try:
            holder, asset, unit = json.loads(key)
        except (TypeError, ValueError):
            rows.append({'holder': _scalar(key), 'asset': '', 'unit': '', 'amount': _scalar(value)})
            continue
        rows.append({'holder': _scalar(holder), 'asset': _scalar(asset), 'unit': _scalar(unit),
                     'amount': _scalar(value)})
    hooks = []
    for key, row in (state.get('hooks') or {}).items():
        if not isinstance(row, dict):
            continue
        seed = row.get('seed') or {}
        hooks.append({
            'id': _scalar(key),
            'text': _scalar(row.get('text')),
            'status': _scalar(row.get('status')),
            'due': row.get('due'),
            'seed_chapter': seed.get('chapter'),
        })
    places_rows = [{'id': _scalar(key), 'name': _scalar((row or {}).get('name') or key),
                    'parent': _scalar((row or {}).get('parent') or '')}
                   for key, row in places.items() if isinstance(row, dict)]
    return rows, hooks, places_rows


def _volumes(book, contract, hooks_by_id):
    outlines = book.get('volumes_outline') or {}
    volumes = []
    for volume in contract.get('volumes') or []:
        vid = volume.get('id')
        outline = outlines.get(vid) or {}
        volume_hooks = []
        for hook in (outline.get('hooks') or []):
            if not isinstance(hook, dict):
                continue
            live = hooks_by_id.get(_scalar(hook.get('id'))) or {}
            volume_hooks.append({
                'id': _scalar(hook.get('id')),
                'text': _scalar(hook.get('text')),
                'plant': hook.get('plant'),
                'payoff': hook.get('payoff'),
                'status': live.get('status') or 'open',
            })
        volumes.append({
            'id': _scalar(vid),
            'first': volume.get('first'),
            'end': volume.get('end'),
            'purpose': _scalar(volume.get('purpose')),
            'arc': _scalar(outline.get('arc')),
            'climax': _scalar(outline.get('climax')),
            'exit_state': _scalar(outline.get('exit_state')),
            'trend': _scalar((outline.get('style') or {}).get('trend')),
            'turns': [{'at': _scalar((row or {}).get('at')), 'turn': _scalar((row or {}).get('turn'))}
                      for row in (outline.get('turns') or []) if isinstance(row, dict)],
            'hooks': volume_hooks,
        })
    return volumes


def build_view(bundle_path, out_dir):
    """Project one bundle into `view.json` plus one Markdown file per submitted chapter."""
    book, store = pipeline.load(bundle_path)
    store_raw = store.to_dict()
    documents = _documents(store_raw)
    contract = book.get('contract') or {}
    plans = book.get('plans') or {}
    rows = store_raw.get('chapters') or {}
    chapters_dir = os.path.join(out_dir, 'chapters')
    os.makedirs(chapters_dir, exist_ok=True)

    volumes = contract.get('volumes') or []
    total = max((volume.get('end') or 0) for volume in volumes) if volumes else 0
    volume_of = {}
    for volume in volumes:
        for n in range(volume.get('first') or 1, (volume.get('end') or 0) + 1):
            volume_of[n] = _scalar(volume.get('id'))

    _, hooks, places_rows = _resources(book)
    hooks_by_id = {row['id']: row for row in hooks}
    chapters = []
    written = 0
    han_total = 0
    for n in range(1, total + 1):
        row = rows.get(str(n)) or {}
        plan = plans.get(str(n)) or {}
        is_written = bool(row)
        file_name = 'chapters/ch%04d.md' % n
        if is_written:
            prose = _prose_of(store_raw, row, documents)
            title = _scalar(row.get('title') or '')
            han = row.get('han')
            heading = title if title.startswith('第') else '第%d章 %s' % (n, title)
            body = '# %s\n\n%s\n' % (heading.strip(), prose.strip('\n'))
            _atomic_bytes(os.path.join(out_dir, file_name), body.encode('utf-8'))
            content = _content(out_dir, body)
            written += 1
            han_total += han if isinstance(han, int) else 0
        else:
            han = None
            title = ''
            content = None
        chapters.append({
            'n': n,
            'volume': volume_of.get(n, ''),
            'title': title,
            'state': 'written' if is_written else ('outlined' if plan else 'planned'),
            'han': han,
            'synopsis': _scalar(plan.get('synopsis')),
            'summary': _scalar(row.get('summary')),
            'beat': _scalar((plan.get('plot') or {}).get('beat')),
            'scenes': [_scalar((scene or {}).get('label')) for scene in (plan.get('scenes') or [])
                       if isinstance(scene, dict)],
            'file': file_name if is_written else '',
            'content': content,
        })

    people, protagonist, head = _characters(book, contract)
    resources, hooks_all, _ = _resources(book)
    style_archive = book.get('style_archive') or {}
    view = {
        'schema': VIEW_SCHEMA,
        'generated_at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
        'source': {'bundle': os.path.abspath(bundle_path), 'revision': book.get('revision'),
                   'branch': _scalar(book.get('branch')), 'last_chapter': book.get('last_chapter')},
        'book': {
            'title': _scalar(contract.get('title')),
            'genre': _scalar(contract.get('genre')),
            'status': _scalar(book.get('status')),
            'written': written,
            'chapter_count': total,
            'written_han': han_total,
            'clock': (book.get('state') or {}).get('clock'),
            'chapter_words': [contract.get('chapter_min'), contract.get('chapter_aim'), contract.get('chapter_max')],
            'style': {'profile': _scalar(contract.get('style_profile')),
                      'source': _scalar(contract.get('style_source')),
                      'kind': _scalar(style_archive.get('source_kind'))},
        },
        'premise': {key: _scalar(contract.get(key)) for key, _ in FACET_LABELS},
        'facets': [{'key': key, 'label': label, 'value': _scalar(contract.get(key))}
                   for key, label in FACET_LABELS],
        'rules': [{'key': 'world_rules', 'title': '世界规则', 'items': [_scalar(x) for x in contract.get('world_rules') or []]},
                  {'key': 'style_traits', 'title': '文风要点', 'items': [_scalar(x) for x in contract.get('style_traits') or []]}],
        'protagonist': {
            'id': _scalar(protagonist.get('id')),
            'name': _scalar(protagonist.get('name')),
            'identity': _scalar(protagonist.get('identity')),
            'desire': _scalar(protagonist.get('desire')),
            'limit': _scalar(protagonist.get('limit')),
        },
        'volumes': _volumes(book, contract, hooks_by_id),
        'chapters': chapters,
        'characters': people,
        'world': _world_view(book),
        'hooks': hooks_all,
        'resources': resources,
        'places': places_rows,
    }
    path = os.path.join(out_dir, 'view.json')
    manifest = {'schema': MANIFEST_SCHEMA, 'view_schema': VIEW_SCHEMA,
                'content': _content(out_dir, _json_bytes(view).decode('utf-8'))}
    raw_manifest = _json_bytes(manifest)
    if len(raw_manifest) > MAX_TRANSPORT_BYTES:
        raise ValueError('写作视图清单超过传输预算，未生成不完整视图。')
    # Publish the entrypoint last; a reader sees the previous complete export
    # until all immutable chunks belonging to the new one exist.
    _atomic_bytes(path, raw_manifest)
    return {'view': path, 'chapters': written, 'chapter_files': written, 'bytes': os.path.getsize(path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='从 novel-ledger-lite 账本导出 GUI 写作模式视图')
    parser.add_argument('bundle', help='pipeline.save 写出的 bundle 路径')
    parser.add_argument('--out', default='.novel-ledger', help='视图输出目录（默认 .novel-ledger）')
    parser.add_argument('--quiet', action='store_true', help='只输出 JSON 结果')
    args = parser.parse_args(argv)
    if not os.path.isfile(args.bundle):
        print(json.dumps({'ok': False, 'error': 'bundle 不存在：%s' % args.bundle}, ensure_ascii=False))
        return 2
    result = build_view(args.bundle, args.out)
    payload = {'ok': True, **result}
    print(json.dumps(payload, ensure_ascii=False))
    if not args.quiet:
        print('写作视图已导出：%s（%d 章正文）' % (result['view'], result['chapters']), file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
