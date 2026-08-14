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

"""Hostile and cold-packet tests for the source-owned Vela integration."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

from formal_conjectures_integration import (
    IntegrationError,
    SCHEMAS,
    build_selected_export,
    document_root,
    validate_repository,
)
from pr_audit import canonical_bytes


REPO = Path(__file__).resolve().parent.parent
ROOT_FIELDS = {kind: f"{kind}_root" for kind in SCHEMAS}


def _copy_packet(destination: Path) -> None:
    shutil.copy2(REPO / "vela.toml", destination / "vela.toml")
    shutil.copytree(REPO / ".vela", destination / ".vela")
    (destination / "scripts").mkdir()
    for name in ("pr_audit.py", "formal_conjectures_integration.py"):
        shutil.copy2(REPO / "scripts" / name, destination / "scripts" / name)
    fixtures = destination / "audit" / "pr-audit-v1" / "fixtures"
    fixtures.parent.mkdir(parents=True)
    shutil.copytree(REPO / "audit" / "pr-audit-v1" / "fixtures", fixtures)


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"mutation target missing from {path}: {old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _reroot(path: Path, kind: str) -> tuple[str, str]:
    root_field = ROOT_FIELDS[kind]
    value = tomllib.loads(path.read_text(encoding="utf-8"))
    old_root = value[root_field]
    new_root = document_root(kind, value)
    text = re.sub(
        rf'(?m)^{root_field} = "sha256:[0-9a-f]{{64}}"$',
        f'{root_field} = "{new_root}"',
        path.read_text(encoding="utf-8"),
        count=1,
    )
    path.write_text(text, encoding="utf-8")
    return old_root, new_root


def _reroot_binding(root: Path, relative: str) -> None:
    old_root, new_root = _reroot(root / relative, "binding")
    _replace(root / "vela.toml", old_root, new_root)
    _reroot(root / "vela.toml", "manifest")


class FormalConjecturesIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        _copy_packet(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_refused(self, pattern: str) -> None:
        with self.assertRaisesRegex(IntegrationError, pattern):
            validate_repository(self.root)

    def test_valid_packet_and_root_domains(self) -> None:
        packet = validate_repository(self.root)
        conditional_references = {
            reference["selector"]["value"]: reference
            for reference in packet["bindings"]["erdos-427-conditional-proof"][
                "references"
            ]
        }
        self.assertEqual(
            conditional_references["erdos427"]["native_identity"]["object_kind"],
            "lean_proof_artifact",
        )
        self.assertEqual(
            conditional_references["erdos427"]["selector"]["value"],
            "erdos427",
        )
        self.assertEqual(
            conditional_references["Erdos427.erdos_427.variants.shiu"]["selector"][
                "value"
            ],
            "Erdos427.erdos_427.variants.shiu",
        )
        all_references = [
            reference
            for binding in packet["bindings"].values()
            for reference in binding["references"]
        ]
        self.assertEqual(len(all_references), 5)
        for reference in all_references:
            self.assertEqual(
                set(reference),
                {
                    "schema",
                    "native_identity",
                    "revision",
                    "content_fixity",
                    "selector",
                    "locator",
                },
            )
        documents = [("manifest", packet["manifest"])]
        documents.extend(("profile", value) for value in packet["profiles"].values())
        documents.extend(("binding", value) for value in packet["bindings"].values())
        documents.extend(("method", value) for value in packet["methods"].values())
        for kind, value in documents:
            normalized = deepcopy(value)
            normalized[ROOT_FIELDS[kind]] = ""
            expected = (
                "sha256:"
                + hashlib.sha256(
                    SCHEMAS[kind].encode("utf-8") + b"\0" + canonical_bytes(normalized)
                ).hexdigest()
            )
            self.assertEqual(value[ROOT_FIELDS[kind]], expected)

    def test_portable_export_keeps_mechanical_semantic_and_review_state_separate(
        self,
    ) -> None:
        first = build_selected_export(self.root)
        second = build_selected_export(self.root)
        self.assertEqual(first, second)
        outcomes = {check["id"]: check["outcome"] for check in first["audit"]["checks"]}
        self.assertEqual(outcomes["exact-head-build"], "pass")
        self.assertEqual(outcomes["answer-slot-scope"], "fail")
        self.assertEqual(first["audit"]["observation_status"]["state"], "MERGED")
        self.assertEqual(
            first["audit"]["observation_status"]["review_decision"], "APPROVED"
        )
        for check in first["audit"]["checks"]:
            self.assertTrue(
                {"responsible_agent", "activity", "entities", "role"} <= check.keys()
            )
            self.assertNotIn("activity", check["responsible_agent"])
        self.assertEqual(first["authority_effect"], "none")
        self.assertNotIn("standing", first)
        normalized = deepcopy(first)
        normalized["export_root"] = ""
        expected = (
            "sha256:"
            + hashlib.sha256(
                first["schema"].encode("utf-8") + b"\0" + canonical_bytes(normalized)
            ).hexdigest()
        )
        self.assertEqual(first["export_root"], expected)

    def test_short_root_and_wrong_root_domain_are_refused(self) -> None:
        _replace(
            self.root / "vela.toml",
            "sha256:9f839593ee5a72c2fba51d0064b2b5c63c32d0a8e1cf9d44d2e62d979ecae3ec",
            "sha256:1234",
        )
        self.assert_refused("full SHA-256 root")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(
            self.root / ".vela/bindings/erdos-887.toml",
            "sha256:8698957b371fb8fbbc7de04c6d5d4e0f0982f39a92798b43fa8a3cbb5f2216d6",
            "sha256:040157f15603d596040d40f95161c7ee14ba08c1bb2787812331e0eedf60051c",
        )
        self.assert_refused("binding_root drift")

    def test_unsupported_schema_and_profile_version_are_refused(self) -> None:
        _replace(
            self.root / "vela.toml", SCHEMAS["manifest"], "vela.integration-manifest.v9"
        )
        self.assert_refused("unsupported manifest schema")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        binding = ".vela/bindings/erdos-887.toml"
        _replace(self.root / binding, 'version = "0.1"', 'version = "9"')
        _reroot_binding(self.root, binding)
        self.assert_refused("unsupported Profile version")

    def test_revision_selector_and_content_drift_are_refused(self) -> None:
        _replace(
            self.root / "vela.toml",
            "96eeecf40bc06ddc8bae6d106f461d4fd774858a",
            "86eeecf40bc06ddc8bae6d106f461d4fd774858a",
        )
        _reroot(self.root / "vela.toml", "manifest")
        self.assert_refused("repository identity or source packet revision drift")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        binding = ".vela/bindings/erdos-887.toml"
        _replace(
            self.root / binding,
            "288608562e684a2f3c97ba0ce960a2649a71370b",
            "188608562e684a2f3c97ba0ce960a2649a71370b",
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("reference revision or native path drift")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(
            self.root / binding,
            'value = "Erdos887.erdos_887"',
            'value = "Erdos887.not_the_declaration"',
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("selector drift")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        source = (
            self.root
            / "audit/pr-audit-v1/fixtures/fidelity-erdos-887-1237/inputs/head-source.lean"
        )
        source.write_bytes(source.read_bytes() + b"\n")
        self.assert_refused("content fixity drift")

    def test_linked_proof_revision_must_match_retained_audit_identity(self) -> None:
        binding = ".vela/bindings/erdos-427-conditional-proof.toml"
        _replace(
            self.root / binding,
            "8ff97800e38582c71246a238e7541a9d69488cbd",
            "7ff97800e38582c71246a238e7541a9d69488cbd",
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("linked proof identity drift")

    def test_in_scope_condition_selector_cannot_drift_from_native_identity(
        self,
    ) -> None:
        binding = ".vela/bindings/erdos-427-conditional-proof.toml"
        _replace(
            self.root / binding,
            'value = "Erdos427.erdos_427.variants.shiu"',
            'value = "Erdos427.erdos_427"',
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("native identifier and selector drift")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(
            self.root / binding,
            'value = "erdos427"',
            'value = "Erdos427.erdos_427"',
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("native identifier and selector drift")

    def test_path_escape_mutable_identity_and_missing_method_are_refused(self) -> None:
        binding = ".vela/bindings/erdos-887.toml"
        _replace(
            self.root / binding,
            'uri = "audit/pr-audit-v1/fixtures/fidelity-erdos-887-1237/inputs/head-source.lean"',
            'uri = "../head-source.lean"',
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("canonical repository-relative path")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(
            self.root / binding,
            "mutable = true",
            "mutable = false",
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("retained locator must be declared mutable")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(
            self.root / binding, 'id = "pr-audit-core-replay"', 'id = "missing-method"'
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("missing or drifted Method")

    def test_flattened_exact_reference_fields_are_refused(self) -> None:
        binding = ".vela/bindings/erdos-887.toml"
        _replace(
            self.root / binding,
            '[[references]]\nschema = "vela.exact-reference.v0.1"',
            '[[references]]\nschema = "vela.exact-reference.v0.1"\nnative_system = "lean4"',
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("unsupported fields: native_system")

    def test_rights_availability_mapping_and_authority_fail_closed(self) -> None:
        binding = ".vela/bindings/erdos-887.toml"
        _replace(self.root / binding, "[rights]", "[rightz]")
        _reroot_binding(self.root, binding)
        self.assert_refused("missing fields: rights")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(self.root / binding, "[availability]", "[availabilitx]")
        _reroot_binding(self.root, binding)
        self.assert_refused("missing fields: availability")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(
            self.root / binding, 'evidence = "available"', 'evidence = "unavailable"'
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("unavailable evidence cannot be converted")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(
            self.root / binding,
            'relation = "exact"',
            'relation = "exact"\ntranslation = "preserved"',
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("mappings has unsupported fields: translation")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(
            self.root / binding,
            'authority_effect = "none"',
            'authority_effect = "none"\nstanding = "accepted"',
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("contains standing")

    def test_build_or_review_result_cannot_be_acceptance(self) -> None:
        binding = ".vela/bindings/erdos-887.toml"
        _replace(
            self.root / binding,
            'authority_effect = "none"',
            'authority_effect = "none"\nacceptance_result = "pass"',
        )
        _reroot_binding(self.root, binding)
        self.assert_refused("contains acceptance_result")


if __name__ == "__main__":
    unittest.main()
