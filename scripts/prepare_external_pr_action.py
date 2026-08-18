#!/usr/bin/env python3
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

"""Bind a manual external-PR dispatch and retain its deterministic result."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from pr_audit import AuditError, parse_json_bytes, write_canonical
from run_external_pr_review import (
    NONCLAIMS,
    OID_RE,
    REQUEST_VERSION,
    ROLE_VERSION,
    StaleReviewError,
)


SLUG_RE = re.compile(r"[A-Za-z0-9_.-]+\Z")
BINDING_VERSION = "formal-conjectures.external-pr-workflow-binding.v1"


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditError(f"{location} must be an object")
    return value


def _load(path: Path) -> dict[str, Any]:
    return _object(parse_json_bytes(path.read_bytes(), label=str(path)), str(path))


def _request(path: Path) -> dict[str, Any]:
    request = _load(path)
    if request.get("schema_version") != REQUEST_VERSION:
        raise AuditError("unsupported external review request schema")
    return request


def _slug(value: str, location: str) -> str:
    if SLUG_RE.fullmatch(value) is None:
        raise AuditError(f"{location} must be a GitHub owner or repository slug")
    return value


def bind(args: argparse.Namespace) -> None:
    request = _request(Path(args.request))
    owner = _slug(args.owner, "--owner")
    repository_name = _slug(args.repository, "--repository")
    try:
        number = int(args.pull_request)
    except ValueError as error:
        raise AuditError("--pull-request must be a positive integer") from error
    if number < 1:
        raise AuditError("--pull-request must be a positive integer")
    if OID_RE.fullmatch(args.expected_head) is None:
        raise AuditError("--expected-head must be a lowercase 40-character Git OID")

    configured_repository = _object(request.get("repository"), "review request.repository")
    configured_pr = _object(request.get("pull_request"), "review request.pull_request")
    if (configured_repository.get("owner"), configured_repository.get("name")) != (owner, repository_name):
        raise AuditError("dispatch repository differs from the retained request")
    if configured_pr.get("number") != number:
        raise AuditError("dispatch pull-request number differs from the retained request")
    if configured_pr.get("head_commit_oid") != args.expected_head:
        raise AuditError("dispatch expected head differs from the retained request")

    live = _load(Path(args.live_pr))
    live_base = _object(live.get("base"), "live pull request.base")
    live_head = _object(live.get("head"), "live pull request.head")
    observed_head = live_head.get("sha")
    if observed_head != args.expected_head:
        raise StaleReviewError(
            f"stale review: observed head {observed_head!r} differs from pinned head {args.expected_head}; prepare a new packet and rerun every role"
        )
    if live.get("number") != number or live.get("html_url") != configured_pr.get("url"):
        raise AuditError("live pull-request identity differs from the retained request")
    if live_base.get("sha") != configured_pr.get("base_commit_oid"):
        raise AuditError("live base commit differs from the retained request")
    if args.checked_out_head != args.expected_head:
        raise StaleReviewError("checked-out pull-request head differs from the pinned head")

    write_canonical(Path(args.output), {
        "schema_version": BINDING_VERSION,
        "authority": "producer_evidence_only",
        "repository": {"owner": owner, "name": repository_name},
        "pull_request": number,
        "base_commit_oid": live_base["sha"],
        "head_commit_oid": observed_head,
        "checked_out_head_commit_oid": args.checked_out_head,
        "stale": False,
        "github_write": False,
        "nonclaims": NONCLAIMS,
    })


def _typed_status(exit_code: int) -> str:
    if exit_code == 0:
        return "pass"
    if exit_code in {124, 126, 127}:
        return "error"
    return "fail"


def capture(args: argparse.Namespace) -> None:
    request_path = Path(args.request)
    request = _request(request_path)
    scope = _object(request.get("scope"), "review request.scope")
    roles = _object(request.get("roles"), "review request.roles")
    deterministic = _object(roles.get("deterministic_verification"), "deterministic role binding")
    if args.output is None:
        role_path = (request_path.parent / str(deterministic.get("path"))).resolve()
        try:
            role_path.relative_to(request_path.parent.resolve())
        except ValueError as error:
            raise AuditError("deterministic role path escapes the request directory") from error
    else:
        role_path = Path(args.output)

    statuses = {
        "lean_build": _typed_status(args.build_exit),
        "diff_check": _typed_status(args.style_exit),
    }
    outcome = "error" if "error" in statuses.values() else "fail" if "fail" in statuses.values() else "pass"
    severity = "meaning" if outcome == "fail" else "none"
    findings = [
        f"lake --wfail build {args.build_target}: {statuses['lean_build']} (exit {args.build_exit}).",
        f"git diff --check at the pinned base and head: {statuses['diff_check']} (exit {args.style_exit}).",
    ]
    if outcome == "error":
        findings.append("At least one deterministic command did not complete as a bounded check; this is a typed error, not a review failure.")
    write_canonical(role_path, {
        "schema_version": ROLE_VERSION,
        "role": "deterministic_verification",
        "authority": "producer_evidence_only",
        "independent": False,
        "exact_input_root": scope.get("head_source_root"),
        "outcome": outcome,
        "severity": severity,
        "findings": findings,
        "witnesses": [
            f"Exact head {request['pull_request']['head_commit_oid']} was checked after the live-head binding passed.",
            f"The checked module target was {args.build_target}.",
        ],
        "limitations": [
            "A successful Lean build and whitespace check do not establish source fidelity or mathematical truth.",
            "Command logs are workflow artifacts; this role result retains only typed command outcomes.",
        ],
        "nonclaims": NONCLAIMS,
    })


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    bind_parser = commands.add_parser("bind", help="bind live and checked-out state to a retained request")
    bind_parser.add_argument("--request", required=True)
    bind_parser.add_argument("--live-pr", required=True)
    bind_parser.add_argument("--owner", required=True)
    bind_parser.add_argument("--repository", required=True)
    bind_parser.add_argument("--pull-request", required=True)
    bind_parser.add_argument("--expected-head", required=True)
    bind_parser.add_argument("--checked-out-head", required=True)
    bind_parser.add_argument("--output", required=True)
    bind_parser.set_defaults(handler=bind)
    capture_parser = commands.add_parser("capture", help="write the deterministic role result")
    capture_parser.add_argument("--request", required=True)
    capture_parser.add_argument("--build-target", required=True)
    capture_parser.add_argument("--build-exit", required=True, type=int)
    capture_parser.add_argument("--style-exit", required=True, type=int)
    capture_parser.add_argument(
        "--output",
        help="optional runtime evidence path; omit only when preparing the retained packet",
    )
    capture_parser.set_defaults(handler=capture)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        args.handler(args)
    except StaleReviewError as error:
        print(f"external-pr-action: {error}", file=sys.stderr)
        return 3
    except (AuditError, OSError, UnicodeError) as error:
        print(f"external-pr-action: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
