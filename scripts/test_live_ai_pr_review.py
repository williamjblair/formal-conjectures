from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "live_ai_pr_review.py"
FIXTURE = REPO / "audit" / "pr-audit-v1" / "fixtures" / "fork-dogfood-erdos-430-2"
CONFIG = FIXTURE / "live-ai-review-config.json"
PROMPT = REPO / ".agents" / "prompts" / "live-ai-review-role.md"
SCHEMA = REPO / ".agents" / "schemas" / "live-ai-review-role-output.schema.json"
HEAD = "84804da2e04a307be223f7dc067704619ca759c1"
SUMMARY = "<!-- formal-conjectures:live-ai-review:v1 -->"


class LiveAIReviewTest(unittest.TestCase):
    def execute(self, *args: str, env=None) -> subprocess.CompletedProcess[str]:
        process_env = os.environ.copy()
        process_env["PYTHONPATH"] = str(REPO / "scripts")
        if env:
            process_env.update(env)
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], text=True, capture_output=True, env=process_env,
        )

    def prepare(self, root: Path):
        source = root / "source" / "FormalConjectures" / "ErdosProblems"
        source.mkdir(parents=True)
        shutil.copyfile(FIXTURE / "inputs" / "head-source.lean", source / "430.lean")
        config = json.loads(CONFIG.read_text())
        live = {
            "number": 2,
            "html_url": "https://github.com/williamjblair/formal-conjectures/pull/2",
            "base": {"sha": config["repository"]["base_commit_oid"]},
            "head": {"sha": HEAD},
        }
        live_path = root / "live.json"
        live_path.write_text(json.dumps(live))
        output = root / "input"
        result = self.execute(
            "prepare", "--config", str(CONFIG), "--live-pr", str(live_path), "--source-root", str(root / "source"),
            "--expected-head", HEAD, "--prompt-template", str(PROMPT), "--output-schema", str(SCHEMA),
            "--output-dir", str(output), "--run-ai-review",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return source / "430.lean", output

    def role(self, role: str, root: str, findings=None, outcome="pass", severity="none"):
        return {
            "schema_version": "formal-conjectures.live-ai-review-role-result.v1",
            "role": role,
            "authority": "advisory_model_review_only",
            "independent": True,
            "exact_input_root": root,
            "outcome": outcome,
            "severity": severity,
            "findings": findings or [{
                "id": "no-localized-finding", "summary": "No localized issue identified.",
                "explanation": "This role found no independently actionable localized issue.",
                "severity": "none", "path": None, "line": None,
                "witnesses": ["Reviewed the exact retained input."], "suggestion": None,
            }],
            "limitations": ["Advisory model review does not establish acceptance."],
            "nonclaims": ["maintainer_disposition", "mathematical_truth", "merge_decision"],
        }

    def test_action_facing_schema_omits_unsupported_meta_schema_declaration(self):
        schema = json.loads(SCHEMA.read_text())
        self.assertNotIn("$schema", schema)
        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["required"],
            [
                "schema_version", "role", "authority", "independent", "exact_input_root",
                "outcome", "severity", "findings", "limitations", "nonclaims",
            ],
        )

    def panel(self, root: Path, two_suggestions=True):
        _, input_dir = self.prepare(root)
        manifest = json.loads((input_dir / "input-manifest.json").read_text())
        source_lines = (FIXTURE / "inputs" / "head-source.lean").read_text().splitlines()
        line = 86
        original = source_lines[line - 1]
        suggestion = {
            "confidence": "high", "path": "FormalConjectures/ErdosProblems/430.lean", "line": line,
            "original": original,
            "replacement": "    answer(sorry)\n    ∀ k, seq n k ≠ 0 → ¬(seq n k).Composite := by",
            "explanation": "Guard the absorbing sentinel before testing compositeness.",
        }
        finding = {
            "id": "sentinel-zero", "summary": "Guard the zero sentinel.",
            "explanation": "Composite zero can witness the existential after termination.",
            "severity": "meaning", "path": suggestion["path"], "line": line,
            "witnesses": ["The recursion retains zero after termination."], "suggestion": suggestion,
        }
        roles = {
            role: self.role(role, manifest["root"], [finding] if (role == "lean_semantics" or two_suggestions and role == "adversarial_edge_cases") else None,
                            "fail" if (role == "lean_semantics" or two_suggestions and role == "adversarial_edge_cases") else "pass",
                            "meaning" if (role == "lean_semantics" or two_suggestions and role == "adversarial_edge_cases") else "none")
            for role in ("source_fidelity", "lean_semantics", "adversarial_edge_cases")
        }
        output = root / "panel"
        env = {f"FC_AI_{role.upper()}_OUTPUT": json.dumps(value) for role, value in roles.items()}
        env.update({f"FC_AI_{role.upper()}_SESSION_ID": f"session-{role}" for role in roles})
        result = self.execute(
            "validate-panel", "--input-manifest", str(input_dir / "input-manifest.json"), "--output-dir", str(output),
            "--action-commit", "d40ddef4c030e508327d6e35a9c45f3368482c50",
            "--model", "claude-sonnet-5", "--effort", "high", "--max-budget-usd-per-role", "5.00",
            "--github-run-id", "123", "--github-run-attempt", "1", env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return output / "ai-review-panel.json"

    def test_prepare_binds_head_and_rejects_publication_without_model_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, output = self.prepare(root)
            manifest = json.loads((output / "input-manifest.json").read_text())
            self.assertEqual(manifest["repository"]["head_commit_oid"], HEAD)
            self.assertEqual(set(path.name for path in output.glob("prompt-*.md")), {
                "prompt-source_fidelity.md", "prompt-lean_semantics.md", "prompt-adversarial_edge_cases.md",
            })
            result = self.execute(
                "prepare", "--config", str(CONFIG), "--live-pr", str(root / "live.json"),
                "--source-root", str(root / "source"), "--expected-head", HEAD,
                "--prompt-template", str(PROMPT), "--output-schema", str(SCHEMA),
                "--output-dir", str(root / "bad"), "--publish-comment",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("requires a real AI review", result.stderr)

    def test_validate_panel_requires_three_actual_model_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, input_dir = self.prepare(root)
            result = self.execute(
                "validate-panel", "--input-manifest", str(input_dir / "input-manifest.json"),
                "--output-dir", str(root / "panel"), "--action-commit", "d40ddef4c030e508327d6e35a9c45f3368482c50",
                "--model", "claude-sonnet-5", "--effort", "high", "--max-budget-usd-per-role", "5.00",
                "--github-run-id", "123", "--github-run-attempt", "1",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("stored role evidence is not a fallback", result.stderr)

    def test_validate_panel_requires_and_retains_claude_session_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, input_dir = self.prepare(root)
            manifest = json.loads((input_dir / "input-manifest.json").read_text())
            roles = ("source_fidelity", "lean_semantics", "adversarial_edge_cases")
            env = {
                f"FC_AI_{role.upper()}_OUTPUT": json.dumps(self.role(role, manifest["root"]))
                for role in roles
            }
            env.update({f"FC_AI_{role.upper()}_SESSION_ID": f"session-{role}" for role in roles[:-1]})
            output = root / "panel"
            args = (
                "validate-panel", "--input-manifest", str(input_dir / "input-manifest.json"),
                "--output-dir", str(output), "--action-commit", "d40ddef4c030e508327d6e35a9c45f3368482c50",
                "--model", "claude-sonnet-5", "--effort", "high", "--max-budget-usd-per-role", "5.00", "--github-run-id", "123",
                "--github-run-attempt", "1",
            )
            result = self.execute(*args, env=env)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Claude session receipt is missing", result.stderr)
            env["FC_AI_ADVERSARIAL_EDGE_CASES_SESSION_ID"] = "session-adversarial"
            result = self.execute(*args, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            panel = json.loads((output / "ai-review-panel.json").read_text())
            self.assertEqual(panel["execution"]["provider"], "anthropic")
            self.assertEqual(panel["execution"]["runner"], "claude-code-action")
            self.assertEqual(set(panel["execution"]["role_receipts"]), set(roles))

    def test_multiple_suggestions_are_validated_and_rendered_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            panel = self.panel(root)
            source = root / "source"
            prepared = root / "prepared.json"
            result = self.execute("validate-suggestion", "--panel", str(panel), "--source-root", str(source), "--output", str(prepared))
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(prepared.read_text())
            self.assertEqual(len(value["candidates"]), 2)
            results = root / "results"
            results.mkdir()
            for item in value["candidates"]:
                checkout = root / f"checkout-{item['key']}"
                shutil.copytree(source, checkout)
                applied = self.execute("apply-suggestion", "--prepared", str(prepared), "--key", item["key"], "--source-root", str(checkout))
                self.assertEqual(applied.returncode, 0, applied.stderr)
                receipt = results / f"{item['key']}.json"
                recorded = self.execute(
                    "record-suggestion", "--prepared", str(prepared), "--key", item["key"],
                    "--build-exit", "0", "--diff-exit", "0", "--output", str(receipt),
                )
                self.assertEqual(recorded.returncode, 0, recorded.stderr)
            aggregated = root / "suggestions.json"
            result = self.execute(
                "aggregate-suggestions", "--prepared", str(prepared), "--results-dir", str(results), "--output", str(aggregated),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(aggregated.read_text())["validated"]), 2)
            deterministic = root / "deterministic.json"
            deterministic.write_text(json.dumps({"outcome": "pass"}))
            inline = root / "inline"
            result = self.execute(
                "render", "--panel", str(panel), "--deterministic", str(deterministic),
                "--suggestion-validation", str(aggregated), "--phase", "complete", "--expected-head", HEAD,
                "--run-url", "https://github.com/example/actions/runs/1", "--artifact-name", "complete-artifact",
                "--summary", str(root / "summary.md"), "--summary-payload", str(root / "summary.json"),
                "--inline-dir", str(inline), "--metadata", str(root / "metadata.json"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads((root / "metadata.json").read_text())
            self.assertEqual(metadata["inline_count"], 2)
            self.assertEqual(len(list(inline.glob("*.json"))), 2)
            self.assertTrue((root / "summary.md").read_text().startswith(SUMMARY))
            self.assertLess(len((root / "summary.md").read_text()), 1_200)

    def test_failed_patch_validation_is_suppressed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            panel = self.panel(root, two_suggestions=False)
            prepared = root / "prepared.json"
            self.assertEqual(self.execute(
                "validate-suggestion", "--panel", str(panel), "--source-root", str(root / "source"), "--output", str(prepared),
            ).returncode, 0)
            item = json.loads(prepared.read_text())["candidates"][0]
            results = root / "results"
            results.mkdir()
            self.execute(
                "record-suggestion", "--prepared", str(prepared), "--key", item["key"],
                "--build-exit", "1", "--diff-exit", "0", "--output", str(results / f"{item['key']}.json"),
            )
            output = root / "suggestions.json"
            result = self.execute(
                "aggregate-suggestions", "--prepared", str(prepared), "--results-dir", str(results), "--output", str(output),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(output.read_text())
            self.assertEqual(value["validated"], [])
            self.assertEqual(value["suppressed"][0]["outcome"], "fail")

    def test_summary_and_inline_selectors_are_app_scoped_and_stale_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            comments = root / "comments.json"
            comments.write_text(json.dumps([
                {"id": 1, "body": SUMMARY, "user": {"login": "human"}},
                {"id": 2, "body": SUMMARY, "user": {"login": "fc-review-pilot[bot]"}},
            ]))
            selection = root / "selection.json"
            result = self.execute("select-summary", "--comments", str(comments), "--app-slug", "fc-review-pilot", "--output", str(selection))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(selection.read_text()), {"action": "update", "comment_id": 2})
            marker = "<!-- formal-conjectures:live-ai-inline:v1:lean-semantics-sentinel-zero -->"
            request = {"body": marker, "commit_id": HEAD, "path": "FormalConjectures/ErdosProblems/430.lean", "line": 86, "side": "RIGHT"}
            request_path = root / "request.json"
            request_path.write_text(json.dumps(request))
            comments.write_text(json.dumps([{**request, "id": 7, "commit_id": "0" * 40, "user": {"login": "fc-review-pilot[bot]"}}]))
            result = self.execute(
                "select-inline", "--comments", str(comments), "--request", str(request_path),
                "--app-slug", "fc-review-pilot", "--output", str(selection),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("another head or line", result.stderr)

    def test_workflow_is_generic_pinned_and_separates_model_from_publisher(self):
        workflow = (REPO / ".github" / "workflows" / "live-ai-advisory-pr-review.yml").read_text()
        action = "anthropics/claude-code-action@d40ddef4c030e508327d6e35a9c45f3368482c50"
        self.assertEqual(workflow.count(action), 3)
        self.assertIn("default: false\n        type: boolean", workflow)
        self.assertIn("actual model receipts", workflow)
        self.assertIn("stored role evidence is not a fallback", (REPO / "scripts" / "live_ai_pr_review.py").read_text())
        self.assertNotIn("clean-room-source-fidelity.json", workflow)
        self.assertNotIn("clean-room-lean-semantics.json", workflow)
        self.assertNotIn("clean-room-adversarial-edge-cases.json", workflow)
        self.assertNotIn("openai/codex-action", workflow)
        self.assertNotIn("FC_REVIEW_OPENAI_API_KEY", workflow)
        self.assertEqual(workflow.count("secrets.FC_REVIEW_ANTHROPIC_API_KEY"), 4)
        self.assertEqual(workflow.count('show_full_output: "false"'), 3)
        self.assertEqual(workflow.count('--tools "Read,Glob,Grep"'), 3)
        self.assertEqual(workflow.count('--disallowedTools "mcp__*"'), 3)
        self.assertEqual(workflow.count("--max-turns 20"), 3)
        self.assertNotIn("--max-turns 4", workflow)
        self.assertEqual(workflow.count("structured_output"), 3)
        self.assertEqual(workflow.count("steps.claude.outputs.session_id"), 3)
        self.assertEqual(workflow.count("_SESSION_ID:"), 3)
        for job in ("ai-source-fidelity", "ai-lean-semantics", "ai-adversarial"):
            block = workflow.split(f"  {job}:", 1)[1].split("\n\n  ", 1)[0]
            self.assertNotIn("FC_REVIEW_APP_PRIVATE_KEY", block)
            self.assertNotIn("pull-requests: write", block)
            self.assertIn("permissions", block)
            self.assertNotIn("\n      - ", block.split("- id: claude", 1)[1])
        self.assertEqual(workflow.count("FC_REVIEW_APP_PRIVATE_KEY"), 2)


if __name__ == "__main__":
    unittest.main()
