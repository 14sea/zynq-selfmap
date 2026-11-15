"""Where the tests keep their files while they run: one directory per process, removed when the process ends.

Every twin run, pretended board and chain of the tests leaves its files in a directory of its own. They used to be
made with tempfile.mkdtemp and never removed — about 160 MB a run of the suite, and a complete run of the mutants is
some 330 runs of the suite: on 2026-11-15 that filled the disk. The directories are made here instead, all under one
root that goes when the process does.
"""
from __future__ import annotations

import atexit
import shutil
import tempfile

_root: str | None = None


def mkdtemp(prefix: str = "") -> str:
    global _root
    if _root is None:
        _root = tempfile.mkdtemp(prefix="selfmap_tests_")
        atexit.register(shutil.rmtree, _root, ignore_errors=True)
    return tempfile.mkdtemp(prefix=prefix, dir=_root)
