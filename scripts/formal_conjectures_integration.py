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

"""Source-owned, non-authoritative Formal Conjectures integration checks."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import re
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


SCHEMAS = {
    "manifest": "vela.integration-manifest.v0.1",
    "profile": "vela.integration-profile.v0.1",
    "binding": "vela.integration-binding.v0.1",
    "method": "vela.integration-method.v0.1",
}
ROOT_FIELDS = {kind: f"{kind}_root" for kind in SCHEMAS}
ROOT_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
OID_RE = re.compile(r"[0-9a-f]{40}\Z")
LEAN_DECLARATION_RE = re.compile(
    r"(?m)^(?:theorem|lemma|def|abbrev|axiom)\s+([^\s(:]+)"
)
MAPPING_RELATIONS = {"exact", "close", "broader", "narrower", "related"}
TRANSLATION_DISPOSITIONS = {
    "preserved",
    "normalized",
    "derived",
    "approximated",
    "omitted",
    "unsupported",
    "assumed",
    "unresolved",
}
OUTPUTS = {"exact_reference", "submission_draft", "verification_input"}
PROHIBITED_KEYS = {
    "acceptance_result",
    "authority_key",
    "decision",
    "event",
    "repository_policy",
    "standing",
}
REQUIRED_NONCLAIMS = {
    "not_an_acceptance_or_merge_decision",
    "not_a_vela_decision_event_or_standing",
}
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


def _expect_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise IntegrationError(f"{label} must be a non-empty string")
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


def _safe_path(root: Path, relative: str, label: str) -> Path:
    candidate = Path(relative)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or relative != candidate.as_posix()
    ):
        raise IntegrationError(f"{label} must be a canonical repository-relative path")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved_root not in resolved.parents and resolved != resolved_root:
        raise IntegrationError(f"{label} escapes the repository")
    if not resolved.is_file() or resolved.is_symlink():
        raise IntegrationError(f"{label} must resolve to a regular non-symlink file")
    return resolved


def document_root(kind: str, value: Mapping[str, Any]) -> str:
    if kind not in SCHEMAS:
        raise IntegrationError(f"unsupported document kind: {kind}")
    normalized = deepcopy(dict(value))
    normalized[ROOT_FIELDS[kind]] = ""
    framing = SCHEMAS[kind].encode("utf-8") + b"\0"
    return "sha256:" + hashlib.sha256(framing + canonical_bytes(normalized)).hexdigest()


def load_document(path: Path, kind: str) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise IntegrationError(f"cannot read {path}: {error}") from error
    root_field = ROOT_FIELDS[kind]
    if value.get("schema") != SCHEMAS[kind]:
        raise IntegrationError(f"{path}: unsupported {kind} schema")
    root = value.get(root_field)
    if not isinstance(root, str) or not ROOT_RE.fullmatch(root):
        raise IntegrationError(f"{path}: {root_field} must be a full SHA-256 root")
    expected = document_root(kind, value)
    if root != expected:
        raise IntegrationError(f"{path}: {root_field} drift: expected {expected}")
    if value.get("authority_effect") != "none":
        raise IntegrationError(f"{path}: authority_effect must be none")
    _reject_authority_fields(value, path.name)
    return value


def _reject_authority_fields(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in PROHIBITED_KEYS:
                raise IntegrationError(f"{label}: integration document contains {key}")
            _reject_authority_fields(child, label)
    elif isinstance(value, list):
        for child in value:
            _reject_authority_fields(child, label)


def _validate_profile(profile: dict[str, Any], path: Path) -> None:
    required = {
        "schema",
        "profile_root",
        "profile_id",
        "version",
        "owner",
        "conformance",
        "rights",
        "limitations",
        "nonclaims",
        "authority_effect",
    }
    _expect_keys(profile, required=required, allowed=required, label=str(path))
    if profile["version"] != "0.1":
        raise IntegrationError(f"{path}: unsupported Profile version")
    rights = _expect_mapping(profile["rights"], f"{path}.rights")
    _expect_keys(
        rights,
        required={"license", "redistribution"},
        allowed={"license", "redistribution"},
        label=f"{path}.rights",
    )
    if not _expect_list(profile["conformance"], f"{path}.conformance"):
        raise IntegrationError(f"{path}: conformance cannot be empty")
    _require_nonclaims(profile, path)


def _validate_method(method: dict[str, Any], path: Path, root: Path) -> None:
    required = {
        "schema",
        "method_root",
        "method_id",
        "version",
        "implementation",
        "environment",
        "inputs",
        "outputs",
        "limitations",
        "nonclaims",
        "authority_effect",
    }
    _expect_keys(method, required=required, allowed=required, label=str(path))
    if method["version"] != "0.1":
        raise IntegrationError(f"{path}: unsupported Method version")
    implementation = _expect_mapping(method["implementation"], f"{path}.implementation")
    _expect_keys(
        implementation,
        required={"path", "digest"},
        allowed={"path", "digest"},
        label=f"{path}.implementation",
    )
    implementation_path = _safe_path(
        root, implementation["path"], f"{path}.implementation.path"
    )
    digest = sha256_digest(implementation_path.read_bytes())
    if implementation["digest"] != digest:
        raise IntegrationError(f"{path}: implementation digest drift")
    environment = _expect_mapping(method["environment"], f"{path}.environment")
    if environment.get("kind") not in {
        "exact",
        "bounded",
        "best_effort",
        "unavailable",
    }:
        raise IntegrationError(f"{path}: invalid environment kind")
    _require_nonclaims(method, path)


def _require_nonclaims(value: Mapping[str, Any], path: Path) -> None:
    nonclaims = set(_expect_list(value["nonclaims"], f"{path}.nonclaims"))
    if not REQUIRED_NONCLAIMS <= nonclaims:
        raise IntegrationError(
            f"{path}: authority and acceptance nonclaims are incomplete"
        )


def _validate_reference(reference: dict[str, Any], root: Path, label: str) -> None:
    required = {
        "schema",
        "id",
        "native_system",
        "object_kind",
        "native_identifier",
        "revision_kind",
        "revision_value",
        "media_type",
        "digest",
        "byte_size",
        "selector_kind",
        "selector_value",
        "locator_uri",
        "locator_mutability",
        "authentication",
    }
    _expect_keys(reference, required=required, allowed=required, label=label)
    if reference["schema"] != "vela.exact-reference.v0.1":
        raise IntegrationError(f"{label}: unsupported Exact Reference version")
    if reference["revision_kind"] != "git_commit" or not OID_RE.fullmatch(
        reference["revision_value"]
    ):
        raise IntegrationError(f"{label}: revision must be a full Git commit")
    if reference["locator_mutability"] != "retained_immutable_bytes":
        raise IntegrationError(
            f"{label}: mutable identity cannot be presented as immutable"
        )
    if reference["native_system"] == "lean4" and reference["object_kind"] in {
        "lean_declaration",
        "lean_proof_artifact",
    }:
        identifier_parts = reference["native_identifier"].rsplit("#", 1)
        if (
            len(identifier_parts) != 2
            or identifier_parts[1] != reference["selector_value"]
        ):
            raise IntegrationError(f"{label}: native identifier and selector drift")
    artifact = _safe_path(root, reference["locator_uri"], f"{label}.locator_uri")
    raw = artifact.read_bytes()
    if reference["digest"] != sha256_digest(raw) or reference["byte_size"] != len(raw):
        raise IntegrationError(f"{label}: content fixity drift")
    if not reference["selector_value"]:
        raise IntegrationError(f"{label}: selector must be explicit")


def _validate_binding(
    binding: dict[str, Any],
    path: Path,
    root: Path,
    profiles: Mapping[str, dict[str, Any]],
    methods: Mapping[str, dict[str, Any]],
) -> None:
    required = {
        "schema",
        "binding_root",
        "binding_id",
        "profile",
        "references",
        "mappings",
        "translations",
        "methods",
        "audit",
        "outputs",
        "rights",
        "availability",
        "limitations",
        "nonclaims",
        "provenance",
        "authority_effect",
    }
    _expect_keys(binding, required=required, allowed=required, label=str(path))
    profile_ref = _expect_mapping(binding["profile"], f"{path}.profile")
    _expect_keys(
        profile_ref,
        required={"id", "version", "root"},
        allowed={"id", "version", "root"},
        label=f"{path}.profile",
    )
    if profile_ref["version"] != "0.1":
        raise IntegrationError(f"{path}: unsupported Profile version")
    profile = profiles.get(profile_ref["id"])
    if profile is None or profile["profile_root"] != profile_ref["root"]:
        raise IntegrationError(f"{path}: Profile identity or root is missing")
    references = _expect_list(binding["references"], f"{path}.references")
    if not references:
        raise IntegrationError(f"{path}: references cannot be empty")
    reference_ids: set[str] = set()
    for index, value in enumerate(references):
        reference = _expect_mapping(value, f"{path}.references[{index}]")
        _validate_reference(reference, root, f"{path}.references[{index}]")
        reference_id = reference["id"]
        if reference_id in reference_ids:
            raise IntegrationError(
                f"{path}: duplicate Exact Reference id {reference_id}"
            )
        reference_ids.add(reference_id)
    mappings = _expect_list(binding["mappings"], f"{path}.mappings")
    translations = _expect_list(binding["translations"], f"{path}.translations")
    if not mappings or not translations:
        raise IntegrationError(
            f"{path}: mapping and translation reports must both be present"
        )
    for mapping in mappings:
        mapping = _expect_mapping(mapping, f"{path}.mappings")
        _expect_keys(
            mapping,
            required={"source", "target", "relation"},
            allowed={"source", "target", "relation"},
            label=f"{path}.mappings",
        )
        _expect_string(mapping["source"], f"{path}.mappings.source")
        _expect_string(mapping["target"], f"{path}.mappings.target")
        if mapping["relation"] not in MAPPING_RELATIONS:
            raise IntegrationError(f"{path}: mapping relation is invalid or collapsed")
    for translation in translations:
        translation = _expect_mapping(translation, f"{path}.translations")
        _expect_keys(
            translation,
            required={"source", "target", "disposition"},
            allowed={"source", "target", "disposition"},
            label=f"{path}.translations",
        )
        _expect_string(translation["source"], f"{path}.translations.source")
        _expect_string(translation["target"], f"{path}.translations.target")
        if translation["disposition"] not in TRANSLATION_DISPOSITIONS:
            raise IntegrationError(
                f"{path}: translation disposition is invalid or collapsed"
            )
    for method_ref in _expect_list(binding["methods"], f"{path}.methods"):
        method_ref = _expect_mapping(method_ref, f"{path}.methods")
        _expect_keys(
            method_ref,
            required={"id", "root"},
            allowed={"id", "root"},
            label=f"{path}.methods",
        )
        method = methods.get(method_ref["id"])
        if method is None or method["method_root"] != method_ref["root"]:
            raise IntegrationError(f"{path}: missing or drifted Method")
    outputs = set(_expect_list(binding["outputs"], f"{path}.outputs"))
    if not outputs or not outputs <= OUTPUTS:
        raise IntegrationError(f"{path}: unsupported integration output")
    rights = _expect_mapping(binding["rights"], f"{path}.rights")
    _expect_keys(
        rights,
        required={"license", "redistribution"},
        allowed={"license", "redistribution"},
        label=f"{path}.rights",
    )
    availability = _expect_mapping(binding["availability"], f"{path}.availability")
    _expect_keys(
        availability,
        required={"evidence", "class", "observed_at", "access", "retention"},
        allowed={"evidence", "class", "observed_at", "access", "retention"},
        label=f"{path}.availability",
    )
    if availability["evidence"] not in {"available", "unavailable"}:
        raise IntegrationError(
            f"{path}: availability evidence must be available or unavailable"
        )
    provenance = _expect_mapping(binding["provenance"], f"{path}.provenance")
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
        label=f"{path}.provenance",
    )
    for field in ("agents", "activities", "entities", "roles"):
        if not _expect_list(provenance[field], f"{path}.provenance.{field}"):
            raise IntegrationError(f"{path}: provenance {field} cannot be empty")
    _require_nonclaims(binding, path)
    _validate_audit_binding(binding, path, root)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return _expect_mapping(
            parse_json_bytes(path.read_bytes(), label=str(path)), str(path)
        )
    except (OSError, AuditError) as error:
        raise IntegrationError(f"cannot validate {path}: {error}") from error


def _validate_audit_binding(binding: dict[str, Any], path: Path, root: Path) -> None:
    audit = _expect_mapping(binding["audit"], f"{path}.audit")
    _expect_keys(
        audit,
        required={
            "core_path",
            "core_root",
            "observation_path",
            "observation_root",
            "check_ids",
        },
        allowed={
            "core_path",
            "core_root",
            "observation_path",
            "observation_root",
            "check_ids",
        },
        label=f"{path}.audit",
    )
    core_path = _safe_path(root, audit["core_path"], f"{path}.audit.core_path")
    observation_path = _safe_path(
        root, audit["observation_path"], f"{path}.audit.observation_path"
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
    if binding["availability"]["evidence"] == "unavailable":
        outcomes = {check["outcome"] for check in core["checks"]}
        if outcomes - {"unavailable"}:
            raise IntegrationError(
                f"{path}: unavailable evidence cannot be converted to pass, fail, error, or zero"
            )
    head = core["repository"]["head"]["commit_oid"]
    changes = {item["path"]: item for item in core["repository"]["changes"]}
    retained_inputs = {
        (item["kind"], item["root"]): item
        for check in core["checks"]
        for item in check["inputs"]
    }
    for reference in binding["references"]:
        if reference["object_kind"] == "lean_declaration":
            native_path = reference["native_identifier"].split("#", 1)[0]
            change = changes.get(native_path)
            if change is None or reference["revision_value"] != head:
                raise IntegrationError(
                    f"{path}: reference revision or native path drift"
                )
            if reference["digest"] != change["head_blob_sha256"]:
                raise IntegrationError(f"{path}: declaration source root drift")
        elif reference["object_kind"] == "lean_proof_artifact":
            retained = retained_inputs.get(("git-blob", reference["digest"]))
            artifact = _safe_path(
                root, reference["locator_uri"], f"{path}: linked proof artifact"
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
                    if mapping["source"] == reference["native_identifier"]
                ),
                None,
            )
            if (
                retained is None
                or reference["revision_value"] not in retained["locator"]
                or reference["selector_value"] not in declarations
                or not any(
                    reference["revision_value"] in proof["locator"]
                    for proof in proof_records
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
        reference["selector_value"]
        for reference in binding["references"]
        if reference["object_kind"] != "lean_proof_artifact"
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
    manifest_path = _safe_path(root, "vela.toml", "manifest")
    manifest = load_document(manifest_path, "manifest")
    required = {
        "schema",
        "manifest_root",
        "repository",
        "profiles",
        "bindings",
        "methods",
        "rights",
        "availability",
        "outputs",
        "limitations",
        "nonclaims",
        "authority_effect",
    }
    _expect_keys(
        manifest, required=required, allowed=required, label=str(manifest_path)
    )
    repository = _expect_mapping(manifest["repository"], "manifest.repository")
    if repository != {
        "identity": SOURCE_REPOSITORY_IDENTITY,
        "revision_policy": "exact_git_commit",
        "revision": SOURCE_PACKET_REVISION,
    }:
        raise IntegrationError(
            "manifest repository identity or source packet revision drift"
        )
    _expect_mapping(manifest["rights"], "manifest.rights")
    _expect_mapping(manifest["availability"], "manifest.availability")
    _require_nonclaims(manifest, manifest_path)
    if not set(manifest["outputs"]) <= OUTPUTS:
        raise IntegrationError("manifest has an unsupported output")

    profiles: dict[str, dict[str, Any]] = {}
    for item in manifest["profiles"]:
        path = _safe_path(root, item["path"], "manifest.profiles.path")
        profile = load_document(path, "profile")
        _validate_profile(profile, path)
        if item != {
            "id": profile["profile_id"],
            "version": profile["version"],
            "path": item["path"],
            "root": profile["profile_root"],
        }:
            raise IntegrationError("manifest Profile inventory drift")
        profiles[profile["profile_id"]] = profile

    methods: dict[str, dict[str, Any]] = {}
    for item in manifest["methods"]:
        path = _safe_path(root, item["path"], "manifest.methods.path")
        method = load_document(path, "method")
        _validate_method(method, path, root)
        if item != {
            "id": method["method_id"],
            "path": item["path"],
            "root": method["method_root"],
        }:
            raise IntegrationError("manifest Method inventory drift")
        methods[method["method_id"]] = method

    bindings: dict[str, dict[str, Any]] = {}
    for item in manifest["bindings"]:
        path = _safe_path(root, item["path"], "manifest.bindings.path")
        binding = load_document(path, "binding")
        _validate_binding(binding, path, root, profiles, methods)
        if item != {
            "id": binding["binding_id"],
            "path": item["path"],
            "root": binding["binding_root"],
        }:
            raise IntegrationError("manifest Binding inventory drift")
        bindings[binding["binding_id"]] = binding
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
    artifact_path = _safe_path(
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
    audit = binding["audit"]
    core_path = _safe_path(root, audit["core_path"], "selected core")
    observation_path = _safe_path(
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
        "rights": binding["rights"],
        "availability": binding["availability"],
        "limitations": binding["limitations"],
        "nonclaims": binding["nonclaims"],
    }
    framing = result["schema"].encode("utf-8") + b"\0"
    result["export_root"] = (
        "sha256:" + hashlib.sha256(framing + canonical_bytes(result)).hexdigest()
    )
    return result


__all__ = [
    "IntegrationError",
    "SCHEMAS",
    "build_selected_export",
    "document_root",
    "load_document",
    "validate_repository",
]
