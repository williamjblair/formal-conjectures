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

"""Finalize a pinned external-PR advisory review from retained role outputs."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from typing import Any

from pr_audit import (
    AuditError,
    canonical_bytes,
    generate_core,
    parse_json_bytes,
    render_markdown,
    sha256_digest,
    write_canonical,
)


REQUEST_VERSION = "formal-conjectures.external-pr-review-request.v1"
ROLE_VERSION = "formal-conjectures.pr-audit-clean-room-role-result.v1"
OID_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
ROLE_AUTHORITIES = {
    "source_fidelity": "advisory_packet_preparation_only",
    "lean_semantics": "advisory_packet_preparation_only",
    "adversarial_edge_cases": "advisory_packet_preparation_only",
    "deterministic_verification": "producer_evidence_only",
}
NONCLAIMS = ["maintainer_disposition", "mathematical_truth", "merge_decision"]


class StaleReviewError(AuditError):
    """Raised when the observed PR head differs from the pinned review head."""


def _dict(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditError(f"{location} must be an object")
    return value


def _exact_keys(value: dict[str, Any], keys: set[str], location: str) -> None:
    if set(value) != keys:
        raise AuditError(f"{location} keys do not match the v1 contract")


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise AuditError(f"{location} must be a nonempty string")
    return value


def _path(root: Path, value: Any, location: str) -> Path:
    text = _string(value, location)
    candidate = (root / text).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise AuditError(f"{location} escapes the request directory") from error
    return candidate


def _load(path: Path, *, canonical: bool) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = _dict(parse_json_bytes(raw, label=str(path)), str(path))
    if canonical and raw != canonical_bytes(value) + b"\n":
        raise AuditError(f"{path} must use canonical JSON with one LF")
    return value, raw


def _validate_role(value: dict[str, Any], role: str, source_root: str) -> None:
    _exact_keys(
        value,
        {
            "schema_version", "role", "authority", "independent", "exact_input_root",
            "outcome", "severity", "findings", "witnesses", "limitations", "nonclaims",
        },
        f"role result {role}",
    )
    if value["schema_version"] != ROLE_VERSION or value["role"] != role:
        raise AuditError(f"role result {role} has the wrong schema or role")
    if value["authority"] != ROLE_AUTHORITIES[role] or value["independent"] is not False:
        raise AuditError(f"role result {role} claims unsupported authority or independence")
    if value["exact_input_root"] != source_root:
        raise AuditError(f"role result {role} is stale for the pinned head source")
    outcome = value["outcome"]
    severity = value["severity"]
    if outcome not in {"pass", "fail", "inconclusive", "error", "unavailable"}:
        raise AuditError(f"role result {role} has an unsupported outcome")
    if severity not in {"none", "nit", "meaning"}:
        raise AuditError(f"role result {role} has an unsupported severity")
    if (outcome == "fail") != (severity != "none"):
        raise AuditError(f"role result {role} outcome and severity are inconsistent")
    for field in ("findings", "witnesses", "limitations"):
        if not isinstance(value[field], list) or not value[field] or any(
            not _nonempty_evidence_value(item) for item in value[field]
        ):
            raise AuditError(
                f"role result {role}.{field} must contain nonempty strings or structured evidence objects"
            )
    if value["nonclaims"] != NONCLAIMS:
        raise AuditError(f"role result {role} omits the advisory authority boundary")


def _nonempty_evidence_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value)
    if isinstance(value, list):
        return bool(value) and all(_nonempty_evidence_value(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and all(
            isinstance(key, str) and bool(key) and _nonempty_evidence_value(item)
            for key, item in value.items()
        )
    if isinstance(value, (bool, int)) or value is None:
        return True
    return False


def _safe(value: Any) -> str:
    text = "".join(" " if ord(character) < 0x20 else character for character in str(value))
    text = html.escape(text, quote=True)
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", text)


def render_comment(core: dict[str, Any]) -> str:
    repository = core["repository"]
    lines = [
        "## Advisory Formal Conjectures review",
        "",
        f"Pinned `{_safe(repository['repository']['owner'])}/{_safe(repository['repository']['name'])}` "
        f"PR #{repository['pull_request']['number']} at `{repository['head']['commit_oid']}`.",
        "",
        f"Advisory disposition: **{_safe(core['disposition']['advisory'])}**",
        "",
    ]
    for check in core["checks"]:
        lines.append(
            f"- `{_safe(check['id'])}` ({_safe(check['property'])}): **{_safe(check['outcome'])}**"
        )
        for evidence in check["evidence"]:
            lines.append(f"  - {_safe(evidence['statement'])}")
    lines.extend([
        "",
        f"Machine-readable core: `{core['root']}`",
        "",
        "This automated report is advisory only. It is not maintainer disposition, acceptance, a merge decision, or a claim of mathematical truth.",
        "",
    ])
    return "\n".join(lines)


def finalize(request_path: Path, observed_head: str, output_dir: Path) -> dict[str, Path]:
    if OID_RE.fullmatch(observed_head) is None:
        raise AuditError("--observed-head must be a 40-character lowercase Git OID")
    request, _ = _load(request_path, canonical=False)
    _exact_keys(
        request,
        {"schema_version", "skill", "repository", "pull_request", "scope", "core_input", "roles", "outputs", "publication"},
        "review request",
    )
    if request["schema_version"] != REQUEST_VERSION:
        raise AuditError("unsupported external review request schema")
    if request["skill"] != ".agents/skills/review-formal-conjectures-pr/SKILL.md":
        raise AuditError("review request does not select the established FC review skill")
    root = request_path.parent.resolve()
    repository = _dict(request["repository"], "review request.repository")
    _exact_keys(repository, {"owner", "name", "url"}, "review request.repository")
    pull_request = _dict(request["pull_request"], "review request.pull_request")
    _exact_keys(
        pull_request,
        {"number", "url", "base_commit_oid", "head_commit_oid"},
        "review request.pull_request",
    )
    pinned_head = _string(pull_request["head_commit_oid"], "review request head")
    if OID_RE.fullmatch(pinned_head) is None:
        raise AuditError("review request head is not a Git OID")
    if observed_head != pinned_head:
        raise StaleReviewError(
            f"stale review: observed head {observed_head} differs from pinned head {pinned_head}; prepare a new packet and rerun all roles"
        )
    scope = _dict(request["scope"], "review request.scope")
    _exact_keys(scope, {"path", "declaration", "head_source_root"}, "review request.scope")
    source_root = _string(scope["head_source_root"], "review request source root")
    if SHA_RE.fullmatch(source_root) is None:
        raise AuditError("review request source root is not a sha256 identity")
    roles = _dict(request["roles"], "review request.roles")
    if set(roles) != set(ROLE_AUTHORITIES):
        raise AuditError("review request must name the four isolated v1 roles")
    role_artifacts: dict[str, tuple[str, str]] = {}
    for role in ROLE_AUTHORITIES:
        binding = _dict(roles[role], f"review request.roles.{role}")
        _exact_keys(binding, {"artifact_id", "path"}, f"review request.roles.{role}")
        role_path = _path(root, binding["path"], f"review request.roles.{role}.path")
        role_value, role_raw = _load(role_path, canonical=True)
        _validate_role(role_value, role, source_root)
        role_artifacts[role] = (_string(binding["artifact_id"], "role artifact id"), sha256_digest(role_raw))

    core_input = _path(root, request["core_input"], "review request.core_input")
    core = generate_core(core_input)
    core_repository = core["repository"]
    expected_repository = {
        "owner": repository["owner"], "name": repository["name"], "url": repository["url"]
    }
    actual_repository = {
        key: core_repository["repository"][key] for key in ("owner", "name", "url")
    }
    if actual_repository != expected_repository:
        raise AuditError("generated core repository does not match the pinned request")
    if core_repository["pull_request"] != {
        "number": pull_request["number"], "url": pull_request["url"]
    }:
        raise AuditError("generated core PR identity does not match the pinned request")
    if core_repository["base"]["commit_oid"] != pull_request["base_commit_oid"] or core_repository["head"]["commit_oid"] != pinned_head:
        raise AuditError("generated core revision does not match the pinned request")
    source_check = next(
        (check for check in core["checks"] if check["property"] == "source-statement-fidelity"),
        None,
    )
    if source_check is None or source_check["scope"] != {
        "revision": "head", "paths": [scope["path"]], "declarations": [scope["declaration"]]
    }:
        raise AuditError("generated core does not bind the requested declaration scope")
    inputs_by_artifact = {item["artifact_id"]: item["root"] for item in source_check["inputs"]}
    for role, (artifact_id, digest) in role_artifacts.items():
        if inputs_by_artifact.get(artifact_id) != digest:
            raise AuditError(f"generated core does not bind the exact {role} role output")
    if "not_an_acceptance_or_merge_decision" not in core["disposition"]["nonclaims"]:
        raise AuditError("generated core omits the advisory no-acceptance boundary")

    publication = _dict(request["publication"], "review request.publication")
    if publication != {"github_write": False, "mode": "local_draft_only"}:
        raise AuditError("review request publication must remain local_draft_only with no GitHub write")
    outputs = _dict(request["outputs"], "review request.outputs")
    _exact_keys(outputs, {"core", "review_report", "pr_comment"}, "review request.outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    destinations = {
        key: _path(output_dir.resolve(), value, f"review request.outputs.{key}")
        for key, value in outputs.items()
    }
    write_canonical(destinations["core"], core, sidecar=True)
    destinations["review_report"].write_text(render_markdown(core), encoding="utf-8")
    destinations["pr_comment"].write_text(render_comment(core), encoding="utf-8")
    return destinations


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--request", required=True, help="pinned external review request JSON")
    result.add_argument("--observed-head", required=True, help="freshly observed PR head Git OID")
    result.add_argument("--output-dir", required=True, help="local output directory")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        destinations = finalize(Path(args.request), args.observed_head, Path(args.output_dir))
    except StaleReviewError as error:
        print(f"external-pr-review: {error}", file=sys.stderr)
        return 3
    except (AuditError, OSError, UnicodeError) as error:
        print(f"external-pr-review: {error}", file=sys.stderr)
        return 2
    for key, destination in sorted(destinations.items()):
        print(f"{key}: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
