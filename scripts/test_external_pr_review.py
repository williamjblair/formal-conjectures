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

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pr_audit import parse_json_bytes, write_canonical


REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "run_external_pr_review.py"
FIXTURE = REPO / "audit" / "pr-audit-v1" / "fixtures" / "external-fork-erdos-430-7"
HEAD = "075c42c999c0c19224fd116d272637d7868df42a"


class ExternalPrReviewEntrypointTest(unittest.TestCase):

    def command(self, fixture: Path, output: Path, head: str = HEAD) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable, "-B", str(SCRIPT),
                "--request", str(fixture / "review-request.json"),
                "--observed-head", head,
                "--output-dir", str(output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_manual_pinned_review_emits_local_advisory_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "out"
            result = self.command(FIXTURE, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            core = parse_json_bytes((output / "audit-core.json").read_bytes())
            self.assertEqual(core["repository"]["repository"]["owner"], "Paul-Lez")
            self.assertEqual(core["repository"]["head"]["commit_oid"], HEAD)
            self.assertEqual(core["disposition"]["advisory"], "needs_revision")
            report = (output / "ReviewReport.md").read_text()
            comment = (output / "pr-comment-draft.md").read_text()
            self.assertIn("This is advisory evidence, not a merge decision", report)
            self.assertIn("This automated report is advisory only", comment)
            self.assertIn("not maintainer disposition", comment)
            self.assertFalse((output / "github-comment-posted").exists())

    def test_new_head_is_typed_stale_and_emits_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "out"
            result = self.command(FIXTURE, output, "0" * 40)
            self.assertEqual(result.returncode, 3)
            self.assertIn("prepare a new packet and rerun all roles", result.stderr)
            self.assertFalse(output.exists())

    def test_role_result_from_another_head_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, fixture)
            role_path = fixture / "inputs" / "clean-room-source-fidelity.json"
            role = parse_json_bytes(role_path.read_bytes())
            role["exact_input_root"] = "sha256:" + "0" * 64
            write_canonical(role_path, role)
            output = Path(temporary) / "out"
            result = self.command(fixture, output)
            self.assertEqual(result.returncode, 2)
            self.assertIn("stale for the pinned head source", result.stderr)
            self.assertFalse(output.exists())

    def test_publication_mode_cannot_enable_a_github_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, fixture)
            request_path = fixture / "review-request.json"
            request = parse_json_bytes(request_path.read_bytes())
            request["publication"] = {"mode": "post_comment", "github_write": True}
            write_canonical(request_path, request)
            result = self.command(fixture, Path(temporary) / "out")
            self.assertEqual(result.returncode, 2)
            self.assertIn("publication must remain local_draft_only", result.stderr)

    def test_fresh_runtime_replay_is_projected_without_rerooting_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "out"
            runtime = Path(temporary) / "runtime.json"
            retained = parse_json_bytes(
                (FIXTURE / "inputs" / "clean-room-deterministic-verification.json").read_bytes()
            )
            retained["outcome"] = "pass"
            retained["severity"] = "none"
            retained["findings"] = [
                "lake --wfail build FormalConjectures.ErdosProblems.«430»: pass (exit 0).",
                "git diff --check at the pinned base and head: pass (exit 0).",
            ]
            write_canonical(runtime, retained)
            result = subprocess.run([
                sys.executable, "-B", str(SCRIPT),
                "--request", str(FIXTURE / "review-request.json"),
                "--observed-head", HEAD,
                "--output-dir", str(output),
                "--runtime-deterministic", str(runtime),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            core = parse_json_bytes((output / "audit-core.json").read_bytes())
            self.assertEqual(core["root"], parse_json_bytes((FIXTURE / "expected-core.json").read_bytes())["root"])
            report = (output / "ReviewReport.md").read_text()
            self.assertIn("Current workflow replay", report)
            self.assertIn("Fresh deterministic outcome at the pinned head: **pass**", report)
            self.assertIn("does not rewrite the retained core", report)


if __name__ == "__main__":
    unittest.main()
