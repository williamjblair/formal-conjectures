#!/usr/bin/env python3
# Copyright 2026 The Formal Conjectures Authors.
# Licensed under the Apache License, Version 2.0 (the "License");

"""Prepare, validate, and render exact-head live AI PR review evidence."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from pr_audit import AuditError, content_root, parse_json_bytes, sha256_digest, write_canonical


CONFIG_VERSION = "formal-conjectures.live-ai-review-config.v1"
INPUT_VERSION = "formal-conjectures.live-ai-review-input.v1"
ROLE_VERSION = "formal-conjectures.live-ai-review-role-result.v1"
PANEL_VERSION = "formal-conjectures.live-ai-review-panel.v1"
SUGGESTION_VERSION = "formal-conjectures.live-ai-suggestion-validation.v1"
OID = re.compile(r"^[0-9a-f]{40}$")
SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
ROLES = ("source_fidelity", "lean_semantics", "adversarial_edge_cases")
NONCLAIMS = ["maintainer_disposition", "mathematical_truth", "merge_decision"]
SUMMARY_MARKER = "<!-- formal-conjectures:live-ai-review:v1 -->"
INLINE_PREFIX = "formal-conjectures:live-ai-inline:v1:"


def obj(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditError(f"{location} must be an object")
    return value


def exact(value: Any, keys: set[str], location: str) -> dict[str, Any]:
    value = obj(value, location)
    if set(value) != keys:
        raise AuditError(f"{location} keys do not match the contract")
    return value


def string(value: Any, location: str, limit: int = 8_000) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise AuditError(f"{location} must be a nonempty bounded string")
    return value


def load(path: Path) -> dict[str, Any]:
    return obj(parse_json_bytes(path.read_bytes(), label=str(path)), str(path))


def safe_relative(root: Path, text: str, location: str) -> Path:
    pure = PurePosixPath(string(text, location, 500))
    if pure.is_absolute() or ".." in pure.parts or str(pure) != text:
        raise AuditError(f"{location} must be a normalized relative path")
    path = (root / text).resolve()
    path.relative_to(root.resolve())
    return path


def digest(path: Path) -> str:
    return sha256_digest(path.read_bytes())


def validated_config(path: Path) -> dict[str, Any]:
    value = exact(load(path), {"schema_version", "repository", "scope", "sources", "nonclaims"}, "config")
    if value["schema_version"] != CONFIG_VERSION or value["nonclaims"] != NONCLAIMS:
        raise AuditError("unsupported live AI config or authority boundary")
    repository = exact(
        value["repository"],
        {"owner", "name", "url", "pull_request", "base_commit_oid", "head_commit_oid"},
        "config.repository",
    )
    if not isinstance(repository["pull_request"], int) or repository["pull_request"] < 1:
        raise AuditError("config pull request must be positive")
    for key in ("base_commit_oid", "head_commit_oid"):
        if not isinstance(repository[key], str) or OID.fullmatch(repository[key]) is None:
            raise AuditError(f"config {key} is not a Git OID")
    scope = exact(value["scope"], {"path", "declaration", "head_source_root"}, "config.scope")
    if SHA.fullmatch(str(scope["head_source_root"])) is None:
        raise AuditError("config head source root is not a sha256 identity")
    if not isinstance(value["sources"], list) or not value["sources"]:
        raise AuditError("config must retain at least one source")
    seen: set[str] = set()
    for index, item in enumerate(value["sources"]):
        item = exact(item, {"id", "locator", "path", "sha256"}, f"config.sources[{index}]")
        identifier = string(item["id"], "source id", 100)
        if identifier in seen or SHA.fullmatch(str(item["sha256"])) is None:
            raise AuditError("source identities must be unique and content addressed")
        seen.add(identifier)
    return value


def prepare(args: argparse.Namespace) -> None:
    config_path = Path(args.config).resolve()
    config = validated_config(config_path)
    repository = config["repository"]
    scope = config["scope"]
    if args.expected_head != repository["head_commit_oid"]:
        raise AuditError("dispatch head differs from trusted live AI config")
    if args.publish_comment and not args.run_ai_review:
        raise AuditError("publication requires a real AI review execution")
    live = load(Path(args.live_pr))
    if (
        live.get("number") != repository["pull_request"]
        or live.get("html_url") != f"{repository['url']}/pull/{repository['pull_request']}"
        or live.get("base", {}).get("sha") != repository["base_commit_oid"]
        or live.get("head", {}).get("sha") != repository["head_commit_oid"]
    ):
        raise AuditError("live PR identity differs from the exact retained AI config")

    source_root = Path(args.source_root).resolve()
    head_source = safe_relative(source_root, scope["path"], "scope.path")
    if digest(head_source) != scope["head_source_root"]:
        raise AuditError("checked-out head source bytes differ from the retained identity")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(head_source, output / "head-source.lean")

    retained_sources = []
    for item in config["sources"]:
        source = safe_relative(config_path.parent, item["path"], "source.path")
        if digest(source) != item["sha256"]:
            raise AuditError(f"retained source {item['id']} digest mismatch")
        filename = f"source-{item['id']}.txt"
        shutil.copyfile(source, output / filename)
        retained_sources.append({
            "id": item["id"], "locator": item["locator"], "filename": filename, "sha256": item["sha256"],
        })

    schema_source = Path(args.output_schema).resolve()
    prompt_source = Path(args.prompt_template).resolve()
    shutil.copyfile(schema_source, output / "role-output.schema.json")
    manifest_without_root = {
        "schema_version": INPUT_VERSION,
        "repository": repository,
        "scope": {**scope, "head_source_filename": "head-source.lean"},
        "sources": retained_sources,
        "rubric_sha256": digest(prompt_source),
        "output_schema_sha256": digest(schema_source),
        "nonclaims": NONCLAIMS,
    }
    manifest = {**manifest_without_root, "root": content_root(manifest_without_root)}
    write_canonical(output / "input-manifest.json", manifest)
    template = prompt_source.read_text(encoding="utf-8")
    for role in ROLES:
        prompt = template.replace("{{ROLE}}", role).replace("{{INPUT_ROOT}}", manifest["root"])
        (output / f"prompt-{role}.md").write_text(prompt, encoding="utf-8", newline="\n")
    write_canonical(output / "preflight.json", {
        "schema_version": "formal-conjectures.live-ai-review-preflight.v1",
        "head_commit_oid": repository["head_commit_oid"],
        "input_root": manifest["root"],
        "run_ai_review": args.run_ai_review,
        "publish_comment": args.publish_comment,
        "authority_effect": "none",
    })


def validate_finding(value: Any, role: str, index: int) -> dict[str, Any]:
    finding = exact(
        value,
        {"id", "summary", "explanation", "severity", "path", "line", "witnesses", "suggestion"},
        f"{role}.findings[{index}]",
    )
    if finding["severity"] not in {"none", "nit", "meaning"}:
        raise AuditError("finding severity is unsupported")
    for key in ("id", "summary", "explanation"):
        string(finding[key], f"finding.{key}")
    if finding["path"] is not None:
        string(finding["path"], "finding.path", 500)
    if finding["line"] is not None and (not isinstance(finding["line"], int) or finding["line"] < 1):
        raise AuditError("finding line must be positive or null")
    if not isinstance(finding["witnesses"], list) or not finding["witnesses"]:
        raise AuditError("finding witnesses must be nonempty")
    suggestion = finding["suggestion"]
    if suggestion is not None:
        suggestion = exact(
            suggestion,
            {"confidence", "path", "line", "original", "replacement", "explanation"},
            "finding.suggestion",
        )
        if suggestion["confidence"] not in {"low", "medium", "high"}:
            raise AuditError("suggestion confidence is unsupported")
        if not isinstance(suggestion["line"], int) or suggestion["line"] < 1:
            raise AuditError("suggestion line must be positive")
        for key in ("path", "original", "replacement", "explanation"):
            string(suggestion[key], f"suggestion.{key}")
    return finding


def validate_role(value: dict[str, Any], expected_role: str, input_root: str) -> dict[str, Any]:
    value = exact(
        value,
        {"schema_version", "role", "authority", "independent", "exact_input_root", "outcome", "severity", "findings", "limitations", "nonclaims"},
        expected_role,
    )
    if (
        value["schema_version"] != ROLE_VERSION
        or value["role"] != expected_role
        or value["authority"] != "advisory_model_review_only"
        or value["independent"] is not True
        or value["exact_input_root"] != input_root
        or value["nonclaims"] != NONCLAIMS
    ):
        raise AuditError(f"{expected_role} output has stale identity or unsupported authority")
    if value["outcome"] not in {"pass", "fail", "inconclusive"}:
        raise AuditError("model role outcome is unsupported")
    if value["severity"] not in {"none", "nit", "meaning"}:
        raise AuditError("model role severity is unsupported")
    if (value["outcome"] == "fail") != (value["severity"] != "none"):
        raise AuditError("model role outcome and severity disagree")
    if not isinstance(value["findings"], list) or not value["findings"]:
        raise AuditError("model role must return bounded structured findings")
    if len(value["findings"]) > 8:
        raise AuditError("model role returned more than eight findings")
    value["findings"] = [validate_finding(item, expected_role, index) for index, item in enumerate(value["findings"])]
    if not isinstance(value["limitations"], list) or not value["limitations"]:
        raise AuditError("model role limitations must be nonempty")
    return value


def disposition(roles: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    meaning = [role for role, value in roles.items() if value["outcome"] == "fail" and value["severity"] == "meaning"]
    nits = [role for role, value in roles.items() if value["outcome"] == "fail" and value["severity"] == "nit"]
    inconclusive = [role for role, value in roles.items() if value["outcome"] == "inconclusive"]
    if meaning:
        return "needs_revision", sorted(meaning)
    if nits:
        return "nits_found", sorted(nits)
    if inconclusive:
        return "inconclusive", sorted(inconclusive)
    return "inconclusive", sorted(roles)


def validate_panel(args: argparse.Namespace) -> None:
    if OID.fullmatch(args.action_commit) is None:
        raise AuditError("model action commit is not a Git OID")
    if args.effort not in {"low", "medium", "high", "xhigh"}:
        raise AuditError("model effort is unsupported")
    if args.max_budget_usd_per_role not in {"1.00", "2.50", "5.00", "10.00"}:
        raise AuditError("model per-role budget is unsupported")
    if not args.github_run_id.isdigit() or not args.github_run_attempt.isdigit():
        raise AuditError("GitHub execution receipt is malformed")
    string(args.model, "model", 100)
    manifest = load(Path(args.input_manifest))
    if manifest.get("schema_version") != INPUT_VERSION or SHA.fullmatch(str(manifest.get("root"))) is None:
        raise AuditError("input manifest is unsupported")
    unrooted = {key: value for key, value in manifest.items() if key != "root"}
    if content_root(unrooted) != manifest["root"]:
        raise AuditError("input manifest root mismatch")
    roles: dict[str, dict[str, Any]] = {}
    receipts: dict[str, dict[str, Any]] = {}
    raw_outputs = Path(args.output_dir) / "raw-model-outputs"
    raw_outputs.mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        env_name = f"FC_AI_{role.upper()}_OUTPUT"
        raw = os.environ.get(env_name)
        if raw is None or not raw.strip():
            raise AuditError(f"actual model output is missing for {role}; stored role evidence is not a fallback")
        value = obj(parse_json_bytes(raw.encode(), label=env_name), env_name)
        roles[role] = validate_role(value, role, manifest["root"])
        session_name = f"FC_AI_{role.upper()}_SESSION_ID"
        session_id = os.environ.get(session_name)
        if session_id is None or not session_id.strip():
            raise AuditError(f"actual Claude session receipt is missing for {role}")
        receipts[role] = {
            "session_id": string(session_id, session_name, 200),
            "structured_output_root": content_root(roles[role]),
        }
        write_canonical(raw_outputs / f"{role}.json", roles[role])
    advisory, basis = disposition(roles)
    findings = [
        {"role": role, **finding}
        for role, value in roles.items()
        for finding in value["findings"]
        if finding["severity"] in {"nit", "meaning"}
    ]
    panel_without_root = {
        "schema_version": PANEL_VERSION,
        "repository": manifest["repository"],
        "scope": manifest["scope"],
        "input_root": manifest["root"],
        "execution": {
            "provider": "anthropic", "runner": "claude-code-action", "action_commit": args.action_commit,
            "model": args.model, "effort": args.effort,
            "max_budget_usd_per_role": args.max_budget_usd_per_role, "role_receipts": receipts,
            "github_run_id": args.github_run_id, "github_run_attempt": args.github_run_attempt,
            "prompt_roots": {role: digest(Path(args.input_manifest).parent / f"prompt-{role}.md") for role in ROLES},
            "output_schema_root": digest(Path(args.input_manifest).parent / "role-output.schema.json"),
        },
        "roles": roles,
        "findings": findings,
        "disposition": {"advisory": advisory, "basis": basis},
        "authority": "advisory_model_review_only",
        "nonclaims": NONCLAIMS,
    }
    write_canonical(Path(args.output_dir) / "ai-review-panel.json", {
        **panel_without_root, "root": content_root(panel_without_root),
    })


def validate_suggestion(args: argparse.Namespace) -> None:
    panel = load(Path(args.panel))
    if panel.get("schema_version") != PANEL_VERSION:
        raise AuditError("unsupported AI review panel")
    source_root = Path(args.source_root).resolve()
    expected_path = panel["scope"]["path"]
    candidates = []
    seen: set[str] = set()
    for finding in panel["findings"]:
        suggestion = finding.get("suggestion")
        if suggestion is not None and suggestion.get("confidence") == "high":
            key = f"{finding['role'].replace('_', '-')}-{finding['id']}"
            if key in seen:
                raise AuditError("model findings do not have unique role-scoped identities")
            seen.add(key)
            candidate: dict[str, Any] = {
                "key": key,
                "role": finding["role"],
                "finding_id": finding["id"],
                "status": "suppressed",
                "reason": "Suggestion path, line, or original text does not match the exact head.",
                "suggestion": suggestion,
            }
            path = suggestion["path"]
            source = safe_relative(source_root, path, "suggestion.path")
            lines = source.read_text(encoding="utf-8").splitlines()
            line = suggestion["line"]
            if path == expected_path and line <= len(lines) and lines[line - 1] == suggestion["original"]:
                candidate.update({
                    "status": "prepared",
                    "reason": "Exact-head replacement is eligible for isolated deterministic validation.",
                })
            candidates.append(candidate)
    result: dict[str, Any] = {
        "schema_version": SUGGESTION_VERSION,
        "input_panel_root": panel["root"],
        "outcome": "prepared" if any(item["status"] == "prepared" for item in candidates) else "unavailable",
        "candidates": candidates,
        "nonclaims": NONCLAIMS,
    }
    write_canonical(Path(args.output), result)


def candidate(value: dict[str, Any], key: str) -> dict[str, Any]:
    matches = [item for item in value.get("candidates", []) if item.get("key") == key]
    if len(matches) != 1:
        raise AuditError("suggestion key does not identify exactly one candidate")
    return matches[0]


def apply_suggestion(args: argparse.Namespace) -> None:
    value = load(Path(args.prepared))
    if value.get("schema_version") != SUGGESTION_VERSION:
        raise AuditError("unsupported suggestion validation input")
    item = candidate(value, args.key)
    if item["status"] != "prepared":
        raise AuditError("only an exact-head prepared suggestion may be applied for validation")
    suggestion = item["suggestion"]
    source = safe_relative(Path(args.source_root).resolve(), suggestion["path"], "suggestion.path")
    lines = source.read_text(encoding="utf-8").splitlines()
    line = suggestion["line"]
    if line > len(lines) or lines[line - 1] != suggestion["original"]:
        raise AuditError("source changed before suggestion validation")
    lines[line - 1:line] = suggestion["replacement"].splitlines()
    source.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def record_suggestion(args: argparse.Namespace) -> None:
    value = load(Path(args.prepared))
    if value.get("schema_version") != SUGGESTION_VERSION:
        raise AuditError("unsupported suggestion validation input")
    item = candidate(value, args.key)
    outcome = "pass" if args.build_exit == 0 and args.diff_exit == 0 else (
        "error" if args.build_exit in {124, 126, 127} else "fail"
    )
    write_canonical(Path(args.output), {
        "schema_version": "formal-conjectures.live-ai-suggestion-result.v1",
        "input_panel_root": value["input_panel_root"],
        "key": args.key,
        "outcome": outcome,
        "exit_codes": {"lean_build": args.build_exit, "diff_check": args.diff_exit},
        "reason": (
            "The localized replacement passed the exact module build and diff check."
            if outcome == "pass"
            else f"Suggestion suppressed: build exit {args.build_exit}, diff-check exit {args.diff_exit}."
        ),
        "suggestion": item["suggestion"] if outcome == "pass" else None,
        "nonclaims": NONCLAIMS,
    })


def aggregate_suggestions(args: argparse.Namespace) -> None:
    prepared = load(Path(args.prepared))
    if prepared.get("schema_version") != SUGGESTION_VERSION:
        raise AuditError("unsupported suggestion validation input")
    results_dir = Path(args.results_dir)
    validated = []
    suppressed = []
    for item in prepared["candidates"]:
        if item["status"] != "prepared":
            suppressed.append({"key": item["key"], "outcome": "unavailable", "reason": item["reason"]})
            continue
        result = load(results_dir / f"{item['key']}.json")
        if result.get("input_panel_root") != prepared["input_panel_root"] or result.get("key") != item["key"]:
            raise AuditError("suggestion result is stale or bound to another finding")
        if result.get("outcome") == "pass":
            validated.append({
                "key": item["key"], "role": item["role"], "finding_id": item["finding_id"],
                **result["suggestion"], "receipt": {"exit_codes": result["exit_codes"], "reason": result["reason"]},
            })
        else:
            suppressed.append({"key": item["key"], "outcome": result.get("outcome", "error"), "reason": result["reason"]})
    outcome = "pass" if validated and not suppressed else "partial" if validated else "unavailable"
    write_canonical(Path(args.output), {
        "schema_version": SUGGESTION_VERSION,
        "input_panel_root": prepared["input_panel_root"],
        "outcome": outcome,
        "validated": validated,
        "suppressed": suppressed,
        "nonclaims": NONCLAIMS,
    })


def capture_deterministic(args: argparse.Namespace) -> None:
    config = validated_config(Path(args.config))
    statuses = {
        "lean_build": "pass" if args.build_exit == 0 else "error" if args.build_exit in {124, 126, 127} else "fail",
        "diff_check": "pass" if args.diff_exit == 0 else "error" if args.diff_exit in {124, 126, 127} else "fail",
    }
    outcome = "error" if "error" in statuses.values() else "fail" if "fail" in statuses.values() else "pass"
    write_canonical(Path(args.output), {
        "schema_version": "formal-conjectures.live-ai-deterministic-result.v1",
        "authority": "producer_evidence_only",
        "head_commit_oid": config["repository"]["head_commit_oid"],
        "head_source_root": config["scope"]["head_source_root"],
        "build_target": args.build_target,
        "outcome": outcome,
        "checks": statuses,
        "exit_codes": {"lean_build": args.build_exit, "diff_check": args.diff_exit},
        "limitations": ["Build and diff checks do not establish source fidelity or mathematical truth."],
        "nonclaims": NONCLAIMS,
    })


def markdown_text(value: Any, limit: int = 500) -> str:
    text = string(value, "rendered text", limit).replace("\r", " ").replace("\n", " ")
    return text.replace("<", "&lt;").replace(">", "&gt;")


def render(args: argparse.Namespace) -> None:
    panel = load(Path(args.panel))
    deterministic = load(Path(args.deterministic)) if args.deterministic else None
    suggestion = load(Path(args.suggestion_validation)) if args.suggestion_validation else None
    head = panel["repository"]["head_commit_oid"]
    if args.expected_head != head:
        raise AuditError("render head differs from live AI panel")
    failed = len(panel["findings"])
    next_action = (
        panel["findings"][0]["summary"] if panel["findings"]
        else "No localized semantic repair was identified; complete human review before disposition."
    )
    validated = suggestion.get("validated", []) if suggestion else []
    inline_note = f" {len(validated)} validated inline suggestion(s) available." if validated else ""
    verification = (
        "**Status:** Review in progress — deterministic Lean verification is pending."
        if args.phase == "in-progress"
        else f"**Lean verification:** `{deterministic.get('outcome', 'error') if deterministic else 'error'}` at the pinned head."
    )
    summary = (
        f"{SUMMARY_MARKER}\n\n## FC Review Pilot — live AI advisory\n\n"
        f"**Verdict:** `{panel['disposition']['advisory']}` · **Findings:** {failed}\n\n"
        f"{verification}\n\n"
        f"**Next action:** {markdown_text(next_action)}{inline_note}\n\nPinned head: `{head}`\n\n"
        f"[Workflow evidence]({args.run_url}) · artifact `{args.artifact_name}`\n\n"
        "This review was produced by fresh isolated model executions and validated deterministically. "
        "It is advisory only, not maintainer disposition, acceptance, a merge decision, or mathematical truth.\n"
    )
    Path(args.summary).write_text(summary, encoding="utf-8", newline="\n")
    write_canonical(Path(args.summary_payload), {"body": summary})
    inline_dir = Path(args.inline_dir)
    inline_dir.mkdir(parents=True, exist_ok=True)
    inline_findings = []
    for item in validated:
        marker = f"<!-- {INLINE_PREFIX}{item['key']} -->"
        body = (
            f"{marker}\n\n{markdown_text(item['explanation'], 2_000)}\n\n```suggestion\n{item['replacement']}\n```\n\n"
            "This model-proposed change passed localized validation but remains advisory; it is not applied or approved.\n"
        )
        create = {"body": body, "commit_id": head, "path": item["path"], "line": item["line"], "side": "RIGHT"}
        payload = inline_dir / f"{item['key']}.json"
        write_canonical(payload, create)
        inline_findings.append({
            "key": item["key"], "payload": payload.name, "marker": marker,
            **{key: create[key] for key in ("commit_id", "path", "line", "side")},
        })
    write_canonical(Path(args.metadata), {
        "inline_count": len(inline_findings), "inline_findings": inline_findings, "finding_count": failed,
    })


def flattened_comments(path: Path) -> list[dict[str, Any]]:
    value = parse_json_bytes(path.read_bytes(), label=str(path))
    if not isinstance(value, list):
        raise AuditError("GitHub comments must be an array")
    result: list[dict[str, Any]] = []
    for item in value:
        values = item if isinstance(item, list) else [item]
        if not all(isinstance(entry, dict) for entry in values):
            raise AuditError("GitHub comments are malformed")
        result.extend(values)
    return result


def select_summary(args: argparse.Namespace) -> None:
    login = f"{string(args.app_slug, 'app slug', 100)}[bot]"
    matches = [item for item in flattened_comments(Path(args.comments))
               if item.get("user", {}).get("login") == login and SUMMARY_MARKER in (item.get("body") or "")]
    if len(matches) > 1:
        raise AuditError("more than one live AI summary comment exists")
    write_canonical(Path(args.output), {
        "action": "update" if matches else "create",
        "comment_id": matches[0]["id"] if matches else None,
    })


def select_inline(args: argparse.Namespace) -> None:
    request = load(Path(args.request))
    marker = re.search(r"<!-- formal-conjectures:live-ai-inline:v1:[a-z0-9-]+ -->", request.get("body", ""))
    if marker is None:
        raise AuditError("live AI inline request lacks a stable finding marker")
    login = f"{string(args.app_slug, 'app slug', 100)}[bot]"
    matches = [item for item in flattened_comments(Path(args.comments))
               if item.get("user", {}).get("login") == login and marker.group(0) in (item.get("body") or "")]
    if len(matches) > 1:
        raise AuditError("more than one inline comment exists for this finding")
    if matches:
        found = matches[0]
        line = found.get("line") if found.get("line") is not None else found.get("original_line")
        side = found.get("side") if found.get("side") is not None else found.get("original_side")
        if (found.get("commit_id"), found.get("path"), line, side) != (
            request["commit_id"], request["path"], request["line"], request["side"],
        ):
            raise AuditError("existing live AI finding is bound to another head or line")
    write_canonical(Path(args.output), {
        "action": "update" if matches else "create",
        "comment_id": matches[0]["id"] if matches else None,
    })


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for name in ("config", "live-pr", "source-root", "expected-head", "prompt-template", "output-schema", "output-dir"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--run-ai-review", action="store_true")
    p.add_argument("--publish-comment", action="store_true")
    p = sub.add_parser("validate-panel")
    for name in (
        "input-manifest", "output-dir", "action-commit", "model", "effort", "max-budget-usd-per-role",
        "github-run-id", "github-run-attempt",
    ):
        p.add_argument(f"--{name}", required=True)
    p = sub.add_parser("validate-suggestion")
    for name in ("panel", "source-root", "output"):
        p.add_argument(f"--{name}", required=True)
    p = sub.add_parser("apply-suggestion")
    for name in ("prepared", "key", "source-root"):
        p.add_argument(f"--{name}", required=True)
    p = sub.add_parser("record-suggestion")
    for name in ("prepared", "key", "output"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--build-exit", type=int, required=True)
    p.add_argument("--diff-exit", type=int, required=True)
    p = sub.add_parser("aggregate-suggestions")
    for name in ("prepared", "results-dir", "output"):
        p.add_argument(f"--{name}", required=True)
    p = sub.add_parser("capture-deterministic")
    for name in ("config", "build-target", "output"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--build-exit", type=int, required=True)
    p.add_argument("--diff-exit", type=int, required=True)
    p = sub.add_parser("render")
    for name in ("panel", "expected-head", "run-url", "artifact-name", "summary", "summary-payload", "inline-dir", "metadata"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--phase", choices=("in-progress", "complete"), required=True)
    p.add_argument("--deterministic")
    p.add_argument("--suggestion-validation")
    p = sub.add_parser("select-summary")
    for name in ("comments", "app-slug", "output"):
        p.add_argument(f"--{name}", required=True)
    p = sub.add_parser("select-inline")
    for name in ("comments", "request", "app-slug", "output"):
        p.add_argument(f"--{name}", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        {"prepare": prepare, "validate-panel": validate_panel, "validate-suggestion": validate_suggestion,
         "apply-suggestion": apply_suggestion, "record-suggestion": record_suggestion,
         "aggregate-suggestions": aggregate_suggestions, "capture-deterministic": capture_deterministic,
         "render": render, "select-summary": select_summary, "select-inline": select_inline}[args.command](args)
    except (AuditError, OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        print(f"live-ai-review: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
