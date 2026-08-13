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

"""Tests for the text handling in `comparator_workspace.py`.

These cover the parts that get a statement wrong quietly. Compiling the result is what `--check`
is for, and it needs a Lean toolchain, so it is not tested here.
"""

import unittest

from comparator_workspace import (
    answer_type,
    find_answer,
    split_at_declaration,
    statement_of,
)

FILE = '''import FormalConjecturesUtil

namespace Erdos1

/-- A definition the statement needs. -/
def helper (n : ℕ) : ℕ := n + 1

/--
The problem, with a docstring that mentions `-/` nowhere in particular.
-/
@[category research open, AMS 11]
theorem erdos_1 : answer(sorry) ↔ ∀ n, helper n = n + 1 := by
  sorry

/-- Something after it. -/
@[category test, AMS 11]
theorem erdos_1.variants.after : True := by
  trivial

end Erdos1
'''


class SplitTest(unittest.TestCase):

    def test_dependencies_stop_before_the_docstring(self):
        before, _ = split_at_declaration(FILE, "erdos_1")
        self.assertIn("def helper", before)
        self.assertNotIn("The problem, with a docstring", before)

    def test_declaration_carries_its_docstring_and_attributes(self):
        _, declaration = split_at_declaration(FILE, "erdos_1")
        self.assertIn("The problem, with a docstring", declaration)
        self.assertIn("@[category research open, AMS 11]", declaration)
        self.assertIn("theorem erdos_1", declaration)

    def test_declaration_stops_before_the_next_one(self):
        _, declaration = split_at_declaration(FILE, "erdos_1")
        self.assertNotIn("variants.after", declaration)
        self.assertNotIn("Something after it", declaration)

    def test_a_later_declaration_also_splits(self):
        before, declaration = split_at_declaration(FILE, "erdos_1.variants.after")
        self.assertIn("theorem erdos_1 ", before)
        self.assertIn("Something after it", declaration)


class StatementTest(unittest.TestCase):

    def test_drops_the_docstring_attributes_and_proof(self):
        _, declaration = split_at_declaration(FILE, "erdos_1")
        statement = statement_of(declaration)
        self.assertTrue(statement.startswith("theorem erdos_1"))
        self.assertNotIn("@[", statement)
        self.assertNotIn(":= by", statement)
        self.assertNotIn("The problem", statement)

    def test_keeps_the_answer_marker(self):
        # `answer(sorry)` is the marker for the unknown, and not the proof. Stripping the proof
        # must not take it with it.
        _, declaration = split_at_declaration(FILE, "erdos_1")
        self.assertIn("answer(sorry)", statement_of(declaration))


class AnswerTest(unittest.TestCase):

    def test_finds_the_span_and_the_contents(self):
        start, end, contents = find_answer("theorem t : answer(sorry) ↔ P")
        self.assertEqual(contents, "sorry")
        self.assertEqual("theorem t : ", "theorem t : answer(sorry) ↔ P"[:start])
        self.assertEqual(" ↔ P", "theorem t : answer(sorry) ↔ P"[end:])

    def test_matches_parentheses_inside_the_answer(self):
        _, _, contents = find_answer("theorem t : answer(f (g x) (h y)) = 3")
        self.assertEqual(contents, "f (g x) (h y)")

    def test_no_answer_gives_none(self):
        self.assertIsNone(find_answer("theorem t : P ↔ Q"))

    def test_an_iff_makes_the_answer_a_prop(self):
        statement = "theorem t : answer(sorry) ↔ P"
        self.assertEqual(answer_type(statement, find_answer(statement)), "Prop")

    def test_an_ascription_gives_the_type(self):
        statement = "theorem t : answer(sorry : ℕ → ℝ) = f"
        self.assertEqual(answer_type(statement, find_answer(statement)), "ℕ → ℝ")

    def test_an_ascription_is_not_confused_by_inner_colons(self):
        statement = "theorem t : answer(sorry : Set (Σ n : ℕ, Fin n)) = s"
        self.assertEqual(answer_type(statement, find_answer(statement)),
                         "Set (Σ n : ℕ, Fin n)")


if __name__ == "__main__":
    unittest.main()
