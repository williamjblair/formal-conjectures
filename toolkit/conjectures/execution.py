"""Isolated candidate execution and the optional hosted API adapter."""
import json
import os
import re
import resource
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from . import report as rr
from .codex import review_schema
MAX_CALLS = 20
MAX_SECONDS = 420

def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, timeout=120, **kwargs).stdout

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rr.encode(value))

def container_args(image, snapshot):
    rr.require(
        re.fullmatch(r"(?:[^\s]+@)?sha256:[0-9a-f]{64}", image) is not None,
        "review image must be pinned by registry digest",
    )
    return [
        "docker",
        "run",
        "--rm",
        "-d",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=256",
        "--memory=6g",
        "--cpus=2",
        "--user=65534:65534",
        "--tmpfs=/tmp:rw,nosuid,size=4g,mode=1777",
        "--mount",
        f"type=bind,src={snapshot.resolve()},dst=/input,readonly",
        "--workdir=/tmp",
        image,
        "sleep",
        "infinity",
    ]


def isolated(image, snapshot):
    container = run(*container_args(image, snapshot)).decode().strip()
    try:
        # The configured image owns the trusted dependency cache and toolchain.
        run(
            "docker",
            "exec",
            container,
            "sh",
            "-c",
            "set -eu; mkdir /tmp/work; cp -R /input/. /tmp/work/; "
            "mkdir /tmp/work/.lake; "
            "ln -s /opt/review-cache/.lake/packages /tmp/work/.lake/packages; "
            "cp -R /opt/review-cache/.lake/build /tmp/work/.lake/build",
        )
        return container
    except BaseException:
        run("docker", "rm", "-f", container)
        raise


def execute(container, command, seconds=60):
    started = time.monotonic()
    try:
        # Bound retained output even when a command floods stdout. The limit applies
        # to the Docker client; the in-container timeout still stops the command.
        with tempfile.TemporaryFile() as output:

            def limit_output():
                resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))

            proc = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-w",
                    "/tmp/work",
                    container,
                    "timeout",
                    "-k",
                    "2",
                    str(seconds),
                    *command,
                ],
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=seconds + 10,
                check=False,
                preexec_fn=limit_output,
            )
            output.seek(0)
            text = output.read(48000).decode(errors="replace")
        return {
            "command": command,
            "exit_code": proc.returncode,
            "output": text,
            "wall_seconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "exit_code": None,
            "output": "Controller timeout",
            "wall_seconds": round(time.monotonic() - started, 3),
        }


def build_targets(scope, snapshot):
    # Utility/config/dependency changes need a broader policy; fail closed in this pilot.
    rr.require(
        all(
            p.startswith("FormalConjectures/")
            and not p.startswith(("FormalConjectures/Util/", "FormalConjectures/Subsets/"))
            and p.endswith(".lean")
            and (snapshot / p).is_file()
            for p in scope
        ),
        "automated review supports one to five new or modified problem modules only",
    )
    rr.require(0 < len(scope) <= 5, "pilot scope limit is five modules")
    rr.require(all("»" not in p and "\n" not in p for p in scope), "unsupported module path")
    return [".".join("«" + part + "»" for part in Path(p).with_suffix("").parts) for p in scope]


def model_review(request, container, evidence, model):
    history = [
        {
            "role": "user",
            "content": "Review the scoped FC contribution. Read /tmp/work/procedure/SKILL.md and follow it. "
            "Use execute for reads and optional scratch checks in /tmp/work. No network is available. "
            "The source snapshot is not authoritative source evidence: unavailable cited sources "
            "must leave source-fidelity coverage incomplete. This is a fresh advisory review. "
            "The independent build receipt is supplied separately; never claim proof verification. "
            "Stop after resolving material questions; do not repeat completed checks. "
            "Return the review JSON. Evidence paths are evidence/tool-NNN.json from tool results. "
            + json.dumps({"request_id": request["id"], "scope": request["scope"], "reviewer": model}),
        }
    ]
    started = time.monotonic()
    calls = 0
    usage = []
    while calls <= MAX_CALLS:
        remaining = MAX_SECONDS - (time.monotonic() - started)
        rr.require(remaining > 0, "model time budget exhausted")
        body = {
            "model": model,
            "store": False,
            "input": history,
            "reasoning": {"effort": "high"},
            "max_output_tokens": 8000,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "fc_review",
                    "strict": True,
                    "schema": review_schema(request, MAX_CALLS),
                }
            },
            "tools": [
                {
                    "type": "function",
                    "name": "execute",
                    "description": "Run a bounded command in the isolated review scratch copy.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                }
            ],
            "parallel_tool_calls": False,
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=rr.encode(body),
            headers={
                "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=min(remaining, 180)) as response:
            value = json.load(response)
        write(evidence / f"model-response-{len(usage):03d}.json", value)
        usage.append(value.get("usage"))
        rr.require(value.get("status") == "completed", "model response incomplete")
        history.extend(value["output"])
        tools = [item for item in value["output"] if item["type"] == "function_call"]
        if not tools:
            texts = [
                part["text"]
                for item in value["output"]
                if item["type"] == "message"
                for part in item["content"]
                if part["type"] == "output_text"
            ]
            review = json.loads("".join(texts))
            rr.require(
                review["context_policy"] == "fresh" and not review["prior_reviews"],
                "pilot requires a fresh review",
            )
            review["reviewer"] = value.get("model", model)
            return review
        for item in tools:
            calls += 1
            rr.require(calls <= MAX_CALLS and item["name"] == "execute", "invalid tool or exhausted budget")
            command = json.loads(item["arguments"])["command"]
            remaining = int(MAX_SECONDS - (time.monotonic() - started))
            rr.require(remaining > 0, "model time budget exhausted")
            record = execute(container, ["sh", "-c", command], min(60, remaining))
            name = f"evidence/tool-{calls:03d}.json"
            write(evidence / Path(name).name, record)
            history.append(
                {
                    "type": "function_call_output",
                    "call_id": item["call_id"],
                    "output": json.dumps({"evidence": name, **record}),
                }
            )
    raise ValueError("model tool budget exhausted")

