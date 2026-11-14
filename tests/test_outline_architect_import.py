import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('architect_import', ROOT / 'scripts/import_outline_architect.py')
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def table(tid, columns, values):
    return '\n### ' + tid + '\n\n| ' + ' | '.join(columns) + ' |\n|' + '|'.join(
        '---' for _ in columns) + '|\n' + ''.join('| ' + ' | '.join(row) + ' |\n' for row in values)


class ArchitectImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='architect-import-')
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / 'outline'
        self.output = Path(self.tmp.name) / 'candidate'
        self.source.mkdir()
        self.names = {did: did + '-样书.md' for did in adapter.DOCS}
        for name in self.names.values():
            (self.source / name).write_text('# 样书\n', encoding='utf-8')
        self.body = table('T-VOL', ['volume_id', '章范围', '卷目标'], [
            ['V01', 'CH0001-CH0002', '查清旧债'], ['V02', 'CH0003-CH0004', '离开城镇']])
        self.body += table('T-UNIT-IDX', ['unit_id', '卷', '章范围'], [
            ['U001', 'V01', 'CH0001-CH0002'], ['U002', 'V02', 'CH0003-CH0004']])
        self.body += table('T-CH', ['章号', 'unit_id', '章目标', '阻碍', '不可逆变化', '伏笔操作'], [
            ['CH0001', 'U001', '寻找账页\\|保留原分隔', '门锁', '拿到钥匙', '—'],
            ['CH0002', 'U001', '取得账页', '守卫', '背下债务', '埋 F001'],
            ['CH0003', 'U002', '离开城镇', '追兵', '通行令被收走', '—']])
        self.write_outline(self.body)

    def rehash(self):
        files = []
        for name in self.names.values():
            raw = (self.source / name).read_bytes()
            files.append({'name': name, 'bytes': len(raw), 'sha256': adapter.sha(
                raw.decode('utf-8-sig').replace('\r\n', '\n').encode())})
        (self.source / '_manifest.json').write_text(json.dumps({'files': files}), encoding='utf-8')

    def write_outline(self, body):
        (self.source / self.names['03']).write_text(body, encoding='utf-8')
        self.rehash()

    def test_native_tables_keep_all_sources_and_partial_volume(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        result = adapter.import_outline_architect(self.source, self.output)
        self.assertEqual(result['chapters'], 3)
        self.assertTrue(result['volumes'][0]['coverage_complete'])
        self.assertFalse(result['volumes'][1]['coverage_complete'])
        self.assertEqual(result['volumes'][1]['missing_range'], [4, 4])
        self.assertFalse(result['engine_installed'])
        self.assertEqual(result['delivery_acceptance'], 'not_verified')
        row = json.loads((self.output / 'volumes/V01_candidate.json').read_text(encoding='utf-8'))['chapters'][0]
        self.assertEqual(row['outline_fields']['章目标'], '寻找账页|保留原分隔')
        self.assertIn('\\|', row['outline_text'])
        self.assertEqual(row['review_status'], 'unreviewed')
        self.assertIn('resource_changes', row['unresolved'])
        self.assertNotIn('resources', row)
        self.assertNotIn('clock', row)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})
        for name, raw in before.items():
            self.assertEqual((self.output / 'source' / name).read_bytes(), raw)
        self.assertEqual(adapter.verify_import(self.output), result)

    def test_bom_crlf_and_audit_are_preserved_byte_for_byte(self):
        path = self.source / self.names['03']
        # setUp 的 write_text 在 Windows 已产生 CRLF；先归一再转，避免 \r\r\n 双重换行。
        normalized = path.read_bytes().replace(b'\r\n', b'\n')
        raw = b'\xef\xbb\xbf' + normalized.replace(b'\n', b'\r\n')
        path.write_bytes(raw)
        audit = self.source / '_audit/T-AUDIT.md'
        audit.parent.mkdir()
        audit.write_text('实际签署回执\n', encoding='utf-8')
        self.rehash()
        adapter.import_outline_architect(self.source, self.output)
        self.assertEqual((self.output / 'source' / path.name).read_bytes(), raw)
        self.assertEqual((self.output / 'source/_audit/T-AUDIT.md').read_bytes(), audit.read_bytes())
        adapter.verify_import(self.output)

    def test_stale_source_fingerprint_cannot_be_rehashed_implicitly(self):
        path = self.source / self.names['02']
        path.write_text('作者刚改了人物事实', encoding='utf-8')
        with self.assertRaises(ValueError):
            adapter.import_outline_architect(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_invalid_structure_never_leaves_candidates(self):
        for body in (self.body.replace('CH0002 |', 'CH0003 |'),
                     self.body.replace('CH0002 |', 'CH0001 |'),
                     self.body.replace('CH0003 | U002', 'CH0003 | U001'),
                     self.body.replace('拿到钥匙', '—'),
                     self.body.replace('CH0003-CH0004', 'CH0004-CH0005'),
                     self.body.replace('CH0001 | U001', 'CH9999 | U001')):
            with self.subTest(body=body[:50]):
                self.write_outline(body)
                with self.assertRaises(ValueError):
                    adapter.import_outline_architect(self.source, self.output)
                self.assertFalse(self.output.exists())

    def test_existing_output_and_overlapping_paths_are_rejected(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            adapter.import_outline_architect(self.source, self.output)
        self.assertEqual(list(self.output.iterdir()), [])
        with self.assertRaises(ValueError):
            adapter.import_outline_architect(self.source, self.source / 'candidate')
        with self.assertRaises(ValueError):
            adapter.import_outline_architect(self.source, self.source.parent)

    def test_explanatory_heading_and_fenced_fake_table_are_not_data(self):
        prefix = '## 字段映射（T-VOL）\n| 名称 | 用途 |\n|---|---|\n| 甲 | 乙 |\n'
        prefix += '```markdown\n' + table('T-VOL', ['假列'], [['假值']]) + '```\n'
        self.write_outline(prefix + self.body)
        adapter.import_outline_architect(self.source, self.output)
        adapter.verify_import(self.output)

    def test_legacy_separator_width_is_allowed_but_extra_data_is_rejected(self):
        # The shipped T-CLAN table historically has one extra separator cell.
        body = self.body.replace('|---|---|---|', '|---|---|---|---|', 1)
        self.write_outline(body)
        adapter.import_outline_architect(self.source, self.output)
        adapter.verify_import(self.output)
        other = Path(self.tmp.name) / 'bad-data'
        self.write_outline(body.replace('拿到钥匙 |', '拿到钥匙 | 额外数据 |'))
        with self.assertRaises(ValueError):
            adapter.import_outline_architect(self.source, other)
        self.assertFalse(other.exists())

    def test_manifest_path_traversal_duplicates_and_wrong_bytes_rejected(self):
        for change in ('traversal', 'duplicate', 'bytes'):
            self.rehash()
            path = self.source / '_manifest.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            if change == 'traversal':
                data['files'][0]['name'] = '../00-样书.md'
            elif change == 'duplicate':
                data['files'][1] = dict(data['files'][0])
            else:
                data['files'][0]['bytes'] += 1
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                adapter.import_outline_architect(self.source, self.output)
            self.assertFalse(self.output.exists())

    def test_source_change_during_import_is_rejected_and_cleaned(self):
        real = adapter.source_snapshot
        calls = 0
        def changing(source):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.source / self.names['00']).write_text('改动', encoding='utf-8')
            return real(source)
        with mock.patch.object(adapter, 'source_snapshot', side_effect=changing):
            with self.assertRaises(ValueError):
                adapter.import_outline_architect(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_derived_index_tampering_fails_even_if_payload_hash_is_rewritten(self):
        adapter.import_outline_architect(self.source, self.output)
        path = self.output / 'volumes/V01_candidate.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['chapters'][0]['outline_fields']['章目标'] = '伪造目标'
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        manifest_path = self.output / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        entry = next(row for row in manifest['files'] if row['name'] == 'volumes/V01_candidate.json')
        entry.update(sha256=adapter.sha(path.read_bytes()), bytes=path.stat().st_size)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            adapter.verify_import(self.output)

    def test_candidate_cannot_self_approve_or_hide_unresolved_fields(self):
        adapter.import_outline_architect(self.source, self.output)
        path = self.output / 'manifest.json'
        original = path.read_bytes()
        for update in ({'engine_installed': True}, {'status': 'ready'}, {'unresolved': []},
                       {'delivery_acceptance': 'passed'}, {'volumes': []}):
            data = json.loads(original)
            data.update(update)
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                adapter.verify_import(self.output)
        path.write_bytes(original)
        adapter.verify_import(self.output)

    def test_duplicate_json_keys_cannot_override_manifest_fields(self):
        path = self.source / '_manifest.json'
        raw = path.read_text(encoding='utf-8')
        path.write_text('{"files": [],' + raw[1:], encoding='utf-8')
        with self.assertRaises(ValueError):
            adapter.import_outline_architect(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_output_failure_cleans_only_new_output_and_keeps_source(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        with mock.patch.object(Path, 'write_bytes', side_effect=OSError('injected write failure')):
            with self.assertRaises(OSError):
                adapter.import_outline_architect(self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})


if __name__ == '__main__':
    unittest.main()
