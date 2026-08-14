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

"""Offline tests for `lean_to_latex.py`.

Each regression here broke a compiled document before it was fixed, so the
tests assert the repair, not the feature list.
"""

import unittest

from lean_to_latex import (
    docstring_to_tex,
    skeleton,
    split_declarations,
    tokens_to_math,
)


class DocstringTest(unittest.TestCase):

    def test_markdown_italics_become_emph(self):
        # `_On sums of two squarefull numbers_` in 940.lean's references was
        # the first compile failure: a bare `_` is math-only in text mode.
        out = docstring_to_tex("/-- see _On sums_ by Baker -/")
        self.assertIn(r"\emph{On sums}", out)
        self.assertNotIn(" _On", out)

    def test_prose_underscore_is_escaped_but_math_is_not(self):
        out = docstring_to_tex("/-- the a_n term satisfies $a_n \\ge 2$ -/")
        self.assertIn(r"a\_n term", out)
        self.assertIn(r"$a_n \ge 2$", out)

    def test_backticks_become_texttt(self):
        out = docstring_to_tex("/-- uses `Nat.Full` here -/")
        self.assertIn(r"\texttt{Nat.Full}", out)

    def test_bullet_list_is_wrapped(self):
        out = docstring_to_tex("/-!\n- first\n- second\n-/")
        self.assertIn(r"\begin{itemize}", out)
        self.assertIn(r"\end{itemize}", out)


class TokensTest(unittest.TestCase):

    def test_quantifiers_and_types(self):
        out = tokens_to_math("∀ n : ℕ, n ≤ n")
        self.assertIn(r"\forall", out)
        self.assertIn(r"\mathbb{N}", out)

    def test_identifiers_are_upright(self):
        self.assertIn(r"\text{Summable}", tokens_to_math("Summable f"))

    def test_tactic_placeholder_underscore_is_escaped(self):
        # `?_` in a proof step put a bare subscript before the closing `$` and
        # broke 92.tex.
        out = tokens_to_math("(hall x hx).trans ?_")
        self.assertNotIn(" _", out.replace(r"\_", ""))
        self.assertIn(r"\_", out)

    def test_anonymous_constructor_brackets(self):
        out = tokens_to_math("⟨h1, h2⟩")
        self.assertIn(r"\langle", out)
        self.assertIn(r"\rangle", out)

    def test_frequently_differs_from_eventually(self):
        self.assertIn("freq", tokens_to_math("∃ᶠ n in atTop, P n"))
        self.assertIn("ev", tokens_to_math("∀ᶠ n in atTop, P n"))


SAMPLE = """
/-- The main statement. -/
@[category research open, AMS 11]
theorem erdos_42 : answer(sorry) ↔ ∀ n, n ≤ n := by
  sorry

/-- A proved helper. -/
theorem helper (n : ℕ) : n ≤ n + 1 := by
  have h : n ≤ n := le_refl n
  calc n ≤ n := h
    _ ≤ n + 1 := by omega
"""


class SplitTest(unittest.TestCase):

    def test_finds_both_declarations_with_docs_and_attrs(self):
        decls = split_declarations(SAMPLE)
        self.assertEqual([d["name"] for d in decls], ["erdos_42", "helper"])
        self.assertIn("main statement", decls[0]["doc"])
        self.assertIn("category research open", decls[0]["attr"])

    def test_statement_and_proof_are_separated(self):
        decls = split_declarations(SAMPLE)
        self.assertIn("answer(sorry)", decls[0]["statement"])
        self.assertEqual(decls[0]["proof"], "sorry")

    def test_blank_line_inside_docstring_does_not_split(self):
        decls = split_declarations(
            "/-- first paragraph.\n\nsecond paragraph. -/\ntheorem t : True := trivial\n")
        self.assertEqual(len(decls), 1)
        self.assertIn("second paragraph", decls[0]["doc"])


class SkeletonTest(unittest.TestCase):

    def test_have_and_calc_are_steps(self):
        decls = split_declarations(SAMPLE)
        kinds = [k for k, _ in skeleton(decls[1]["proof"])]
        self.assertIn("have", kinds)
        self.assertIn("calc", kinds)

    def test_sorry_has_no_skeleton(self):
        self.assertEqual(skeleton("sorry"), [])


if __name__ == "__main__":
    unittest.main()
