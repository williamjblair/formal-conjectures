from __future__ import annotations

import hashlib
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
PRIMARY_FIXTURE = REPO / "audit" / "pr-audit-v1" / "fixtures" / "live-ai-contract" / "primary-pass.json"
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

    def usage(self, role: str, cost: str = "0.25"):
        return {
            "schema_version": "formal-conjectures.live-ai-provider-usage.v1",
            "role": role,
            "provider": "anthropic",
            "model": "claude-sonnet-5",
            "configured_cap_usd": "5.00",
            "actual_cost_usd": {"status": "reported", "value": cost, "reason": None},
            "turn_count": {"status": "reported", "value": 7, "reason": None},
            "timing": {
                "started_at_epoch_ms": 2_000, "finished_at_epoch_ms": 5_000, "wall_clock_ms": 3_000,
                "provider_duration_ms": {"status": "reported", "value": 2_500, "reason": None},
                "api_duration_ms": {"status": "unknown", "value": None, "reason": "unknown/not reported by provider"},
            },
            "tokens": {
                "status": "reported", "input": 100, "output": 20, "cache_read_input": 50,
                "cache_creation_input": 10, "reason": None,
            },
            "cache": {"status": "reported", "read_input_tokens": 50, "creation_input_tokens": 10, "reason": None},
            "retry": {"status": "unknown", "count": None, "reason": "unknown/not reported by provider"},
            "execution_file": {"status": "parsed", "reason": None},
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
        from jsonschema import Draft202012Validator
        Draft202012Validator(schema).validate(json.loads(PRIMARY_FIXTURE.read_text()))

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
            "primary_review": self.role("primary_review", manifest["root"], [finding], "fail", "meaning"),
        }
        if two_suggestions:
            roles["escalation_review"] = self.role(
                "escalation_review", manifest["root"], [finding], "fail", "meaning",
            )
        output = root / "panel"
        env = {f"FC_AI_{role.upper()}_OUTPUT": json.dumps(value) for role, value in roles.items()}
        env.update({f"FC_AI_{role.upper()}_SESSION_ID": f"session-{role}" for role in roles})
        env.update({f"FC_AI_{role.upper()}_USAGE": json.dumps(self.usage(role)) for role in roles})
        result = self.execute(
            "validate-panel", "--input-manifest", str(input_dir / "input-manifest.json"), "--output-dir", str(output),
            "--action-commit", "d40ddef4c030e508327d6e35a9c45f3368482c50",
            "--model", "claude-sonnet-5", "--effort", "high", "--max-budget-usd-per-role", "5.00",
            "--github-run-id", "123", "--github-run-attempt", "1",
            "--escalation-trigger", "manual" if two_suggestions else "none", env=env,
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
                "prompt-primary_review.md", "prompt-escalation_review.md",
            })
            result = self.execute(
                "prepare", "--config", str(CONFIG), "--live-pr", str(root / "live.json"),
                "--source-root", str(root / "source"), "--expected-head", HEAD,
                "--prompt-template", str(PROMPT), "--output-schema", str(SCHEMA),
                "--output-dir", str(root / "bad"), "--publish-comment",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("requires a real AI review", result.stderr)

    def test_pr2_packet_retains_exact_composite_api_and_mathlib_lock(self):
        config = json.loads(CONFIG.read_text())
        sources = {item["id"]: item for item in config["sources"]}
        self.assertEqual(
            set(sources),
            {"current", "history", "original", "dependency-api-nat-composite", "dependency-lock-mathlib"},
        )
        api = FIXTURE / sources["dependency-api-nat-composite"]["path"]
        self.assertIn("abbrev Nat.Composite (n : ℕ) : Prop := 1 < n ∧ ¬n.Prime", api.read_text())
        self.assertEqual("sha256:" + hashlib.sha256(api.read_bytes()).hexdigest(), sources["dependency-api-nat-composite"]["sha256"])
        lock = json.loads((FIXTURE / sources["dependency-lock-mathlib"]["path"]).read_text())
        manifest = (REPO / "lake-manifest.json").read_bytes()
        self.assertEqual(lock["manifest_sha256"], "sha256:" + hashlib.sha256(manifest).hexdigest())
        mathlib = next(item for item in json.loads(manifest)["packages"] if item["name"] == "mathlib")
        self.assertEqual(lock["mathlib"], {
            "input_rev": mathlib["inputRev"], "rev": mathlib["rev"], "url": mathlib["url"],
        })

    def test_provider_usage_is_sanitized_and_cost_ledger_is_aggregated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution = root / "execution.json"
            execution.write_text(json.dumps([
                {"type": "assistant", "message": {"content": "must not be retained"}},
                {
                    "type": "result", "total_cost_usd": 0.375, "num_turns": 6,
                    "duration_ms": 2_400, "duration_api_ms": 1_900,
                    "usage": {"input_tokens": 120, "output_tokens": 30, "cache_read_input_tokens": 80},
                },
            ]))
            usage_path = root / "usage.json"
            result = self.execute(
                "capture-provider-usage", "--role", "primary_review", "--execution-file", str(execution),
                "--model", "claude-sonnet-5", "--max-budget-usd-per-role", "5.00",
                "--started-at-epoch-ms", "1000", "--finished-at-epoch-ms", "4000", "--output", str(usage_path),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            usage = json.loads(usage_path.read_text())
            self.assertEqual(usage["actual_cost_usd"]["value"], "0.375")
            self.assertEqual(usage["turn_count"]["value"], 6)
            self.assertEqual(usage["retry"]["reason"], "unknown/not reported by provider")
            self.assertNotIn("must not be retained", usage_path.read_text())
            unknown_path = root / "unknown.json"
            result = self.execute(
                "capture-provider-usage", "--role", "primary_review", "--execution-file", "",
                "--model", "claude-sonnet-5", "--max-budget-usd-per-role", "5.00",
                "--started-at-epoch-ms", "1000", "--finished-at-epoch-ms", "4000", "--output", str(unknown_path),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(unknown_path.read_text())["actual_cost_usd"], {
                "reason": "unknown/not reported by provider", "status": "unknown", "value": None,
            })

            panel = self.panel(root / "panel-root")
            for phase, started, finished in (("prepare", 100, 200), ("deterministic", 250, 600), ("finalize", 650, 800)):
                result = self.execute(
                    "record-phase", "--phase", phase, "--started-at-epoch-ms", str(started),
                    "--finished-at-epoch-ms", str(finished), "--output", str(root / f"{phase}.json"),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            ledger = root / "cost-ledger.json"
            result = self.execute(
                "aggregate-cost-ledger", "--panel", str(panel), "--prepare-timing", str(root / "prepare.json"),
                "--deterministic-timing", str(root / "deterministic.json"),
                "--finalize-timing", str(root / "finalize.json"), "--output", str(ledger),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(ledger.read_text())
            self.assertEqual(value["actual_cost_usd"], {
                "reason": None, "reported_subtotal_usd": "0.50", "status": "reported", "value": "0.50",
            })
            self.assertEqual(value["configured_caps_usd"], {"per_pass": "5.00", "role_limit": 2, "total": "10.00"})
            self.assertEqual(value["end_to_end_wall_clock_ms"], 700)

    def test_validate_panel_requires_an_actual_primary_model_output(self):
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
            self.assertIn("no valid model review receipt", result.stderr)

    def test_validate_panel_requires_and_retains_claude_session_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, input_dir = self.prepare(root)
            manifest = json.loads((input_dir / "input-manifest.json").read_text())
            roles = ("primary_review",)
            primary = json.loads(PRIMARY_FIXTURE.read_text())
            primary["exact_input_root"] = manifest["root"]
            env = {"FC_AI_PRIMARY_REVIEW_OUTPUT": json.dumps(primary)}
            env.update({})
            output = root / "panel"
            args = (
                "validate-panel", "--input-manifest", str(input_dir / "input-manifest.json"),
                "--output-dir", str(output), "--action-commit", "d40ddef4c030e508327d6e35a9c45f3368482c50",
                "--model", "claude-sonnet-5", "--effort", "high", "--max-budget-usd-per-role", "5.00", "--github-run-id", "123",
                "--github-run-attempt", "1",
            )
            result = self.execute(*args, env=env)
            self.assertEqual(result.returncode, 2)
            self.assertIn("no valid model review receipt", result.stderr)
            env["FC_AI_PRIMARY_REVIEW_SESSION_ID"] = "session-primary"
            result = self.execute(*args, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            panel = json.loads((output / "ai-review-panel.json").read_text())
            self.assertEqual(panel["execution"]["provider"], "anthropic")
            self.assertEqual(panel["execution"]["runner"], "claude-code-action")
            self.assertEqual(set(panel["execution"]["role_receipts"]), set(roles))

    def test_primary_pass_with_nit_is_retained_and_conservatively_normalized(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, input_dir = self.prepare(root)
            manifest = json.loads((input_dir / "input-manifest.json").read_text())
            nit = self.role("primary_review", manifest["root"])
            nit["findings"][0]["severity"] = "nit"
            env = {
                "FC_AI_PRIMARY_REVIEW_OUTPUT": json.dumps(nit),
                "FC_AI_PRIMARY_REVIEW_SESSION_ID": "session-primary",
            }
            inspection = root / "inspection.json"
            result = self.execute(
                "inspect-primary", "--input-manifest", str(input_dir / "input-manifest.json"),
                "--output", str(inspection), env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            inspected = json.loads(inspection.read_text())
            self.assertEqual(inspected["status"], "valid")
            self.assertFalse(inspected["escalation_required"])
            output = root / "panel"
            result = self.execute(
                "validate-panel", "--input-manifest", str(input_dir / "input-manifest.json"),
                "--output-dir", str(output), "--action-commit", "d40ddef4c030e508327d6e35a9c45f3368482c50",
                "--model", "claude-sonnet-5", "--effort", "high", "--max-budget-usd-per-role", "5.00",
                "--github-run-id", "123", "--github-run-attempt", "1",
                "--escalation-trigger", "none", env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            panel = json.loads((output / "ai-review-panel.json").read_text())
            primary = panel["roles"]["primary_review"]
            self.assertEqual(primary["outcome"], "fail")
            self.assertEqual(primary["severity"], "nit")
            self.assertEqual(primary["findings"][0]["severity"], "nit")
            self.assertIn("declared severity 'none' was conservatively normalized to 'nit'", primary["limitations"][-2])
            self.assertIn("declared outcome 'pass' was normalized to 'fail'", primary["limitations"][-1])
            self.assertEqual(panel["disposition"]["advisory"], "nits_found")
            self.assertEqual(len(panel["findings"]), 1)

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
            self.assertIn("## FC Review Pilot", (root / "summary.md").read_text())
            self.assertIn("**Needs Revision** · 2 findings · Lean `pass` · 2 inline suggestion(s)", (root / "summary.md").read_text())
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

    def test_mechanical_import_and_typed_gate_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare(root)
            import_result = root / "imports.json"
            result = self.execute(
                "check-imports", "--config", str(CONFIG), "--source-root", str(root / "source"),
                "--output", str(import_result),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(import_result.read_text())["outcome"], "pass")
            deterministic = root / "deterministic.json"
            result = self.execute(
                "capture-deterministic", "--config", str(CONFIG), "--build-target", "Example.Target",
                "--lean-exit", "0", "--diff-exit", "0", "--style-exit", "1", "--import-exit", "127",
                "--output", str(deterministic),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(deterministic.read_text())
            self.assertEqual(value["checks"], {
                "diff_check": "pass", "import_policy": "error", "lean_build": "pass", "style_lint": "fail",
            })
            self.assertEqual(value["outcome"], "error")

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
        self.assertEqual(workflow.count(action), 2)
        self.assertEqual(workflow.count("default: true\n        type: boolean"), 2)
        self.assertIn("actual primary output", workflow)
        self.assertIn("stored role evidence is not a fallback", (REPO / "scripts" / "live_ai_pr_review.py").read_text())
        self.assertNotIn("clean-room-source-fidelity.json", workflow)
        self.assertNotIn("clean-room-lean-semantics.json", workflow)
        self.assertNotIn("clean-room-adversarial-edge-cases.json", workflow)
        self.assertNotIn("openai/codex-action", workflow)
        self.assertNotIn("FC_REVIEW_OPENAI_API_KEY", workflow)
        self.assertEqual(workflow.count("secrets.FC_REVIEW_ANTHROPIC_API_KEY"), 3)
        self.assertEqual(workflow.count('show_full_output: "false"'), 2)
        self.assertEqual(workflow.count(".agents/skills/formal-conjectures-review/SKILL.md"), 2)
        self.assertEqual(workflow.count("--agents-path reviewer/AGENTS.md"), 2)
        self.assertNotIn('--tools "Read,Glob,Grep"', workflow)
        self.assertNotIn('--disallowedTools "mcp__*"', workflow)
        self.assertEqual(workflow.count("--max-turns ${{ inputs.max_turns }}"), 2)
        self.assertIn('default: "20"', workflow)
        self.assertIn('options: ["20", "40", "60"]', workflow)
        self.assertNotRegex(workflow, r"--max-turns 4(?:\s|$)")
        self.assertEqual(workflow.count("steps.claude.outputs.structured_output != ''"), 2)
        self.assertEqual(workflow.count("steps.claude.outputs.session_id"), 2)
        self.assertEqual(workflow.count("steps.claude.outputs.execution_file"), 2)
        self.assertEqual(workflow.count("continue-on-error: true"), 2)
        self.assertEqual(workflow.count("evaluate-provider-controls"), 2)
        self.assertEqual(workflow.count("Retain provider controls even when the model fails"), 2)
        self.assertEqual(workflow.count("Fail closed on any provider ceiling or receipt error"), 2)
        self.assertEqual(workflow.count("timeout-minutes: ${{ fromJSON(inputs.max_ai_wall_clock_minutes) }}"), 2)
        self.assertNotIn("ref: refs/pull/${{ inputs.pull_request }}/head", workflow)
        self.assertEqual(workflow.count("ref: ${{ inputs.expected_head }}"), 5)
        self.assertEqual(workflow.count("record-provider-job-failure"), 2)
        self.assertIn("retain-primary-failure:", workflow)
        self.assertIn("retain-escalation-failure:", workflow)
        self.assertIn("fc-live-ai-provider-primary-failure-${{ inputs.pull_request }}-${{ inputs.expected_head }}", workflow)
        self.assertIn("fc-live-ai-provider-escalation-failure-${{ inputs.pull_request }}-${{ inputs.expected_head }}", workflow)
        self.assertNotIn("steps.controls.outputs.artifact_name", workflow)
        check_block = workflow.split("- name: Publish neutral exact-head check", 1)[1].split("- id: metadata", 1)[0]
        self.assertIn("if: ${{ inputs.publish_comment }}", check_block)
        self.assertIn("--require-provider-controls", workflow)
        self.assertIn("FC_AI_PRIMARY_REVIEW_CONTROLS", workflow)
        self.assertIn("FC_AI_ESCALATION_REVIEW_CONTROLS", workflow)
        self.assertIn('default: "15"', workflow)
        self.assertIn('options: ["10", "15", "20"]', workflow)
        self.assertIn("cost-ledger.json", workflow)
        self.assertIn("aggregate-cost-ledger", workflow)
        self.assertIn("always() && needs.validate-ai.result == 'success'", workflow)
        self.assertIn("needs.validate-suggestions.result == 'success'", workflow)
        self.assertIn("always() && inputs.publish_comment && needs.render-progress.result == 'success'", workflow)
        self.assertIn("escalation_mode", workflow)
        self.assertIn("needs.inspect-primary.outputs.reason == 'primary_inconclusive'", workflow)
        self.assertIn('default: "off"', workflow)
        self.assertIn("check-imports", workflow)
        self.assertEqual(workflow.count("checks: write"), 1)
        for job in ("ai-primary", "ai-escalation"):
            block = workflow.split(f"  {job}:", 1)[1].split("\n\n  ", 1)[0]
            self.assertNotIn("FC_REVIEW_APP_PRIVATE_KEY", block)
            self.assertNotIn("pull-requests: write", block)
            self.assertIn("permissions", block)
            self.assertIn("id-token: write", block)
            self.assertIn("ref: ${{ inputs.expected_head }}", block)
            self.assertIn("persist-credentials: false", block)
            before_model, after_model = block.split("- id: claude", 1)
            self.assertNotIn("path: reviewer", before_model)
            self.assertIn("Load trusted usage sanitizer after model execution", after_model)
            self.assertIn("capture-provider-usage", after_model)
            self.assertIn("evaluate-provider-controls", after_model)
            self.assertIn("Fail closed on any provider ceiling or receipt error", after_model)
        self.assertEqual(workflow.count("FC_REVIEW_APP_PRIVATE_KEY"), 2)


if __name__ == "__main__":
    unittest.main()
