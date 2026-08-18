# Copyright 2026 The Formal Conjectures Authors.
# Licensed under the Apache License, Version 2.0 (the "License");

"""Render and safely select actionable advisory PR comments."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from pr_audit import AuditError, parse_json_bytes

SUMMARY_MARKER = "<!-- formal-conjectures:advisory-review:v1 -->"
INLINE_PREFIX = "formal-conjectures:advisory-inline:v1:"
OID = re.compile(r"^[0-9a-f]{40}$")
KEY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load(path: Path) -> Any:
    return parse_json_bytes(path.read_bytes())


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def exact(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise AuditError(f"{name} must have exactly keys {sorted(keys)}")
    return value


def text(value: Any, name: str, limit: int = 2_000) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise AuditError(f"{name} must be a nonempty bounded string")
    return value


def comments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise AuditError("GitHub comments must be an array")
    flat: list[Any] = []
    for item in value:
        flat.extend(item if isinstance(item, list) else [item])
    if len(flat) > 10_000 or not all(isinstance(item, dict) for item in flat):
        raise AuditError("GitHub comments are malformed or too large")
    return flat


def bot_login(app_slug: str) -> str:
    if not app_slug or app_slug.endswith("[bot]") or any(c.isspace() for c in app_slug):
        raise AuditError("GitHub App slug is malformed")
    return f"{app_slug}[bot]"


def inline_marker(key: str) -> str:
    if not KEY.fullmatch(key):
        raise AuditError("inline suggestion key is malformed")
    return f"<!-- {INLINE_PREFIX}{key} -->"


def render(args: argparse.Namespace) -> None:
    if not OID.fullmatch(args.expected_head):
        raise AuditError("expected head must be a lowercase 40-character Git OID")
    if not args.run_url.startswith("https://github.com/") or "/actions/runs/" not in args.run_url:
        raise AuditError("run URL must be a github.com Actions URL")
    core = load(args.core)
    config = exact(
        load(args.actionable),
        {"schema_version", "repository", "finding", "inline_suggestion"},
        "actionable review",
    )
    if config["schema_version"] != "formal-conjectures.actionable-review.v1":
        raise AuditError("unsupported actionable review version")
    repository = exact(
        config["repository"], {"owner", "name", "pull_request", "head_commit_oid"}, "repository binding",
    )
    core_repo = core["repository"]
    expected = {
        "owner": core_repo["repository"]["owner"], "name": core_repo["repository"]["name"],
        "pull_request": core_repo["pull_request"]["number"], "head_commit_oid": core_repo["head"]["commit_oid"],
    }
    if repository != expected or repository["head_commit_oid"] != args.expected_head:
        raise AuditError("actionable review does not match the exact audit-core PR head")
    finding = exact(config["finding"], {"check_id", "next_action"}, "finding")
    next_action = text(finding["next_action"], "next action", 240)
    if "\n" in next_action or "\r" in next_action:
        raise AuditError("next action must be one line")
    checks = [check for check in core["checks"] if check.get("id") == finding["check_id"]]
    if len(checks) != 1:
        raise AuditError("actionable finding must bind one core check")
    failed = [check for check in core["checks"] if check.get("outcome") == "fail"]
    if failed and checks[0].get("outcome") != "fail":
        raise AuditError("actionable finding must bind a failed core check when failures exist")
    if not failed and config["inline_suggestion"] is not None:
        raise AuditError("an inline suggestion requires a failed core check")
    count = len(failed)
    disposition = core["disposition"]["advisory"]
    suffix = " A localized inline suggestion is available." if config["inline_suggestion"] else ""
    if args.phase == "in-progress":
        verification = "**Status:** Review in progress — deterministic Lean verification is pending.\n\n"
    else:
        if args.runtime_deterministic is None:
            raise AuditError("complete summary requires runtime deterministic evidence")
        runtime = load(args.runtime_deterministic)
        outcome = runtime.get("outcome") if isinstance(runtime, dict) else None
        if outcome not in {"pass", "fail", "error"}:
            raise AuditError("runtime deterministic evidence has an unsupported outcome")
        verification = f"**Lean verification:** `{outcome}` at the pinned head.\n\n"
    summary = (
        f"{SUMMARY_MARKER}\n\n## FC Review Pilot — advisory\n\n"
        f"**Verdict:** `{disposition}` · **Findings:** {count}\n\n"
        f"{verification}"
        f"**Next action:** {next_action}{suffix}\n\n"
        f"Pinned head: `{args.expected_head}`\n\n"
        f"[Workflow evidence]({args.run_url}) · artifact `{args.artifact_name}`\n\n"
        "This automated summary is advisory only. It is not maintainer disposition, acceptance, "
        "a merge decision, or a claim of mathematical truth.\n"
    )
    write(args.summary_output, summary)
    write(args.summary_payload, json.dumps({"body": summary}, ensure_ascii=False, separators=(",", ":")) + "\n")
    inline = config["inline_suggestion"]
    metadata: dict[str, Any] = {"inline_available": inline is not None, "finding_count": count}
    if inline is not None:
        inline = exact(
            inline,
            {"key", "check_id", "confidence", "path", "line", "side", "original", "replacement", "explanation"},
            "inline suggestion",
        )
        if inline["check_id"] != finding["check_id"] or inline["confidence"] != "high":
            raise AuditError("inline suggestion must bind the failed check at high confidence")
        path = text(inline["path"], "inline path", 500)
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or str(pure) != path:
            raise AuditError("inline path must be normalized and repository-relative")
        line = inline["line"]
        if not isinstance(line, int) or isinstance(line, bool) or line <= 0 or inline["side"] != "RIGHT":
            raise AuditError("inline location must be a positive RIGHT-side line")
        original = text(inline["original"], "original line")
        replacement = text(inline["replacement"], "replacement", 8_000)
        explanation = text(inline["explanation"], "explanation")
        if "\n" in original or "```" in replacement or "```" in explanation:
            raise AuditError("inline suggestion text is unsafe")
        source = (args.source_root / path).resolve(strict=True)
        source.relative_to(args.source_root.resolve(strict=True))
        lines = source.read_text(encoding="utf-8").splitlines()
        if line > len(lines) or lines[line - 1] != original:
            raise AuditError("inline original does not match the exact-head source line")
        if path not in {change["path"] for change in core_repo["changes"]}:
            raise AuditError("inline path is not in the audit-core change set")
        body = (
            f"{inline_marker(inline['key'])}\n\n{explanation}\n\n"
            f"```suggestion\n{replacement}\n```\n\n"
            "This suggested change is advisory only. It does not approve, apply, merge, or establish "
            "maintainer disposition or mathematical truth.\n"
        )
        create = {"body": body, "commit_id": args.expected_head, "path": path, "line": line, "side": "RIGHT"}
        write(args.inline_output, body)
        write(args.inline_create_payload, json.dumps(create, ensure_ascii=False, separators=(",", ":")) + "\n")
        write(args.inline_update_payload, json.dumps({"body": body}, ensure_ascii=False, separators=(",", ":")) + "\n")
        metadata.update({"key": inline["key"], "head_commit_oid": args.expected_head, "path": path, "line": line, "side": "RIGHT"})
    write(args.metadata_output, json.dumps(metadata, separators=(",", ":")) + "\n")


def select_summary(args: argparse.Namespace) -> None:
    matches = [
        comment for comment in comments(load(args.comments))
        if comment.get("user", {}).get("login") == bot_login(args.app_slug)
        and SUMMARY_MARKER in (comment.get("body") or "")
    ]
    if len(matches) > 1:
        raise AuditError("more than one App advisory summary exists")
    result = {"action": "update", "comment_id": matches[0]["id"]} if matches else {"action": "create", "comment_id": None}
    write(args.output, json.dumps(result, separators=(",", ":")) + "\n")


def select_inline(args: argparse.Namespace) -> None:
    request = exact(load(args.request), {"body", "commit_id", "path", "line", "side"}, "inline request")
    marker = re.search(r"<!-- formal-conjectures:advisory-inline:v1:[a-z0-9-]+ -->", request["body"])
    if marker is None:
        raise AuditError("inline request lacks its stable marker")
    matches = [
        comment for comment in comments(load(args.comments))
        if comment.get("user", {}).get("login") == bot_login(args.app_slug)
        and marker.group(0) in (comment.get("body") or "")
    ]
    if len(matches) > 1:
        raise AuditError("more than one App inline suggestion exists")
    if not matches:
        result = {"action": "create", "comment_id": None}
    else:
        found = matches[0]
        found_line = found.get("line") if found.get("line") is not None else found.get("original_line")
        found_side = found.get("side") if found.get("side") is not None else found.get("original_side")
        if (found.get("commit_id"), found.get("path"), found_line, found_side) != (
            request["commit_id"], request["path"], request["line"], request["side"],
        ):
            raise AuditError("existing inline suggestion is bound to another head or line")
        result = {"action": "update", "comment_id": found["id"]}
    write(args.output, json.dumps(result, separators=(",", ":")) + "\n")


def verify_head(args: argparse.Namespace) -> None:
    live = load(args.live_pr)
    if (
        live.get("number") != args.pull_request
        or live.get("base", {}).get("repo", {}).get("full_name", "").casefold()
        != f"{args.owner}/{args.repository}".casefold()
    ):
        raise AuditError("live pull request identity mismatch")
    observed = live.get("head", {}).get("sha")
    if observed != args.expected_head:
        raise AuditError(f"head changed from {args.expected_head} to {observed}; refusing stale publication")
    value = {"repository": {"owner": args.owner, "name": args.repository}, "pull_request": args.pull_request,
             "head_commit_oid": args.expected_head, "stale": False, "authority_effect": "none"}
    write(args.output, json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("render")
    for name in ("core", "actionable", "source-root", "summary-output", "summary-payload", "inline-output",
                 "inline-create-payload", "inline-update-payload", "metadata-output"):
        p.add_argument(f"--{name}", type=Path, required=True)
    p.add_argument("--expected-head", required=True); p.add_argument("--run-url", required=True); p.add_argument("--artifact-name", required=True)
    p.add_argument("--phase", choices=("in-progress", "complete"), required=True)
    p.add_argument("--runtime-deterministic", type=Path)
    p = sub.add_parser("select-summary"); p.add_argument("--comments", type=Path, required=True); p.add_argument("--app-slug", required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("select-inline"); p.add_argument("--comments", type=Path, required=True); p.add_argument("--request", type=Path, required=True); p.add_argument("--app-slug", required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("verify-head"); p.add_argument("--live-pr", type=Path, required=True); p.add_argument("--owner", required=True); p.add_argument("--repository", required=True); p.add_argument("--pull-request", type=int, required=True); p.add_argument("--expected-head", required=True); p.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        {"render": render, "select-summary": select_summary, "select-inline": select_inline, "verify-head": verify_head}[args.command](args)
    except (AuditError, OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as error:
        print(f"external-pr-comment: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
