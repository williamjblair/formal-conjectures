from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "fc-contribution/v0"
MANDATORY_GATES = (
    "mechanical_validity",
    "semantic_fidelity",
    "resolution_validity",
    "priority",
    "provenance",
)
OPTIONAL_GATES = ("dependency_impact",)
VALID_STATUSES = {"pass", "fail", "unresolved", "not_applicable"}
ADVISORY_REVIEW_SCHEMA = "formal-conjectures.live-ai-review-role-result.v1"
ADVISORY_BINDABLE_GATES = {"semantic_fidelity", "resolution_validity", "priority", "provenance"}


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings)}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(_canonical_bytes(value))


def bind_advisory_review(
    manifest: dict[str, Any],
    gate_name: str,
    review: dict[str, Any],
    *,
    evidence_path: str,
    evidence_sha256: str,
    replace: bool = False,
) -> dict[str, Any]:
    """Bind one independent fc-review-bot result to an acceptance gate.

    The review remains advisory. The caller selects which semantic gate the
    review was commissioned to assess. Mechanical validity is deliberately not
    bindable from a model review.
    """
    if gate_name not in ADVISORY_BINDABLE_GATES:
        raise ValueError(
            f"advisory reviews may bind only {sorted(ADVISORY_BINDABLE_GATES)}; "
            f"got {gate_name!r}"
        )
    if review.get("schema_version") != ADVISORY_REVIEW_SCHEMA:
        raise ValueError("review schema_version is not the supported fc-review-bot v1 schema")
    if review.get("authority") != "advisory_model_review_only":
        raise ValueError("review authority must be advisory_model_review_only")
    if review.get("independent") is not True:
        raise ValueError("review must declare independent=true")
    if review.get("nonclaims") != ["maintainer_disposition", "mathematical_truth", "merge_decision"]:
        raise ValueError("review must preserve the fc-review-bot nonclaims boundary")
    outcome = review.get("outcome")
    if outcome not in {"pass", "fail", "inconclusive"}:
        raise ValueError("review outcome must be pass, fail, or inconclusive")
    if not isinstance(evidence_sha256, str) or len(evidence_sha256) != 64:
        raise ValueError("evidence_sha256 must be a 64-character digest")

    out = deepcopy(manifest)
    gates = out.setdefault("gates", {})
    gate = gates.setdefault(gate_name, {"status": "unresolved", "evidence": []})
    old_status = gate.get("status", "unresolved")
    if old_status != "unresolved" and not replace:
        raise ValueError(
            f"gates.{gate_name} is already {old_status!r}; pass replace=True to replace its status"
        )
    gate["status"] = {"pass": "pass", "fail": "fail", "inconclusive": "unresolved"}[outcome]
    evidence = gate.setdefault("evidence", [])
    evidence.append(
        {
            "kind": "fc-review-bot-advisory-review",
            "path": evidence_path,
            "sha256": evidence_sha256,
            "verifier": "fc-review-bot",
            "review_role": review.get("role"),
            "review_outcome": outcome,
            "exact_input_root": review.get("exact_input_root"),
        }
    )
    return out


def _require(mapping: dict[str, Any], key: str, prefix: str, errors: list[str]) -> Any:
    if key not in mapping:
        errors.append(f"{prefix}.{key}: missing required field")
        return None
    return mapping[key]


def _check_string(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: expected non-empty string")


def _resolve_local(root: Path, rel: str) -> Path:
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes root: {rel}") from exc
    return candidate


def check_manifest(manifest: dict[str, Any], root: str | Path = ".") -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []
    root_path = Path(root)

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: expected {SCHEMA_VERSION!r}")

    authority = manifest.get("authority")
    if not isinstance(authority, dict):
        errors.append("authority: expected object")
    else:
        for key in ("repository", "revision", "target"):
            value = _require(authority, key, "authority", errors)
            if value is not None:
                _check_string(value, f"authority.{key}", errors)

    contribution = manifest.get("contribution")
    if not isinstance(contribution, dict):
        errors.append("contribution: expected object")
    else:
        for key in ("kind", "relationship", "artifact"):
            value = _require(contribution, key, "contribution", errors)
            if value is not None:
                _check_string(value, f"contribution.{key}", errors)

    gates = manifest.get("gates")
    if not isinstance(gates, dict):
        errors.append("gates: expected object")
        gates = {}

    for gate_name in MANDATORY_GATES:
        if gate_name not in gates:
            errors.append(f"gates.{gate_name}: missing mandatory gate")

    known_gates = set(MANDATORY_GATES) | set(OPTIONAL_GATES)
    for gate_name, gate in gates.items():
        if gate_name not in known_gates:
            warnings.append(f"gates.{gate_name}: unknown gate retained but ignored by v0 recommendation")
        if not isinstance(gate, dict):
            errors.append(f"gates.{gate_name}: expected object")
            continue
        status = gate.get("status")
        if status not in VALID_STATUSES:
            errors.append(
                f"gates.{gate_name}.status: expected one of {sorted(VALID_STATUSES)}, got {status!r}"
            )
        evidence = gate.get("evidence", [])
        if not isinstance(evidence, list):
            errors.append(f"gates.{gate_name}.evidence: expected array")
            continue
        if status in {"pass", "fail"} and not evidence:
            warnings.append(f"gates.{gate_name}: {status} with no evidence references")
        for i, ref in enumerate(evidence):
            path = f"gates.{gate_name}.evidence[{i}]"
            if not isinstance(ref, dict):
                errors.append(f"{path}: expected object")
                continue
            kind = ref.get("kind")
            if not isinstance(kind, str) or not kind.strip():
                errors.append(f"{path}.kind: expected non-empty string")
            local_path = ref.get("path")
            url = ref.get("url")
            if not local_path and not url:
                errors.append(f"{path}: requires path or url")
                continue
            if local_path:
                if not isinstance(local_path, str):
                    errors.append(f"{path}.path: expected string")
                    continue
                try:
                    resolved = _resolve_local(root_path, local_path)
                except ValueError as exc:
                    errors.append(f"{path}.path: {exc}")
                    continue
                if not resolved.is_file():
                    errors.append(f"{path}.path: file not found: {local_path}")
                    continue
                expected_hash = ref.get("sha256")
                if expected_hash is not None:
                    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
                        errors.append(f"{path}.sha256: expected 64-character hex digest")
                    else:
                        actual_hash = sha256_bytes(resolved.read_bytes())
                        if actual_hash.lower() != expected_hash.lower():
                            errors.append(
                                f"{path}.sha256: mismatch expected {expected_hash.lower()} got {actual_hash}"
                            )
            if url is not None and (not isinstance(url, str) or not url.strip()):
                errors.append(f"{path}.url: expected non-empty string")

    producer = manifest.get("producer")
    if not isinstance(producer, dict):
        errors.append("producer: expected object")
    else:
        for key in ("name", "type"):
            value = _require(producer, key, "producer", errors)
            if value is not None:
                _check_string(value, f"producer.{key}", errors)

    return CheckResult(ok=not errors, errors=tuple(errors), warnings=tuple(warnings))


def recommend(manifest: dict[str, Any]) -> str:
    gates = manifest.get("gates", {})

    def status(name: str) -> str:
        gate = gates.get(name, {})
        return gate.get("status", "unresolved") if isinstance(gate, dict) else "unresolved"

    if status("mechanical_validity") == "fail":
        return "INVALID"
    if status("semantic_fidelity") == "fail":
        return "FIDELITY_FAILED"
    if status("resolution_validity") == "fail":
        return "DOES_NOT_RESOLVE_TARGET"
    if status("provenance") == "fail":
        return "PROVENANCE_FAILED"
    if status("priority") == "fail":
        return "PRIORITY_CONFLICT"

    if status("mechanical_validity") == "unresolved":
        return "NEEDS_MECHANICAL_VERIFICATION"
    if status("semantic_fidelity") == "unresolved":
        return "NEEDS_FIDELITY_REVIEW"
    if status("resolution_validity") == "unresolved":
        return "NEEDS_RESOLUTION_REVIEW"
    if status("provenance") == "unresolved":
        return "NEEDS_PROVENANCE_REVIEW"
    if status("priority") == "unresolved":
        return "PRIORITY_UNRESOLVED"

    if all(status(name) in {"pass", "not_applicable"} for name in MANDATORY_GATES):
        return "READY_FOR_MAINTAINER_REVIEW"
    return "NEEDS_REVIEW"


def _materialize_evidence(manifest: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    materialized: list[dict[str, Any]] = []
    gates = manifest.get("gates", {})
    for gate_name in sorted(gates):
        gate = gates[gate_name]
        if not isinstance(gate, dict):
            continue
        for ref in gate.get("evidence", []):
            if not isinstance(ref, dict):
                continue
            item = {"gate": gate_name, **ref}
            if ref.get("path"):
                resolved = _resolve_local(root, ref["path"])
                if resolved.is_file():
                    item["observed_sha256"] = sha256_bytes(resolved.read_bytes())
                    item["bytes"] = resolved.stat().st_size
            materialized.append(item)
    return materialized


def build_packet(manifest: dict[str, Any], root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    check = check_manifest(manifest, root_path)
    evidence = _materialize_evidence(manifest, root_path) if check.ok else []
    body = {
        "packet_version": "fc-contribution-packet/v0",
        "manifest_sha256": canonical_sha256(manifest),
        "authority": manifest.get("authority"),
        "producer": manifest.get("producer"),
        "contribution": manifest.get("contribution"),
        "gate_summary": {
            name: gate.get("status") if isinstance(gate, dict) else "unresolved"
            for name, gate in sorted(manifest.get("gates", {}).items())
        },
        "recommendation": recommend(manifest),
        "checks": check.as_dict(),
        "evidence": evidence,
        "authority_note": (
            "This packet is advisory. It does not approve, merge, publish, or establish scientific priority. "
            "The authoritative repository and its maintainers retain the acceptance decision."
        ),
    }
    body["packet_sha256"] = canonical_sha256(body)
    return body
