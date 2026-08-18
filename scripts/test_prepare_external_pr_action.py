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

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pr_audit import parse_json_bytes


REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "prepare_external_pr_action.py"
FIXTURE = REPO / "audit" / "pr-audit-v1" / "fixtures" / "external-fork-erdos-430-7"
WORKFLOW = REPO / ".github" / "workflows" / "advisory-external-pr-review.yml"
BASE = "398958d3964d738886bd24433918c365df4a2aab"
HEAD = "075c42c999c0c19224fd116d272637d7868df42a"


class ExternalPrActionTest(unittest.TestCase):

    def bind(self, fixture: Path, live: Path, output: Path, *, head: str = HEAD) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            sys.executable, "-B", str(SCRIPT), "bind",
            "--request", str(fixture / "review-request.json"),
            "--live-pr", str(live),
            "--owner", "Paul-Lez",
            "--repository", "formal-conjectures",
            "--pull-request", "7",
            "--expected-head", HEAD,
            "--checked-out-head", head,
            "--output", str(output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def live_pr(self, path: Path, *, head: str = HEAD) -> None:
        path.write_text(json.dumps({
            "number": 7,
            "html_url": "https://github.com/Paul-Lez/formal-conjectures/pull/7",
            "base": {"sha": BASE},
            "head": {"sha": head},
        }), encoding="utf-8")

    def test_binding_records_exact_read_only_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live.json"
            output = root / "binding.json"
            self.live_pr(live)
            result = self.bind(FIXTURE, live, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            binding = parse_json_bytes(output.read_bytes())
            self.assertEqual(binding["repository"], {"owner": "Paul-Lez", "name": "formal-conjectures"})
            self.assertEqual(binding["head_commit_oid"], HEAD)
            self.assertFalse(binding["stale"])
            self.assertFalse(binding["github_write"])

    def test_live_head_change_is_typed_stale(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live.json"
            output = root / "binding.json"
            self.live_pr(live, head="0" * 40)
            result = self.bind(FIXTURE, live, output)
            self.assertEqual(result.returncode, 3)
            self.assertIn("rerun every role", result.stderr)
            self.assertFalse(output.exists())

    def test_capture_distinguishes_failure_from_invocation_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, fixture)
            command = [
                sys.executable, "-B", str(SCRIPT), "capture",
                "--request", str(fixture / "review-request.json"),
                "--build-target", "FormalConjectures.ErdosProblems.«430»",
                "--build-exit", "1",
                "--style-exit", "127",
            ]
            result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            role = parse_json_bytes((fixture / "inputs" / "clean-room-deterministic-verification.json").read_bytes())
            self.assertEqual(role["outcome"], "error")
            self.assertEqual(role["severity"], "none")
            self.assertIn("typed error, not a review failure", role["findings"][-1])

    def test_runtime_capture_does_not_rewrite_retained_role(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, fixture)
            retained = fixture / "inputs" / "clean-room-deterministic-verification.json"
            before = retained.read_bytes()
            runtime = Path(temporary) / "runtime.json"
            result = subprocess.run([
                sys.executable, "-B", str(SCRIPT), "capture",
                "--request", str(fixture / "review-request.json"),
                "--build-target", "FormalConjectures.ErdosProblems.«430»",
                "--build-exit", "0",
                "--style-exit", "0",
                "--output", str(runtime),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(retained.read_bytes(), before)
            self.assertEqual(parse_json_bytes(runtime.read_bytes())["outcome"], "pass")

    def test_workflow_uses_separate_opt_in_app_publication_job(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        workflow_token_permissions = workflow.split("permissions:", 1)[1].split("concurrency:", 1)[0]
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("pull-requests: read", workflow_token_permissions)
        self.assertIn("checks: write", workflow_token_permissions)
        self.assertNotIn("pull-requests: write", workflow_token_permissions)
        self.assertNotIn("issues: write", workflow_token_permissions)
        self.assertNotIn("gh pr comment", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertIn("publish_comment:", workflow)
        self.assertIn("default: false", workflow)
        self.assertIn("prepare_external_pr_action.py bind", workflow)
        self.assertIn("run_external_pr_review.py", workflow)
        self.assertIn("prepare_external_pr_comment.py render", workflow)
        self.assertIn("prepare_external_pr_comment.py verify-head", workflow)
        self.assertIn("prepare_external_pr_comment.py select-summary", workflow)
        self.assertIn("prepare_external_pr_comment.py select-inline", workflow)
        self.assertIn("actionable_review_path:", workflow)
        self.assertIn("fast-review:", workflow)
        self.assertIn("deterministic:", workflow)
        self.assertIn("publish-fast:", workflow)
        self.assertIn("finalize:", workflow)
        self.assertIn("publish-final:", workflow)
        self.assertIn("needs: fast-review", workflow)
        self.assertIn("needs: [fast-review, deterministic]", workflow)
        self.assertIn("needs: [finalize, publish-fast]", workflow)
        self.assertIn("--phase in-progress", workflow)
        self.assertIn("--phase complete", workflow)
        self.assertIn("FC advisory review", workflow)
        self.assertIn("check-runs", workflow)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", workflow)
        self.assertIn("actions/download-artifact@018cc2cf5baa6db3ef3c5f8a56943fffe632ef53", workflow)
        self.assertIn("actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349", workflow)
        self.assertIn("app-id: ${{ vars.FC_REVIEW_APP_ID }}", workflow)
        self.assertIn("private-key: ${{ secrets.FC_REVIEW_APP_PRIVATE_KEY }}", workflow)
        self.assertIn("permission-pull-requests: write", workflow)
        self.assertIn("steps.app-token.outputs.app-slug", workflow)
        self.assertIn("issues/${PULL_REQUEST}/comments", workflow)
        self.assertIn("pulls/${PULL_REQUEST}/comments", workflow)
        self.assertIn("pulls/comments/${COMMENT_ID}", workflow)


if __name__ == "__main__":
    unittest.main()
