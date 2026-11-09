"""Atomically replace JSON snapshots without exposing a partial save."""
from __future__ import annotations

import json
import os
import tempfile


def save_json(value, path):
    """Keep the previous file intact until a complete, flushed replacement is ready."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
    target = os.path.abspath(os.fspath(path))
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + os.path.basename(target) + '.',
                                             suffix='.tmp', dir=directory)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
