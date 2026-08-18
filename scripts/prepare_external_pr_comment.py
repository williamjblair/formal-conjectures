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

"""Prepare and safely select the stable advisory comment for an external PR."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pr_audit import AuditError, parse_json_bytes


COMMENT_MARKER = "<!-- formal-conjectures:advisory-review:v1 -->"
MAX_COMMENT_BYTES = 60_000
OID_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _text(path: Path, description: str) -> str:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise AuditError(f"cannot read {description}: {error}") from error
    if len(raw) > MAX_COMMENT_BYTES:
        raise AuditError(f"{description} exceeds {MAX_COMMENT_BYTES} bytes")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AuditError(f"{description} is not UTF-8") from error


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def render_comment(
    draft_path: Path,
    output_path: Path,
    payload_path: Path,
    expected_head: str,
    run_url: str,
    artifact_name: str,
) -> None:
    if not OID_PATTERN.fullmatch(expected_head):
        raise AuditError("expected head must be a lowercase 40-character Git OID")
    if not run_url.startswith("https://github.com/") or "/actions/runs/" not in run_url:
        raise AuditError("workflow run URL must be an HTTPS github.com Actions run URL")
    if not artifact_name or any(character in artifact_name for character in "\r\n`"):
        raise AuditError("artifact name is empty or contains an unsafe character")

    draft = _text(draft_path, "advisory comment draft").strip()
    required = {
        f"`{expected_head}`": "exact pull request head",
        "Advisory disposition: **": "advisory disposition",
        "`source\\-statement\\-fidelity`": "semantic source-fidelity finding",
        "Fresh deterministic outcome at the pinned head: **": "fresh deterministic outcome",
        "not maintainer disposition, acceptance, a merge decision, or a claim of mathematical truth":
            "authority boundary",
    }
    for fragment, description in required.items():
        if fragment not in draft:
            raise AuditError(f"advisory comment draft is missing {description}")

    body = (
        f"{COMMENT_MARKER}\n\n{draft}\n\n---\n"
        f"Workflow evidence: [Actions run]({run_url}); artifact `{artifact_name}`.\n"
        "The machine-readable JSON report in that artifact is authoritative over this Markdown projection.\n"
    )
    if len(body.encode("utf-8")) > MAX_COMMENT_BYTES:
        raise AuditError(f"rendered comment exceeds {MAX_COMMENT_BYTES} bytes")
    _write(output_path, body)
    _write(payload_path, json.dumps({"body": body}, ensure_ascii=False, separators=(",", ":")) + "\n")


def _comments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise AuditError("GitHub comments response must be an array")
    flattened: list[Any] = []
    for item in value:
        if isinstance(item, list):
            flattened.extend(item)
        else:
            flattened.append(item)
    if len(flattened) > 10_000:
        raise AuditError("GitHub comments response is unexpectedly large")
    if not all(isinstance(item, dict) for item in flattened):
        raise AuditError("GitHub comments response contains a non-object")
    return flattened


def select_comment(comments_path: Path, app_slug: str, output_path: Path) -> None:
    if not app_slug or app_slug.endswith("[bot]") or any(character.isspace() for character in app_slug):
        raise AuditError("GitHub App slug is malformed")
    value = parse_json_bytes(comments_path.read_bytes())
    expected_login = f"{app_slug}[bot]"
    matches: list[int] = []
    for comment in _comments(value):
        user = comment.get("user")
        if not isinstance(user, dict) or user.get("login") != expected_login:
            continue
        body = comment.get("body")
        identifier = comment.get("id")
        if isinstance(body, str) and COMMENT_MARKER in body:
            if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
                raise AuditError("matching GitHub comment has an invalid id")
            matches.append(identifier)
    if len(matches) > 1:
        raise AuditError("more than one App-authored advisory comment exists; refusing to add or update")
    decision = {"action": "update", "comment_id": matches[0]} if matches else {
        "action": "create", "comment_id": None,
    }
    _write(output_path, json.dumps(decision, separators=(",", ":")) + "\n")


def verify_head(
    live_pr_path: Path,
    owner: str,
    repository: str,
    pull_request: int,
    expected_head: str,
    output_path: Path,
) -> None:
    if not OID_PATTERN.fullmatch(expected_head):
        raise AuditError("expected head must be a lowercase 40-character Git OID")
    value = parse_json_bytes(live_pr_path.read_bytes())
    if not isinstance(value, dict):
        raise AuditError("live pull request response must be an object")
    try:
        observed_number = value["number"]
        observed_head = value["head"]["sha"]
        full_name = value["base"]["repo"]["full_name"]
    except (KeyError, TypeError) as error:
        raise AuditError("live pull request response lacks number, head.sha, or base.repo.full_name") from error
    expected_full_name = f"{owner}/{repository}"
    if observed_number != pull_request or full_name.casefold() != expected_full_name.casefold():
        raise AuditError("live pull request identity does not match the requested base repository and number")
    if observed_head != expected_head:
        raise AuditError(
            f"pull request head changed from {expected_head} to {observed_head}; refusing stale publication"
        )
    result = {
        "schema_version": "formal-conjectures.external-pr-comment-binding.v1",
        "repository": {"owner": owner, "name": repository},
        "pull_request": pull_request,
        "head_commit_oid": expected_head,
        "stale": False,
        "authority_effect": "none",
    }
    _write(output_path, json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render")
    render.add_argument("--draft", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--payload-output", type=Path, required=True)
    render.add_argument("--expected-head", required=True)
    render.add_argument("--run-url", required=True)
    render.add_argument("--artifact-name", required=True)

    select = commands.add_parser("select")
    select.add_argument("--comments", type=Path, required=True)
    select.add_argument("--app-slug", required=True)
    select.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify-head")
    verify.add_argument("--live-pr", type=Path, required=True)
    verify.add_argument("--owner", required=True)
    verify.add_argument("--repository", required=True)
    verify.add_argument("--pull-request", type=int, required=True)
    verify.add_argument("--expected-head", required=True)
    verify.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "render":
            render_comment(
                arguments.draft,
                arguments.output,
                arguments.payload_output,
                arguments.expected_head,
                arguments.run_url,
                arguments.artifact_name,
            )
        elif arguments.command == "select":
            select_comment(arguments.comments, arguments.app_slug, arguments.output)
        else:
            verify_head(
                arguments.live_pr,
                arguments.owner,
                arguments.repository,
                arguments.pull_request,
                arguments.expected_head,
                arguments.output,
            )
    except (AuditError, OSError) as error:
        print(f"external-pr-comment: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
