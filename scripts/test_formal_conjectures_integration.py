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

"""Source-semantic tests layered above the shared Vela integration check."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

import formal_conjectures_integration as integration
from formal_conjectures_integration import (
    IntegrationError,
    build_selected_export,
    validate_repository,
)
from pr_audit import canonical_bytes


REPO = Path(__file__).resolve().parent.parent


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


class FormalConjecturesIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        _copy_packet(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _source_only(self):
        manifest = tomllib.loads((self.root / "vela.toml").read_text(encoding="utf-8"))
        return patch.object(
            integration,
            "_run_core_check",
            return_value={"manifest_root": manifest["manifest_root"]},
        )

    def assert_source_refused(self, pattern: str) -> None:
        with self._source_only(), self.assertRaisesRegex(IntegrationError, pattern):
            validate_repository(self.root)

    def test_valid_packet_consumes_core_and_closes_source_extensions(self) -> None:
        packet = validate_repository(self.root)
        self.assertEqual(len(packet["profiles"]), 2)
        self.assertEqual(len(packet["bindings"]), 3)
        self.assertEqual(len(packet["methods"]), 5)
        for profile in packet["profiles"].values():
            self.assertEqual(set(profile["source"]), {"owner"})
        all_references = [
            reference
            for binding in packet["bindings"].values()
            for reference in binding["references"]
        ]
        self.assertEqual(len(all_references), 5)
        for binding in packet["bindings"].values():
            self.assertEqual(
                set(binding["source"]),
                {"audit", "rights", "availability", "provenance"},
            )

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

    def test_source_repository_and_profile_owner_drift_refuse(self) -> None:
        _replace(
            self.root / "vela.toml",
            "96eeecf40bc06ddc8bae6d106f461d4fd774858a",
            "86eeecf40bc06ddc8bae6d106f461d4fd774858a",
        )
        self.assert_source_refused(
            "repository identity or source packet revision drift"
        )
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        profile = self.root / ".vela/profiles/audited-declaration-v0.1.toml"
        _replace(profile, "contributor fork", "upstream repository")
        self.assert_source_refused("source owner drift")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        _replace(profile, "[source]", '[source]\nadoption = "upstream"')
        self.assert_source_refused("source has unsupported fields: adoption")

    def test_retained_reference_bytes_and_audit_identity_refuse_drift(self) -> None:
        source = (
            self.root
            / "audit/pr-audit-v1/fixtures/fidelity-erdos-887-1237/inputs/head-source.lean"
        )
        source.write_bytes(source.read_bytes() + b"\n")
        self.assert_source_refused("retained content fixity drift")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        source = (
            self.root
            / "audit/pr-audit-v1/fixtures/fidelity-erdos-887-1237/inputs/head-source.lean"
        )
        target = source.with_name("typed-result-answer-slot-scope.json")
        source.unlink()
        source.symlink_to(target.name)
        self.assert_source_refused("regular non-symlink file")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        binding = self.root / ".vela/bindings/erdos-427-conditional-proof.toml"
        _replace(
            binding,
            "8ff97800e38582c71246a238e7541a9d69488cbd",
            "7ff97800e38582c71246a238e7541a9d69488cbd",
        )
        self.assert_source_refused("linked proof identity drift")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        binding = self.root / ".vela/bindings/erdos-427-conditional-proof.toml"
        _replace(
            binding,
            "Erdos427.erdos_427.variants.shiu",
            "Erdos427.erdos_427.variants.other",
        )
        _replace(
            binding,
            "Erdos427.erdos_427.variants.shiu",
            "Erdos427.erdos_427.variants.other",
        )
        self.assert_source_refused("selector drift from audit scope")

    def test_source_audit_rights_availability_and_provenance_are_closed(self) -> None:
        binding = self.root / ".vela/bindings/erdos-887.toml"
        _replace(binding, "[source.rights]", "[source.rightz]")
        self.assert_source_refused("source is missing fields: rights")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        binding = self.root / ".vela/bindings/erdos-887.toml"
        _replace(binding, 'evidence = "available"', 'evidence = "unavailable"')
        self.assert_source_refused("unavailable evidence cannot become")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        binding = self.root / ".vela/bindings/erdos-887.toml"
        _replace(
            binding,
            'agents = ["codex_ai_packet_preparer", "github_actions"]',
            "agents = []",
        )
        self.assert_source_refused("provenance agents cannot be empty")
        shutil.rmtree(self.root)
        self.root.mkdir()
        _copy_packet(self.root)
        binding = self.root / ".vela/bindings/erdos-887.toml"
        _replace(
            binding,
            'check_ids = ["answer-slot-scope", "exact-head-build"]',
            'check_ids = ["answer-slot-scope"]',
        )
        self.assert_source_refused("audit check inventory drift")


if __name__ == "__main__":
    unittest.main()
