from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fc_contribution.core import build_packet, canonical_sha256, check_manifest, recommend, sha256_bytes


class GatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def base_manifest(self) -> dict:
        receipt = self.root / "receipt.txt"
        receipt.write_text("passed\n", encoding="utf-8")
        digest = sha256_bytes(receipt.read_bytes())
        return {
            "schema_version": "fc-contribution/v0",
            "authority": {
                "repository": "google-deepmind/formal-conjectures",
                "revision": "abc123",
                "target": "FormalConjectures/Test.lean:test",
            },
            "producer": {"name": "test-agent", "type": "agent"},
            "contribution": {
                "kind": "formal_proof",
                "relationship": "claims_to_resolve",
                "artifact": "Proof.lean",
            },
            "gates": {
                "mechanical_validity": {
                    "status": "pass",
                    "evidence": [{"kind": "lean", "path": "receipt.txt", "sha256": digest}],
                },
                "semantic_fidelity": {"status": "pass", "evidence": [{"kind": "review", "url": "https://x/f"}]},
                "resolution_validity": {"status": "pass", "evidence": [{"kind": "review", "url": "https://x/r"}]},
                "priority": {"status": "pass", "evidence": [{"kind": "search", "url": "https://x/p"}]},
                "provenance": {"status": "pass", "evidence": [{"kind": "git", "url": "https://x/g"}]},
                "dependency_impact": {"status": "unresolved", "evidence": []},
            },
        }

    def test_ready_manifest(self) -> None:
        manifest = self.base_manifest()
        result = check_manifest(manifest, self.root)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(recommend(manifest), "READY_FOR_MAINTAINER_REVIEW")
        packet = build_packet(manifest, self.root)
        self.assertEqual(packet["recommendation"], "READY_FOR_MAINTAINER_REVIEW")
        self.assertEqual(
            packet["evidence"][0]["observed_sha256"],
            manifest["gates"]["mechanical_validity"]["evidence"][0]["sha256"],
        )

    def test_hash_mismatch_fails_closed(self) -> None:
        manifest = self.base_manifest()
        manifest["gates"]["mechanical_validity"]["evidence"][0]["sha256"] = "0" * 64
        result = check_manifest(manifest, self.root)
        self.assertFalse(result.ok)
        self.assertTrue(any("mismatch" in error for error in result.errors))

    def test_semantic_failure_blocks(self) -> None:
        manifest = self.base_manifest()
        manifest["gates"]["semantic_fidelity"]["status"] = "fail"
        self.assertEqual(recommend(manifest), "FIDELITY_FAILED")

    def test_unresolved_priority_is_explicit(self) -> None:
        manifest = self.base_manifest()
        manifest["gates"]["priority"] = {"status": "unresolved", "evidence": []}
        self.assertEqual(recommend(manifest), "PRIORITY_UNRESOLVED")

    def test_canonical_hash_ignores_json_formatting(self) -> None:
        manifest = self.base_manifest()
        decoded = json.loads(json.dumps(manifest, indent=8))
        self.assertEqual(canonical_sha256(manifest), canonical_sha256(decoded))

    def test_packet_hash_stable(self) -> None:
        manifest = self.base_manifest()
        self.assertEqual(
            build_packet(manifest, self.root)["packet_sha256"],
            build_packet(manifest, self.root)["packet_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
