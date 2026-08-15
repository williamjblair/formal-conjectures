#!/usr/bin/env python3
"""Adapt Comparator execution into separate invocation, parse, and policy outcomes.

Terminal text is retained as evidence, never interpreted as a property verdict.
The policy result must come from an explicit JSON sidecar produced by a trusted
Comparator wrapper. This prevents an uncaught exception from becoming `fail`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any

RESULT_SCHEMA = "formal-conjectures.comparator-result.v1"
ADAPTER_SCHEMA = "formal-conjectures.comparator-outcome.v1"


class ResultError(ValueError):
    pass


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def parse_property_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema", "property", "outcome", "witnesses"
    }:
        raise ResultError("invalid structured Comparator result shape")
    if value["schema"] != RESULT_SCHEMA:
        raise ResultError("unsupported structured Comparator result schema")
    if value["property"] != "statement_equivalence_and_permitted_axioms":
        raise ResultError("unexpected Comparator property")
    if value["outcome"] not in ("pass", "fail"):
        raise ResultError("property outcome must be pass or fail")
    if not isinstance(value["witnesses"], list) or not all(
        isinstance(item, str) and item for item in value["witnesses"]
    ):
        raise ResultError("property witnesses must be nonempty strings")
    if value["outcome"] == "fail" and not value["witnesses"]:
        raise ResultError("a property failure requires a witness")
    return value


def adapt(returncode: int | None, stdout: bytes, stderr: bytes,
          structured: Any = None, *, unavailable: str | None = None,
          timed_out: bool = False) -> dict[str, Any]:
    evidence = {
        "stdout_sha256": _sha256(stdout),
        "stderr_sha256": _sha256(stderr),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
    }
    if unavailable is not None:
        invocation = {"outcome": "unavailable", "reason": unavailable}
    elif timed_out:
        invocation = {"outcome": "error", "reason": "timeout"}
    elif returncode != 0:
        invocation = {
            "outcome": "error",
            "reason": "nonzero_exit",
            "exit_code": returncode,
        }
    else:
        invocation = {"outcome": "pass", "exit_code": 0}

    if invocation["outcome"] != "pass":
        parsing = {"outcome": "not_attempted", "reason": "invocation_not_successful"}
        policy = {"outcome": "not_evaluated"}
    elif structured is None:
        parsing = {"outcome": "error", "reason": "structured_result_missing"}
        policy = {"outcome": "not_evaluated"}
    else:
        try:
            policy = parse_property_result(structured)
        except ResultError as exc:
            parsing = {"outcome": "error", "reason": str(exc)}
            policy = {"outcome": "not_evaluated"}
        else:
            parsing = {"outcome": "pass"}

    return {
        "schema": ADAPTER_SCHEMA,
        "authority_effect": "none",
        "invocation": invocation,
        "result_parse": parsing,
        "policy_result": policy,
        "terminal_evidence": evidence,
        "nonclaims": [
            "not_an_acceptance_or_merge_decision",
            "not_a_claim_of_mathematical_truth",
            "terminal_text_was_not_used_as_a_property_verdict",
        ],
    }


def run(command: list[str], result_file: pathlib.Path | None,
        timeout: int, *, cwd: pathlib.Path | None = None,
        env: dict[str, str] | None = None) -> tuple[dict[str, Any], bytes, bytes]:
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout,
                              cwd=cwd, env=env)
    except FileNotFoundError as exc:
        return adapt(None, b"", b"", unavailable=str(exc)), b"", b""
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        return adapt(None, stdout, stderr, timed_out=True), stdout, stderr
    structured = None
    if result_file is not None and result_file.is_file():
        try:
            structured = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            structured = {"invalid_result_file": str(exc)}
    return adapt(proc.returncode, proc.stdout, proc.stderr, structured), proc.stdout, proc.stderr


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-file", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("give a command after --")
    report, stdout, stderr = run(command, args.result_file, args.timeout)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            parser.error(f"refusing to overwrite immutable output: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    print(payload, file=sys.stderr, end="")
    return 0 if report["invocation"]["outcome"] == "pass" and \
        report["result_parse"]["outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
