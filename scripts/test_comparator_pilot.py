#!/usr/bin/env python3
"""Offline integrity and authority-boundary tests for the FC-07 packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
PILOT = REPOSITORY / "audit/pr-audit-v1/comparator-pilot"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class ComparatorPilotTest(unittest.TestCase):
    def load(self, path: Path) -> tuple[dict[str, object], bytes]:
        raw = path.read_bytes()
        value = json.loads(raw)
        self.assertEqual(raw, canonical(value) + b"\n")
        return value, raw

    def test_root_and_complete_case_inventory(self) -> None:
        pilot, _ = self.load(PILOT / "pilot.json")
        unrooted = dict(pilot)
        claimed = unrooted.pop("root")
        self.assertEqual(claimed, digest(canonical(unrooted)))
        ids = {case["case_id"] for case in pilot["cases"] + pilot["composed_cases"]}
        self.assertEqual(ids, {
            "clean-unconditional", "conditional-permitted-axiom", "target-mismatch",
            "definition-hole-semantic-gap", "missing-or-ambiguous-target",
        })

    def test_observations_bind_inputs_outputs_and_unsandboxed_boundary(self) -> None:
        pilot, _ = self.load(PILOT / "pilot.json")
        for descriptor in pilot["cases"]:
            path = REPOSITORY / descriptor["observation_path"]
            value, raw = self.load(path)
            self.assertEqual(descriptor["observation_raw_sha256"], digest(raw))
            unrooted = dict(value)
            claimed = unrooted.pop("root")
            self.assertEqual(claimed, digest(canonical(unrooted)))
            self.assertEqual(descriptor["observation_root"], claimed)
            self.assertFalse(value["execution"]["sandboxed"])
            self.assertTrue(value["execution"]["development_fake_landrun"])
            self.assertIn("not_evidence_of_landrun_sandbox_isolation", value["nonclaims"])
            capture = value["execution"]["capture_implementation"]
            capture_bytes = (REPOSITORY / capture["path"]).read_bytes()
            self.assertEqual(capture["size"], len(capture_bytes))
            self.assertEqual(capture["raw_sha256"], digest(capture_bytes))
            for input_descriptor in value["inputs"]:
                data = (REPOSITORY / input_descriptor["path"]).read_bytes()
                self.assertEqual(input_descriptor["size"], len(data))
                self.assertEqual(input_descriptor["raw_sha256"], digest(data))
            self.assertEqual(value["observed"]["stdout_sha256"], digest(value["observed"]["stdout"].encode()))
            self.assertEqual(value["observed"]["stderr_sha256"], digest(value["observed"]["stderr"].encode()))

    def test_composed_unavailable_case_is_exact_and_non_authoritative(self) -> None:
        pilot, _ = self.load(PILOT / "pilot.json")
        case = pilot["composed_cases"][0]
        for prefix in ("core", "observation"):
            value, raw = self.load(REPOSITORY / case[f"{prefix}_path"])
            self.assertEqual(case[f"{prefix}_raw_sha256"], digest(raw))
            self.assertEqual(case[f"{prefix}_root"], value["root"])
        self.assertIn("The packet is not an FC acceptance or merge decision.", pilot["nonclaims"])
        self.assertIn("The packet is not a Vela Verification, Decision, or Standing change.", pilot["nonclaims"])

    def test_public_packet_contains_no_private_paths_or_credentials(self) -> None:
        for path in PILOT.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(errors="ignore")
            self.assertNotIn("/Users/", text)
            self.assertNotIn("/private/tmp/", text)
            self.assertNotIn("ghp_", text)
            self.assertNotIn("github_pat_", text)


if __name__ == "__main__":
    unittest.main()
