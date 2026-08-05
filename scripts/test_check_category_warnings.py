#!/usr/bin/env python3
"""Tests for `check_category_warnings.py`.

Run with `python3 -m unittest discover -s scripts -p 'test_*.py'`.
No dependencies beyond the standard library.
"""

import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
import unittest.mock

import check_category_warnings as cw


def problem(theorem, category, has_proof, module="FormalConjectures.Example"):
    return {
        "theorem": theorem,
        "module": module,
        "category": category,
        "hasSorryFreeProof": has_proof,
    }


class ClassifyTest(unittest.TestCase):

    def test_each_code(self):
        found = cw.classify([
            problem("A", "research open", True),
            problem("B", "test", False),
            problem("C", "API", False),
        ], "test")
        self.assertEqual({d[0] for d in found}, set(cw.CODES))

    def test_healthy_combinations_are_silent(self):
        found = cw.classify([
            problem("A", "research open", False),
            problem("B", "research solved", True),
            problem("C", "test", True),
            problem("D", "API", True),
            problem("E", "textbook", False),
            problem("F", "textbook", True),
        ], "test")
        self.assertEqual(found, set())

    def test_duplicate_records_collapse(self):
        found = cw.classify([problem("A", "test", False)] * 3, "test")
        self.assertEqual(len(found), 1)

    def test_same_name_in_two_modules_stays_distinct(self):
        found = cw.classify([
            problem("M_two", "test", False, "FormalConjectures.ErdosProblems.«36»"),
            problem("M_two", "test", False, "FormalConjectures.Wikipedia.Dedekind"),
        ], "test")
        self.assertEqual(len(found), 2)

    def test_missing_field(self):
        entry = problem("A", "test", False)
        del entry["hasSorryFreeProof"]
        with self.assertRaisesRegex(cw.DataError, "hasSorryFreeProof"):
            cw.classify([entry], "test")

    def test_wrong_field_type(self):
        entry = problem("A", "test", False)
        entry["hasSorryFreeProof"] = "false"
        with self.assertRaisesRegex(cw.DataError, "hasSorryFreeProof"):
            cw.classify([entry], "test")

    def test_entry_not_an_object(self):
        with self.assertRaisesRegex(cw.DataError, "not an object"):
            cw.classify(["A"], "test")


class ModulePathTest(unittest.TestCase):

    def test_plain(self):
        self.assertEqual(
            cw.module_to_path("FormalConjectures.Wikipedia.ScholzConjecture"),
            "FormalConjectures/Wikipedia/ScholzConjecture.lean")

    def test_quoted_numeral(self):
        self.assertEqual(
            cw.module_to_path("FormalConjectures.ErdosProblems.«36»"),
            "FormalConjectures/ErdosProblems/36.lean")

    def test_dot_inside_quotes_is_not_a_separator(self):
        self.assertEqual(
            cw.module_to_path("FormalConjectures.Arxiv.«1609.08688»"),
            "FormalConjectures/Arxiv/1609.08688.lean")


class DeltaTest(unittest.TestCase):
    """The set arithmetic the run summary reports."""

    def diff(self, head, base):
        return sorted(head - base), sorted(base - head)

    def test_new_resolved_and_unchanged(self):
        base = cw.classify([
            problem("kept", "test", False),
            problem("fixed", "test", False),
        ], "base")
        head = cw.classify([
            problem("kept", "test", False),
            problem("fixed", "test", True),
            problem("added", "API", False),
        ], "head")
        new, resolved = self.diff(head, base)
        self.assertEqual([d[1] for d in new], ["added"])
        self.assertEqual([d[1] for d in resolved], ["fixed"])

    def test_category_change_is_a_new_diagnostic(self):
        base = cw.classify([problem("A", "test", False)], "base")
        head = cw.classify([problem("A", "API", False)], "head")
        new, resolved = self.diff(head, base)
        self.assertEqual([d[0] for d in new], ["api_without_proof"])
        self.assertEqual([d[0] for d in resolved], ["test_without_proof"])

    def test_proof_appearing_resolves(self):
        base = cw.classify([problem("A", "test", False)], "base")
        head = cw.classify([problem("A", "test", True)], "head")
        self.assertEqual(self.diff(head, base), ([], sorted(base)))

    def test_proof_disappearing_is_new(self):
        base = cw.classify([problem("A", "test", True)], "base")
        head = cw.classify([problem("A", "test", False)], "head")
        self.assertEqual(self.diff(head, base), (sorted(head), []))


class SnapshotTest(unittest.TestCase):

    def setUp(self):
        self.dir = pathlib.Path(
            self.enterContext(tempfile.TemporaryDirectory()))

    def test_round_trip(self):
        found = cw.classify([
            problem("B", "test", False),
            problem("A", "API", False),
        ], "test")
        path = self.dir / "snapshot.json"
        cw.write_snapshot(path, "abc123", found)
        self.assertEqual(cw.load_snapshot(path, "abc123"), found)

    def test_output_is_ordered(self):
        names = ["z", "a", "m"]
        found = cw.classify([problem(n, "test", False) for n in names], "test")
        path = self.dir / "snapshot.json"
        cw.write_snapshot(path, "abc123", found)
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([d["theorem"] for d in written["diagnostics"]],
                         sorted(names))

    def test_unicode_names_survive(self):
        name = "Arxiv.«1609.08688».erdős_problem"
        found = cw.classify([problem(name, "test", False)], "test")
        path = self.dir / "snapshot.json"
        cw.write_snapshot(path, "abc123", found)
        self.assertEqual(
            {d[1] for d in cw.load_snapshot(path, "abc123")}, {name})

    def test_sha_mismatch_is_rejected(self):
        path = self.dir / "snapshot.json"
        cw.write_snapshot(path, "abc123", set())
        with self.assertRaisesRegex(cw.DataError, "not 'def456'"):
            cw.load_snapshot(path, "def456")

    def test_wrong_schema_version_is_rejected(self):
        path = self.dir / "snapshot.json"
        path.write_text(json.dumps(
            {"schemaVersion": 99, "sourceSha": "abc123", "diagnostics": []}))
        with self.assertRaisesRegex(cw.DataError, "schemaVersion"):
            cw.load_snapshot(path, "abc123")

    def test_unknown_code_is_rejected(self):
        path = self.dir / "snapshot.json"
        path.write_text(json.dumps({
            "schemaVersion": cw.SCHEMA_VERSION,
            "sourceSha": "abc123",
            "diagnostics": [{"code": "made_up", "theorem": "A", "module": "M"}],
        }))
        with self.assertRaisesRegex(cw.DataError, "unknown code"):
            cw.load_snapshot(path, "abc123")

    def test_malformed_json_is_rejected(self):
        path = self.dir / "snapshot.json"
        path.write_text("{not json")
        with self.assertRaisesRegex(cw.DataError, "not valid JSON"):
            cw.load_snapshot(path, "")


class MainTest(unittest.TestCase):
    """End to end, including exit codes and the run summary."""

    def setUp(self):
        self.dir = pathlib.Path(
            self.enterContext(tempfile.TemporaryDirectory()))
        self.summary = self.dir / "summary.md"
        self.enterContext(unittest.mock.patch.dict(
            os.environ, {"GITHUB_STEP_SUMMARY": str(self.summary)}))

    def extraction(self, problems):
        path = self.dir / "conjectures.json"
        path.write_text(json.dumps({"problems": problems}), encoding="utf-8")
        return str(path)

    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cw.main(argv)
        summary = (self.summary.read_text(encoding="utf-8")
                   if self.summary.exists() else "")
        return code, out.getvalue(), summary

    def test_research_open_with_proof_fails(self):
        path = self.extraction([problem("A", "research open", True)])
        code, out, summary = self.run_main([path])
        self.assertEqual(code, 1)
        self.assertIn("::error file=FormalConjectures/Example.lean", out)
        self.assertIn("**Failing**", summary)

    def test_advisory_only_succeeds(self):
        path = self.extraction([problem("A", "test", False)])
        code, _, summary = self.run_main([path])
        self.assertEqual(code, 0)
        self.assertIn("test_without_proof", summary)

    def test_no_base_requested_reports_totals_without_apology(self):
        path = self.extraction([problem("A", "test", False)])
        code, out, summary = self.run_main([path])
        self.assertEqual(code, 0)
        self.assertNotIn("unavailable", summary)
        self.assertIn("| Diagnostic | Total |", summary)
        self.assertNotIn("::warning file=", out)

    def test_malformed_extraction_fails_loudly(self):
        path = self.dir / "conjectures.json"
        path.write_text("{not json", encoding="utf-8")
        code, out, _ = self.run_main([str(path)])
        self.assertEqual(code, 2)
        self.assertIn("::error::", out)

    def test_missing_problems_list_fails(self):
        path = self.dir / "conjectures.json"
        path.write_text(json.dumps({"moduleDocstrings": {}}), encoding="utf-8")
        code, _, _ = self.run_main([str(path)])
        self.assertEqual(code, 2)

    def test_delta_against_a_base_snapshot(self):
        base = self.dir / "base.json"
        cw.write_snapshot(
            base, "abc123", cw.classify([problem("gone", "test", False)],
                                        "base"))
        path = self.extraction([problem("fresh", "test", False)])
        code, out, summary = self.run_main(
            [path, "--base-snapshot", str(base), "--base-sha", "abc123"])
        self.assertEqual(code, 0)
        self.assertIn("New in this change", summary)
        self.assertIn("Resolved in this change", summary)
        self.assertIn("::warning file=FormalConjectures/Example.lean", out)
        self.assertIn("fresh", out)

    def test_missing_base_snapshot_degrades(self):
        path = self.extraction([problem("A", "test", False)])
        code, out, summary = self.run_main(
            [path, "--base-snapshot", str(self.dir / "absent.json"),
             "--base-sha", "abc1234567"])
        self.assertEqual(code, 0)
        self.assertIn("unavailable", summary)
        self.assertIn("abc1234", summary)
        # Everything on the branch is not "new".
        self.assertNotIn("::warning file=", out)

    def test_mismatched_base_snapshot_degrades_but_says_so(self):
        base = self.dir / "base.json"
        cw.write_snapshot(base, "other", set())
        path = self.extraction([problem("A", "test", False)])
        code, out, summary = self.run_main(
            [path, "--base-snapshot", str(base), "--base-sha", "abc123"])
        self.assertEqual(code, 0)
        self.assertIn("::warning::unusable base snapshot", out)
        self.assertIn("unavailable", summary)

    def test_missing_base_still_fails_on_a_blocking_diagnostic(self):
        path = self.extraction([problem("A", "research open", True)])
        code, _, _ = self.run_main(
            [path, "--base-snapshot", str(self.dir / "absent.json")])
        self.assertEqual(code, 1)

    def test_snapshot_is_written(self):
        path = self.extraction([problem("A", "test", False)])
        snapshot = self.dir / "out.json"
        code, _, _ = self.run_main(
            [path, "--snapshot", str(snapshot), "--source-sha", "deadbeef"])
        self.assertEqual(code, 0)
        written = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(written["sourceSha"], "deadbeef")
        self.assertEqual(len(written["diagnostics"]), 1)


if __name__ == "__main__":
    unittest.main()
