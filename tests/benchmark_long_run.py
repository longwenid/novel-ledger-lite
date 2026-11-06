"""确定性合成长程压测，不生成文学作品；直接运行可验证千万汉字机械链路。"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import random
import resource
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import fixtures
from novel_ledger_lite import delta, facts, pipeline
from novel_ledger_lite.contracts import digest, han_count
from novel_ledger_lite.drift_reconcile import _planned
from novel_ledger_lite.store import LiteStore


def outlines(book, volume):
    outline = fixtures.volume_row(volume)
    hook = 'hook-' + volume['id']
    outline['hooks'][0]['id'] = hook
    outline['clock'] = {'advance_days': volume['end'] - volume['first'] + 1, 'to': volume['end']}
    scratch = copy.deepcopy(book['state'])
    rows = []
    for n in range(volume['first'], volume['end'] + 1):
        row = fixtures._chapter_row(scratch, book['contract'], volume, n, True, True)
        for action in row['hooks']:
            action['hook'] = hook
        row['hook_refs'] = [hook] if volume['first'] < n < volume['end'] else []
        # 每章新增一项知情，确保历史条目真实随书龄增长。
        topic = 'batch-' + str(n)
        row['knowledge'].append({'who': 'shen', 'topic': topic, 'from': None, 'to': 'confirmed',
                                 'reason': '核对本批次凭据，确认本批次来源。'})
        row['enter'].append({'kind': 'knowledge', 'key': 'shen:' + topic, 'expected': None})
        row['exit'].append({'kind': 'knowledge', 'key': 'shen:' + topic, 'expected': 'confirmed'})
        rows.append(row)
    return outline, {'volume': volume['id'], 'chapters': rows}


def draft(book, chapter, target_han):
    plan = book['plans'][str(chapter)]
    action = plan['hooks'][0]['action'] if plan['hooks'] else None
    prose, quotes = fixtures.prose_for(chapter, fixtures.moves_for(chapter), action)
    rng = random.Random(chapter)
    marker = ''.join(chr(rng.randrange(0x4e00, 0x9fa5)) for _ in range(8))
    # 章号超过千位后中文数字共享长前缀；用批次随机标签避免夹具自身变成重复模板。
    quotes = {kind: quote.replace(fixtures._cn(chapter), marker) for kind, quote in quotes.items()}
    prose = '。'.join(quote for quote in quotes.values() if quote) + '。'
    remaining = target_han - han_count(prose)
    # 无语义的确定性汉字填充，只用于真实长度、重复窗和存储负载，不代表文学质量。
    filler = ''.join(chr(rng.randrange(0x4e00, 0x9fa5)) for _ in range(remaining))
    prose += '\n'.join(filler[i:i + 30] + '。' for i in range(0, len(filler), 30))
    items = []
    for entry in _planned(plan):
        kind = entry['kind']
        key = 'advance_days' if kind == 'clock' else 'action' if kind == 'hook' else 'to'
        items.append({'kind': kind, 'key': entry['key'], 'planned': entry['planned'],
                      'status': 'kept', 'actual': {key: entry['planned'][key]},
                      'evidence': {'chapter': chapter, 'quote': quotes['hook' if kind == 'hook' else kind]}})
    return {'title': '核对第%s批' % fixtures._cn(chapter), 'summary': plan['synopsis'][:30],
            'self_check': '按章纲核对本批次凭据及已冻结状态。', 'prose': prose,
            'drift_check': {'items': items, 'unplanned': [], 'verdict': 'clean'}}


def run(chapters=3000, chapter_han=3500, volume_size=30):
    import tiktoken  # 仅压测度量依赖；引擎不依赖 tokenizer。

    encoding = tiktoken.get_encoding('cl100k_base')
    source_files = sorted((Path(__file__).resolve().parents[1] / 'scripts' / 'novel_ledger_lite').glob('*.py'))
    source_hash = digest({path.name: path.read_text(encoding='utf-8') for path in source_files})
    raw = fixtures.contract(chapters)
    raw.update(chapter_min=chapter_han, chapter_aim=chapter_han, chapter_max=chapter_han,
               volumes=[{'id': 'v%d' % (first // volume_size + 1), 'purpose': '核对本卷批次并结清责任。',
                         'end': min(first + volume_size, chapters)}
                        for first in range(0, chapters, volume_size)])
    # 核心资源常驻，并在每次补读核对。
    raw['initial_facts'] = [{'entity': 'shen', 'key': 'identity', 'value': '夜班工人，不是主管。'}]
    raw['pinned'] = [{'kind': 'facts', 'key': 'shen:identity'}]
    book = pipeline.open_book(raw, '长程合成压测', fixtures.world_fixture())
    store = LiteStore()
    observations = []
    replay_hashes = {}
    midpoint = chapters // 2
    milestones = {1, 30, 100, 500, 1000, midpoint, 2000, chapters}
    started = time.perf_counter()
    resume = None
    total_payload_bytes = 0
    calls = {'envelope': 0, 'materialize': 0, 'submit': 0, 'resource': 0,
             'catalog': 0, 'recall': 0, 'rejected_drafts': 0}
    for volume in book['contract']['volumes']:
        outline, rows = outlines(book, volume)
        pipeline.install_outlines(book, volume['id'], outline, rows)
        group = None
        for n in range(volume['first'], volume['end'] + 1):
            if group is None or n > group['members'][1]:
                group = pipeline.group(book, store, volume['id'], size=5)
            envelope = pipeline.envelope(book, store, n, group)
            calls['envelope'] += 1
            assert not envelope['warnings'], envelope['warnings']
            sampled = n in milestones or n - 1 in milestones
            delivered = pipeline.materialize(envelope, store,
                token_counter=(lambda value: len(encoding.encode(value))) if sampled else None,
                tokenizer_id='cl100k_base')
            calls['materialize'] += 1
            payload = delivered['text']
            total_payload_bytes += len(payload.encode())
            if sampled:
                state_record = store.read_document(envelope['records']['state'])
                observations.append({'chapter': n, 'group_head': n == group['members'][0],
                                     'payload_bytes': len(payload.encode()),
                                     'tokens_cl100k_base': delivered['metrics']['tokens'],
                                     'state_bytes': delivered['metrics']['by_record']['state']['bytes'],
                                     'category_bytes': delivered['metrics']['category_bytes'],
                                     'far_omitted': state_record['material_scope']['far_omitted']})
            result = pipeline.submit(book, store, n, draft(book, n, chapter_han))
            calls['submit'] += 1
            calls['rejected_drafts'] += int(not result['ok'])
            assert result['ok'], result.get('findings')
            calls['resource'] += 1
            assert pipeline.resource(book, 'facts', 'shen:identity')['value'] == '夜班工人，不是主管。'
            if n in (max(0, midpoint - 1), midpoint):
                replay_hashes[n] = digest(book['state'])
            if n == midpoint:
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'book.json'
                    pipeline.save(book, store, path)
                    file_bytes = path.stat().st_size
                    saved_hash = digest(book['state'])
                    book, store = pipeline.load(path)
                    group = pipeline.group_for(book, n)
                    assert digest(book['state']) == saved_hash
                    resume = {'chapter': n, 'json_bytes': file_bytes, 'state_match': True}
            if n % 100 == 0:
                print(json.dumps({'through': n, 'han': book['written_han'],
                                  'seconds': round(time.perf_counter() - started, 2)}), flush=True)
    write_seconds = time.perf_counter() - started
    audit_start = time.perf_counter()
    audit = pipeline.verify_full(book, store)
    audit_seconds = time.perf_counter() - audit_start
    assert audit['ok'], audit
    recovery = []
    for n, expected in replay_hashes.items():
        state, last = delta.rebuild(book, store, through=n)
        recovery.append({'chapter': n, 'applied_to': last, 'match': digest(state) == expected})
    assert all(row['match'] and row['chapter'] == row['applied_to'] for row in recovery)
    assert source_hash == digest({path.name: path.read_text(encoding='utf-8') for path in source_files}), \
        '压测期间引擎源码发生变化，请用最终代码重新运行。'
    return {'workload': 'synthetic mechanics only; random Han filler, not a novel or literary evaluation',
            'engine_source_hash': source_hash,
            'measurement': 'task/2 canonical materialize text; self-contained dispatch with no assumed cache',
            'calls': calls,
            'chapters': chapters, 'volumes': len(book['contract']['volumes']),
            'han_per_chapter': chapter_han, 'written_han': book['written_han'],
            'history_knowledge_entries': len(book['state']['knowledge']),
            'tokenizer': 'cl100k_base (measurement only, not actual model billing)',
            'total_dispatch_bytes': total_payload_bytes, 'samples': observations,
            'write_seconds': round(write_seconds, 3), 'audit_seconds': round(audit_seconds, 3),
            'audit': audit, 'resume': resume, 'recovery': recovery,
            'max_rss_bytes_macos': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chapters', type=int, default=3000)
    parser.add_argument('--chapter-han', type=int, default=3500)
    parser.add_argument('--volume-size', type=int, default=30)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.chapters, args.chapter_han, args.volume_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}, ensure_ascii=False), flush=True)
