from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SCHEMA = REPO / "schemas" / "review-role-output.schema.json"
SKILL_TEXT = "# Review\n\nCheck source fidelity and boundaries.\n"
AGENTS_TEXT = "# Repository instructions\n\nRun the scoped Lean check.\n"
HEAD = "b" * 40
BASE = "a" * 40
NONCLAIMS = ["maintainer_disposition", "mathematical_truth", "merge_decision"]


def sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class EngineTest(unittest.TestCase):
    def run_cli(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        process_env = os.environ.copy()
        process_env["PYTHONPATH"] = str(SRC)
        if env:
            process_env.update(env)
        return subprocess.run(
            [sys.executable, "-B", "-m", "fc_review_bot", *args],
            text=True,
            capture_output=True,
            env=process_env,
        )

    def packet(self, root: Path) -> tuple[Path, Path, Path, Path, Path]:
        source_root = root / "target"
        target = source_root / "Target" / "Statement.lean"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("import Example\n\ntheorem example (n : Nat) : n = n := by rfl\n", encoding="utf-8")

        config_root = root / "consumer"
        inputs = config_root / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        rubric = inputs / "rubric.txt"
        original = inputs / "original.txt"
        rubric.write_text("Check exact quantifiers, endpoints, and degenerate cases.\n", encoding="utf-8")
        original.write_text("For every natural n, n equals itself.\n", encoding="utf-8")
        config = {
            "schema_version": "formal-conjectures.live-ai-review-config.v1",
            "repository": {
                "owner": "example", "name": "formal-statements",
                "url": "https://github.com/example/formal-statements", "pull_request": 3,
                "base_commit_oid": BASE, "head_commit_oid": HEAD,
            },
            "scope": {
                "path": "Target/Statement.lean", "declaration": "example",
                "head_source_root": sha(target.read_bytes()),
            },
            "sources": [
                {"id": "consumer-rubric", "locator": "consumer policy", "path": "inputs/rubric.txt", "sha256": sha(rubric.read_bytes())},
                {"id": "original", "locator": "immutable source", "path": "inputs/original.txt", "sha256": sha(original.read_bytes())},
            ],
            "nonclaims": NONCLAIMS,
        }
        config_path = config_root / "review-config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        skill = config_root / "SKILL.md"
        agents = config_root / "AGENTS.md"
        skill.write_text(SKILL_TEXT, encoding="utf-8")
        agents.write_text(AGENTS_TEXT, encoding="utf-8")
        live = {
            "number": 3,
            "html_url": "https://github.com/example/formal-statements/pull/3",
            "base": {"sha": BASE},
            "head": {"sha": HEAD},
        }
        live_path = root / "live-pr.json"
        live_path.write_text(json.dumps(live), encoding="utf-8")
        return config_path, live_path, source_root, skill, agents

    def prepare(self, root: Path) -> Path:
        config, live, source, skill, agents = self.packet(root)
        output = root / "prepared"
        result = self.run_cli(
            "prepare", "--config", str(config), "--live-pr", str(live),
            "--source-root", str(source), "--expected-head", HEAD,
            "--skill-path", str(skill), "--agents-path", str(agents), "--output-schema", str(SCHEMA),
            "--output-dir", str(output), "--run-ai-review",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return output

    @staticmethod
    def role(root: str) -> dict[str, object]:
        value = json.loads((REPO / "tests" / "fixtures" / "primary-pass.json").read_text())
        value["exact_input_root"] = root
        return value

    @staticmethod
    def usage() -> dict[str, object]:
        return {
            "schema_version": "formal-conjectures.live-ai-provider-usage.v1",
            "role": "primary_review", "provider": "anthropic", "model": "claude-sonnet-5",
            "configured_cap_usd": "5.00",
            "actual_cost_usd": {"status": "reported", "value": "0.25", "reason": None},
            "turn_count": {"status": "reported", "value": 4, "reason": None},
            "timing": {
                "started_at_epoch_ms": 2000, "finished_at_epoch_ms": 5000, "wall_clock_ms": 3000,
                "provider_duration_ms": {"status": "reported", "value": 2500, "reason": None},
                "api_duration_ms": {"status": "unknown", "value": None, "reason": "unknown/not reported by provider"},
            },
            "tokens": {
                "status": "reported", "input": 100, "output": 20,
                "cache_read_input": 50, "cache_creation_input": 10, "reason": None,
            },
            "cache": {"status": "reported", "read_input_tokens": 50, "creation_input_tokens": 10, "reason": None},
            "retry": {"status": "unknown", "count": None, "reason": "unknown/not reported by provider"},
            "execution_file": {"status": "parsed", "reason": None},
            "nonclaims": NONCLAIMS,
        }

    def panel(self, root: Path) -> tuple[Path, Path, Path, Path]:
        prepared = self.prepare(root)
        manifest = json.loads((prepared / "input-manifest.json").read_text())
        output = root / "panel"
        result = self.run_cli(
            "validate-panel", "--input-manifest", str(prepared / "input-manifest.json"),
            "--output-dir", str(output), "--action-commit", "c" * 40,
            "--model", "claude-sonnet-5", "--effort", "high",
            "--max-budget-usd-per-role", "5.00", "--github-run-id", "123",
            "--github-run-attempt", "1", "--escalation-trigger", "none",
            env={
                "FC_AI_PRIMARY_REVIEW_OUTPUT": json.dumps(self.role(manifest["root"])),
                "FC_AI_PRIMARY_REVIEW_SESSION_ID": "session-primary",
                "FC_AI_PRIMARY_REVIEW_USAGE": json.dumps(self.usage()),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        config, _live, source, _skill, _agents = self.packet(root)
        return output / "ai-review-panel.json", prepared, config, source

    def test_schema_and_fixture(self):
        schema = json.loads(SCHEMA.read_text())
        self.assertNotIn("$schema", schema)
        Draft202012Validator(schema).validate(json.loads((REPO / "tests" / "fixtures" / "primary-pass.json").read_text()))

    def test_prepare_binds_exact_head_and_rejects_stale_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self.prepare(root)
            manifest = json.loads((output / "input-manifest.json").read_text())
            self.assertEqual(manifest["repository"]["head_commit_oid"], HEAD)
            self.assertEqual(manifest["skill_sha256"], sha(SKILL_TEXT.encode()))
            self.assertEqual(manifest["agents_sha256"], sha(AGENTS_TEXT.encode()))
            prompt = (output / "prompt-primary_review.md").read_text()
            self.assertIn("formal-conjectures-review/SKILL.md", prompt)
            self.assertIn("AGENTS.md", prompt)
            self.assertNotIn(SKILL_TEXT.strip(), prompt)
            self.assertNotIn(AGENTS_TEXT.strip(), prompt)
            config, live, source, skill, agents = self.packet(root)
            stale = self.run_cli(
                "prepare", "--config", str(config), "--live-pr", str(live), "--source-root", str(source),
                "--expected-head", "d" * 40, "--skill-path", str(skill), "--agents-path", str(agents),
                "--output-schema", str(SCHEMA), "--output-dir", str(root / "stale"), "--run-ai-review",
            )
            self.assertEqual(stale.returncode, 2)
            self.assertIn("dispatch head differs", stale.stderr)

    def test_publication_requires_actual_ai_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, live, source, skill, agents = self.packet(root)
            result = self.run_cli(
                "prepare", "--config", str(config), "--live-pr", str(live), "--source-root", str(source),
                "--expected-head", HEAD, "--skill-path", str(skill), "--agents-path", str(agents), "--output-schema", str(SCHEMA),
                "--output-dir", str(root / "bad"), "--publish-comment",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("publication requires a real AI review", result.stderr)

    def test_panel_requires_fresh_model_receipt_and_has_no_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepared = self.prepare(root)
            result = self.run_cli(
                "validate-panel", "--input-manifest", str(prepared / "input-manifest.json"),
                "--output-dir", str(root / "panel"), "--action-commit", "c" * 40,
                "--model", "claude-sonnet-5", "--effort", "high", "--max-budget-usd-per-role", "5.00",
                "--github-run-id", "123", "--github-run-attempt", "1",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("no valid model review receipt", result.stderr)

    def test_cost_ledger_and_summary_are_bound_to_panel(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            panel, prepared, config, _source = self.panel(root)
            deterministic = root / "deterministic.json"
            result = self.run_cli(
                "capture-deterministic", "--config", str(config), "--build-target", "Consumer.Target",
                "--lean-exit", "0", "--diff-exit", "0", "--style-exit", "0", "--import-exit", "0",
                "--output", str(deterministic),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            timings = {}
            for phase, start, finish in (("prepare", 1000, 1500), ("deterministic", 1500, 4500), ("finalize", 5000, 5200)):
                path = root / f"{phase}.json"
                result = self.run_cli(
                    "record-phase", "--phase", phase, "--started-at-epoch-ms", str(start),
                    "--finished-at-epoch-ms", str(finish), "--output", str(path),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                timings[phase] = path
            ledger = root / "cost-ledger.json"
            result = self.run_cli(
                "aggregate-cost-ledger", "--panel", str(panel), "--prepare-timing", str(timings["prepare"]),
                "--deterministic-timing", str(timings["deterministic"]), "--finalize-timing", str(timings["finalize"]),
                "--output", str(ledger),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(ledger.read_text())
            self.assertEqual(value["actual_cost_usd"]["value"], "0.25")
            self.assertEqual(value["configured_caps_usd"], {"per_pass": "5.00", "role_limit": 2, "total": "10.00"})

            suggestion = root / "suggestions.json"
            suggestion.write_text(json.dumps({
                "schema_version": "formal-conjectures.live-ai-suggestion-validation.v1",
                "input_panel_root": json.loads(panel.read_text())["root"],
                "outcome": "unavailable", "validated": [], "suppressed": [], "nonclaims": NONCLAIMS,
            }), encoding="utf-8")
            result = self.run_cli(
                "render", "--panel", str(panel), "--deterministic", str(deterministic),
                "--suggestion-validation", str(suggestion), "--cost-ledger", str(ledger), "--phase", "complete",
                "--expected-head", HEAD, "--run-url", "https://github.com/example/actions/runs/123",
                "--artifact-name", "review-3", "--summary", str(root / "summary.md"),
                "--summary-payload", str(root / "summary.json"), "--inline-dir", str(root / "inline"),
                "--metadata", str(root / "metadata.json"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = (root / "summary.md").read_text()
            self.assertIn("<!-- formal-conjectures:live-ai-review:v1 -->", summary)
            self.assertIn("## FC Review Pilot", summary)
            self.assertIn("No high-confidence issue found", summary)

    def test_consumer_owns_import_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _live, source, _skill, _agents = self.packet(root)
            result = self.run_cli(
                "check-imports", "--config", str(config), "--source-root", str(source),
                "--expected-import", "Example", "--output", str(root / "imports.json"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((root / "imports.json").read_text())["outcome"], "pass")

    def test_publication_planner_is_unique_and_head_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            comments = root / "comments.json"
            comments.write_text(json.dumps([{
                "id": 7, "user": {"login": "review-bot[bot]"},
                "body": "<!-- formal-conjectures:live-ai-review:v1 -->\nold",
            }]), encoding="utf-8")
            selection = root / "selection.json"
            result = self.run_cli(
                "select-summary", "--comments", str(comments), "--app-slug", "review-bot", "--output", str(selection),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(selection.read_text()), {"action": "update", "comment_id": 7})

            request = root / "inline.json"
            request.write_text(json.dumps({
                "body": "<!-- formal-conjectures:live-ai-inline:v1:edge-case -->\nbody",
                "commit_id": HEAD, "path": "Target/Statement.lean", "line": 3, "side": "RIGHT",
            }), encoding="utf-8")
            inline_comments = root / "inline-comments.json"
            inline_comments.write_text(json.dumps([{
                "id": 9, "user": {"login": "review-bot[bot]"},
                "body": "<!-- formal-conjectures:live-ai-inline:v1:edge-case -->\nold",
                "commit_id": "d" * 40, "path": "Target/Statement.lean", "line": 3, "side": "RIGHT",
            }]), encoding="utf-8")
            result = self.run_cli(
                "select-inline", "--comments", str(inline_comments), "--request", str(request),
                "--app-slug", "review-bot", "--output", str(root / "inline-selection.json"),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("bound to another head", result.stderr)


if __name__ == "__main__":
    unittest.main()
