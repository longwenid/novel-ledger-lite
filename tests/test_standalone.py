"""A relocated copy must run with standard-library-only Python and no access to the checkout."""
import json
from pathlib import Path
import shutil
import subprocess
import sys


def test_relocated_skill_runs_without_site_packages_or_original_checkout(tmp_path):
    original = Path(__file__).resolve().parents[1]
    standalone = tmp_path / 'standalone-skill'
    shutil.copytree(original, standalone,
                    ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache'))
    unrelated = tmp_path / 'unrelated'
    unrelated.mkdir()
    # The audit hook blocks reads from the original tree and its parent, including any sibling
    # checkout. Only the relocated copy and the Python runtime remain accessible to the example.
    code = '''
import os, pathlib, runpy, sys
script = pathlib.Path(sys.argv[1])
forbidden = pathlib.Path(sys.argv[2]).resolve()
def audit(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = pathlib.Path(os.fsdecode(args[0])).resolve()
        if path == forbidden or forbidden in path.parents:
            raise PermissionError('Read outside relocated skill: ' + str(path))
sys.addaudithook(audit)
sys.argv = [str(script)]
runpy.run_path(str(script), run_name='__main__')
'''
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code,
                             str(standalone / 'scripts' / 'run_example.py'), str(original.parent)],
                            cwd=unrelated, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['ok'] and report['roundtrip'] and report['matches_book']
    assert report['chapters'] == 4 and report['written_han'] > 0
