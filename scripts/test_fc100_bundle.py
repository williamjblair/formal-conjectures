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

    def test_submission_paths_cannot_escape_the_lean_eval_layout(self) -> None:
        case = copy.deepcopy(self.manifest["cases"][0])
        case["source"]["files"][0]["submission_path"] = "lakefile.toml"
        with self.assertRaisesRegex(fc100_bundle.BundleError, "escapes Submission"):
            fc100_bundle.validate_case(case)


if __name__ == "__main__":
    unittest.main()
