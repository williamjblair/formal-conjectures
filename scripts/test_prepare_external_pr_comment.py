from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "prepare_external_pr_comment.py"
FIXTURE = REPO / "audit" / "pr-audit-v1" / "fixtures" / "fork-dogfood-erdos-430-2"
HEAD = "84804da2e04a307be223f7dc067704619ca759c1"
SUMMARY = "<!-- formal-conjectures:advisory-review:v1 -->"
INLINE = "<!-- formal-conjectures:advisory-inline:v1:source-statement-fidelity -->"


class ActionableCommentTest(unittest.TestCase):
    def execute(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], text=True, capture_output=True)

    def rendered(self, mutate=None, phase="in-progress"):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        source = root / "source" / "FormalConjectures" / "ErdosProblems"
        source.mkdir(parents=True)
        shutil.copyfile(FIXTURE / "inputs" / "head-source.lean", source / "430.lean")
        config = json.loads((FIXTURE / "actionable-review.json").read_text())
        if mutate:
            mutate(config)
        config_path = root / "actionable.json"
        config_path.write_text(json.dumps(config))
        args = [
            "render", "--core", str(FIXTURE / "expected-core.json"), "--actionable", str(config_path),
            "--source-root", str(root / "source"), "--summary-output", str(root / "summary.md"),
            "--summary-payload", str(root / "summary.json"), "--inline-output", str(root / "inline.md"),
            "--inline-create-payload", str(root / "inline-create.json"),
            "--inline-update-payload", str(root / "inline-update.json"), "--metadata-output", str(root / "metadata.json"),
            "--expected-head", HEAD, "--run-url", "https://github.com/williamjblair/formal-conjectures/actions/runs/123",
            "--artifact-name", f"advisory-external-pr-2-{HEAD}",
            "--phase", phase,
        ]
        if phase == "complete":
            args.extend(["--runtime-deterministic", str(FIXTURE / "inputs" / "clean-room-deterministic-verification.json")])
        return temporary, root, self.execute(*args)

    def test_renders_concise_summary_and_localized_suggestion(self):
        temporary, root, result = self.rendered()
        with temporary:
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = (root / "summary.md").read_text()
            inline = (root / "inline.md").read_text()
            request = json.loads((root / "inline-create.json").read_text())
            self.assertTrue(summary.startswith(SUMMARY))
            self.assertIn("**Verdict:** `needs_revision` · **Findings:** 1", summary)
            self.assertIn("**Next action:** Guard the existential", summary)
            self.assertIn("**Status:** Review in progress", summary)
            self.assertLess(len(summary), 1000)
            self.assertTrue(inline.startswith(INLINE))
            self.assertIn("```suggestion\n    answer(sorry)", inline)
            self.assertIn("seq n k ≠ 0 ∧ (seq n k).Composite := by", inline)
            self.assertEqual((request["commit_id"], request["path"], request["line"], request["side"]),
                             (HEAD, "FormalConjectures/ErdosProblems/430.lean", 86, "RIGHT"))
            self.assertEqual(json.loads((root / "inline-update.json").read_text()), {"body": inline})

    def test_render_refuses_source_line_drift(self):
        temporary, _, result = self.rendered(lambda value: value["inline_suggestion"].update({"line": 85}))
        with temporary:
            self.assertEqual(result.returncode, 2)
            self.assertIn("does not match", result.stderr)

    def test_complete_summary_projects_typed_lean_outcome(self):
        temporary, root, result = self.rendered(phase="complete")
        with temporary:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("**Lean verification:** `error` at the pinned head.", (root / "summary.md").read_text())

    def select(self, command: str, comments, request=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "comments.json"; source.write_text(json.dumps(comments))
            output = root / "output.json"
            args = [command, "--comments", str(source), "--app-slug", "fc-review-pilot", "--output", str(output)]
            if request is not None:
                request_path = root / "request.json"; request_path.write_text(json.dumps(request))
                args.extend(["--request", str(request_path)])
            result = self.execute(*args)
            return result, json.loads(output.read_text()) if output.exists() else None

    def test_summary_upserts_without_matching_human_comment(self):
        result, value = self.select("select-summary", [[
            {"id": 1, "body": SUMMARY, "user": {"login": "human"}},
            {"id": 2, "body": SUMMARY, "user": {"login": "fc-review-pilot[bot]"}},
        ]])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(value, {"action": "update", "comment_id": 2})

    def test_inline_updates_only_same_head_and_line(self):
        request = {"body": INLINE, "commit_id": HEAD, "path": "FormalConjectures/ErdosProblems/430.lean", "line": 86, "side": "RIGHT"}
        comment = {**request, "id": 7, "user": {"login": "fc-review-pilot[bot]"}}
        result, value = self.select("select-inline", [comment], request)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(value, {"action": "update", "comment_id": 7})
        comment["commit_id"] = "0" * 40
        result, value = self.select("select-inline", [comment], request)
        self.assertEqual(result.returncode, 2)
        self.assertIsNone(value)
        self.assertIn("another head or line", result.stderr)


if __name__ == "__main__":
    unittest.main()
