"""Bounded local Codex OAuth adapter and shared review output schema."""
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from . import report as rr

def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(rr.encode(value))

def schema_object(**fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def schema_array(item, **limits):
    return {"type": "array", "items": item, **limits}


def schema_enum(*values):
    return {"type": "string", "enum": list(values)}


STRING = {"type": "string"}


BOOLEAN = {"type": "boolean"}


def review_schema(request, max_calls=30, context=()):
    paths = [item["path"] for item in request.get("sources", [])]
    paths += [f"evidence/tool-{n:03d}.json" for n in range(1, max_calls + 1)]
    evidence = schema_array(schema_enum(*paths, *context), minItems=1)
    return schema_object(
        request_id=schema_enum(request["id"]),
        reviewer=STRING,
        context_policy=schema_enum("fresh", "rereview"),
        prior_reviews=schema_array(STRING),
        coverage=schema_object(**{angle: schema_enum("complete", "incomplete") for angle in rr.ANGLES}),
        findings=schema_array(
            schema_object(
                angle=schema_enum(*rr.ANGLES),
                file=schema_enum(*request["scope"]),
                line={"type": "integer", "minimum": 0},
                severity=schema_enum("semantic", "nit"),
                message=STRING,
                suggestion=STRING,
                evidence=evidence,
            )
        ),
        questions=schema_array(STRING),
        reconciliations=schema_array(
            schema_object(
                prior_evidence=schema_enum(*context) if context else STRING,
                status=schema_enum("retained", "corrected", "withdrawn"),
                reason=STRING,
                evidence=evidence,
            ),
            **({} if context else {"maxItems": 0}),
        ),
    )


def allowed_call(call):
    if call.get("type") != "mcp_tool_call":
        return False
    if call.get("server") == "review_workspace":
        return True
    # Codex exposes built-in resource discovery even with plugins disabled. Only an
    # empty catalog is admissible; imported host resources invalidate the invocation.
    keys = {"list_mcp_resources": "resources", "list_mcp_resource_templates": "resourceTemplates"}
    if call.get("server") == "codex" and call.get("tool") in keys:
        content = (call.get("result") or {}).get("content", [])
        try:
            return len(content) == 1 and json.loads(content[0]["text"]) == {keys[call["tool"]]: []}
        except (KeyError, TypeError, ValueError):
            return False
    return False


def invoke_model(prompt_text, destination, model, timeout, schema=None, server_args=None):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "prompt.txt").write_text(prompt_text)
    args = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--model",
        model,
        "--json",
        "-o",
        str(destination / "answer.json"),
    ]
    settings = {"model_reasoning_effort": '"high"', "web_search": '"disabled"'}
    for feature in (
        "shell_tool",
        "unified_exec",
        "multi_agent",
        "apps",
        "plugins",
        "remote_plugin",
        "browser_use",
        "in_app_browser",
        "skill_search",
    ):
        settings["features." + feature] = "false"
    # --ignore-user-config alone still discovers host skill catalogs.
    installed = {
        str(p.parent)
        for folder in (".codex/skills", ".agents/skills", ".codex/plugins/cache")
        for p in (Path.home() / folder).rglob("SKILL.md")
    }
    overrides = ",".join("{path=" + json.dumps(p) + ",enabled=false}" for p in sorted(installed))
    settings["skills.config"] = "[" + overrides + "]"
    if schema:
        write(destination / "schema.json", schema)
        args += ["--output-schema", str(destination / "schema.json")]
    if server_args:
        server = {
            "command": json.dumps(sys.executable),
            "args": json.dumps(server_args),
            "default_tools_approval_mode": '"approve"',
            "required": "true",
            "tool_timeout_sec": "90",
        }
        settings.update(
            {"mcp_servers.review_workspace." + key: value for key, value in server.items()}
        )
    for key, value in settings.items():
        args += ["-c", f"{key}={value}"]
    args += ["-"]
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="fc-review-engine-") as temp:
        # A per-process Codex configuration directory prevents plugin and skill cache
        # discovery from importing the caller's review context. Authentication stays
        # in the existing host store and is never mounted into the reviewer container.
        engine_directory = Path(temp) / "codex"
        engine_directory.mkdir(mode=0o700)
        auth = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
        if auth.exists():
            (engine_directory / "auth.json").symlink_to(auth.resolve())
        engine_env = {
            k: v for k, v in os.environ.items() if k not in ("CODEX_SESSION_ID", "CODEX_THREAD_ID", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GH_TOKEN", "GITHUB_TOKEN")
        }
        engine_env["CODEX_HOME"] = str(engine_directory)
        with (
            (destination / "events.jsonl").open("w") as out,
            (destination / "stderr.txt").open("w") as err,
        ):
            proc = subprocess.Popen(
                args,
                cwd=temp,
                env=engine_env,
                stdin=subprocess.PIPE,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
            try:
                proc.communicate(prompt_text.encode(), timeout=timeout)
                status = "completed" if proc.returncode == 0 else "provider_error"
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
                status = "timeout"
    events = [json.loads(line) for line in (destination / "events.jsonl").read_text().splitlines()]
    usage = [e["usage"] for e in events if e.get("type") == "turn.completed"]
    calls = [
        e["item"]
        for e in events
        if e.get("type") == "item.completed"
        and e.get("item", {}).get("type") not in ("reasoning", "agent_message", "error")
    ]
    if any(not allowed_call(c) for c in calls):
        status = "unexpected_tool"
    elif any(
        c.get("error") is not None
        or (c.get("result") or {}).get("is_error")
        or (c.get("result") or {}).get("isError")
        for c in calls
    ):
        status = "tool_transport_error"
    record = {
        "status": status,
        "model": model,
        "model_identity_source": "explicit CLI model selection; provider alias resolution is not exposed",
        "wall_seconds": round(time.monotonic() - start, 3),
        "usage": usage,
        "cost_usd": None,
        "tool_calls": len(calls),
        "command": args,
        "cli_version": subprocess.check_output(["codex", "--version"], text=True).strip(),
        "mcp_version": importlib.metadata.version("mcp") if server_args else None,
    }
    write(destination / "invocation.json", record)
    return record

