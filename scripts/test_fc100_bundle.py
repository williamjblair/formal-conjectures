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

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest

import fc100_bundle


class FC100ManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = fc100_bundle.load_manifest()

    def test_three_distinct_capabilities_are_pinned(self) -> None:
        self.assertEqual(
            {case["role"] for case in self.manifest["cases"]},
            {"theorem_proof", "definition_answer", "multi_file_theorem"},
        )
        for case in self.manifest["cases"]:
            self.assertEqual(case["cohort"], "solved")
            self.assertRegex(case["source"]["commit"], r"^[0-9a-f]{40}$")
            self.assertTrue(case["source"]["license"])

    def test_blocked_multifile_case_is_not_rewritten_into_a_green_projection(self) -> None:
        case = next(item for item in self.manifest["cases"] if item["id"] == "erdos-130")
        self.assertEqual(case["projection"]["status"], "blocked")
        self.assertIsNone(case["projection"]["entrypoint_import"])
        self.assertFalse(any("submission_path" in item for item in case["source"]["files"]))

    def test_embargo_requires_a_time_but_has_no_authority_effect(self) -> None:
        case = copy.deepcopy(self.manifest["cases"][0])
        case["disclosure"]["visibility"] = "embargoed"
        with self.assertRaisesRegex(fc100_bundle.BundleError, "embargoed source"):
            fc100_bundle.validate_case(case)
        case["disclosure"]["embargo_until"] = "2026-09-16T00:00:00Z"
        fc100_bundle.validate_case(case)

    def test_open_conjecture_source_must_be_public(self) -> None:
        case = copy.deepcopy(self.manifest["cases"][0])
        case["cohort"] = "open"
        case["disclosure"]["visibility"] = "private"
        with self.assertRaisesRegex(fc100_bundle.BundleError, "must be public"):
            fc100_bundle.validate_case(case)

    def test_embargo_timestamp_is_exact_utc(self) -> None:
        for timestamp in (
            "2026-09-16",
            "2026-09-16 00:00:00Z",
            "2026-09-16T00:00:00+00:00",
        ):
            with self.subTest(timestamp=timestamp):
                case = copy.deepcopy(self.manifest["cases"][0])
                case["disclosure"]["visibility"] = "embargoed"
                case["disclosure"]["embargo_until"] = timestamp
                with self.assertRaisesRegex(fc100_bundle.BundleError, "RFC 3339 UTC"):
                    fc100_bundle.validate_case(case)

    def test_solved_embargo_records_the_future_release_action(self) -> None:
        case = copy.deepcopy(self.manifest["cases"][0])
        case["disclosure"]["visibility"] = "embargoed"
        case["disclosure"]["embargo_until"] = "2026-09-16T00:00:00Z"
        fc100_bundle.validate_case(case)
        projected = fc100_bundle.disclosure_projection(case)
        self.assertTrue(projected["submission_eligible"])
        self.assertEqual(projected["release_action"], "publish_at_embargo_until")
        self.assertEqual(projected["effect_on_comparator_or_acceptance"], "none")

    def test_submission_paths_cannot_escape_the_lean_eval_layout(self) -> None:
        case = copy.deepcopy(self.manifest["cases"][0])
        case["source"]["files"][0]["submission_path"] = "lakefile.toml"
        with self.assertRaisesRegex(fc100_bundle.BundleError, "escapes Submission"):
            fc100_bundle.validate_case(case)


class FC100MaterializationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(
            ["git", "-C", str(self.source), "config", "user.name", "FC100 Test"],
            check=True)
        subprocess.run(
            ["git", "-C", str(self.source), "config", "user.email", "fc100@example.com"],
            check=True)
        source_file = self.source / "Example.lean"
        source_file.write_text("theorem example : True := by trivial\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.source), "add", "Example.lean"], check=True)
        subprocess.run(
            ["git", "-C", str(self.source), "commit", "-q", "-m", "fixture"],
            check=True)

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", "-C", str(self.source), *args], check=True,
                capture_output=True, text=True).stdout.strip()

        raw = source_file.read_bytes()
        self.case = {
            "id": "example",
            "cohort": "solved",
            "role": "theorem_proof",
            "fc_module": "FormalConjectures.Example",
            "fc_declaration": "example",
            "source": {
                "repository": "https://example.com/source.git",
                "commit": git("rev-parse", "HEAD"),
                "license": "Apache-2.0",
                "lean_toolchain": "leanprover/lean4:v4.27.0",
                "files": [{
                    "path": "Example.lean",
                    "git_blob_sha1": git("rev-parse", "HEAD:Example.lean"),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "submission_path": "Submission/Example.lean",
                }],
            },
            "projection": {
                "status": "prepared",
                "entrypoint_import": "Submission.Example",
                "external_declaration": "example",
                "bridge_status": "requires_adapter",
                "gate": "semantic bridge required",
            },
            "disclosure": {
                "visibility": "public",
                "embargo_until": None,
                "release_at": None,
            },
        }
        fc100_bundle.validate_case(self.case)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_exact_source_materializes_a_stage_separated_bundle(self) -> None:
        output = self.root / "bundle"
        evidence = fc100_bundle.materialize(self.case, self.source, output)
        self.assertEqual(
            (output / "source/Example.lean").read_bytes(),
            (output / "Submission/Example.lean").read_bytes())
        self.assertEqual(
            (output / "Submission.lean").read_text(encoding="utf-8").splitlines()[0],
            "import Submission.Example")
        self.assertEqual(evidence["stages"]["source_inspection"], "pass")
        self.assertEqual(evidence["stages"]["comparator"], "not_evaluated")
        self.assertEqual(
            json.loads((output / "bundle.json").read_text(encoding="utf-8")),
            evidence)
        with self.assertRaisesRegex(fc100_bundle.BundleError, "refusing to overwrite"):
            fc100_bundle.materialize(self.case, self.source, output)

    def test_modified_worktree_source_is_rejected_as_drift(self) -> None:
        (self.source / "Example.lean").write_text(
            "theorem example : False := by trivial\n", encoding="utf-8")
        with self.assertRaisesRegex(fc100_bundle.BundleError, "SHA-256 drift"):
            fc100_bundle.materialize(self.case, self.source, self.root / "drifted")


if __name__ == "__main__":
    unittest.main()
