#!/usr/bin/env python3
"""Focused and hostile-mutation tests for the Problem collection profile.

Copyright 2026 The Formal Conjectures Authors.
Licensed under the Apache License, Version 2.0.
"""

from __future__ import annotations

import copy
import json
import unittest
from dataclasses import dataclass
from pathlib import Path

try:
    import jsonschema
except ImportError:  # The builder itself intentionally uses only the standard library.
    jsonschema = None

from scripts.build_problem_collection import (
    INVENTORY_PATH,
    PROFILE_PATH,
    REGISTRY_PATH,
    TreeReader,
    ValidationError,
    build_snapshot,
    canonical_bytes,
    resolve_declaration_route,
    scan_declarations,
    validate_and_expand,
)


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class OverlayReader:
    base: TreeReader
    overlays: dict[str, bytes]

    def read(self, path: str) -> bytes:
        return self.overlays.get(path, self.base.read(path))


class ProblemCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = TreeReader(ROOT)
        self.profile = json.loads(self.reader.read(PROFILE_PATH))
        self.registry = json.loads(self.reader.read(REGISTRY_PATH))

    def validate(self, registry: dict | None = None, profile: dict | None = None, reader=None):
        return validate_and_expand(
            self.reader if reader is None else reader,
            self.profile if profile is None else profile,
            self.registry if registry is None else registry,
        )

    def problem(self, registry: dict, problem_id: str) -> dict:
        return next(item for item in registry["problems"] if item["problem_id"] == problem_id)

    def test_pilot_has_independent_variant_and_part_identities(self) -> None:
        problems, groups, exclusions, routes, _ = self.validate()
        self.assertEqual(7, len(problems))
        self.assertEqual(2, len(groups))
        self.assertTrue(all(len(problem["declarations"]) == 1 for problem in problems))
        self.assertTrue(all(
            declaration["category"] == "research open"
            for problem in problems
            for declaration in problem["declarations"]
        ))
        self.assertTrue(any(group["kind"] == "multipart" for group in groups))
        self.assertTrue(any(group["kind"] == "variant-set" for group in groups))
        self.assertTrue(any(item["reason_code"] == "question_text_rights_unresolved" for item in exclusions))
        self.assertEqual("included", resolve_declaration_route(
            routes, "OeisA103662.conjecture.variants.a_40"
        )["disposition"])

    def test_retained_questions_have_explicit_rights(self) -> None:
        problems, _, _, _, _ = self.validate()
        for problem in problems:
            basis = problem["question"]["retention_basis"]
            self.assertTrue(basis["retained_bytes"])
            self.assertEqual("CC-BY-SA-4.0", basis["license_spdx"])
            self.assertEqual("redistribution-permitted-under-license", basis["retention_permission"])
            self.assertFalse(problem["rights"]["third_party_source"]["retained_bytes"])

    def test_output_is_deterministic_and_authority_free(self) -> None:
        first = canonical_bytes(build_snapshot(self.reader, "0" * 40))
        second = canonical_bytes(build_snapshot(self.reader, "0" * 40))
        self.assertEqual(first, second)
        snapshot = json.loads(first)
        self.assertEqual("none", snapshot["authority_effect"])
        self.assertEqual(
            {"data_root", "profile_root", "registry_root", "snapshot_root", "tracked_input_root"},
            set(snapshot["roots"]),
        )

    @unittest.skipUnless(jsonschema is not None, "jsonschema is not installed")
    def test_generated_snapshot_matches_published_schema(self) -> None:
        snapshot = build_snapshot(self.reader, "0" * 40)
        schema = json.loads((ROOT / "problem-collection/schema/problem-collection-snapshot-v1.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(snapshot)

    def test_duplicate_problem_id_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["problems"][1]["problem_id"] = registry["problems"][0]["problem_id"]
        with self.assertRaisesRegex(ValidationError, "problem_id values must be unique"):
            self.validate(registry)

    def test_source_key_cannot_drift_from_module_path(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["problems"][0]["source_identity"]["source_key"] = "NotOppermann"
        with self.assertRaisesRegex(ValidationError, "source identity does not match"):
            self.validate(registry)

    def test_problem_id_cannot_drift_from_source_identity(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["problems"][0]["problem_id"] = "formal-conjectures:wikipedia:Oppermann:999999"
        with self.assertRaisesRegex(ValidationError, "problem_id does not match"):
            self.validate(registry)

    def test_identity_component_must_come_from_source_declaration(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["problems"][0]["source_identity"]["component"] = "agent-guess"
        registry["problems"][0]["problem_id"] = "formal-conjectures:wikipedia:Oppermann:agent-guess"
        with self.assertRaisesRegex(ValidationError, "component does not match its source declaration"):
            self.validate(registry)

    def test_fc_wikipedia_module_key_is_not_labeled_upstream_identity(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["problems"][0]["upstream_identity"] = {
            "id": "Oppermann",
            "provider": "Wikipedia",
        }
        with self.assertRaisesRegex(ValidationError, "must not label an FC Wikipedia module key"):
            self.validate(registry)

    def test_solved_declaration_cannot_be_included(self) -> None:
        registry = copy.deepcopy(self.registry)
        problem = registry["problems"][0]
        problem["declarations"][0] = {
            "name": "Oppermann.oppermann_conjecture.ferreira_large_x",
            "relationship": "primary",
            "source_path": "FormalConjectures/Wikipedia/Oppermann.lean",
        }
        problem["question_declarations"] = ["Oppermann.oppermann_conjecture.ferreira_large_x"]
        with self.assertRaisesRegex(ValidationError, "included declaration is not research open"):
            self.validate(registry)

    def test_missing_declaration_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["problems"][0]["declarations"][0]["name"] = "Oppermann.not_a_declaration"
        with self.assertRaisesRegex(ValidationError, "listed declaration is absent"):
            self.validate(registry)

    def test_question_without_retention_basis_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        del registry["problems"][0]["rights"]["question_text"]["license_spdx"]
        with self.assertRaisesRegex(ValidationError, "question_text.license_spdx"):
            self.validate(registry)

    def test_question_retention_cannot_be_hidden(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["problems"][0]["rights"]["question_text"]["retained_bytes"] = False
        with self.assertRaisesRegex(ValidationError, "retained question text"):
            self.validate(registry)

    def test_blanket_software_license_for_record_data_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["problems"][0]["rights"]["formal_conjectures_record"]["license_spdx"] = "Apache-2.0"
        with self.assertRaisesRegex(ValidationError, "record data must use"):
            self.validate(registry)

    def test_agent_authored_title_without_source_basis_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["problems"][0]["title"] = "A Catchier Agent Title"
        with self.assertRaisesRegex(ValidationError, "absent from its tracked declaration"):
            self.validate(registry)

    def test_agent_status_guess_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        status = registry["problems"][0]["status_assertion"]
        status["asserted_by"] = "Agent guess"
        status["method"] = "No source checked"
        with self.assertRaisesRegex(ValidationError, "tracked source assertion"):
            self.validate(registry)

    def test_invalid_split_history_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        problem = registry["problems"][0]
        problem["history"].append({
            "date": "2026-08-17",
            "event": "split",
            "from_problem_id": problem["problem_id"],
            "resulting_problem_ids": [problem["problem_id"]],
            "note": "Hostile self-split.",
        })
        with self.assertRaisesRegex(ValidationError, "invalid split history"):
            self.validate(registry)

    def test_group_cannot_erase_a_member_identity(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["groups"][0]["member_problem_ids"].pop()
        with self.assertRaisesRegex(ValidationError, "does not explicitly retain membership|must match exactly|erases that member identity"):
            self.validate(registry)

    def test_group_id_cannot_drift_from_member_source_identity(self) -> None:
        registry = copy.deepcopy(self.registry)
        old_id = registry["groups"][0]["group_id"]
        new_id = "formal-conjectures:group:wikipedia:AgentGuess"
        registry["groups"][0]["group_id"] = new_id
        for problem in registry["problems"]:
            if old_id in problem.get("group_ids", []):
                problem["group_ids"] = [new_id if value == old_id else value for value in problem["group_ids"]]
        with self.assertRaisesRegex(ValidationError, "group_id does not match"):
            self.validate(registry)

    def test_real_machine_inventory_ghost_fails_closed(self) -> None:
        inventory = json.loads(self.reader.read(INVENTORY_PATH))
        inventory["problems"].append({
            "category": "research solved",
            "module": "FormalConjectures.Wikipedia.Oppermann",
            "theorem": "Oppermann.oppermann_conjecture.ferreira_large_x",
        })
        reader = OverlayReader(self.reader, {INVENTORY_PATH: canonical_bytes(inventory)})
        with self.assertRaisesRegex(ValidationError, "ghost=.*ferreira_large_x"):
            self.validate(reader=reader)

    def test_quoted_numeric_namespace_matches_metadata_v2_identity(self) -> None:
        path = "FormalConjectures/Arxiv/2501.03234/ArithmeticSumS.lean"
        theorem = "Arxiv.«2501.03234».conjecture_1_1"
        declarations = scan_declarations(self.reader.read(path), path)
        inventory = json.loads(self.reader.read(INVENTORY_PATH))
        self.assertIn(theorem, declarations)
        self.assertTrue(any(item["theorem"] == theorem for item in inventory["problems"]))

    def test_working_tree_mode_cannot_publish_a_symbolic_commit(self) -> None:
        with self.assertRaisesRegex(ValidationError, "exact 40-character"):
            build_snapshot(self.reader, "HEAD")


if __name__ == "__main__":
    unittest.main()
