# Copyright 2026 The Formal Conjectures Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the offline halves of `verify_formal_proof.py`.

Nothing here touches the network or a toolchain. The link parser, the static
audit and the axiom-output parser are the parts a regression would corrupt
silently; the clone-and-build stages fail loudly on their own.
"""

import pathlib
import tempfile
import unittest

from verify_formal_proof import (
    parse_axioms,
    resolve,
    static_audit,
    strip_comments,
)


class ResolveTest(unittest.TestCase):

    def test_repo_root(self):
        plan = resolve("https://github.com/kim-em/KnuthClaudeLean")
        self.assertEqual(plan["kind"], "repo")
        self.assertIsNone(plan["ref"])

    def test_blob_keeps_ref_and_file(self):
        plan = resolve("https://github.com/o/r/blob/master/A/B.lean#L5")
        self.assertEqual(plan["ref"], "master")
        self.assertEqual(plan["file"], "A/B.lean")

    def test_commit(self):
        plan = resolve("https://github.com/o/r/commit/9c7f21e7")
        self.assertEqual(plan["ref"], "9c7f21e7")

    def test_pull_request_commit(self):
        plan = resolve("https://github.com/o/r/pull/1894/commits/7a286754")
        self.assertEqual(plan["ref"], "7a286754")

    def test_gist(self):
        plan = resolve("https://gist.github.com/llllvvuu/40d68cfa9de9f43e")
        self.assertEqual(plan["kind"], "gist")

    def test_fragment_is_dropped(self):
        self.assertEqual(resolve("https://github.com/o/r#readme")["kind"], "repo")

    def test_non_github_is_refused(self):
        with self.assertRaises(ValueError):
            resolve("https://example.com/proof.lean")


class StaticAuditTest(unittest.TestCase):

    def audit_of(self, **files):
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in files.items():
                (pathlib.Path(tmp) / name).write_text(text)
            return static_audit(tmp)

    def test_counts_a_sorry(self):
        report = self.audit_of(**{"A.lean": "theorem t : True := by\n  sorry\n"})
        self.assertEqual(report["sorry"], {"A.lean": 1})

    def test_sorry_in_a_comment_does_not_count(self):
        # A repository whose README-style comments discuss being sorry-free must
        # not be reported as carrying one.
        report = self.audit_of(**{"A.lean": "-- no sorry here\n/- sorry -/\n"})
        self.assertEqual(report["sorry"], {})

    def test_sorry_as_identifier_fragment_does_not_count(self):
        report = self.audit_of(**{"A.lean": "def sorryAx_count := 3\n"})
        self.assertEqual(report["sorry"], {})

    def test_axiom_declaration_counts(self):
        report = self.audit_of(**{"A.lean": "axiom bad : False\n"})
        self.assertEqual(report["axiom"], {"A.lean": 1})

    def test_axiom_with_attribute_counts(self):
        report = self.audit_of(**{"A.lean": "@[simp] axiom bad : False\n"})
        self.assertEqual(report["axiom"], {"A.lean": 1})

    def test_native_decide_counts(self):
        report = self.audit_of(**{"A.lean": "theorem t : 2 = 2 := by native_decide\n"})
        self.assertEqual(report["native_decide"], {"A.lean": 1})

    def test_lake_directory_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            hidden = pathlib.Path(tmp) / ".lake" / "packages"
            hidden.mkdir(parents=True)
            (hidden / "Dep.lean").write_text("sorry")
            report = static_audit(tmp)
        self.assertEqual(report["files"], 0)

    def test_nested_block_comments_are_stripped(self):
        # Lean block comments nest, so a `sorry` inside a nested comment is
        # commentary, not a proof hole, and must not be counted.
        stripped = strip_comments("/- a /- b -/ sorry -/ code")
        self.assertNotIn("sorry", stripped)
        self.assertIn("code", stripped)


class ParseAxiomsTest(unittest.TestCase):

    CLEAN = "'Erdos42.witness' depends on axioms: [propext, Classical.choice, Quot.sound]"
    SORRIED = "'Erdos42.main' depends on axioms: [propext, sorryAx, Quot.sound]"
    EXTRA = "'Erdos42.native' depends on axioms: [propext, Lean.ofReduceBool]"
    NONE_AT_ALL = "'Erdos42.pure' does not depend on any axioms"

    def test_standard_axioms_are_sorry_free_with_no_extras(self):
        out = parse_axioms(self.CLEAN, ["Erdos42.witness"])
        self.assertTrue(out["Erdos42.witness"]["sorry_free"])
        self.assertEqual(out["Erdos42.witness"]["extra"], [])

    def test_sorryAx_is_flagged(self):
        out = parse_axioms(self.SORRIED, ["Erdos42.main"])
        self.assertFalse(out["Erdos42.main"]["sorry_free"])

    def test_nonstandard_axiom_is_listed(self):
        out = parse_axioms(self.EXTRA, ["Erdos42.native"])
        self.assertEqual(out["Erdos42.native"]["extra"], ["Lean.ofReduceBool"])

    def test_axiomless_declaration(self):
        out = parse_axioms(self.NONE_AT_ALL, ["Erdos42.pure"])
        self.assertTrue(out["Erdos42.pure"]["sorry_free"])
        self.assertEqual(out["Erdos42.pure"]["axioms"], [])

    def test_short_name_matches_qualified_output(self):
        out = parse_axioms(self.CLEAN, ["witness"])
        self.assertTrue(out["witness"]["sorry_free"])

    def test_missing_output_is_an_error_not_a_pass(self):
        out = parse_axioms("", ["Erdos42.ghost"])
        self.assertIn("error", out["Erdos42.ghost"])


if __name__ == "__main__":
    unittest.main()
