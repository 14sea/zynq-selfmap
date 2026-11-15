"""The tests' own files: made under one root per process, and gone when the process ends (tests/scratch_dirs.py)."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402


class TheTestsLeaveNothingBehind(unittest.TestCase):
    def test_a_directory_made_for_a_test_is_gone_when_the_process_ends(self) -> None:
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import scratch_dirs; from pathlib import Path\n"
                "a, b = Path(scratch_dirs.mkdtemp(prefix='x_')), Path(scratch_dirs.mkdtemp(prefix='x_'))\n"
                "(a / 'f').write_bytes(b'1' * 100); print(a); print(b); assert a != b and a.parent == b.parent")
        for ending in ("", "\nraise SystemExit(3)", "\nraise RuntimeError('a test run that fails')"):
            with self.subTest(ending=ending):
                p = subprocess.run([sys.executable, "-B", "-c", code + ending, str(ROOT / "tests")], capture_output=True, text=True)
                a, b = (Path(line) for line in p.stdout.split())
                self.assertEqual((a.name[:2], a.parent.name[:14]), ("x_", "selfmap_tests_"))
                self.assertFalse(a.exists() or b.exists() or a.parent.exists(), "nothing of it is left")

    def test_no_test_makes_its_directories_anywhere_else(self) -> None:
        for f in sorted((ROOT / "tests").glob("test_*.py")):
            if f.name != Path(__file__).name:
                self.assertNotIn("tempfile.", f.read_text(), f"{f.name}: directories for tests are made with scratch_dirs.mkdtemp")

    def test_here_too_they_are_under_the_one_root(self) -> None:
        d = Path(scratch_dirs.mkdtemp(prefix="smcheck_"))
        self.assertTrue(d.is_dir() and d.parent.name.startswith("selfmap_tests_"))
        self.assertEqual(Path(scratch_dirs.mkdtemp()).parent, d.parent)


if __name__ == "__main__":
    unittest.main()
