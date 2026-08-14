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

"""Offline tests for `make_comparator_workspace.py`.

Every case here pins a failure the first real workspace build produced, or a
rule whose violation would generate a workspace that builds but poses the
wrong problem. The build itself is the comparator's job, not these tests'.
"""

import unittest

from make_comparator_workspace import (
    drop_problem_attributes,
    hoist_answers,
    replace_proof_with_sorry,
    split_blocks,
    strip_decorations,
)


class AttributeTest(unittest.TestCase):
    """ChallengeDeps imports the module without the problem attributes."""

    def test_category_and_ams_only_leaves_bare_declaration(self):
        out = drop_problem_attributes("@[category test, AMS 5]\ntheorem t : True := trivial")
        self.assertTrue(out.startswith("theorem"))

    def test_real_lean_attributes_survive(self):
        out = drop_problem_attributes("@[simp, category API, AMS 11]\ntheorem t : True := trivial")
        self.assertIn("@[simp]", out)
        self.assertNotIn("category", out)
        self.assertNotIn("AMS", out)

    def test_untouched_when_there_is_nothing_to_prune(self):
        src = "@[simp, ext]\ntheorem t : True := trivial"
        self.assertEqual(drop_problem_attributes(src), src)


class HoistTest(unittest.TestCase):
    """The answer slot becomes a hole the solver must fill."""

    def test_iff_slot_is_a_prop(self):
        stmt, holes = hoist_answers(
            "theorem t : answer(sorry) ↔ ∀ n, n ≤ n := by\n  sorry", "t", None)
        self.assertIn("t_answer", stmt)
        self.assertIn("noncomputable def t_answer : Prop := sorry", holes)

    def test_non_iff_slot_without_a_type_is_refused(self):
        # Guessing here would generate a workspace posing a different problem.
        with self.assertRaises(SystemExit):
            hoist_answers("theorem t : sSup S = answer(sorry) := by\n  sorry", "t", None)

    def test_non_iff_slot_uses_the_supplied_type(self):
        stmt, holes = hoist_answers(
            "theorem t : sSup S = answer(sorry) := by\n  sorry", "t", "ℝ")
        self.assertIn("t_answer : ℝ", holes[0])
        self.assertNotIn("answer(sorry)", stmt)

    def test_two_slots_get_distinct_names(self):
        _, holes = hoist_answers(
            "theorem t : answer(sorry) ↔ answer(sorry) := by\n  sorry", "t", None)
        self.assertEqual(len(holes), 2)
        self.assertIn("t_answer_1", holes[0])
        self.assertIn("t_answer_2", holes[1])

    def test_no_slot_is_left_alone(self):
        stmt, holes = hoist_answers("theorem t : True := by\n  sorry", "t", None)
        self.assertEqual(holes, [])


class StatementTest(unittest.TestCase):

    def test_proof_is_replaced_but_statement_kept(self):
        out = replace_proof_with_sorry(
            "theorem t : True := by\n  have h := trivial\n  exact h")
        self.assertIn("theorem t : True", out)
        self.assertNotIn("have h", out)
        self.assertTrue(out.rstrip().endswith("sorry"))

    def test_term_mode_proof_is_replaced_too(self):
        out = replace_proof_with_sorry("theorem t : True := trivial")
        self.assertNotIn("trivial", out)
        self.assertTrue(out.rstrip().endswith("sorry"))

    def test_decorations_are_stripped_from_the_target(self):
        out = strip_decorations("/-- doc -/\n@[category research open]\ntheorem t : True := by\n  sorry")
        self.assertTrue(out.startswith("theorem"))


class SplitTest(unittest.TestCase):

    def test_blank_line_inside_a_docstring_does_not_split(self):
        # A docstring paragraph break would otherwise orphan the declaration
        # from its documentation and lose the attribute line with it.
        blocks = split_blocks("/-- first.\n\nsecond. -/\ntheorem t : True := trivial\n")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].name, "t")

    def test_declarations_separate_on_blank_lines(self):
        blocks = split_blocks("def a := 1\n\ndef b := 2\n")
        self.assertEqual([b.name for b in blocks], ["a", "b"])

    def test_kind_line_is_the_matching_line_not_the_first(self):
        # A `/-!` section docstring can sit above `namespace` in one block.
        # Reading the namespace name off lines[0] crashed on 22 real files.
        blocks = split_blocks("/-! ## A section -/\nnamespace Erdos196\n")
        self.assertEqual(blocks[0].kind, "namespace")
        self.assertEqual(blocks[0].kind_line.split(None, 1)[1].strip(), "Erdos196")

    def test_category_is_read_off_the_block(self):
        blocks = split_blocks("@[category research open, AMS 5]\ntheorem t : True := trivial\n")
        self.assertEqual(blocks[0].category, "research open")


if __name__ == "__main__":
    unittest.main()
