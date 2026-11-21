"""The two PL designs and their copies in git — host/stage_designs.py, docs/s2_plan.md, section 24.

Found by review (2026-11-21): build/ is not in git, the tests read both designs from it, and a clean copy of the
repository could run almost none of them. Each design now has a copy in git, a record of its hash that is not that
copy, and one program that puts it where it is looked for.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402
import stage_designs  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TheCopiesInGit(unittest.TestCase):
    def test_each_copy_is_the_file_its_record_names_and_the_file_the_sets_declare(self) -> None:
        carrier, s2a = stage_designs.designs()
        self.assertEqual((carrier["name"], s2a["name"]), ("carrier.bit", "s2a.bit"))
        for d in (carrier, s2a):
            self.assertEqual((sha(d["copy"]), d["copy"].stat().st_size), (d["sha256"], d["bytes"]), d["name"])
        # the carrier: the hash the known frames were read under (zynq-psmap's record), which every set with the carrier declares
        known = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())["pl_design"]
        self.assertEqual((carrier["sha256"], carrier["bytes"]), (known["sha256"], known["bytes"]))
        # s2a: what its build recorded, which the sets of S2.1 and S2.2 declare, and the file that was on the board
        subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
        for stage, d in (("s1b4", carrier), ("s2_0", carrier), ("s2_1", s2a), ("s2_2", s2a)):
            declared = json.loads(s1a_run.STAGES[stage]["expected"].read_text())["pl_design"]
            self.assertEqual((declared["sha256"], declared["bytes"]), (d["sha256"], d["bytes"]), stage)
            self.assertEqual(s1a_run.pl_file({"pl_design": declared}), d["staged"], stage)

    def test_the_copies_are_tracked_and_the_staged_files_are_not(self) -> None:
        asked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", "imported", "evidence/s2_1_17A6_2026-11-20", "build"], capture_output=True, text=True)
        tracked = asked.stdout.split()
        if asked.returncode or not tracked:
            self.skipTest("not a git checkout (an archive, or a copy made for a mutant): nothing to ask")
        self.assertIn("imported/fabricmap/carrier.bit", tracked)
        self.assertIn("evidence/s2_1_17A6_2026-11-20/s2a.bit", tracked)
        self.assertFalse([f for f in tracked if f.startswith("build/")])

    def test_what_is_staged_here_is_what_the_copies_hold(self) -> None:
        stage_designs.stage()
        for d in stage_designs.designs():
            self.assertEqual(d["staged"].read_bytes(), d["copy"].read_bytes(), d["name"])


class TheReadinessStep(unittest.TestCase):
    def test_no_test_class_makes_build_ready_once_for_all_its_tests(self) -> None:
        """The step that makes build/ ready is the image's own tests, run as a command that must succeed. A class that
        runs it in setUpClass loses all its tests when one test of the image fails: the suite then runs fewer tests,
        and the mutant tool, which counts them, calls the mutant one that did not build. One class did (found
        2026-11-21, section 25 of the S2 plan); every mutant that only the image's tests catch was BROKEN for it."""
        import ast
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            tree = ast.parse(path.read_text())
            for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
                for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ("setUpClass", "tearDownClass")):
                    self.assertNotIn("test_prober_image", ast.unparse(fn), f"{path.name}: {cls.name}.{fn.name}")
            for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("setUpModule", "tearDownModule")):
                self.assertNotIn("test_prober_image", ast.unparse(fn), f"{path.name}: {fn.name}")


class Staging(unittest.TestCase):
    """On a made-up tree with the same places and small files."""

    def setUp(self) -> None:
        self.root = Path(scratch_dirs.mkdtemp(prefix="smstage_"))
        self.files = {"carrier.bit": b"the carrier" * 7, "s2a.bit": b"the probe design" * 5}
        (self.root / "imported" / "fabricmap").mkdir(parents=True)
        (self.root / "pl" / "s2a").mkdir(parents=True)
        (self.root / "evidence" / "s2_1_17A6_2026-11-20").mkdir(parents=True)
        (self.root / "imported" / "fabricmap" / "carrier.bit").write_bytes(self.files["carrier.bit"])
        (self.root / "evidence" / "s2_1_17A6_2026-11-20" / "s2a.bit").write_bytes(self.files["s2a.bit"])
        record = lambda data: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}   # noqa: E731
        (self.root / "imported" / "fabricmap" / "IMPORT.json").write_text(json.dumps({"files": {"carrier.bit": record(self.files["carrier.bit"])}}))
        (self.root / "pl" / "s2a" / "build.json").write_text(json.dumps({"bitstream": record(self.files["s2a.bit"])}))
        self.staged = {name: self.root / "build" / "pl" / name for name in self.files}

    def test_what_is_missing_is_staged_and_said(self) -> None:
        done = stage_designs.stage(self.root)
        self.assertEqual({n: p.read_bytes() for n, p in self.staged.items()}, self.files)
        self.assertEqual([line.split(":")[0] for line in done], ["carrier.bit", "s2a.bit"])
        self.assertTrue(all("staged from" in line for line in done), done)
        self.assertTrue(all("already staged, left as it is" in line for line in stage_designs.stage(self.root)))

    def test_a_design_that_is_there_is_left_as_it_is_whatever_it_is(self) -> None:
        self.staged["s2a.bit"].parent.mkdir(parents=True)
        self.staged["s2a.bit"].write_bytes(b"built again since")
        stage_designs.stage(self.root)
        self.assertEqual((self.staged["s2a.bit"].read_bytes(), self.staged["carrier.bit"].read_bytes()), (b"built again since", self.files["carrier.bit"]))

    def test_a_copy_that_is_not_what_its_record_says_is_refused_and_nothing_of_it_is_written(self) -> None:
        copy = self.root / "evidence" / "s2_1_17A6_2026-11-20" / "s2a.bit"
        for name, damage in (("one byte changed", lambda b: b[:3] + bytes([b[3] ^ 1]) + b[4:]), ("one byte more", lambda b: b + b"\0"), ("cut short", lambda b: b[:-1])):
            with self.subTest(name):
                shutil.rmtree(self.root / "build", ignore_errors=True)
                copy.write_bytes(damage(self.files["s2a.bit"]))
                with self.assertRaisesRegex(ValueError, r"s2a\.bit: the copy in git \(evidence/s2_1_17A6_2026-11-20/s2a\.bit\) is not the file pl/s2a/build\.json records"):
                    stage_designs.stage(self.root)
                self.assertFalse(self.staged["s2a.bit"].exists())
        copy.unlink()
        with self.assertRaisesRegex(ValueError, r"s2a\.bit: the copy in git .* is not there"):
            stage_designs.stage(self.root)
        (self.root / "imported" / "fabricmap" / "carrier.bit").write_bytes(b"another carrier")
        shutil.rmtree(self.root / "build", ignore_errors=True)
        with self.assertRaisesRegex(ValueError, r"carrier\.bit: the copy in git \(imported/fabricmap/carrier\.bit\) is not the file imported/fabricmap/IMPORT\.json records"):
            stage_designs.stage(self.root)
        self.assertFalse((self.root / "build").exists())

    def test_the_command(self) -> None:
        p = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "stage_designs.py")], capture_output=True, text=True)
        self.assertEqual((p.returncode, [ln.split(":")[0] for ln in p.stdout.splitlines()]), (0, ["carrier.bit", "s2a.bit"]))


if __name__ == "__main__":
    unittest.main()
