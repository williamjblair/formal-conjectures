"""Offline boundary tests; these do not establish hosted Actions qualification."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import review_workflow as w
except ModuleNotFoundError as error:
    if error.name not in ("review_report", "review_eval"):
        raise
    raise unittest.SkipTest(
        "Requires #4899; the dedicated integration job supplies its pinned tools"
    ) from error


class WorkflowTests(unittest.TestCase):
    def test_authorization_uses_effective_permission_and_exact_command(self):
        event = {"action": "created", "comment": {"body": "/review"}, "issue": {"pull_request": {}}}
        w.authorize(event, "write")
        for permission in ("read", "triage", "none"):
            with self.assertRaises(ValueError):
                w.authorize(event, permission)
        event["comment"]["body"] = "/review\necho injected"
        with self.assertRaises(ValueError):
            w.authorize(event, "admin")

    def test_freshness_binds_head_base_tooling_and_open_state(self):
        ticket = {"head": "a", "base": "b", "tooling": "c"}
        pr = {"head": {"sha": "a"}, "base": {"sha": "b"}, "state": "open"}
        self.assertEqual(w.freshness(ticket, pr, "c"), "current")
        self.assertEqual(w.freshness(ticket, pr, "d"), "STALE")
        for change in ({"head": {"sha": "x"}}, {"base": {"sha": "x"}}, {"state": "closed"}):
            self.assertEqual(w.freshness(ticket, pr | change, "c"), "STALE")

    def test_container_has_no_host_execution_or_credentials(self):
        args = w.container_args("ghcr.io/example/cache@sha256:" + "a" * 64, Path("/tmp/input"))
        for flag in ("--network=none", "--read-only", "--cap-drop=ALL", "--user=65534:65534"):
            self.assertIn(flag, args)
        self.assertNotIn("--privileged", args)
        self.assertNotIn("-e", args)
        self.assertIn(
            (
                "type=bind,src=/private/tmp/input,dst=/input,readonly"
                if Path("/tmp").resolve() != Path("/tmp")
                else "type=bind,src=/tmp/input,dst=/input,readonly"
            ),
            args,
        )
        with self.assertRaises(ValueError):
            w.container_args("ghcr.io/example/cache:latest", Path("/tmp/input"))

    def test_scope_rejects_project_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / "FormalConjectures/Fixture/12.lean"
            p.parent.mkdir(parents=True)
            p.write_text("")
            self.assertEqual(
                w.build_targets(["FormalConjectures/Fixture/12.lean"], root),
                ["«FormalConjectures».«Fixture».«12»"],
            )
            utility = root / "FormalConjectures/Util/ProblemImports.lean"
            utility.parent.mkdir(parents=True)
            utility.write_text("")
            for scope in (
                ["lakefile.toml"],
                ["FormalConjectures/deleted.lean"],
                ["FormalConjectures/Util/ProblemImports.lean"],
            ):
                with self.assertRaises(ValueError):
                    w.build_targets(scope, root)

    def test_timeout_is_an_execution_error(self):
        with patch.object(w.subprocess, "run", side_effect=w.subprocess.TimeoutExpired("docker", 70)):
            self.assertIsNone(w.execute("container", ["lake", "build"])["exit_code"])

    def test_model_tools_remain_container_calls_and_keep_evidence(self):
        request = {"id": "r", "scope": ["FormalConjectures/Example.lean"], "sources": []}
        answer = {"context_policy": "fresh", "prior_reviews": [], "reviewer": "invented"}
        responses = [
            {
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "name": "execute",
                        "arguments": json.dumps({"command": "cat FormalConjectures/Example.lean"}),
                        "call_id": "c",
                    }
                ],
            },
            {
                "status": "completed",
                "model": "actual-model",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            w.os.environ, {"OPENAI_API_KEY": "test"}
        ), patch.object(
            w.urllib.request, "urlopen", side_effect=[io.BytesIO(json.dumps(x).encode()) for x in responses]
        ), patch.object(
            w, "execute", return_value={"exit_code": 0, "output": "source"}
        ) as execute:
            result = w.model_review(request, "isolated-container", Path(directory), "requested-model")
            self.assertEqual(result["reviewer"], "actual-model")
            execute.assert_called_once_with(
                "isolated-container", ["sh", "-c", "cat FormalConjectures/Example.lean"], 60
            )
            self.assertTrue((Path(directory) / "tool-001.json").is_file())
            self.assertEqual(len(list(Path(directory).glob("model-response-*.json"))), 2)

    def test_publisher_reconstructs_bundle_and_rejects_tampering(self):
        from test_review_report import ReportTest

        fixture = ReportTest()
        fixture.setUp()
        try:
            bundle = fixture.root / "bundle"
            w.rr.write_directory(bundle, fixture.run_report())
            ticket = {
                "repository": "owner/repo",
                "pr": 1,
                "comment_id": 100,
                "head": "a" * 40,
                "base": "b" * 40,
                "tooling": "c" * 40,
                "request_id": fixture.request["id"],
                "run_id": "123",
                "attempt": "1",
            }
            w.write(bundle / "ticket.json", ticket)
            env = {
                "GITHUB_REPOSITORY": "owner/repo",
                "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "1",
                "TICKET_SHA256": w.rr.digest(w.rr.encode(ticket)),
                "BUNDLE_SHA256": w.rr.digest((bundle / "report.json").read_bytes()),
            }
            pr = {"state": "open", "head": {"sha": ticket["head"]}, "base": {"sha": ticket["base"]}}
            with patch.dict(w.os.environ, env), patch.object(
                w, "api", side_effect=[pr, {"default_branch": "main"}, {"sha": ticket["tooling"]}, [], {}]
            ) as api:
                w.publish(bundle)
                self.assertTrue(api.call_args.args[1]["body"].startswith(w.MARKER))
            (bundle / "evidence/build.json").write_text("forged")
            with patch.dict(w.os.environ, env), patch.object(w, "api") as api:
                with self.assertRaises(ValueError):
                    w.publish(bundle)
                api.assert_not_called()
        finally:
            fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
