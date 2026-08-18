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
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "prepare_external_pr_comment.py"
HEAD = "84804da2e04a307be223f7dc067704619ca759c1"
MARKER = "<!-- formal-conjectures:advisory-review:v1 -->"


class ExternalPrCommentTest(unittest.TestCase):

    def run_script(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def draft(self) -> str:
        return f"""## Advisory Formal Conjectures review

Pinned `williamjblair/formal\\-conjectures` PR #2 at `{HEAD}`.

Advisory disposition: **needs\\_revision**

- `source\\-statement\\-fidelity` (source\\-statement\\-fidelity): **fail**
  - The terminal value 0 can witness the existential after the source sequence stops.

This automated report is advisory only. It is not maintainer disposition, acceptance, a merge decision, or a claim of mathematical truth.

## Current workflow replay

Fresh deterministic outcome at the pinned head: **pass**.
"""

    def test_render_requires_and_preserves_publishable_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "draft.md"
            output = root / "comment.md"
            payload = root / "payload.json"
            draft.write_text(self.draft(), encoding="utf-8")
            result = self.run_script(
                "render", "--draft", str(draft), "--output", str(output),
                "--payload-output", str(payload), "--expected-head", HEAD,
                "--run-url", "https://github.com/williamjblair/formal-conjectures/actions/runs/123",
                "--artifact-name", f"advisory-external-pr-2-{HEAD}",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            body = output.read_text(encoding="utf-8")
            self.assertTrue(body.startswith(MARKER))
            self.assertIn(HEAD, body)
            self.assertIn("Advisory disposition: **needs\\_revision**", body)
            self.assertIn("Fresh deterministic outcome at the pinned head: **pass**", body)
            self.assertIn("not maintainer disposition, acceptance", body)
            self.assertIn("[Actions run]", body)
            self.assertEqual(json.loads(payload.read_text(encoding="utf-8")), {"body": body})

    def test_render_rejects_missing_authority_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "draft.md"
            draft.write_text(self.draft().replace("not maintainer disposition", "not a decision"), encoding="utf-8")
            result = self.run_script(
                "render", "--draft", str(draft), "--output", str(root / "comment.md"),
                "--payload-output", str(root / "payload.json"), "--expected-head", HEAD,
                "--run-url", "https://github.com/williamjblair/formal-conjectures/actions/runs/123",
                "--artifact-name", "artifact",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("authority boundary", result.stderr)

    def selection(self, comments: object) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "comments.json"
            output = root / "selection.json"
            source.write_text(json.dumps(comments), encoding="utf-8")
            result = self.run_script(
                "select", "--comments", str(source), "--app-slug", "fc-review-pilot", "--output", str(output),
            )
            return result, json.loads(output.read_text(encoding="utf-8")) if output.exists() else None

    def test_selection_creates_when_no_app_comment_exists(self):
        result, selection = self.selection([
            {"id": 1, "body": MARKER, "user": {"login": "human"}},
            {"id": 2, "body": "ordinary", "user": {"login": "fc-review-pilot[bot]"}},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(selection, {"action": "create", "comment_id": None})

    def test_selection_updates_one_app_comment(self):
        result, selection = self.selection([
            [{"id": 7, "body": f"{MARKER}\nold", "user": {"login": "fc-review-pilot[bot]"}}],
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(selection, {"action": "update", "comment_id": 7})

    def test_selection_refuses_duplicate_app_comments(self):
        result, selection = self.selection([
            {"id": 7, "body": MARKER, "user": {"login": "fc-review-pilot[bot]"}},
            {"id": 8, "body": MARKER, "user": {"login": "fc-review-pilot[bot]"}},
        ])
        self.assertEqual(result.returncode, 2)
        self.assertIsNone(selection)
        self.assertIn("more than one", result.stderr)

    def test_verify_head_refuses_stale_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live.json"
            output = root / "binding.json"
            live.write_text(json.dumps({
                "number": 2,
                "base": {"repo": {"full_name": "williamjblair/formal-conjectures"}},
                "head": {"sha": "0" * 40},
            }), encoding="utf-8")
            result = self.run_script(
                "verify-head", "--live-pr", str(live), "--owner", "williamjblair",
                "--repository", "formal-conjectures", "--pull-request", "2",
                "--expected-head", HEAD, "--output", str(output),
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())
            self.assertIn("refusing stale publication", result.stderr)


if __name__ == "__main__":
    unittest.main()
