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

import pathlib
import tempfile
import unittest

import make_comparator_workspace as mcw
from make_comparator_workspace import (
    declares,
    explicit_binder_names,
    load_manifest,
    resolve,
    hoist_answers,
    locate,
    module_name,
    peel_loose,
    replace_proof_with_sorry,
    slug,
    split_blocks,
    strip_decorations,
)


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

    def test_term_proof_with_a_structure_literal_is_refused(self):
        # The statement's own `:=` cannot be told from the proof's, and
        # cutting at the wrong one truncates the statement.
        with self.assertRaises(SystemExit):
            replace_proof_with_sorry("theorem t : F { a := 1 } := ⟨rfl⟩")

    def test_a_line_comment_between_docstring_and_attribute_is_stripped(self):
        # Erdos 918 writes a `--` formalisation note there. One anchored pass
        # each left `@[category research open]` on the statement, and Lean
        # parsed as far as the `open` inside it.
        out = strip_decorations(
            "/-- doc -/\n-- note\n@[category research open, AMS 5]\n"
            "theorem t : True := by\n  sorry")
        self.assertTrue(out.startswith("theorem"))

    def test_open_in_survives_stripping(self):
        # It binds to the declaration, and it sits above the docstring.
        out = strip_decorations(
            "open scoped Classical in\n/-- doc -/\n@[category research open]\n"
            "theorem t : True := by\n  sorry")
        self.assertTrue(out.startswith("open scoped Classical in\ntheorem"))

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

    def test_section_docstring_does_not_hide_the_namespace(self):
        # A `/-!` section docstring can sit above `namespace` with no blank
        # line. Reading the namespace name off lines[0] crashed on 22 real
        # files; the directive is now its own block.
        blocks = split_blocks("/-! ## A section -/\nnamespace Erdos196\n")
        ns = [b for b in blocks if b.kind == "namespace"]
        self.assertEqual(len(ns), 1)
        self.assertEqual(ns[0].kind_line.split(None, 1)[1].strip(), "Erdos196")

    def test_directive_between_docstring_and_declaration_splits_all_three(self):
        blocks = split_blocks("/-! ## A -/\nnamespace E\ndef y := 1\n")
        self.assertEqual([b.kind for b in blocks], [None, "namespace", "def"])

    def test_open_in_above_a_docstring_stays_with_its_declaration(self):
        # Erdos 184 writes `open scoped Classical in` above the docstring.
        # Splitting at the docstring dropped the modifier, and the statement
        # then failed to synthesize a `Decidable` instance.
        blocks = split_blocks(
            "open scoped Classical in\n/-- doc -/\ntheorem t : True := trivial\n")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].name, "t")
        self.assertIn("open scoped Classical in", blocks[0].text)

    def test_a_docstring_line_starting_with_a_keyword_does_not_split(self):
        blocks = split_blocks("/--\nend of the story\n-/\ndef f := 1\n")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].name, "f")

    def test_category_is_read_off_the_block(self):
        blocks = split_blocks("@[category research open, AMS 5]\ntheorem t : True := trivial\n")
        self.assertEqual(blocks[0].category, "research open")

    def test_namespace_does_not_swallow_the_declaration_below_it(self):
        # Erdos 269 writes `namespace Erdos269` directly above its first
        # definition. Keeping one kind per block dropped `HasPrimeFactorsIn`,
        # and the workspace only failed once Lean elaborated it.
        blocks = split_blocks("namespace Erdos269\ndef HasPrimeFactorsIn : Prop := True\n")
        self.assertEqual([b.kind for b in blocks], ["namespace", "def"])
        self.assertEqual(blocks[1].name, "HasPrimeFactorsIn")

    def test_namespace_does_not_swallow_a_variable(self):
        # The same shape cost Erdos 41 its `variable {α : Type}`.
        blocks = split_blocks("namespace Erdos41\nvariable {a : Type}\n")
        self.assertEqual([b.kind for b in blocks], ["namespace", "variable"])

    def test_section_and_its_end_are_separate_readable_blocks(self):
        # Carried `section` lines need their `end` carried too. Reading the
        # closed name off the block is what lets the namespace's own `end` be
        # dropped while a section's is kept.
        blocks = split_blocks("section N4_D2\ndef a := 1\nend N4_D2\n")
        self.assertEqual([b.kind for b in blocks], ["section", "def", "end"])
        self.assertEqual(blocks[2].kind_line.split(None, 1)[1].strip(), "N4_D2")

    def test_open_in_stays_with_its_declaration(self):
        # `open X in` modifies the declaration below, so peeling it would
        # detach the modifier from what it modifies, and typing the block
        # `open` would carry the declaration into the preamble.
        self.assertEqual(peel_loose(["open Classical in", "theorem t : True := trivial"]),
                         [["open Classical in", "theorem t : True := trivial"]])
        blocks = split_blocks("open Classical in\ntheorem t : True := trivial\n")
        self.assertEqual(blocks[0].kind, "theorem")
        self.assertEqual(blocks[0].name, "t")


class BinderTest(unittest.TestCase):
    """The Solution adapter applies the Submission theorem to these."""

    def test_no_binders(self):
        self.assertEqual(explicit_binder_names("theorem t :\n    True"), [])

    def test_explicit_groups_only(self):
        sig = "theorem t (a b : Nat) {V : Type*} [Fintype V] (h : a < b) : True"
        self.assertEqual(explicit_binder_names(sig), ["a", "b", "h"])

    def test_unascribed_binder_is_its_own_name(self):
        # Erdos 1055 writes `(r)`, leaving the type to Lean.
        self.assertEqual(explicit_binder_names("theorem t (r) : P r"), ["r"])

    def test_open_in_prefix_is_skipped(self):
        sig = "open scoped Classical in\ntheorem t (n : Nat) : P n"
        self.assertEqual(explicit_binder_names(sig), ["n"])

    def test_colon_inside_a_group_does_not_end_the_signature(self):
        sig = "theorem k {I : Ideal R} (hI : IsNil I) :\n  (I : Set R) ⊆ K"
        self.assertEqual(explicit_binder_names(sig), ["hI"])


class LocateTest(unittest.TestCase):
    """Only directives in force at the statement are carried."""

    def test_variable_in_a_closed_section_is_dropped(self):
        blocks = split_blocks("section S\nvariable {n : Nat}\nend S\n\n"
                              "open Nat\n\ntheorem t : True := trivial\n")
        target, _, pre = locate(blocks, "t")
        self.assertEqual(target.name, "t")
        self.assertEqual(pre, ["open Nat"])

    def test_directive_after_the_target_is_dropped(self):
        # It played no part in how the statement's names resolved, and an
        # extra `open` can make a name ambiguous.
        blocks = split_blocks("theorem t : True := trivial\n\nopen Nat\n")
        _, _, pre = locate(blocks, "t")
        self.assertEqual(pre, [])

    def test_directive_in_an_enclosing_namespace_is_kept(self):
        blocks = split_blocks("namespace A\nopen Nat\n"
                              "theorem t : True := trivial\nend A\n")
        _, namespaces, pre = locate(blocks, "t")
        self.assertEqual(namespaces, ["A"])
        self.assertEqual(pre, ["open Nat"])

    def test_anonymous_section_scopes_its_variable(self):
        blocks = split_blocks("section\nvariable {n : Nat}\nend\n\n"
                              "theorem t : True := trivial\n")
        _, _, pre = locate(blocks, "t")
        self.assertEqual(pre, [])

    def test_missing_declaration_raises(self):
        with self.assertRaises(SystemExit):
            locate(split_blocks("def a := 1\n"), "t")


class NameTest(unittest.TestCase):
    """A request may name a declaration in full or drop a leading prefix."""

    def test_qualified_name_matches_itself(self):
        self.assertTrue(declares("erdos_940.variants.large_integers",
                                 "erdos_940.variants.large_integers"))

    def test_any_whole_suffix_matches(self):
        self.assertTrue(declares("erdos_940.variants.large_integers", "variants.large_integers"))
        self.assertTrue(declares("erdos_940.variants.large_integers", "large_integers"))

    def test_a_partial_component_does_not_match(self):
        self.assertFalse(declares("erdos_940.variants.large_integers", "integers"))
        self.assertFalse(declares("erdos_940.variants.large_integers", "erdos_940.variants"))

    def test_module_name_quotes_a_numeric_component(self):
        # Problem files are named for a number, which is not an identifier.
        self.assertEqual(module_name("FormalConjectures/ErdosProblems/940.lean"),
                         "FormalConjectures.ErdosProblems.«940»")
        self.assertEqual(module_name("FormalConjectures/Wikipedia/Hadamard.lean"),
                         "FormalConjectures.Wikipedia.Hadamard")
        self.assertEqual(module_name("FormalConjectures/Arxiv/1609.08688/S.lean"),
                         "FormalConjectures.Arxiv.«1609.08688».S")

    def test_exact_name_wins_over_a_suffix_match(self):
        # One file declares both `foo` and `CH.foo`, so the first is a suffix
        # of the second and asking for it matched both.
        blocks = split_blocks("theorem foo : True := trivial\n\n"
                              "theorem CH.foo : True := trivial\n")
        both = [b for b in blocks if b.name and declares(b.name, "foo")]
        self.assertEqual(len(both), 2)
        self.assertEqual([b.name for b in resolve(both, "foo")], ["foo"])

    def test_a_suffix_request_still_matches_when_there_is_no_exact_name(self):
        blocks = split_blocks("theorem a.b.c : True := trivial\n")
        hits = [b for b in blocks if b.name and declares(b.name, "b.c")]
        self.assertEqual([b.name for b in resolve(hits, "b.c")], ["a.b.c"])

    def test_slug_makes_a_lake_package_name(self):
        # Lake package names are identifiers, so the dots cannot survive.
        self.assertEqual(slug("erdos_940.variants.large_integers"),
                         "erdos_940_variants_large_integers")
        self.assertEqual(slug("dean_conjecture"), "dean_conjecture")


class TemplateTest(unittest.TestCase):

    def test_workspace_test_template_exists_and_is_the_runner(self):
        # The generator copies this file into every workspace; a missing or
        # gutted template would only surface at `lake test` time, elsewhere.
        text = (mcw.COMPARATOR_DIR / "templates" / "WorkspaceTest.lean").read_text()
        self.assertIn("def main", text)
        self.assertIn("COMPARATOR_BIN", text)


class ManifestTest(unittest.TestCase):
    """A manifest supplies what the Lean source cannot."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._saved = mcw.MANIFEST_DIR
        mcw.MANIFEST_DIR = pathlib.Path(self._dir.name)

    def tearDown(self):
        mcw.MANIFEST_DIR = self._saved
        self._dir.cleanup()

    def write(self, name, body):
        (mcw.MANIFEST_DIR / name).write_text(body)

    def test_absent_manifest_is_not_an_error(self):
        # Most statements need none, and the generator works without one.
        self.assertEqual(load_manifest("no_such_problem"), {})

    def test_fields_are_read(self):
        self.write("p.toml", 'id = "p"\ndeclaration = "d"\nanswer_type = "ENNReal"\n')
        self.assertEqual(load_manifest("p")["answer_type"], "ENNReal")

    def test_id_must_match_the_filename(self):
        # The filename is what the generator looks up, so a disagreeing `id`
        # would silently name a workspace directory nobody asked for.
        self.write("p.toml", 'id = "other"\ndeclaration = "d"\n')
        with self.assertRaises(SystemExit):
            load_manifest("p")

    def test_declaration_is_required(self):
        self.write("p.toml", 'id = "p"\n')
        with self.assertRaises(SystemExit):
            load_manifest("p")


if __name__ == "__main__":
    unittest.main()
