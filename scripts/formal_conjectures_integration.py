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

"""Source-owned Formal Conjectures semantics above the shared Vela waist."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tomllib
from typing import Any, Mapping

from pr_audit import (
    AuditError,
    canonical_bytes,
    parse_json_bytes,
    sha256_digest,
    validate_core,
    validate_observation,
)


class IntegrationError(ValueError):
    """The source-owned integration packet is malformed or has drifted."""


CORE_CHECK_ENV = "VELA_INTEGRATION_CHECK_BIN"
CORE_CHECK_SCHEMA = "vela.cli.integration-check.v1"
CORE_METHOD_ID = "integration-validator"
CORE_METHOD_IMPLEMENTATION = "scripts/formal_conjectures_integration.py"
CORE_METHOD_ENVIRONMENT = {
    "kind": "exact",
    "revision": "96eeecf40bc06ddc8bae6d106f461d4fd774858a",
    "runtime": "Python 3.11 or newer with the repository test environment",
    "core": {
        "repository": "https://github.com/vela-science/vela.git",
        "revision": "bea4ec2af0772e366a0670d49a10b7085a4c73c1",
        "binary": "vela",
        "version": "0.974.2",
        "command": "vela integration check <repository> --json",
        "result_schema": CORE_CHECK_SCHEMA,
    },
}
LEAN_DECLARATION_RE = re.compile(
    r"(?m)^(?:theorem|lemma|def|abbrev|axiom)\s+([^\s(:]+)"
)
REQUIRED_NONCLAIMS = {
    "not_an_acceptance_or_merge_decision",
    "not_a_vela_decision_event_or_standing",
}
SOURCE_OWNER = "williamjblair/formal-conjectures contributor fork"
SOURCE_REPOSITORY_IDENTITY = "https://github.com/williamjblair/formal-conjectures"
SOURCE_PACKET_REVISION = "96eeecf40bc06ddc8bae6d106f461d4fd774858a"


def _expect_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IntegrationError(f"{label} must be a table")
    return value


def _expect_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise IntegrationError(f"{label} must be an array")
    return value


def _expect_keys(
    value: Mapping[str, Any], *, required: set[str], allowed: set[str], label: str
) -> None:
    missing = required - value.keys()
    extra = value.keys() - allowed
    if missing:
        raise IntegrationError(
            f"{label} is missing fields: {', '.join(sorted(missing))}"
        )
    if extra:
        raise IntegrationError(
            f"{label} has unsupported fields: {', '.join(sorted(extra))}"
        )


def _retained_file(root: Path, relative: str, label: str) -> Path:
    candidate = Path(relative)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or relative != candidate.as_posix()
    ):
        raise IntegrationError(f"{label} must be a canonical repository-relative path")
    resolved_root = root.resolve()
    retained = resolved_root / candidate
    try:
        metadata = retained.lstat()
    except OSError as error:
        raise IntegrationError(f"{label} is not retained: {error}") from error
    if retained.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise IntegrationError(f"{label} must resolve to a regular non-symlink file")
    resolved = retained.resolve()
    if resolved_root not in resolved.parents and resolved != resolved_root:
        raise IntegrationError(f"{label} escapes the repository")
    return retained


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise IntegrationError(f"cannot read {path}: {error}") from error
    return _expect_mapping(value, str(path))


def _core_checker() -> Path:
    configured = os.environ.get(CORE_CHECK_ENV)
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            discovered = shutil.which(configured)
            if discovered is not None:
                candidate = Path(discovered)
        candidate = candidate.resolve()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise IntegrationError(
            f"{CORE_CHECK_ENV} does not name an executable Vela binary: {configured}"
        )
    discovered = shutil.which("vela")
    if discovered is None:
        raise IntegrationError(
            f"set {CORE_CHECK_ENV} to the exact reviewed Vela binary"
        )
    return Path(discovered).resolve()


def _run_core_check(root: Path) -> dict[str, Any]:
    checker = _core_checker()
    try:
        completed = subprocess.run(
            [str(checker), "integration", "check", str(root), "--json"],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise IntegrationError(
            f"cannot run shared Vela integration check: {error}"
        ) from error
    try:
        result = _expect_mapping(
            json.loads(completed.stdout.decode("utf-8")), "Vela integration check"
        )
    except (UnicodeError, json.JSONDecodeError, IntegrationError) as error:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise IntegrationError(
            f"shared Vela integration check returned invalid JSON: {stderr or error}"
        ) from error
    if completed.returncode != 0:
        message = result.get("error", {}).get("message", "shared contract refused")
        raise IntegrationError(f"shared Vela integration check failed: {message}")
    if (
        result.get("schema") != CORE_CHECK_SCHEMA
        or result.get("ok") is not True
        or result.get("authority_effect") != "none"
    ):
        raise IntegrationError(
            "shared Vela integration check returned an invalid success"
        )
    return result


def _require_nonclaims(value: Mapping[str, Any], path: Path) -> None:
    nonclaims = set(_expect_list(value["nonclaims"], f"{path}.nonclaims"))
    if not REQUIRED_NONCLAIMS <= nonclaims:
        raise IntegrationError(
            f"{path}: authority and acceptance nonclaims are incomplete"
        )


def _validate_source_profile(profile: dict[str, Any], path: Path) -> None:
    source = _expect_mapping(profile.get("source"), f"{path}.source")
    _expect_keys(
        source,
        required={"owner"},
        allowed={"owner"},
        label=f"{path}.source",
    )
    if source["owner"] != SOURCE_OWNER:
        raise IntegrationError(f"{path}: source owner drift")
    _require_nonclaims(profile, path)


def _validate_retained_reference(
    reference: dict[str, Any], root: Path, label: str
) -> None:
    identity = reference["native_identity"]
    if identity["system"] != "lean4" or identity["object_kind"] not in {
        "lean_declaration",
        "lean_proof_artifact",
    }:
        raise IntegrationError(f"{label}: unsupported source object kind")
    if reference["locator"]["mutable"] is not True:
        raise IntegrationError(
            f"{label}: retained repository-relative locator must be declared mutable"
        )
    artifact = _retained_file(root, reference["locator"]["uri"], f"{label}.locator")
    raw = artifact.read_bytes()
    fixity = reference["content_fixity"]
    if fixity["digest"] != sha256_digest(raw) or fixity["size"] != len(raw):
        raise IntegrationError(f"{label}: retained content fixity drift")


def _validate_source_binding(binding: dict[str, Any], path: Path, root: Path) -> None:
    source = _expect_mapping(binding.get("source"), f"{path}.source")
    _expect_keys(
        source,
        required={"audit", "rights", "availability", "provenance"},
        allowed={"audit", "rights", "availability", "provenance"},
        label=f"{path}.source",
    )
    rights = _expect_mapping(source["rights"], f"{path}.source.rights")
    _expect_keys(
        rights,
        required={"license", "redistribution"},
        allowed={"license", "redistribution"},
        label=f"{path}.source.rights",
    )
    availability = _expect_mapping(
        source["availability"], f"{path}.source.availability"
    )
    availability_keys = {"evidence", "class", "observed_at", "access", "retention"}
    _expect_keys(
        availability,
        required=availability_keys,
        allowed=availability_keys,
        label=f"{path}.source.availability",
    )
    if availability["evidence"] not in {"available", "unavailable"}:
        raise IntegrationError(
            f"{path}: availability evidence must be available or unavailable"
        )
    provenance = _expect_mapping(source["provenance"], f"{path}.source.provenance")
    provenance_keys = {
        "agents",
        "activities",
        "entities",
        "roles",
        "independence",
        "shared_dependencies",
    }
    _expect_keys(
        provenance,
        required=provenance_keys,
        allowed=provenance_keys,
        label=f"{path}.source.provenance",
    )
    for field in ("agents", "activities", "entities", "roles"):
        if not _expect_list(provenance[field], f"{path}.source.provenance.{field}"):
            raise IntegrationError(f"{path}: provenance {field} cannot be empty")
    for index, reference in enumerate(binding["references"]):
        _validate_retained_reference(reference, root, f"{path}.references[{index}]")
    _require_nonclaims(binding, path)
    _validate_audit_binding(binding, source, path, root)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return _expect_mapping(
            parse_json_bytes(path.read_bytes(), label=str(path)), str(path)
        )
    except (OSError, AuditError) as error:
        raise IntegrationError(f"cannot validate {path}: {error}") from error


def _validate_audit_binding(
    binding: dict[str, Any], source: dict[str, Any], path: Path, root: Path
) -> None:
    audit = _expect_mapping(source["audit"], f"{path}.source.audit")
    audit_keys = {
        "core_path",
        "core_root",
        "observation_path",
        "observation_root",
        "check_ids",
    }
    _expect_keys(
        audit,
        required=audit_keys,
        allowed=audit_keys,
        label=f"{path}.source.audit",
    )
    core_path = _retained_file(
        root, audit["core_path"], f"{path}.source.audit.core_path"
    )
    observation_path = _retained_file(
        root, audit["observation_path"], f"{path}.source.audit.observation_path"
    )
    try:
        core = validate_core(_load_json(core_path))
        observation = validate_observation(_load_json(observation_path))
    except AuditError as error:
        raise IntegrationError(
            f"{path}: frozen PR-audit validation failed: {error}"
        ) from error
    if (
        core["root"] != audit["core_root"]
        or observation["root"] != audit["observation_root"]
    ):
        raise IntegrationError(f"{path}: audit root drift")
    if observation["core"]["root"] != core["root"]:
        raise IntegrationError(f"{path}: observation does not bind the declared core")
    check_ids = {check["id"] for check in core["checks"]}
    if set(audit["check_ids"]) != check_ids:
        raise IntegrationError(f"{path}: audit check inventory drift")
    if source["availability"]["evidence"] == "unavailable":
        outcomes = {check["outcome"] for check in core["checks"]}
        if outcomes - {"unavailable"}:
            raise IntegrationError(
                f"{path}: unavailable evidence cannot become pass, fail, error, or zero"
            )
    head = core["repository"]["head"]["commit_oid"]
    changes = {item["path"]: item for item in core["repository"]["changes"]}
    retained_inputs = {
        (item["kind"], item["root"]): item
        for check in core["checks"]
        for item in check["inputs"]
    }
    for reference in binding["references"]:
        identity = reference["native_identity"]
        revision = reference["revision"]
        fixity = reference["content_fixity"]
        selector = reference.get("selector")
        if identity["object_kind"] == "lean_declaration":
            native_path = identity["identifier"].split("#", 1)[0]
            change = changes.get(native_path)
            if change is None or revision["value"] != head:
                raise IntegrationError(
                    f"{path}: reference revision or native path drift"
                )
            if fixity["digest"] != change["head_blob_sha256"]:
                raise IntegrationError(f"{path}: declaration source root drift")
        elif identity["object_kind"] == "lean_proof_artifact":
            retained = retained_inputs.get(("git-blob", fixity["digest"]))
            artifact = _retained_file(
                root, reference["locator"]["uri"], f"{path}: linked proof artifact"
            )
            declarations = set(
                LEAN_DECLARATION_RE.findall(artifact.read_text(encoding="utf-8"))
            )
            proof_records = [
                proof for check in core["checks"] for proof in check.get("proofs", [])
            ]
            proof_mapping = next(
                (
                    mapping
                    for mapping in binding["mappings"]
                    if mapping["source"] == identity["identifier"]
                ),
                None,
            )
            if (
                retained is None
                or revision["value"] not in retained["locator"]
                or selector is None
                or selector["value"] not in declarations
                or not any(
                    revision["value"] in proof["locator"] for proof in proof_records
                )
                or proof_mapping is None
                or proof_mapping["relation"] != "related"
                or proof_mapping["target"]
                not in {proof["declaration"] for proof in proof_records}
            ):
                raise IntegrationError(f"{path}: linked proof identity drift")
        else:
            raise IntegrationError(f"{path}: unsupported source object kind")
    declared_selectors = {
        reference["selector"]["value"]
        for reference in binding["references"]
        if reference["native_identity"]["object_kind"] != "lean_proof_artifact"
        and "selector" in reference
    }
    scoped = {
        declaration
        for check in core["checks"]
        for declaration in check["scope"]["declarations"]
    }
    if not declared_selectors <= scoped:
        raise IntegrationError(f"{path}: selector drift from audit scope")


def validate_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    core_check = _run_core_check(root)
    manifest = _load_toml(_retained_file(root, "vela.toml", "manifest"))
    repository = _expect_mapping(manifest["repository"], "manifest.repository")
    if repository != {
        "identity": SOURCE_REPOSITORY_IDENTITY,
        "revision_policy": "exact_git_commit",
        "revision": SOURCE_PACKET_REVISION,
    }:
        raise IntegrationError(
            "manifest repository identity or source packet revision drift"
        )
    _require_nonclaims(manifest, root / "vela.toml")
    profiles: dict[str, dict[str, Any]] = {}
    for item in manifest["profiles"]:
        path = _retained_file(root, item["path"], "manifest.profiles.path")
        profile = _load_toml(path)
        _validate_source_profile(profile, path)
        profiles[profile["profile_id"]] = profile
    methods: dict[str, dict[str, Any]] = {}
    for item in manifest["methods"]:
        path = _retained_file(root, item["path"], "manifest.methods.path")
        method = _load_toml(path)
        methods[method["method_id"]] = method
    core_method = methods.get(CORE_METHOD_ID)
    if core_method is None:
        raise IntegrationError("published Vela Core integration Method is missing")
    if (
        core_method["implementation"]["path"] != CORE_METHOD_IMPLEMENTATION
        or core_method["environment"] != CORE_METHOD_ENVIRONMENT
    ):
        raise IntegrationError("published Vela Core integration Method drift")
    bindings: dict[str, dict[str, Any]] = {}
    for item in manifest["bindings"]:
        path = _retained_file(root, item["path"], "manifest.bindings.path")
        binding = _load_toml(path)
        _validate_source_binding(binding, path, root)
        if CORE_METHOD_ID not in {method["id"] for method in binding["methods"]}:
            raise IntegrationError(
                f"{path}: published Vela Core integration Method is missing"
            )
        bindings[binding["binding_id"]] = binding
    if core_check["manifest_root"] != manifest["manifest_root"]:
        raise IntegrationError("shared Vela check returned a different Manifest root")
    return {
        "manifest": manifest,
        "profiles": profiles,
        "methods": methods,
        "bindings": bindings,
    }


def _typed_result_for_check(
    root: Path, core_path: Path, core: dict[str, Any], check: dict[str, Any]
) -> dict[str, Any]:
    typed_ids = [
        item["artifact_id"]
        for item in check["inputs"]
        if item["kind"] == "typed-result"
    ]
    if len(typed_ids) != 1:
        raise IntegrationError(
            f"check {check['id']} must retain exactly one typed result"
        )
    descriptors = {item["id"]: item for item in core["inputs"]["artifacts"]}
    descriptor = descriptors[typed_ids[0]]
    artifact_path = _retained_file(
        core_path.parent, descriptor["path"], f"typed result {typed_ids[0]}"
    )
    raw = artifact_path.read_bytes()
    if sha256_digest(raw) != descriptor["sha256"]:
        raise IntegrationError(f"typed result {typed_ids[0]} drift")
    return _load_json(artifact_path)


def build_selected_export(root: Path) -> dict[str, Any]:
    packet = validate_repository(root)
    binding = packet["bindings"].get("erdos-887-selected-declaration")
    if binding is None:
        raise IntegrationError("selected declaration Binding is missing")
    source = binding["source"]
    audit = source["audit"]
    core_path = _retained_file(root, audit["core_path"], "selected core")
    observation_path = _retained_file(
        root, audit["observation_path"], "selected observation"
    )
    core = validate_core(_load_json(core_path))
    observation = validate_observation(_load_json(observation_path))
    checks = []
    for check in core["checks"]:
        typed = _typed_result_for_check(root, core_path, core, check)
        producer = typed["producer"]
        checks.append(
            {
                "id": check["id"],
                "property": check["property"],
                "kind": check["kind"],
                "outcome": check["outcome"],
                "severity": check["severity"],
                "method": check["implementation"],
                "responsible_agent": {
                    "id": producer["id"],
                    "kind": producer["kind"],
                    "authority": producer["authority"],
                },
                "activity": {"type": check["property"], "mode": check["mode"]},
                "entities": [
                    {"kind": item["kind"], "root": item["root"]}
                    for item in check["inputs"]
                ],
                "role": check["role"],
                "independent": producer["independent"],
                "conditions": check["conditions"],
                "assumptions": check["assumptions"],
                "limitations": check["limitations"],
                "does_not_establish": check["does_not_establish"],
            }
        )
    result: dict[str, Any] = {
        "schema": "formal-conjectures.portable-declaration-export.v0.1",
        "export_root": "",
        "authority_effect": "none",
        "output_kind": "verification_input",
        "source_repository": core["repository"]["repository"],
        "subject": binding["references"][0],
        "audit": {
            "core_root": core["root"],
            "observation_root": observation["root"],
            "observation_status": {
                "state": observation["pull_request"]["state"],
                "review_decision": observation["pull_request"]["review_decision"],
                "observed_at": observation["observed_at"],
            },
            "checks": checks,
            "advisory_disposition": core["disposition"],
        },
        "mappings": binding["mappings"],
        "translations": binding["translations"],
        "rights": source["rights"],
        "availability": source["availability"],
        "limitations": binding["limitations"],
        "nonclaims": binding["nonclaims"],
    }
    framing = result["schema"].encode("utf-8") + b"\0"
    result["export_root"] = (
        "sha256:" + hashlib.sha256(framing + canonical_bytes(result)).hexdigest()
    )
    return result


__all__ = [
    "CORE_CHECK_ENV",
    "IntegrationError",
    "build_selected_export",
    "validate_repository",
]
