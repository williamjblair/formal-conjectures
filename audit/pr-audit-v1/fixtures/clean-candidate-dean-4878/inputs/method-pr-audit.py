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

"""Offline, deterministic construction of Formal Conjectures PR audit records.

The module deliberately has no network, Git, Lean, model, or subprocess adapter.
It combines content-addressed artifacts that another process has already retained.
Its output is advisory evidence, never a merge or acceptance decision.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


CORE_SCHEMA_VERSION = "formal-conjectures.pr-audit.v1"
OBSERVATION_SCHEMA_VERSION = "formal-conjectures.pr-audit-observation.v1"
CORE_INPUT_VERSION = "formal-conjectures.pr-audit-input.v1"
OBSERVATION_INPUT_VERSION = "formal-conjectures.pr-audit-observation-input.v1"
GENERATOR_VERSION = "formal-conjectures.pr-audit-generator.v1"
REPOSITORY_VERSION = "formal-conjectures.pr-audit-repository.v1"
CHECKS_VERSION = "formal-conjectures.pr-audit-checks.v1"
TYPED_RESULT_VERSION = "formal-conjectures.pr-audit-typed-result.v1"

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_ARTIFACTS = 64
MAX_JSON_DEPTH = 64
MAX_CONTAINER_ITEMS = 100_000
RUNTIME_ROOT = Path(__file__).resolve().parent.parent
GENERATOR_OVERLAY_PATHS = (
    "scripts/pr_audit.py",
    "scripts/generate_pr_audit.py",
    "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit.v1.schema.json",
    "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit-observation.v1.schema.json",
)
GENERATOR_REPOSITORY = "https://github.com/google-deepmind/formal-conjectures"
GENERATOR_BASELINE = {
    "commit_oid": "c9052e8577118ed0ada54462bd4ef1f3beff37d6",
    "tree_oid": "864ee77ee26a7cbd85b30558f8d9d2036f8717ed",
}
CORE_GRAPHQL_OPERATION = "query PullRequestAuditCoreSnapshot($owner:String!,$name:String!,$number:Int!,$baseOid:GitObjectID!,$headOid:GitObjectID!,$baseExpression:String!,$headExpression:String!){repository(owner:$owner,name:$name){pullRequest(number:$number){number url baseRefOid headRefOid files(first:100){nodes{path changeType} pageInfo{hasNextPage endCursor}}} baseCommit:object(oid:$baseOid){... on Commit{oid tree{oid}}} headCommit:object(oid:$headOid){... on Commit{oid tree{oid}}} baseBlob:object(expression:$baseExpression){... on Blob{oid byteSize isBinary text}} headBlob:object(expression:$headExpression){... on Blob{oid byteSize isBinary text}}}}"
OBSERVATION_GRAPHQL_OPERATION = "query PullRequestAuditObservation($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){number url state isDraft mergeStateStatus reviewDecision updatedAt baseRefOid headRefOid reviews(first:100){nodes{id author{login} state submittedAt commit{oid}} pageInfo{hasNextPage endCursor}}}}}"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
OID_RE = re.compile(r"[0-9a-f]{40}\Z")
IDENTIFIER_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?\Z")
HTTPS_RE = re.compile(r"https://[^\s]+\Z")
RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)
IMMUTABLE_RAW_GIST_RE = re.compile(
    r"https://gist\.githubusercontent\.com/[^/]+/[0-9a-f]+/raw/[0-9a-f]{40}/[^/?#]+\Z"
)
IMMUTABLE_GITHUB_BLOB_RE = re.compile(
    r"https://github\.com/[^/]+/[^/]+/blob/[0-9a-f]{40}/[^?#]+\Z"
)
IMMUTABLE_RAW_GITHUB_RE = re.compile(
    r"https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/[^?#]+\Z"
)
TYPED_RESULT_LOCATOR_RE = re.compile(
    r"typed-result/(deterministic_adapter|retained_external_result|ai_review_preparer|human_reviewer)/([^/]+)\Z"
)

CORE_NONCLAIMS = (
    "not_a_claim_of_mathematical_truth",
    "not_a_claim_that_unlisted_checks_ran",
    "not_an_acceptance_or_merge_decision",
    "not_source_fidelity_beyond_the_listed_checks",
)

SUPPORTED_PROPERTIES = frozenset({
    "immutable-input-identity",
    "formal-proof-conditions-retained",
    "lean-build",
    "answer-slot-scope-fidelity",
    "hypothesis-satisfiability",
    "exact-formal-proof-artifact-identity",
    "comparator-packet-identity",
})
CORE_ARTIFACT_ROLES = frozenset({
    "generator_identity",
    "repository_snapshot",
    "check_results",
    "source_file",
    "method",
    "configuration",
    "tool_output",
    "query",
    "typed_result",
})


class AuditError(ValueError):
    """Raised when retained input cannot safely produce an audit record."""


class _DuplicateKey(AuditError):
    pass


def _pairs_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_number(token: str) -> Any:
    raise AuditError(f"non-integer JSON number is not supported: {token!r}")


def _validate_and_normalize(value: Any, location: str = "$", depth: int = 0) -> Any:
    if depth > MAX_JSON_DEPTH:
        raise AuditError(f"JSON nesting exceeds {MAX_JSON_DEPTH} at {location}")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise AuditError(f"integer outside canonical profile at {location}")
        return value
    if isinstance(value, float):
        raise AuditError(f"floating-point number at {location}")
    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError as error:
            raise AuditError(f"lone surrogate at {location}") from error
        # RFC 8785/JCS deliberately preserves Unicode code points. In particular,
        # canonically equivalent NFC and NFD strings remain different inputs.
        return value
    if isinstance(value, list):
        if len(value) > MAX_CONTAINER_ITEMS:
            raise AuditError(f"array has more than {MAX_CONTAINER_ITEMS} items at {location}")
        return [
            _validate_and_normalize(item, f"{location}[{index}]", depth + 1)
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        if len(value) > MAX_CONTAINER_ITEMS:
            raise AuditError(f"object has more than {MAX_CONTAINER_ITEMS} members at {location}")
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise AuditError(f"non-string key at {location}")
            key = _validate_and_normalize(raw_key, f"{location}.<key>", depth + 1)
            if key in result:
                raise AuditError(f"duplicate key at {location}: {key!r}")
            result[key] = _validate_and_normalize(item, f"{location}.{key}", depth + 1)
        return result
    raise AuditError(f"unsupported JSON value at {location}: {type(value).__name__}")


def parse_json_bytes(raw: bytes, *, label: str = "input") -> Any:
    """Parse strict UTF-8 JSON, rejecting ambiguity and non-canonical number types."""

    if len(raw) > MAX_INPUT_BYTES:
        raise AuditError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AuditError(f"{label} has a UTF-8 BOM")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise AuditError(f"{label} is not strict UTF-8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except AuditError:
        raise
    except json.JSONDecodeError as error:
        raise AuditError(f"malformed JSON in {label}: {error.msg}") from error
    return _validate_and_normalize(value)


def _utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be", "strict")


def _encode_canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise AuditError("integer outside canonical profile")
        return str(value)
    if isinstance(value, str):
        normalized = _validate_and_normalize(value)
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_encode_canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        normalized = _validate_and_normalize(value)
        keys = sorted(normalized, key=_utf16_sort_key)
        return "{" + ",".join(
            _encode_canonical(key) + ":" + _encode_canonical(normalized[key])
            for key in keys
        ) + "}"
    raise AuditError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Return exact JCS bytes for the documented integer-only I-JSON subset."""

    normalized = _validate_and_normalize(value)
    return _encode_canonical(normalized).encode("utf-8", "strict")


def sha256_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def git_blob_oid(raw: bytes) -> str:
    """Compute a Git blob object ID from retained bytes, without invoking Git."""

    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def content_root(value: Any) -> str:
    return sha256_digest(canonical_bytes(value))


def classify_proof_target(kind: str, locator: str, resolved_targets: Sequence[str] = ()) -> str:
    """Classify retained proof-target metadata without fetching it.

    An empty locator for an in-repository `formal_conjectures` proof means the
    declaration itself is the target. Other proof kinds require one exact,
    immutable file locator, either directly or in retained resolution evidence.
    """

    if kind not in {"formal_conjectures", "lean4", "other_system"}:
        raise AuditError(f"unsupported formal proof kind: {kind!r}")
    if not isinstance(locator, str) or not all(isinstance(item, str) for item in resolved_targets):
        raise AuditError("formal proof locators must be strings")
    if kind == "formal_conjectures" and locator == "" and not resolved_targets:
        return "in_source"
    candidates = [locator, *resolved_targets]
    exact = sorted(set(
        candidate
        for candidate in candidates
        if IMMUTABLE_RAW_GIST_RE.fullmatch(candidate)
        or IMMUTABLE_GITHUB_BLOB_RE.fullmatch(candidate)
        or IMMUTABLE_RAW_GITHUB_RE.fullmatch(candidate)
    ))
    return "resolvable" if len(exact) == 1 else "unavailable"


def _expect_dict(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditError(f"{location} must be an object")
    return value


def _expect_list(value: Any, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise AuditError(f"{location} must be an array")
    return value


def _expect_keys(
    value: Mapping[str, Any],
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
    location: str,
) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = sorted(required_set - set(value))
    extra = sorted(set(value) - allowed)
    if missing:
        raise AuditError(f"{location} missing required keys: {', '.join(missing)}")
    if extra:
        raise AuditError(f"{location} has unsupported keys: {', '.join(extra)}")


def _expect_string(value: Any, location: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        raise AuditError(f"{location} must be a string")
    if nonempty and not value:
        raise AuditError(f"{location} must not be empty")
    return value


def _expect_bool(value: Any, location: str) -> bool:
    if not isinstance(value, bool):
        raise AuditError(f"{location} must be a boolean")
    return value


def _expect_choice(value: Any, choices: set[str], location: str) -> str:
    text = _expect_string(value, location)
    if text not in choices:
        raise AuditError(f"{location} has unsupported value: {text!r}")
    return text


def _expect_pattern(value: Any, pattern: re.Pattern[str], location: str) -> str:
    text = _expect_string(value, location)
    if not pattern.fullmatch(text):
        raise AuditError(f"{location} has invalid format")
    return text


def _expect_identifier(value: Any, location: str) -> str:
    return _expect_pattern(value, IDENTIFIER_RE, location)


def _expect_sha(value: Any, location: str) -> str:
    return _expect_pattern(value, SHA256_RE, location)


def _expect_oid(value: Any, location: str) -> str:
    return _expect_pattern(value, OID_RE, location)


def _expect_https(value: Any, location: str) -> str:
    return _expect_pattern(value, HTTPS_RE, location)


def _expect_timestamp(value: Any, location: str) -> str:
    text = _expect_pattern(value, RFC3339_RE, location)
    try:
        datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as error:
        raise AuditError(f"{location} is not a valid RFC 3339 timestamp") from error
    return text


def _repo_path(value: Any, location: str) -> str:
    text = _expect_string(value, location)
    if "\\" in text or "\x00" in text:
        raise AuditError(f"{location} is not a portable repository path")
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise AuditError(f"{location} must be a normalized relative path")
    if path.as_posix() != text:
        raise AuditError(f"{location} must be a normalized relative path")
    return text


def _sorted_unique_strings(values: Any, location: str) -> list[str]:
    items = [_expect_string(item, f"{location}[]") for item in _expect_list(values, location)]
    return sorted(set(items), key=_utf16_sort_key)


def _require_nonempty_strings(values: Any, location: str) -> list[str]:
    items = _sorted_unique_strings(values, location)
    if not items or any(item == "" for item in items):
        raise AuditError(f"{location} must contain at least one nonempty string")
    return items


def _sort_dicts(values: Iterable[dict[str, Any]], fields: Sequence[str]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[bytes, ...]:
        parts: list[bytes] = []
        for field in fields:
            value = item.get(field)
            if isinstance(value, list):
                value = canonical_bytes(value).decode("utf-8")
            elif value is None:
                value = ""
            elif not isinstance(value, str):
                value = str(value)
            parts.append(_utf16_sort_key(value))
        return tuple(parts)

    return sorted(values, key=key)


def _read_regular_file(root: Path, relative_path: str) -> bytes:
    path_text = _repo_path(relative_path, "artifact.path")
    candidate = root.joinpath(*PurePosixPath(path_text).parts)
    current = root
    for part in PurePosixPath(path_text).parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as error:
            raise AuditError(f"artifact is missing: {path_text}") from error
        if stat.S_ISLNK(mode):
            raise AuditError(f"artifact path contains a symlink: {path_text}")
    resolved_root = root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise AuditError(f"artifact escapes input root: {path_text}") from error
    if not resolved.is_file():
        raise AuditError(f"artifact is not a regular file: {path_text}")
    size = os.stat(resolved, follow_symlinks=False).st_size
    if size > MAX_INPUT_BYTES:
        raise AuditError(f"artifact exceeds {MAX_INPUT_BYTES} bytes: {path_text}")
    return resolved.read_bytes()


def _validate_generator(value: Any, *, bind_runtime: bool = False) -> dict[str, Any]:
    obj = _expect_dict(value, "generator")
    _expect_keys(
        obj,
        required=("schema_version", "name", "version", "canonicalization", "source", "noncapabilities"),
        location="generator",
    )
    if obj["schema_version"] != GENERATOR_VERSION:
        raise AuditError(f"unsupported generator schema: {obj['schema_version']!r}")
    name = _expect_identifier(obj["name"], "generator.name")
    version = _expect_string(obj["version"], "generator.version")
    canonicalization = _expect_choice(
        obj["canonicalization"],
        {"fc-jcs-ijson-integer-v1"},
        "generator.canonicalization",
    )
    source = _expect_dict(obj["source"], "generator.source")
    _expect_keys(source, required=("kind", "repository", "baseline", "overlay"), location="generator.source")
    if source["kind"] != "git_baseline_with_content_addressed_overlay":
        raise AuditError("generator.source.kind is unsupported")
    repository = _expect_https(source["repository"], "generator.source.repository")
    baseline = _validate_revision(source["baseline"], "generator.source.baseline")
    overlay = _expect_dict(source["overlay"], "generator.source.overlay")
    _expect_keys(overlay, required=("files", "root"), location="generator.source.overlay")
    files: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, raw_file in enumerate(_expect_list(overlay["files"], "generator.source.overlay.files")):
        item = _expect_dict(raw_file, f"generator.source.overlay.files[{index}]")
        _expect_keys(item, required=("path", "sha256"), location=f"generator.source.overlay.files[{index}]")
        path = _repo_path(item["path"], f"generator.source.overlay.files[{index}].path")
        if path in seen_paths:
            raise AuditError(f"duplicate generator source path: {path}")
        seen_paths.add(path)
        files.append({"path": path, "sha256": _expect_sha(item["sha256"], "generator source digest")})
    if not files:
        raise AuditError("generator.source.files must not be empty")
    files = _sort_dicts(files, ("path", "sha256"))
    expected_root = content_root({"files": files})
    if _expect_sha(overlay["root"], "generator.source.overlay.root") != expected_root:
        raise AuditError("generator source root does not match its complete file list")
    if bind_runtime:
        if name != "formal-conjectures-pr-audit" or version != "1.0.0" or canonicalization != "fc-jcs-ijson-integer-v1" or source["kind"] != "git_baseline_with_content_addressed_overlay":
            raise AuditError("generator metadata does not match reviewed local build identity")
        if repository != GENERATOR_REPOSITORY or baseline != GENERATOR_BASELINE:
            raise AuditError("generator source baseline does not match reviewed local build identity")
        runtime_files = _sort_dicts(
            [
                {"path": path, "sha256": sha256_digest((RUNTIME_ROOT / path).read_bytes())}
                for path in GENERATOR_OVERLAY_PATHS
            ],
            ("path", "sha256"),
        )
        if files != runtime_files:
            raise AuditError("generator source overlay does not match executing local bytes")
    noncapabilities = _sorted_unique_strings(obj["noncapabilities"], "generator.noncapabilities")
    required_noncapabilities = {"git", "github", "lean", "model", "network", "subprocess"}
    if not required_noncapabilities.issubset(noncapabilities):
        raise AuditError("generator identity omits a required noncapability")
    return {
        "schema_version": GENERATOR_VERSION,
        "name": name,
        "version": version,
        "canonicalization": canonicalization,
        "source": {
            "kind": source["kind"],
            "repository": repository,
            "baseline": baseline,
            "overlay": {"files": files, "root": expected_root},
        },
        "noncapabilities": noncapabilities,
    }


def _validate_descriptor(value: Any, index: int) -> dict[str, str]:
    location = f"manifest.artifacts[{index}]"
    obj = _expect_dict(value, location)
    _expect_keys(obj, required=("id", "role", "media_type", "path", "sha256"), location=location)
    media_type = _expect_choice(
        obj["media_type"],
        {"application/json", "application/vnd.github+json", "text/plain", "text/x-lean"},
        f"{location}.media_type",
    )
    return {
        "id": _expect_identifier(obj["id"], f"{location}.id"),
        "role": _expect_choice(
            obj["role"],
            {
                "generator_identity", "repository_snapshot", "check_results",
                "source_file", "method", "configuration", "tool_output", "typed_result",
                "authoritative_observation", "acquisition_receipt", "query", "provenance_event",
            },
            f"{location}.role",
        ),
        "media_type": media_type,
        "path": _repo_path(obj["path"], f"{location}.path"),
        "sha256": _expect_sha(obj["sha256"], f"{location}.sha256"),
    }


def _load_manifest(manifest_path: Path, expected_version: str) -> tuple[dict[str, Any], dict[str, tuple[dict[str, str], Any, bytes]], str]:
    raw_manifest = _read_regular_file(manifest_path.parent, manifest_path.name)
    manifest = _expect_dict(parse_json_bytes(raw_manifest, label=str(manifest_path)), "manifest")
    required = ("schema_version", "artifact_root", "artifacts")
    optional = ("observed_at",)
    _expect_keys(manifest, required=required, optional=optional, location="manifest")
    if manifest["schema_version"] != expected_version:
        raise AuditError(f"unsupported input schema: {manifest['schema_version']!r}")
    descriptors = [
        _validate_descriptor(item, index)
        for index, item in enumerate(_expect_list(manifest["artifacts"], "manifest.artifacts"))
    ]
    if not descriptors:
        raise AuditError("manifest.artifacts must not be empty")
    if len(descriptors) > MAX_MANIFEST_ARTIFACTS:
        raise AuditError(f"manifest has more than {MAX_MANIFEST_ARTIFACTS} artifacts")
    ids = [item["id"] for item in descriptors]
    paths = [item["path"] for item in descriptors]
    if len(ids) != len(set(ids)):
        raise AuditError("manifest has duplicate artifact ids")
    if len(paths) != len(set(paths)):
        raise AuditError("manifest has duplicate artifact paths")
    descriptors = _sort_dicts(descriptors, ("id", "role", "path", "sha256"))
    expected_root = content_root({"artifacts": descriptors})
    if _expect_sha(manifest["artifact_root"], "manifest.artifact_root") != expected_root:
        raise AuditError("manifest artifact root does not match descriptors")
    loaded: dict[str, tuple[dict[str, str], Any, bytes]] = {}
    for descriptor in descriptors:
        raw = _read_regular_file(manifest_path.parent, descriptor["path"])
        if sha256_digest(raw) != descriptor["sha256"]:
            raise AuditError(f"artifact digest mismatch: {descriptor['path']}")
        if descriptor["media_type"] in {"application/json", "application/vnd.github+json"}:
            value = parse_json_bytes(raw, label=descriptor["path"])
            canonical_roles = {
                "generator_identity", "repository_snapshot", "check_results", "method",
                "configuration", "tool_output", "typed_result", "acquisition_receipt",
            }
            if descriptor["role"] in canonical_roles and raw != canonical_bytes(value) + b"\n":
                raise AuditError(
                    f"structured artifact must use canonical file framing: {descriptor['path']}"
                )
        else:
            try:
                value = raw.decode("utf-8", "strict")
            except UnicodeDecodeError as error:
                raise AuditError(f"artifact is not strict UTF-8: {descriptor['path']}") from error
        loaded[descriptor["id"]] = (descriptor, value, raw)
    normalized: dict[str, Any] = {
        "schema_version": expected_version,
        "artifact_root": expected_root,
        "artifacts": descriptors,
    }
    if expected_version == OBSERVATION_INPUT_VERSION:
        normalized["observed_at"] = _expect_timestamp(manifest.get("observed_at"), "manifest.observed_at")
    if raw_manifest != canonical_bytes(normalized) + b"\n":
        raise AuditError("manifest must use canonical file framing")
    return normalized, loaded, sha256_digest(raw_manifest)


def _one_role(loaded: Mapping[str, tuple[dict[str, str], Any, bytes]], role: str) -> tuple[dict[str, str], Any, bytes]:
    matches = [value for value in loaded.values() if value[0]["role"] == role]
    if len(matches) != 1:
        raise AuditError(f"manifest must contain exactly one {role!r} artifact")
    return matches[0]


def _validate_revision(value: Any, location: str) -> dict[str, str]:
    obj = _expect_dict(value, location)
    _expect_keys(obj, required=("commit_oid", "tree_oid"), location=location)
    return {
        "commit_oid": _expect_oid(obj["commit_oid"], f"{location}.commit_oid"),
        "tree_oid": _expect_oid(obj["tree_oid"], f"{location}.tree_oid"),
    }


def _validate_repository(value: Any) -> dict[str, Any]:
    obj = _expect_dict(value, "repository snapshot")
    _expect_keys(
        obj,
        required=("schema_version", "repository", "pull_request", "comparison", "base", "head", "changes"),
        location="repository snapshot",
    )
    if obj["schema_version"] != REPOSITORY_VERSION:
        raise AuditError(f"unsupported repository snapshot schema: {obj['schema_version']!r}")
    repository = _expect_dict(obj["repository"], "repository")
    _expect_keys(repository, required=("host", "owner", "name", "url"), location="repository")
    normalized_repository = {
        "host": _expect_choice(repository["host"], {"github.com"}, "repository.host"),
        "owner": _expect_string(repository["owner"], "repository.owner"),
        "name": _expect_string(repository["name"], "repository.name"),
        "url": _expect_https(repository["url"], "repository.url"),
    }
    expected_repository_url = (
        f"https://{normalized_repository['host']}/"
        f"{normalized_repository['owner']}/{normalized_repository['name']}"
    )
    if normalized_repository["url"] != expected_repository_url:
        raise AuditError("repository.url does not match host/owner/name")
    pull_request = _expect_dict(obj["pull_request"], "pull_request")
    _expect_keys(pull_request, required=("number", "url"), location="pull_request")
    number = pull_request["number"]
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise AuditError("pull_request.number must be a positive integer")
    normalized_pr = {"number": number, "url": _expect_https(pull_request["url"], "pull_request.url")}
    if normalized_pr["url"] != f"{expected_repository_url}/pull/{number}":
        raise AuditError("pull_request.url does not match repository identity and number")
    comparison = _expect_dict(obj["comparison"], "comparison")
    _expect_keys(comparison, required=("kind", "complete"), location="comparison")
    normalized_comparison = {
        "kind": _expect_choice(
            comparison["kind"],
            {"github_pull_request_file_snapshot"},
            "comparison.kind",
        ),
        "complete": _expect_bool(comparison["complete"], "comparison.complete"),
    }
    if not normalized_comparison["complete"]:
        raise AuditError("repository comparison must declare a complete retained file snapshot")
    base = _validate_revision(obj["base"], "base")
    head = _validate_revision(obj["head"], "head")
    changes: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, raw_change in enumerate(_expect_list(obj["changes"], "changes")):
        location = f"changes[{index}]"
        change = _expect_dict(raw_change, location)
        _expect_keys(
            change,
            required=("path", "status", "base_blob_oid", "base_blob_sha256", "head_blob_oid", "head_blob_sha256"),
            location=location,
        )
        path = _repo_path(change["path"], f"{location}.path")
        if path in seen_paths:
            raise AuditError(f"duplicate changed path: {path}")
        seen_paths.add(path)
        status_value = _expect_choice(change["status"], {"added", "modified", "deleted"}, f"{location}.status")
        def optional_oid(raw: Any, field: str) -> str | None:
            return None if raw is None else _expect_oid(raw, f"{location}.{field}")
        def optional_sha(raw: Any, field: str) -> str | None:
            return None if raw is None else _expect_sha(raw, f"{location}.{field}")
        normalized_change = {
            "path": path,
            "status": status_value,
            "base_blob_oid": optional_oid(change["base_blob_oid"], "base_blob_oid"),
            "base_blob_sha256": optional_sha(change["base_blob_sha256"], "base_blob_sha256"),
            "head_blob_oid": optional_oid(change["head_blob_oid"], "head_blob_oid"),
            "head_blob_sha256": optional_sha(change["head_blob_sha256"], "head_blob_sha256"),
        }
        base_present = normalized_change["base_blob_oid"] is not None and normalized_change["base_blob_sha256"] is not None
        head_present = normalized_change["head_blob_oid"] is not None and normalized_change["head_blob_sha256"] is not None
        if status_value == "added" and (base_present or not head_present):
            raise AuditError(f"added path has inconsistent blob identities: {path}")
        if status_value == "deleted" and (not base_present or head_present):
            raise AuditError(f"deleted path has inconsistent blob identities: {path}")
        if status_value == "modified" and (not base_present or not head_present):
            raise AuditError(f"modified path has incomplete blob identities: {path}")
        changes.append(normalized_change)
    if not changes:
        raise AuditError("repository snapshot must contain at least one changed path")
    changes = _sort_dicts(changes, ("path", "status"))
    return {
        "repository": normalized_repository,
        "pull_request": normalized_pr,
        "comparison": normalized_comparison,
        "base": base,
        "head": head,
        "changes": changes,
    }


def _validate_implementation(value: Any, location: str) -> dict[str, Any]:
    obj = _expect_dict(value, location)
    _expect_keys(obj, required=("name", "version", "kind", "locator", "root"), location=location)
    return {
        "name": _expect_identifier(obj["name"], f"{location}.name"),
        "version": _expect_string(obj["version"], f"{location}.version"),
        "kind": _expect_choice(
            obj["kind"],
            {"retained_procedure", "github_actions_workflow", "human_review_guide", "external_checker"},
            f"{location}.kind",
        ),
        "locator": _expect_string(obj["locator"], f"{location}.locator"),
        "root": _expect_sha(obj["root"], f"{location}.root"),
    }


def _validate_check_input(value: Any, location: str) -> dict[str, str]:
    obj = _expect_dict(value, location)
    _expect_keys(obj, required=("id", "artifact_id", "kind", "locator", "root"), location=location)
    return {
        "id": _expect_identifier(obj["id"], f"{location}.id"),
        "artifact_id": _expect_identifier(obj["artifact_id"], f"{location}.artifact_id"),
        "kind": _expect_identifier(obj["kind"], f"{location}.kind"),
        "locator": _expect_string(obj["locator"], f"{location}.locator"),
        "root": _expect_sha(obj["root"], f"{location}.root"),
    }


def _validate_condition(value: Any, location: str) -> dict[str, str]:
    obj = _expect_dict(value, location)
    _expect_keys(obj, required=("declaration", "statement", "locator"), location=location)
    return {
        "declaration": _expect_string(obj["declaration"], f"{location}.declaration"),
        "statement": _expect_string(obj["statement"], f"{location}.statement"),
        "locator": _expect_string(obj["locator"], f"{location}.locator"),
    }


def _validate_proof(value: Any, location: str) -> dict[str, Any]:
    obj = _expect_dict(value, location)
    _expect_keys(obj, required=("declaration", "kind", "locator", "conditions"), location=location)
    conditions = [
        _validate_condition(item, f"{location}.conditions[{index}]")
        for index, item in enumerate(_expect_list(obj["conditions"], f"{location}.conditions"))
    ]
    conditions = _sort_dicts(conditions, ("declaration", "statement", "locator"))
    kind = _expect_choice(
        obj["kind"],
        {"formal_conjectures", "lean4", "other_system"},
        f"{location}.kind",
    )
    locator = _expect_string(obj["locator"], f"{location}.locator", nonempty=False)
    if kind != "formal_conjectures" and not locator:
        raise AuditError(f"{location}.locator must not be empty for {kind}")
    return {
        "declaration": _expect_string(obj["declaration"], f"{location}.declaration"),
        "kind": kind,
        "locator": locator,
        "conditions": conditions,
    }


def _validate_evidence(value: Any, location: str) -> dict[str, str]:
    obj = _expect_dict(value, location)
    _expect_keys(obj, required=("kind", "locator", "sha256", "statement", "witness"), location=location)
    return {
        "kind": _expect_identifier(obj["kind"], f"{location}.kind"),
        "locator": _expect_string(obj["locator"], f"{location}.locator"),
        "sha256": _expect_sha(obj["sha256"], f"{location}.sha256"),
        "statement": _expect_string(obj["statement"], f"{location}.statement"),
        "witness": _expect_string(obj["witness"], f"{location}.witness", nonempty=False),
    }


def _validate_check(value: Any, index: int) -> dict[str, Any]:
    location = f"checks[{index}]"
    obj = _expect_dict(value, location)
    _expect_keys(
        obj,
        required=(
            "id", "kind", "mode", "property", "role", "outcome", "severity", "scope",
            "implementation", "inputs", "evidence", "conditions", "assumptions", "proofs",
            "limitations", "does_not_establish",
        ),
        location=location,
    )
    scope = _expect_dict(obj["scope"], f"{location}.scope")
    _expect_keys(scope, required=("revision", "paths", "declarations"), location=f"{location}.scope")
    paths = [_repo_path(path, f"{location}.scope.paths[]") for path in _expect_list(scope["paths"], f"{location}.scope.paths")]
    paths = sorted(set(paths), key=_utf16_sort_key)
    declarations = _sorted_unique_strings(scope["declarations"], f"{location}.scope.declarations")
    if not paths and not declarations:
        raise AuditError(f"{location}.scope must name a path or declaration")
    evidence = [
        _validate_evidence(item, f"{location}.evidence[{evidence_index}]")
        for evidence_index, item in enumerate(_expect_list(obj["evidence"], f"{location}.evidence"))
    ]
    if not evidence:
        raise AuditError(f"{location}.evidence must not be empty")
    evidence = _sort_dicts(evidence, ("kind", "locator", "sha256", "statement", "witness"))
    proofs = [
        _validate_proof(item, f"{location}.proofs[{proof_index}]")
        for proof_index, item in enumerate(_expect_list(obj["proofs"], f"{location}.proofs"))
    ]
    proofs = sorted(
        proofs,
        key=lambda item: (
            _utf16_sort_key(item["declaration"]),
            _utf16_sort_key(item["kind"]),
            _utf16_sort_key(item["locator"]),
            canonical_bytes(item["conditions"]),
        ),
    )
    inputs = [
        _validate_check_input(item, f"{location}.inputs[{input_index}]")
        for input_index, item in enumerate(_expect_list(obj["inputs"], f"{location}.inputs"))
    ]
    if not inputs:
        raise AuditError(f"{location}.inputs must not be empty")
    input_ids = [item["id"] for item in inputs]
    if len(input_ids) != len(set(input_ids)):
        raise AuditError(f"{location}.inputs contains duplicate ids")
    inputs = _sort_dicts(inputs, ("id", "artifact_id", "kind", "locator", "root"))
    conditions = [
        _validate_condition(item, f"{location}.conditions[{condition_index}]")
        for condition_index, item in enumerate(_expect_list(obj["conditions"], f"{location}.conditions"))
    ]
    conditions = _sort_dicts(conditions, ("declaration", "statement", "locator"))
    assumptions = [
        _validate_condition(item, f"{location}.assumptions[{assumption_index}]")
        for assumption_index, item in enumerate(_expect_list(obj["assumptions"], f"{location}.assumptions"))
    ]
    assumptions = _sort_dicts(assumptions, ("declaration", "statement", "locator"))
    outcome = _expect_choice(
        obj["outcome"], {"pass", "fail", "inconclusive", "error", "unavailable"},
        f"{location}.outcome",
    )
    severity = _expect_choice(obj["severity"], {"none", "nit", "meaning"}, f"{location}.severity")
    if outcome == "fail" and severity == "none":
        raise AuditError(f"{location} fail outcome requires nit or meaning severity")
    if outcome != "fail" and severity != "none":
        raise AuditError(f"{location} non-fail outcome requires none severity")
    return {
        "id": _expect_identifier(obj["id"], f"{location}.id"),
        "kind": _expect_choice(
            obj["kind"],
            {"mechanical", "semantic", "proof", "metadata"},
            f"{location}.kind",
        ),
        "mode": _expect_choice(
            obj["mode"],
            {"native", "comparator", "human_review", "retained_replay"},
            f"{location}.mode",
        ),
        "property": _expect_identifier(obj["property"], f"{location}.property"),
        "role": _expect_choice(obj["role"], {"producer", "independent", "advisory"}, f"{location}.role"),
        "outcome": outcome,
        "severity": severity,
        "scope": {
            "revision": _expect_choice(scope["revision"], {"base", "head", "comparison"}, f"{location}.scope.revision"),
            "paths": paths,
            "declarations": declarations,
        },
        "implementation": _validate_implementation(obj["implementation"], f"{location}.implementation"),
        "inputs": inputs,
        "evidence": evidence,
        "conditions": conditions,
        "assumptions": assumptions,
        "proofs": proofs,
        "limitations": _sorted_unique_strings(obj["limitations"], f"{location}.limitations"),
        "does_not_establish": _require_nonempty_strings(
            obj["does_not_establish"], f"{location}.does_not_establish"
        ),
    }


def _validate_checks(value: Any) -> list[dict[str, Any]]:
    obj = _expect_dict(value, "check results")
    _expect_keys(obj, required=("schema_version", "checks"), location="check results")
    if obj["schema_version"] != CHECKS_VERSION:
        raise AuditError(f"unsupported check results schema: {obj['schema_version']!r}")
    checks = [
        _validate_check(item, index)
        for index, item in enumerate(_expect_list(obj["checks"], "checks"))
    ]
    if not checks:
        raise AuditError("check results must contain at least one check")
    ids = [check["id"] for check in checks]
    if len(ids) != len(set(ids)):
        raise AuditError("check results contain duplicate check ids")
    return _sort_dicts(checks, ("id", "property", "role", "outcome"))


def _validate_implementation_binding(
    check: Mapping[str, Any],
    descriptors_by_id: Mapping[str, Mapping[str, Any]],
    generator: Mapping[str, Any],
) -> None:
    """Bind a v1 implementation claim to its retained method identity."""

    implementation = check["implementation"]
    implementation_inputs = [
        input_record
        for input_record in check["inputs"]
        if descriptors_by_id[input_record["artifact_id"]]["role"] in {"method", "configuration"}
        and input_record["root"] == implementation["root"]
        and (
            input_record["locator"] == implementation["locator"]
            or implementation["locator"].startswith(input_record["locator"] + "#")
        )
    ]
    if len(implementation_inputs) != 1:
        raise AuditError(
            f"check {check['id']!r} implementation root/locator must match exactly one retained method/configuration input"
        )

    locator = implementation["locator"]
    if locator == "scripts/pr_audit.py":
        expected = ("pr-audit-snapshot-validator", "1", "retained_procedure")
    elif locator == "scripts/pr_audit.py#classify_proof_target":
        expected = ("formal-proof-target-classifier", "1", "retained_procedure")
    elif locator == "metadata-review-procedure.json":
        expected = ("retained-formal-proof-metadata-review", "1", "retained_procedure")
    elif locator == "comparator-packet-procedure.json":
        expected = ("comparator-packet-inspection", "1", "retained_procedure")
    elif locator == "model-advisory-procedure.json":
        expected = ("model-advisory-adapter", "1", "external_checker")
    elif re.fullmatch(r"\.github/workflows/build-and-docs\.yml@[0-9a-f]{40}", locator):
        expected = ("build-and-docs", "1", "github_actions_workflow")
    elif re.fullmatch(r"REVIEW_MATH\.md@[0-9a-f]{40}#L[0-9]+-L[0-9]+", locator):
        expected = ("mathematical-review-guide", "1", "human_review_guide")
    else:
        raise AuditError(f"check {check['id']!r} implementation locator is not defined by the v1 profile")

    actual = (implementation["name"], implementation["version"], implementation["kind"])
    if actual != expected:
        raise AuditError(
            f"check {check['id']!r} implementation name/version/kind do not match its retained method"
        )
    if locator in {"scripts/pr_audit.py", "scripts/pr_audit.py#classify_proof_target"}:
        overlay_files = generator["source"]["overlay"]["files"]
        implementation_digest = next(
            (item["sha256"] for item in overlay_files if item["path"] == "scripts/pr_audit.py"),
            None,
        )
        if implementation["root"] != implementation_digest:
            raise AuditError(
                f"check {check['id']!r} retained internal method does not match the generator overlay"
            )


def _check_result_projection(check: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in check.items() if key != "inputs"}


def _validate_result_producer(value: Any, location: str) -> dict[str, Any]:
    producer = _expect_dict(value, location)
    _expect_keys(
        producer,
        required=("kind", "id", "authority", "independent"),
        location=location,
    )
    normalized = {
        "kind": _expect_choice(
            producer["kind"],
            {
                "deterministic_adapter", "retained_external_result", "ai_review_preparer",
                "human_reviewer",
            },
            f"{location}.kind",
        ),
        "id": _expect_identifier(producer["id"], f"{location}.id"),
        "authority": _expect_choice(
            producer["authority"],
            {"producer_evidence_only", "advisory_packet_preparation_only", "independent_human_review"},
            f"{location}.authority",
        ),
        "independent": _expect_bool(producer["independent"], f"{location}.independent"),
    }
    expected_authority = {
        "deterministic_adapter": ("producer_evidence_only", False),
        "retained_external_result": ("producer_evidence_only", False),
        "ai_review_preparer": ("advisory_packet_preparation_only", False),
        "human_reviewer": ("independent_human_review", True),
    }[normalized["kind"]]
    if (normalized["authority"], normalized["independent"]) != expected_authority:
        raise AuditError(f"{location} kind cannot claim that authority or independence")
    return normalized


def _expected_result_producer(
    check: Mapping[str, Any], result_input: Mapping[str, Any]
) -> dict[str, Any]:
    location = f"typed result for {check['id']}"
    if result_input["id"] != "typed-result" or result_input["kind"] != "typed-result":
        raise AuditError(f"{location} relation has an invalid id or kind")
    match = TYPED_RESULT_LOCATOR_RE.fullmatch(result_input["locator"])
    if match is None:
        raise AuditError(f"{location} relation locator does not identify its producer")
    claimed_kind, raw_identifier = match.groups()
    claimed_id = _expect_identifier(raw_identifier, f"{location}.producer_id")
    if check["kind"] == "semantic" and check["role"] == "independent":
        expected_kind, expected_id = "human_reviewer", claimed_id
    elif check["kind"] == "semantic" or check["mode"] == "human_review":
        expected_kind, expected_id = "ai_review_preparer", "codex_ai_packet_preparer"
    elif check["property"] == "lean-build":
        expected_kind, expected_id = "retained_external_result", "github_actions"
    else:
        expected_kind, expected_id = "deterministic_adapter", "formal_conjectures_pr_audit"
    if (claimed_kind, claimed_id) != (expected_kind, expected_id):
        raise AuditError(f"{location} relation does not match the supported producer profile")
    authority, independent = {
        "deterministic_adapter": ("producer_evidence_only", False),
        "retained_external_result": ("producer_evidence_only", False),
        "ai_review_preparer": ("advisory_packet_preparation_only", False),
        "human_reviewer": ("independent_human_review", True),
    }[expected_kind]
    return {
        "kind": expected_kind,
        "id": expected_id,
        "authority": authority,
        "independent": independent,
    }


def _expected_typed_result(
    *,
    check: Mapping[str, Any],
    repository: Mapping[str, Any],
    result_input: Mapping[str, Any],
) -> dict[str, Any]:
    location = f"typed result for {check['id']}"
    if check["property"] not in SUPPORTED_PROPERTIES:
        raise AuditError(f"unsupported or unimplemented check property: {check['property']}")
    producer = _expected_result_producer(check, result_input)
    artifacts = _sort_dicts(
        [item for item in check["inputs"] if item["kind"] != "typed-result"],
        ("id", "artifact_id", "kind", "locator", "root"),
    )
    semantic_review: dict[str, Any] | None = None
    if check["kind"] == "semantic":
        if len(check["evidence"]) != 1:
            raise AuditError(f"{location} semantic review requires exactly one finding/witness")
        matching_changes = [
            item for item in repository["changes"] if item["path"] in check["scope"]["paths"]
        ]
        if (
            len(matching_changes) != 1
            or matching_changes[0]["head_blob_oid"] is None
            or matching_changes[0]["head_blob_sha256"] is None
        ):
            raise AuditError(f"{location} semantic review requires exactly one exact head source")
        changed = matching_changes[0]
        head_relations = [
            item for item in artifacts
            if item["locator"] == f"{changed['path']}@{repository['head']['commit_oid']}"
            and item["root"] == changed["head_blob_sha256"]
        ]
        if len(head_relations) != 1:
            raise AuditError(f"{location} semantic review must bind exactly one head-source relation")
        if check["role"] == "independent":
            if check["mode"] != "human_review" or producer["kind"] != "human_reviewer":
                raise AuditError(f"{location} independent semantic result requires a named human reviewer")
            reviewer: str | None = producer["id"]
        else:
            if check["role"] != "advisory" or producer["kind"] != "ai_review_preparer":
                raise AuditError(f"{location} AI-prepared semantic result must remain advisory")
            reviewer = None
        evidence = check["evidence"][0]
        semantic_review = {
            "preparer": producer["id"],
            "reviewer": reviewer,
            "authority": producer["authority"],
            "independent": producer["independent"],
            "outcome": check["outcome"],
            "severity": check["severity"],
            "finding": evidence["statement"],
            "witness": evidence["witness"],
            "head_commit_oid": repository["head"]["commit_oid"],
            "head_blob_oid": changed["head_blob_oid"],
            "source_root": changed["head_blob_sha256"],
            "scope": check["scope"],
            "declarations": check["scope"]["declarations"],
            "method": check["implementation"],
        }
    return {
        "schema_version": TYPED_RESULT_VERSION,
        "result_id": check["id"],
        "check": _check_result_projection(check),
        "artifacts": artifacts,
        "producer": producer,
        "semantic_review": semantic_review,
    }


def _validate_typed_result(
    value: Any,
    *,
    check: Mapping[str, Any],
    repository: Mapping[str, Any],
    result_input: Mapping[str, Any],
) -> dict[str, Any]:
    location = f"typed result for {check['id']}"
    expected = _expected_typed_result(
        check=check,
        repository=repository,
        result_input=result_input,
    )
    result = _expect_dict(value, location)
    _expect_keys(
        result,
        required=("schema_version", "result_id", "check", "artifacts", "producer", "semantic_review"),
        location=location,
    )
    if result["schema_version"] != TYPED_RESULT_VERSION:
        raise AuditError(f"{location} has unsupported schema")
    if _expect_identifier(result["result_id"], f"{location}.result_id") != check["id"]:
        raise AuditError(f"{location} id does not match check")
    projection = _expect_dict(result["check"], f"{location}.check")
    if projection != expected["check"]:
        raise AuditError(f"{location} does not derive the complete check projection")
    artifacts = [
        _validate_check_input(item, f"{location}.artifacts[{index}]")
        for index, item in enumerate(_expect_list(result["artifacts"], f"{location}.artifacts"))
    ]
    artifact_ids = [item["id"] for item in artifacts]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise AuditError(f"{location} has duplicate artifact relations")
    artifacts = _sort_dicts(artifacts, ("id", "artifact_id", "kind", "locator", "root"))
    if artifacts != expected["artifacts"]:
        raise AuditError(f"{location} artifact relations do not match check inputs")
    producer = _validate_result_producer(result["producer"], f"{location}.producer")
    if producer != expected["producer"]:
        raise AuditError(f"{location} producer does not match its typed relation")
    semantic_review = result["semantic_review"]
    normalized_review: dict[str, Any] | None = None
    if expected["semantic_review"] is None:
        if semantic_review is not None:
            raise AuditError(f"{location} non-semantic result must not claim semantic review")
    else:
        review = _expect_dict(semantic_review, f"{location}.semantic_review")
        _expect_keys(
            review,
            required=(
                "preparer", "reviewer", "authority", "independent", "outcome", "severity",
                "finding", "witness", "head_commit_oid", "head_blob_oid", "source_root",
                "scope", "declarations", "method",
            ),
            location=f"{location}.semantic_review",
        )
        reviewer = review["reviewer"]
        if reviewer is not None:
            reviewer = _expect_identifier(reviewer, f"{location}.semantic_review.reviewer")
        normalized_review = {
            "preparer": _expect_identifier(review["preparer"], f"{location}.semantic_review.preparer"),
            "reviewer": reviewer,
            "authority": _expect_string(review["authority"], f"{location}.semantic_review.authority"),
            "independent": _expect_bool(review["independent"], f"{location}.semantic_review.independent"),
            "outcome": _expect_choice(review["outcome"], {"pass", "fail", "inconclusive", "error", "unavailable"}, f"{location}.semantic_review.outcome"),
            "severity": _expect_choice(review["severity"], {"none", "nit", "meaning"}, f"{location}.semantic_review.severity"),
            "finding": _expect_string(review["finding"], f"{location}.semantic_review.finding"),
            "witness": _expect_string(review["witness"], f"{location}.semantic_review.witness", nonempty=False),
            "head_commit_oid": _expect_oid(review["head_commit_oid"], f"{location}.semantic_review.head_commit_oid"),
            "head_blob_oid": _expect_oid(review["head_blob_oid"], f"{location}.semantic_review.head_blob_oid"),
            "source_root": _expect_sha(review["source_root"], f"{location}.semantic_review.source_root"),
            "scope": review["scope"],
            "declarations": _sorted_unique_strings(review["declarations"], f"{location}.semantic_review.declarations"),
            "method": _validate_implementation(review["method"], f"{location}.semantic_review.method"),
        }
        if normalized_review != expected["semantic_review"]:
            raise AuditError(f"{location} semantic review does not match outcome, scope, source, or method")
    normalized = {
        "schema_version": TYPED_RESULT_VERSION,
        "result_id": check["id"],
        "check": expected["check"],
        "artifacts": artifacts,
        "producer": producer,
        "semantic_review": normalized_review,
    }
    if normalized != expected:
        raise AuditError(f"{location} does not match its supported typed profile")
    return normalized


def _disposition(
    checks: Sequence[dict[str, Any]], required_semantic_paths: Iterable[str] = ()
) -> tuple[str, list[str]]:
    invalid_failures = [check["id"] for check in checks if check["outcome"] == "fail" and check["severity"] == "none"]
    meaning_failures = [check["id"] for check in checks if check["outcome"] == "fail" and check["severity"] == "meaning"]
    nit_failures = [check["id"] for check in checks if check["outcome"] == "fail" and check["severity"] == "nit"]
    unavailable = [check["id"] for check in checks if check["outcome"] == "unavailable"]
    inconclusive = [check["id"] for check in checks if check["outcome"] == "inconclusive"]
    errors = [check["id"] for check in checks if check["outcome"] == "error"]
    if invalid_failures or meaning_failures:
        return "needs_revision", sorted(invalid_failures + meaning_failures, key=_utf16_sort_key)
    if nit_failures:
        return "nits_found", sorted(nit_failures, key=_utf16_sort_key)
    if errors or inconclusive:
        return "inconclusive", sorted(errors + inconclusive, key=_utf16_sort_key)
    if unavailable:
        return "unavailable", sorted(unavailable, key=_utf16_sort_key)
    semantic_ground_truth = [
        check["id"]
        for check in checks
        if check["kind"] == "semantic"
        and check["mode"] == "human_review"
        and check["role"] == "independent"
        and check["outcome"] == "pass"
    ]
    covered_paths = {
        path
        for check in checks
        if check["id"] in semantic_ground_truth
        for path in check["scope"]["paths"]
    }
    required_paths = set(required_semantic_paths)
    if not semantic_ground_truth or not required_paths.issubset(covered_paths):
        return "inconclusive", sorted((check["id"] for check in checks), key=_utf16_sort_key)
    return "clean", sorted(semantic_ground_truth, key=_utf16_sort_key)


def _with_root(value: dict[str, Any]) -> dict[str, Any]:
    rooted = dict(value)
    rooted["root"] = content_root(value)
    return rooted


def generate_core(manifest_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Generate a deterministic core from retained repository and check artifacts."""

    path = Path(manifest_path).resolve(strict=True)
    manifest, loaded, manifest_digest = _load_manifest(path, CORE_INPUT_VERSION)
    invalid_core_roles = sorted(
        {descriptor["role"] for descriptor in manifest["artifacts"]} - CORE_ARTIFACT_ROLES,
        key=_utf16_sort_key,
    )
    if invalid_core_roles:
        raise AuditError(f"core manifest contains observation/provenance roles: {invalid_core_roles!r}")
    generator_descriptor, generator_value, _ = _one_role(loaded, "generator_identity")
    repository_descriptor, repository_value, _ = _one_role(loaded, "repository_snapshot")
    check_artifacts = [value for value in loaded.values() if value[0]["role"] == "check_results"]
    if not check_artifacts:
        raise AuditError("core manifest must contain at least one check_results artifact")
    if any(value[0]["role"] == "authoritative_observation" for value in loaded.values()):
        raise AuditError("mutable observation artifacts are forbidden in a core manifest")
    generator = _validate_generator(generator_value, bind_runtime=True)
    repository = _validate_repository(repository_value)
    if len(check_artifacts) != 1:
        raise AuditError("core manifest must contain exactly one normalized check_results artifact")
    checks: list[dict[str, Any]] = []
    for _, value, _ in check_artifacts:
        checks.extend(_validate_checks(value))
    ids = [check["id"] for check in checks]
    if len(ids) != len(set(ids)):
        raise AuditError("duplicate check ids across retained artifacts")
    checks = _sort_dicts(checks, ("id", "property", "role", "outcome"))
    descriptors_by_id = {descriptor["id"]: descriptor for descriptor in manifest["artifacts"]}
    referenced_artifact_ids = {
        input_record["artifact_id"]
        for check in checks
        for input_record in check["inputs"]
    }
    core_evidence_ids = {
        descriptor["id"]
        for descriptor in manifest["artifacts"]
        if descriptor["role"] in {"source_file", "method", "configuration", "tool_output", "query", "typed_result"}
    }
    if referenced_artifact_ids != core_evidence_ids:
        missing = sorted(core_evidence_ids - referenced_artifact_ids, key=_utf16_sort_key)
        unknown = sorted(referenced_artifact_ids - core_evidence_ids, key=_utf16_sort_key)
        raise AuditError(f"check input artifact inventory mismatch; unreferenced={missing!r}, unknown={unknown!r}")
    for check in checks:
        if check["property"] not in SUPPORTED_PROPERTIES:
            raise AuditError(f"unsupported or unimplemented check property: {check['property']}")
        result_inputs = [item for item in check["inputs"] if item["kind"] == "typed-result"]
        if len(result_inputs) != 1:
            raise AuditError(f"check {check['id']!r} must bind exactly one typed result")
        result_input = result_inputs[0]
        result_descriptor = descriptors_by_id.get(result_input["artifact_id"])
        if result_descriptor is None or result_descriptor["role"] != "typed_result":
            raise AuditError(f"check {check['id']!r} typed result relation has the wrong artifact role")
        if (
            result_descriptor["id"] != f"typed-result-{check['id']}"
            or result_descriptor["path"] != f"inputs/typed-result-{check['id']}.json"
            or result_descriptor["media_type"] != "application/json"
        ):
            raise AuditError(f"check {check['id']!r} typed result descriptor identity is invalid")
        _validate_typed_result(
            loaded[result_input["artifact_id"]][1],
            check=check,
            repository=repository,
            result_input=result_input,
        )
        for input_record in check["inputs"]:
            descriptor = descriptors_by_id[input_record["artifact_id"]]
            if input_record["root"] != descriptor["sha256"]:
                raise AuditError(
                    f"check {check['id']!r} input {input_record['id']!r} root does not match retained artifact"
                )
        for evidence_record in check["evidence"]:
            if not any(
                input_record["root"] == evidence_record["sha256"]
                and input_record["locator"] == evidence_record["locator"]
                for input_record in check["inputs"]
            ):
                raise AuditError(
                    f"check {check['id']!r} evidence locator/root tuple is not among its retained inputs"
                )
        for proof in check["proofs"]:
            classification = classify_proof_target(proof["kind"], proof["locator"])
            matching_proof_inputs = [
                input_record for input_record in check["inputs"]
                if input_record["locator"] == proof["locator"]
                and descriptors_by_id[input_record["artifact_id"]]["role"] == "source_file"
            ]
            if classification == "resolvable" and not matching_proof_inputs:
                raise AuditError(f"check {check['id']!r} external proof locator is not bound to retained source bytes")
            if classification == "unavailable" and not (
                check["property"] == "exact-formal-proof-artifact-identity"
                and check["outcome"] == "unavailable"
            ):
                raise AuditError(f"check {check['id']!r} external proof locator is mutable or ambiguous")
        if check["property"] == "comparator-packet-identity":
            procedures = [
                loaded[input_record["artifact_id"]][1]
                for input_record in check["inputs"]
                if input_record["locator"] == "comparator-packet-procedure.json"
            ]
            observations = [
                loaded[input_record["artifact_id"]][1]
                for input_record in check["inputs"]
                if input_record["kind"] == "packet-inspection-observation"
            ]
            expected_procedure = {
                "schema_version": "formal-conjectures.pr-audit-packet-inspection-procedure.v1",
                "name": "comparator-packet-inspection",
                "version": "1",
                "operation": "inspect_retained_packet_inventory_only",
                "required_identities": sorted(
                    ["exact executable bytes", "exact invocation", "package or toolchain lock", "raw execution result"],
                    key=_utf16_sort_key,
                ),
                "executes_tool": False,
            }
            if procedures != [expected_procedure]:
                raise AuditError("Comparator packet inspection procedure is incomplete or invalid")
            if len(observations) != 1:
                raise AuditError("Comparator packet identity requires one retained inspection observation")
            observation = _expect_dict(observations[0], "Comparator packet inspection observation")
            _expect_keys(
                observation,
                required=("schema_version", "procedure", "preparer", "inventory_scope", "missing_identities", "outcome", "tool_resolution_attempted", "tool_invocation_attempted", "authority"),
                location="Comparator packet inspection observation",
            )
            expected_missing = expected_procedure["required_identities"]
            if (
                observation["schema_version"] != "formal-conjectures.pr-audit-packet-inspection-observation.v1"
                or observation["procedure"] != "comparator-packet-inspection"
                or observation["preparer"] != "codex_ai_packet_preparer"
                or observation["inventory_scope"] != "retained PR-audit packet and reviewed baseline overlay"
                or _sorted_unique_strings(observation["missing_identities"], "Comparator packet missing identities") != expected_missing
                or observation["outcome"] != "unavailable"
                or observation["tool_resolution_attempted"] is not False
                or observation["tool_invocation_attempted"] is not False
                or observation["authority"] != "advisory_packet_preparation_only"
                or check["outcome"] != "unavailable"
            ):
                raise AuditError("Comparator packet inspection observation is invalid")
        if check["property"] == "comparator-tool-availability":
            raise AuditError(
                "Comparator tool availability requires a real retained invocation and is not implemented by v1"
            )
        if check["property"].startswith("model-"):
            raise AuditError(
                "model checks are deferred until v1 has a rooted model, prompt, rubric, request, and raw response profile"
            )
        _validate_implementation_binding(check, descriptors_by_id, generator)
        if check["property"] == "exact-formal-proof-artifact-identity":
            if len(check["proofs"]) != 1:
                raise AuditError("formal-proof artifact identity check requires exactly one proof target")
            proof = check["proofs"][0]
            classification = classify_proof_target(proof["kind"], proof["locator"])
            expected_outcome = "unavailable" if classification == "unavailable" else "pass"
            if check["outcome"] != expected_outcome:
                raise AuditError("formal-proof artifact identity outcome does not match retained classifier")
    git_inputs = {
        input_record["locator"]: input_record
        for check in checks
        for input_record in check["inputs"]
        if input_record["kind"] == "git-blob"
    }
    for change in repository["changes"]:
        for revision, identity in (("base", repository["base"]), ("head", repository["head"])):
            sha_field = f"{revision}_blob_sha256"
            oid_field = f"{revision}_blob_oid"
            if change[sha_field] is None:
                continue
            locator = f"{change['path']}@{identity['commit_oid']}"
            input_record = git_inputs.get(locator)
            if input_record is None or input_record["root"] != change[sha_field]:
                raise AuditError(f"retained {revision} source is missing for changed path: {change['path']}")
            raw = loaded[input_record["artifact_id"]][2]
            if git_blob_oid(raw) != change[oid_field]:
                raise AuditError(f"retained {revision} source Git blob OID mismatch: {change['path']}")
    for check in checks:
        implementation = check["implementation"]
        implementation_locator = implementation["locator"]
        if implementation["kind"] == "github_actions_workflow":
            method_input = next(
                item for item in check["inputs"]
                if item["root"] == implementation["root"]
                and descriptors_by_id[item["artifact_id"]]["role"] == "configuration"
            )
            identity_values = [
                loaded[item["artifact_id"]][1]
                for item in check["inputs"]
                if item["kind"] == "git-object-identity" and item["locator"] == implementation_locator
            ]
            if len(identity_values) != 1:
                raise AuditError("workflow implementation requires one retained Git object identity")
            identity = _expect_dict(identity_values[0], "workflow Git object identity")
            _expect_keys(identity, required=("schema_version", "repository", "commit_oid", "tree_oid", "path", "blob_oid", "sha256", "authority"), location="workflow Git object identity")
            raw_method = loaded[method_input["artifact_id"]][2]
            if identity != {
                "schema_version": "formal-conjectures.pr-audit-git-object-identity.v1",
                "repository": repository["repository"]["url"],
                "commit_oid": repository["head"]["commit_oid"],
                "tree_oid": repository["head"]["tree_oid"],
                "path": ".github/workflows/build-and-docs.yml",
                "blob_oid": git_blob_oid(raw_method),
                "sha256": sha256_digest(raw_method),
                "authority": "retained_exact_head_git_object_identity",
            }:
                raise AuditError("workflow Git object identity does not bind exact head method bytes")
        if implementation["kind"] == "human_review_guide":
            method_input = next(
                item for item in check["inputs"]
                if item["root"] == implementation["root"]
                and descriptors_by_id[item["artifact_id"]]["role"] == "method"
            )
            base_locator = implementation_locator.split("#", 1)[0]
            identity_values = [
                loaded[item["artifact_id"]][1]
                for item in check["inputs"]
                if item["kind"] == "git-object-identity" and item["locator"] == base_locator
            ]
            if len(identity_values) != 1:
                raise AuditError("review guide implementation requires one retained Git object identity")
            identity = _expect_dict(identity_values[0], "review guide Git object identity")
            _expect_keys(identity, required=("schema_version", "repository", "commit_oid", "path", "blob_oid", "sha256", "authority"), location="review guide Git object identity")
            raw_method = loaded[method_input["artifact_id"]][2]
            revision = base_locator.rsplit("@", 1)[1]
            if identity != {
                "schema_version": "formal-conjectures.pr-audit-git-object-identity.v1",
                "repository": repository["repository"]["url"],
                "commit_oid": revision,
                "path": "REVIEW_MATH.md",
                "blob_oid": git_blob_oid(raw_method),
                "sha256": sha256_digest(raw_method),
                "authority": "retained_commit_qualified_git_object_identity",
            }:
                raise AuditError("review guide Git object identity does not bind commit-qualified method bytes")
    queries = [value for value in loaded.values() if value[0]["role"] == "query"]
    if len(queries) != 1:
        raise AuditError("core manifest must retain exactly one repository authority query")
    query_text = _expect_string(queries[0][1], "core repository authority query")
    if query_text != CORE_GRAPHQL_OPERATION:
        raise AuditError("core repository authority query bytes are not the exact v1 operation")
    authority_results = [
        value for value in loaded.values()
        if value[0]["role"] == "tool_output"
        and isinstance(value[1], dict)
        and value[1].get("schema_version") == "formal-conjectures.pr-audit-repository-result.v1"
    ]
    if len(authority_results) != 1:
        raise AuditError("core manifest must retain exactly one normalized repository result")
    request_identities = [
        value for value in loaded.values()
        if value[0]["role"] == "configuration"
        and isinstance(value[1], dict)
        and value[1].get("schema_version") == "formal-conjectures.pr-audit-request-identity.v1"
    ]
    if len(request_identities) != 1:
        raise AuditError("core manifest must retain exactly one deterministic request identity")
    request_identity = _expect_dict(request_identities[0][1], "core repository request identity")
    _expect_keys(
        request_identity,
        required=("schema_version", "operation_name", "variables", "query_sha256", "result_sha256"),
        location="core repository request identity",
    )
    if request_identity["operation_name"] != "PullRequestAuditCoreSnapshot":
        raise AuditError("core request identity operation name is invalid")
    variables = _expect_dict(request_identity["variables"], "core repository request identity.variables")
    _expect_keys(variables, required=("owner", "name", "number", "baseOid", "headOid", "baseExpression", "headExpression"), location="core repository request identity.variables")
    change = repository["changes"][0]
    expected_variables = {
        "owner": repository["repository"]["owner"], "name": repository["repository"]["name"],
        "number": repository["pull_request"]["number"],
        "baseOid": repository["base"]["commit_oid"], "headOid": repository["head"]["commit_oid"],
        "baseExpression": f"{repository['base']['commit_oid']}:{change['path']}",
        "headExpression": f"{repository['head']['commit_oid']}:{change['path']}",
    }
    if variables != expected_variables:
        raise AuditError("core request identity variables do not match the retained repository")
    if _expect_sha(request_identity["query_sha256"], "core request identity.query_sha256") != queries[0][0]["sha256"]:
        raise AuditError("core request identity query digest does not match retained query")
    if _expect_sha(request_identity["result_sha256"], "core request identity.result_sha256") != authority_results[0][0]["sha256"]:
        raise AuditError("core request identity result digest does not match normalized result")
    authority = _expect_dict(authority_results[0][1], "retained normalized repository result")
    _expect_keys(
        authority,
        required=("schema_version", "pull_request", "base_commit", "head_commit", "base_blob", "head_blob"),
        location="retained normalized repository result",
    )
    if authority["schema_version"] != "formal-conjectures.pr-audit-repository-result.v1":
        raise AuditError("unsupported normalized repository result schema")
    authority_pr = _expect_dict(authority["pull_request"], "retained normalized repository pull_request")
    _expect_keys(
        authority_pr,
        required=("number", "url", "baseRefOid", "headRefOid", "files"),
        location="retained normalized repository pull_request",
    )
    authority_files = authority_pr["files"]
    authority_identity = {key: value for key, value in authority_pr.items() if key != "files"}
    if authority_identity != {
        "number": repository["pull_request"]["number"], "url": repository["pull_request"]["url"],
        "baseRefOid": repository["base"]["commit_oid"], "headRefOid": repository["head"]["commit_oid"],
    }:
        raise AuditError("retained core GraphQL pull request identity mismatch")
    if len(repository["changes"]) != 1:
        raise AuditError("core snapshot query v1 requires exactly one changed path")
    change = repository["changes"][0]
    expected_change_type = {"added": "ADDED", "modified": "MODIFIED", "deleted": "DELETED"}
    expected_files = [{"path": item["path"], "changeType": expected_change_type[item["status"]]} for item in repository["changes"]]
    if authority_files != expected_files:
        raise AuditError("retained normalized repository changed-file inventory mismatch")
    for revision in ("base", "head"):
        commit = authority[f"{revision}_commit"]
        if commit != {"oid": repository[revision]["commit_oid"], "tree": {"oid": repository[revision]["tree_oid"]}}:
            raise AuditError(f"retained core GraphQL {revision} commit/tree mismatch")
        blob = authority[f"{revision}_blob"]
        expected_oid = change[f"{revision}_blob_oid"]
        if expected_oid is None:
            if blob is not None:
                raise AuditError(f"retained core GraphQL {revision} blob should be absent")
            continue
        locator = f"{change['path']}@{repository[revision]['commit_oid']}"
        source_input = git_inputs[locator]
        source_raw = loaded[source_input["artifact_id"]][2]
        if blob != {"oid": expected_oid, "byteSize": len(source_raw), "isBinary": False, "text": source_raw.decode("utf-8")}:
            raise AuditError(f"retained core GraphQL {revision} blob mismatch")
    job_artifact_ids = {
        input_record["artifact_id"]
        for check in checks
        for input_record in check["inputs"]
        if input_record["kind"] == "github-check-run"
    }
    for descriptor, candidate, _ in loaded.values():
        if descriptor["id"] not in job_artifact_ids:
            continue
        job = _expect_dict(candidate, "retained normalized GitHub job result")
        _expect_keys(
            job,
            required=("schema_version", "job_id", "run_id", "head_sha", "workflow_name", "job_name", "conclusion", "run_attempt", "job_url"),
            location="retained normalized GitHub job result",
        )
        if job["schema_version"] != "formal-conjectures.pr-audit-github-job-result.v1":
            raise AuditError("unsupported normalized GitHub job result schema")
        if job["head_sha"] != repository["head"]["commit_oid"]:
            raise AuditError("retained GitHub job result head does not match core")
        if job["conclusion"] != "success":
            raise AuditError("retained GitHub job result does not establish success")
        if job["job_name"] != "Build project" or job["workflow_name"] != "Build Lean project and deploy docs":
            raise AuditError("retained GitHub job is not the exact repository Lean build job")
        if not isinstance(job["run_id"], int) or not isinstance(job["job_id"], int) or not isinstance(job["run_attempt"], int):
            raise AuditError("retained GitHub job/run identity is invalid")
        expected_job_url = (
            f"https://github.com/{repository['repository']['owner']}/{repository['repository']['name']}"
            f"/actions/runs/{job['run_id']}/job/{job['job_id']}"
        )
        if job["job_url"] != expected_job_url:
            raise AuditError("retained GitHub job identity is inconsistent")
        _expect_https(job["job_url"], "retained normalized GitHub job result.job_url")
    changed_paths = {change["path"] for change in repository["changes"]}
    for check in checks:
        unknown_paths = set(check["scope"]["paths"]) - changed_paths
        if unknown_paths:
            raise AuditError(
                f"check {check['id']!r} names paths outside the retained PR comparison: "
                + ", ".join(sorted(unknown_paths))
            )
    semantic_paths = [
        change["path"]
        for change in repository["changes"]
        if change["path"].endswith(".lean") and change["status"] != "deleted"
    ]
    advisory, basis = _disposition(checks, semantic_paths)
    record = {
        "schema_version": CORE_SCHEMA_VERSION,
        "generator": generator,
        "repository": repository,
        "inputs": {
            "manifest_sha256": manifest_digest,
            "artifact_root": manifest["artifact_root"],
            "artifacts": manifest["artifacts"],
            "generator_artifact_id": generator_descriptor["id"],
            "repository_artifact_id": repository_descriptor["id"],
        },
        "checks": checks,
        "disposition": {
            "advisory": advisory,
            "basis_check_ids": basis,
            "nonclaims": list(CORE_NONCLAIMS),
        },
    }
    return _with_root(record)


def validate_core(value: Any) -> dict[str, Any]:
    """Validate a generated core and return its normalized representation."""

    obj = _expect_dict(value, "core")
    _expect_keys(
        obj,
        required=("schema_version", "generator", "repository", "inputs", "checks", "disposition", "root"),
        location="core",
    )
    if obj["schema_version"] != CORE_SCHEMA_VERSION:
        raise AuditError(f"unsupported core schema: {obj['schema_version']!r}")
    generator = _validate_generator(obj["generator"])
    # Repository and checks use the same normalized shapes as their retained wrappers.
    repository_wrapper = {"schema_version": REPOSITORY_VERSION, **_expect_dict(obj["repository"], "core.repository")}
    repository = _validate_repository(repository_wrapper)
    checks_wrapper = {"schema_version": CHECKS_VERSION, "checks": obj["checks"]}
    checks = _validate_checks(checks_wrapper)
    inputs = _expect_dict(obj["inputs"], "core.inputs")
    _expect_keys(
        inputs,
        required=("manifest_sha256", "artifact_root", "artifacts", "generator_artifact_id", "repository_artifact_id"),
        location="core.inputs",
    )
    descriptors = [
        _validate_descriptor(item, index)
        for index, item in enumerate(_expect_list(inputs["artifacts"], "core.inputs.artifacts"))
    ]
    if not descriptors:
        raise AuditError("core input artifacts must not be empty")
    if len(descriptors) > MAX_MANIFEST_ARTIFACTS:
        raise AuditError(f"core has more than {MAX_MANIFEST_ARTIFACTS} input artifacts")
    descriptor_ids = [descriptor["id"] for descriptor in descriptors]
    descriptor_paths = [descriptor["path"] for descriptor in descriptors]
    if len(descriptor_ids) != len(set(descriptor_ids)):
        raise AuditError("core inputs have duplicate artifact ids")
    if len(descriptor_paths) != len(set(descriptor_paths)):
        raise AuditError("core inputs have duplicate artifact paths")
    descriptors = _sort_dicts(descriptors, ("id", "role", "path", "sha256"))
    invalid_core_roles = sorted(
        {descriptor["role"] for descriptor in descriptors} - CORE_ARTIFACT_ROLES,
        key=_utf16_sort_key,
    )
    if invalid_core_roles:
        raise AuditError(f"core contains observation/provenance roles: {invalid_core_roles!r}")
    if content_root({"artifacts": descriptors}) != _expect_sha(inputs["artifact_root"], "core.inputs.artifact_root"):
        raise AuditError("core input artifact root is invalid")
    normalized_inputs = {
        "manifest_sha256": _expect_sha(inputs["manifest_sha256"], "core.inputs.manifest_sha256"),
        "artifact_root": inputs["artifact_root"],
        "artifacts": descriptors,
        "generator_artifact_id": _expect_identifier(inputs["generator_artifact_id"], "core.inputs.generator_artifact_id"),
        "repository_artifact_id": _expect_identifier(inputs["repository_artifact_id"], "core.inputs.repository_artifact_id"),
    }
    reconstructed_manifest = {
        "schema_version": CORE_INPUT_VERSION,
        "artifact_root": normalized_inputs["artifact_root"],
        "artifacts": descriptors,
    }
    if normalized_inputs["manifest_sha256"] != sha256_digest(canonical_bytes(reconstructed_manifest) + b"\n"):
        raise AuditError("core input manifest digest is invalid")
    descriptors_by_id = {descriptor["id"]: descriptor for descriptor in descriptors}
    generator_artifact_id = normalized_inputs["generator_artifact_id"]
    repository_artifact_id = normalized_inputs["repository_artifact_id"]
    generator_descriptors = [descriptor for descriptor in descriptors if descriptor["role"] == "generator_identity"]
    repository_descriptors = [descriptor for descriptor in descriptors if descriptor["role"] == "repository_snapshot"]
    check_descriptors = [descriptor for descriptor in descriptors if descriptor["role"] == "check_results"]
    if len(generator_descriptors) != 1 or generator_descriptors[0]["id"] != generator_artifact_id:
        raise AuditError("core must reference exactly one generator_identity artifact")
    if len(repository_descriptors) != 1 or repository_descriptors[0]["id"] != repository_artifact_id:
        raise AuditError("core must reference exactly one repository_snapshot artifact")
    if len(check_descriptors) != 1:
        raise AuditError("core must retain exactly one check_results artifact")
    generator_raw = canonical_bytes(generator) + b"\n"
    repository_raw = canonical_bytes({"schema_version": REPOSITORY_VERSION, **repository}) + b"\n"
    checks_raw = canonical_bytes({"schema_version": CHECKS_VERSION, "checks": _sort_dicts(checks, ("id", "property", "role", "outcome"))}) + b"\n"
    if generator_descriptors[0]["sha256"] != sha256_digest(generator_raw):
        raise AuditError("core generator value does not match retained descriptor")
    if repository_descriptors[0]["sha256"] != sha256_digest(repository_raw):
        raise AuditError("core repository value does not match retained descriptor")
    if check_descriptors[0]["sha256"] != sha256_digest(checks_raw):
        raise AuditError("core checks value does not match retained descriptor")
    changed_paths = {change["path"] for change in repository["changes"]}
    for check in checks:
        unknown_paths = set(check["scope"]["paths"]) - changed_paths
        if unknown_paths:
            raise AuditError("core check names paths outside the retained PR comparison")
    referenced_artifact_ids = {
        input_record["artifact_id"]
        for check in checks
        for input_record in check["inputs"]
    }
    evidence_artifact_ids = {
        descriptor["id"]
        for descriptor in descriptors
        if descriptor["role"] in {"source_file", "method", "configuration", "tool_output", "query", "typed_result"}
    }
    if referenced_artifact_ids != evidence_artifact_ids:
        raise AuditError("core check input artifact inventory is incomplete")
    for check in checks:
        if check["property"] not in SUPPORTED_PROPERTIES:
            raise AuditError(f"unsupported or unimplemented core check property: {check['property']}")
        result_inputs = [item for item in check["inputs"] if item["kind"] == "typed-result"]
        if len(result_inputs) != 1:
            raise AuditError("core check must bind exactly one typed result")
        result_input = result_inputs[0]
        result_descriptor = descriptors_by_id.get(result_input["artifact_id"])
        if result_descriptor is None or result_descriptor["role"] != "typed_result":
            raise AuditError("core check typed result relation has the wrong artifact role")
        if (
            result_descriptor["id"] != f"typed-result-{check['id']}"
            or result_descriptor["path"] != f"inputs/typed-result-{check['id']}.json"
            or result_descriptor["media_type"] != "application/json"
        ):
            raise AuditError("core check typed result descriptor identity is invalid")
        for input_record in check["inputs"]:
            descriptor = descriptors_by_id.get(input_record["artifact_id"])
            if descriptor is None or descriptor["sha256"] != input_record["root"]:
                raise AuditError("core check input root does not match retained artifact")
        expected_typed_result = _expected_typed_result(
            check=check,
            repository=repository,
            result_input=result_input,
        )
        if result_descriptor["sha256"] != sha256_digest(canonical_bytes(expected_typed_result) + b"\n"):
            raise AuditError("core check typed result digest does not derive the published check")
        for evidence_record in check["evidence"]:
            if not any(
                input_record["root"] == evidence_record["sha256"]
                and input_record["locator"] == evidence_record["locator"]
                for input_record in check["inputs"]
            ):
                raise AuditError("core check evidence locator/root tuple is not among its retained inputs")
        for proof in check["proofs"]:
            classification = classify_proof_target(proof["kind"], proof["locator"])
            matching_proof_inputs = [
                input_record for input_record in check["inputs"]
                if input_record["locator"] == proof["locator"]
                and descriptors_by_id[input_record["artifact_id"]]["role"] == "source_file"
            ]
            if classification == "resolvable" and not matching_proof_inputs:
                raise AuditError("core external proof locator is not bound to retained source bytes")
            if classification == "unavailable" and not (
                check["property"] == "exact-formal-proof-artifact-identity"
                and check["outcome"] == "unavailable"
            ):
                raise AuditError("core external proof locator is mutable or ambiguous")
        if check["property"] == "comparator-packet-identity" and check["outcome"] != "unavailable":
            raise AuditError("core Comparator packet identity outcome must remain unavailable")
        if check["property"] == "comparator-tool-availability":
            raise AuditError("core Comparator tool availability is not implemented by v1")
        if check["property"].startswith("model-"):
            raise AuditError("core model checks are not implemented by v1")
        _validate_implementation_binding(check, descriptors_by_id, generator)
        if check["property"] == "exact-formal-proof-artifact-identity":
            if len(check["proofs"]) != 1:
                raise AuditError("core formal-proof artifact identity check requires exactly one proof target")
            proof = check["proofs"][0]
            classification = classify_proof_target(proof["kind"], proof["locator"])
            expected_outcome = "unavailable" if classification == "unavailable" else "pass"
            if check["outcome"] != expected_outcome:
                raise AuditError("core formal-proof artifact identity outcome does not match retained classifier")
    disposition = _expect_dict(obj["disposition"], "core.disposition")
    _expect_keys(disposition, required=("advisory", "basis_check_ids", "nonclaims"), location="core.disposition")
    semantic_paths = [
        change["path"]
        for change in repository["changes"]
        if change["path"].endswith(".lean") and change["status"] != "deleted"
    ]
    advisory, basis = _disposition(checks, semantic_paths)
    if disposition["advisory"] != advisory or _sorted_unique_strings(disposition["basis_check_ids"], "basis") != basis:
        raise AuditError("core disposition does not follow the listed check outcomes")
    nonclaims = _sorted_unique_strings(disposition["nonclaims"], "core.disposition.nonclaims")
    if nonclaims != list(CORE_NONCLAIMS):
        raise AuditError("core nonclaims are incomplete")
    normalized = {
        "schema_version": CORE_SCHEMA_VERSION,
        "generator": generator,
        "repository": repository,
        "inputs": normalized_inputs,
        "checks": checks,
        "disposition": {"advisory": advisory, "basis_check_ids": basis, "nonclaims": nonclaims},
    }
    if _expect_sha(obj["root"], "core.root") != content_root(normalized):
        raise AuditError("core root is invalid")
    return _with_root(normalized)


def _validate_observation_source(value: Any, core: Mapping[str, Any]) -> dict[str, Any]:
    obj = _expect_dict(value, "authoritative observation")
    _expect_keys(obj, required=("data",), location="authoritative observation")
    data = _expect_dict(obj["data"], "authoritative observation.data")
    _expect_keys(data, required=("repository",), location="authoritative observation.data")
    repository = _expect_dict(data["repository"], "authoritative observation.data.repository")
    _expect_keys(repository, required=("pullRequest",), location="authoritative observation.data.repository")
    pr = _expect_dict(repository["pullRequest"], "authoritative observation pullRequest")
    _expect_keys(
        pr,
        required=(
            "number", "url", "state", "isDraft", "mergeStateStatus", "reviewDecision",
            "updatedAt", "baseRefOid", "headRefOid", "reviews",
        ),
        location="authoritative observation pullRequest",
    )
    core_pr = core["repository"]["pull_request"]
    if pr["number"] != core_pr["number"] or pr["url"] != core_pr["url"]:
        raise AuditError("observation pull request identity does not match core")
    if pr["baseRefOid"] != core["repository"]["base"]["commit_oid"]:
        raise AuditError("observation base commit does not match core")
    if pr["headRefOid"] != core["repository"]["head"]["commit_oid"]:
        raise AuditError("observation head commit does not match core")
    reviews_container = _expect_dict(pr["reviews"], "authoritative observation reviews")
    _expect_keys(reviews_container, required=("nodes", "pageInfo"), location="authoritative observation reviews")
    page_info = _expect_dict(reviews_container["pageInfo"], "authoritative observation reviews.pageInfo")
    _expect_keys(page_info, required=("hasNextPage", "endCursor"), location="authoritative observation reviews.pageInfo")
    if _expect_bool(page_info["hasNextPage"], "authoritative observation reviews.pageInfo.hasNextPage"):
        raise AuditError("authoritative observation has an incomplete paginated review set")
    reviews: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_review in enumerate(_expect_list(reviews_container["nodes"], "observation reviews")):
        location = f"observation reviews[{index}]"
        review = _expect_dict(raw_review, location)
        _expect_keys(review, required=("id", "author", "state", "submittedAt", "commit"), location=location)
        review_id = _expect_string(review["id"], f"{location}.id")
        if review_id in seen_ids:
            raise AuditError(f"duplicate observation review id: {review_id}")
        seen_ids.add(review_id)
        author = _expect_dict(review["author"], f"{location}.author")
        _expect_keys(author, required=("login",), location=f"{location}.author")
        commit = _expect_dict(review["commit"], f"{location}.commit")
        _expect_keys(commit, required=("oid",), location=f"{location}.commit")
        reviews.append({
            "id": review_id,
            "author": _expect_string(author["login"], f"{location}.author.login"),
            "state": _expect_choice(review["state"], {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"}, f"{location}.state"),
            "submitted_at": _expect_timestamp(review["submittedAt"], f"{location}.submittedAt"),
            "commit_oid": _expect_oid(commit["oid"], f"{location}.commit.oid"),
        })
    reviews = _sort_dicts(reviews, ("submitted_at", "id", "author", "state", "commit_oid"))
    review_decision = pr["reviewDecision"]
    if review_decision is not None:
        review_decision = _expect_choice(review_decision, {"APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED"}, "reviewDecision")
    return {
        "number": pr["number"],
        "url": _expect_https(pr["url"], "observation url"),
        "state": _expect_choice(pr["state"], {"OPEN", "CLOSED", "MERGED"}, "observation state"),
        "is_draft": _expect_bool(pr["isDraft"], "observation isDraft"),
        "merge_state_status": _expect_choice(
            pr["mergeStateStatus"],
            {"BEHIND", "BLOCKED", "CLEAN", "DIRTY", "DRAFT", "HAS_HOOKS", "UNKNOWN", "UNSTABLE"},
            "observation mergeStateStatus",
        ),
        "review_decision": review_decision,
        "updated_at": _expect_timestamp(pr["updatedAt"], "observation updatedAt"),
        "base_commit_oid": _expect_oid(pr["baseRefOid"], "observation baseRefOid"),
        "head_commit_oid": _expect_oid(pr["headRefOid"], "observation headRefOid"),
        "reviews": reviews,
    }


def _validate_observation_receipt(
    value: Any,
    *,
    number: int,
    observed_at: str,
    response_sha256: str,
    query_sha256: str,
) -> dict[str, Any]:
    receipt = _expect_dict(value, "observation acquisition receipt")
    _expect_keys(
        receipt,
        required=(
            "schema_version", "transport", "endpoint", "operation_name", "variables",
            "acquired_at", "response_sha256", "query_sha256", "http_status", "request_id",
            "limitations",
        ),
        location="observation acquisition receipt",
    )
    if receipt["schema_version"] != "formal-conjectures.pr-audit-acquisition-receipt.v1":
        raise AuditError("unsupported acquisition receipt schema")
    if receipt["transport"] != "https" or receipt["endpoint"] != "https://api.github.com/graphql":
        raise AuditError("observation receipt does not identify the GitHub GraphQL HTTPS endpoint")
    if receipt["operation_name"] != "PullRequestAuditObservation":
        raise AuditError("observation receipt operation name is invalid")
    variables = _expect_dict(receipt["variables"], "observation acquisition receipt.variables")
    _expect_keys(variables, required=("owner", "name", "number"), location="observation acquisition receipt.variables")
    expected_variables = {
        "owner": "google-deepmind",
        "name": "formal-conjectures",
        "number": number,
    }
    if variables != expected_variables:
        raise AuditError("observation receipt variables do not match the core")
    acquired_at = _expect_timestamp(receipt["acquired_at"], "observation acquisition receipt.acquired_at")
    if acquired_at != observed_at:
        raise AuditError("observation receipt acquisition time does not match manifest observation time")
    if _expect_sha(receipt["response_sha256"], "observation acquisition receipt.response_sha256") != response_sha256:
        raise AuditError("observation receipt response digest does not match retained raw response")
    if _expect_sha(receipt["query_sha256"], "observation acquisition receipt.query_sha256") != query_sha256:
        raise AuditError("observation receipt query digest does not match retained query")
    if receipt["http_status"] != 200:
        raise AuditError("observation receipt HTTP status is not successful")
    return {
        "schema_version": receipt["schema_version"],
        "transport": receipt["transport"],
        "endpoint": receipt["endpoint"],
        "operation_name": receipt["operation_name"],
        "variables": expected_variables,
        "acquired_at": acquired_at,
        "response_sha256": response_sha256,
        "query_sha256": query_sha256,
        "http_status": 200,
        "request_id": _expect_string(receipt["request_id"], "observation acquisition receipt.request_id"),
        "limitations": _require_nonempty_strings(
            receipt["limitations"], "observation acquisition receipt.limitations"
        ),
    }


def generate_observation(
    manifest_path: str | os.PathLike[str],
    core_path: str | os.PathLike[str],
) -> dict[str, Any]:
    """Generate a mutable observation envelope over a validated immutable core."""

    core_file = Path(core_path).resolve(strict=True)
    raw_core = _read_regular_file(core_file.parent, core_file.name)
    core = validate_core(parse_json_bytes(raw_core, label=str(core_file)))
    if raw_core != canonical_bytes(core) + b"\n":
        raise AuditError("observation core input must use canonical file framing")
    path = Path(manifest_path).resolve(strict=True)
    manifest, loaded, manifest_digest = _load_manifest(path, OBSERVATION_INPUT_VERSION)
    generator_descriptor, generator_value, _ = _one_role(loaded, "generator_identity")
    observation_descriptor, observation_value, _ = _one_role(loaded, "authoritative_observation")
    receipt_descriptor, receipt_value, _ = _one_role(loaded, "acquisition_receipt")
    query_descriptor, query_value, _ = _one_role(loaded, "query")
    if any(
        value[0]["role"] not in {
            "generator_identity", "authoritative_observation", "acquisition_receipt", "query",
            "provenance_event",
        }
        for value in loaded.values()
    ):
        raise AuditError("immutable core artifacts are forbidden in an observation manifest")
    provenance_artifact_ids = sorted(
        [descriptor["id"] for descriptor, _, _ in loaded.values() if descriptor["role"] == "provenance_event"],
        key=_utf16_sort_key,
    )
    generator = _validate_generator(generator_value)
    if generator != core["generator"]:
        raise AuditError("observation generator identity does not match the core generator identity")
    status = _validate_observation_source(observation_value, core)
    query_text = _expect_string(query_value, "observation query")
    if query_text != OBSERVATION_GRAPHQL_OPERATION:
        raise AuditError("observation query bytes are not the exact v1 operation")
    receipt = _validate_observation_receipt(
        receipt_value,
        number=core["repository"]["pull_request"]["number"],
        observed_at=manifest["observed_at"],
        response_sha256=observation_descriptor["sha256"],
        query_sha256=query_descriptor["sha256"],
    )
    record = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "generator": generator,
        "core": {"root": core["root"], "sha256": sha256_digest(raw_core)},
        "inputs": {
            "manifest_sha256": manifest_digest,
            "artifact_root": manifest["artifact_root"],
            "artifacts": manifest["artifacts"],
            "generator_artifact_id": generator_descriptor["id"],
            "observation_artifact_id": observation_descriptor["id"],
            "receipt_artifact_id": receipt_descriptor["id"],
            "query_artifact_id": query_descriptor["id"],
            "provenance_artifact_ids": provenance_artifact_ids,
        },
        "observed_at": manifest["observed_at"],
        "source": {
            "authority": "github_graphql",
            "artifact_id": observation_descriptor["id"],
            "sha256": observation_descriptor["sha256"],
            "endpoint": receipt["endpoint"],
            "operation_name": receipt["operation_name"],
            "query_sha256": query_descriptor["sha256"],
            "receipt_sha256": receipt_descriptor["sha256"],
            "receipt": receipt,
            "acquired_at": receipt["acquired_at"],
            "http_status": 200,
            "request_id": receipt["request_id"],
            "limitations": receipt["limitations"],
        },
        "pull_request": status,
    }
    return _with_root(record)


def validate_observation(value: Any) -> dict[str, Any]:
    """Validate a published observation envelope without ambient network state."""

    obj = _expect_dict(value, "observation")
    _expect_keys(
        obj,
        required=("schema_version", "generator", "core", "inputs", "observed_at", "source", "pull_request", "root"),
        location="observation",
    )
    if obj["schema_version"] != OBSERVATION_SCHEMA_VERSION:
        raise AuditError("unsupported observation schema")
    generator = _validate_generator(obj["generator"])
    core_ref = _expect_dict(obj["core"], "observation.core")
    _expect_keys(core_ref, required=("root", "sha256"), location="observation.core")
    normalized_core_ref = {
        "root": _expect_sha(core_ref["root"], "observation.core.root"),
        "sha256": _expect_sha(core_ref["sha256"], "observation.core.sha256"),
    }
    inputs = _expect_dict(obj["inputs"], "observation.inputs")
    _expect_keys(inputs, required=("manifest_sha256", "artifact_root", "artifacts", "generator_artifact_id", "observation_artifact_id", "receipt_artifact_id", "query_artifact_id", "provenance_artifact_ids"), location="observation.inputs")
    descriptors = [_validate_descriptor(item, index) for index, item in enumerate(_expect_list(inputs["artifacts"], "observation.inputs.artifacts"))]
    ids = [item["id"] for item in descriptors]
    paths = [item["path"] for item in descriptors]
    if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
        raise AuditError("observation inputs have duplicate artifact ids or paths")
    descriptors = _sort_dicts(descriptors, ("id", "role", "path", "sha256"))
    allowed_roles = {
        "generator_identity", "authoritative_observation", "acquisition_receipt", "query",
        "provenance_event",
    }
    if not {item["role"] for item in descriptors}.issubset(allowed_roles):
        raise AuditError("observation contains an unsupported input role")
    artifact_root = _expect_sha(inputs["artifact_root"], "observation.inputs.artifact_root")
    if artifact_root != content_root({"artifacts": descriptors}):
        raise AuditError("observation input artifact root is invalid")
    ids_by_role = {role: [item["id"] for item in descriptors if item["role"] == role] for role in ("generator_identity", "authoritative_observation", "acquisition_receipt", "query")}
    expected_refs = {
        "generator_artifact_id": "generator_identity",
        "observation_artifact_id": "authoritative_observation",
        "receipt_artifact_id": "acquisition_receipt",
        "query_artifact_id": "query",
    }
    normalized_refs: dict[str, str] = {}
    for field, role in expected_refs.items():
        identifier = _expect_identifier(inputs[field], f"observation.inputs.{field}")
        if ids_by_role[role] != [identifier]:
            raise AuditError(f"observation must reference exactly one {role} artifact")
        normalized_refs[field] = identifier
    provenance_artifact_ids = _sorted_unique_strings(
        inputs["provenance_artifact_ids"], "observation.inputs.provenance_artifact_ids"
    )
    expected_provenance_ids = sorted(
        [item["id"] for item in descriptors if item["role"] == "provenance_event"],
        key=_utf16_sort_key,
    )
    if provenance_artifact_ids != expected_provenance_ids:
        raise AuditError("observation provenance artifact inventory is incomplete")
    descriptors_by_id = {item["id"]: item for item in descriptors}
    generator_descriptor = descriptors_by_id[normalized_refs["generator_artifact_id"]]
    if generator_descriptor["sha256"] != sha256_digest(canonical_bytes(generator) + b"\n"):
        raise AuditError("observation generator value does not match retained descriptor")
    observed_at = _expect_timestamp(obj["observed_at"], "observation.observed_at")
    manifest_digest = _expect_sha(inputs["manifest_sha256"], "observation.inputs.manifest_sha256")
    reconstructed_manifest = {"schema_version": OBSERVATION_INPUT_VERSION, "artifact_root": artifact_root, "artifacts": descriptors, "observed_at": observed_at}
    if manifest_digest != sha256_digest(canonical_bytes(reconstructed_manifest) + b"\n"):
        raise AuditError("observation input manifest digest is invalid")
    source = _expect_dict(obj["source"], "observation.source")
    _expect_keys(source, required=("authority", "artifact_id", "sha256", "endpoint", "operation_name", "query_sha256", "receipt_sha256", "receipt", "acquired_at", "http_status", "request_id", "limitations"), location="observation.source")
    if source["authority"] != "github_graphql" or source["endpoint"] != "https://api.github.com/graphql" or source["operation_name"] != "PullRequestAuditObservation" or source["http_status"] != 200:
        raise AuditError("observation source authority fields are invalid")
    if source["artifact_id"] != normalized_refs["observation_artifact_id"] or _expect_sha(source["sha256"], "observation.source.sha256") != descriptors_by_id[normalized_refs["observation_artifact_id"]]["sha256"]:
        raise AuditError("observation source artifact binding is invalid")
    if _expect_sha(source["query_sha256"], "observation.source.query_sha256") != descriptors_by_id[normalized_refs["query_artifact_id"]]["sha256"]:
        raise AuditError("observation query binding is invalid")
    if _expect_sha(source["receipt_sha256"], "observation.source.receipt_sha256") != descriptors_by_id[normalized_refs["receipt_artifact_id"]]["sha256"]:
        raise AuditError("observation receipt binding is invalid")
    if descriptors_by_id[normalized_refs["query_artifact_id"]]["sha256"] != sha256_digest(OBSERVATION_GRAPHQL_OPERATION.encode("utf-8")):
        raise AuditError("observation query descriptor is not the exact v1 operation")
    acquired_at = _expect_timestamp(source["acquired_at"], "observation.source.acquired_at")
    if acquired_at != observed_at:
        raise AuditError("observation acquisition time mismatch")
    pr_for_receipt = _expect_dict(obj["pull_request"], "observation.pull_request")
    number_for_receipt = pr_for_receipt.get("number")
    if not isinstance(number_for_receipt, int) or isinstance(number_for_receipt, bool):
        raise AuditError("observation pull request number is invalid")
    receipt = _validate_observation_receipt(
        source["receipt"],
        number=number_for_receipt,
        observed_at=observed_at,
        response_sha256=descriptors_by_id[normalized_refs["observation_artifact_id"]]["sha256"],
        query_sha256=descriptors_by_id[normalized_refs["query_artifact_id"]]["sha256"],
    )
    if sha256_digest(canonical_bytes(receipt) + b"\n") != descriptors_by_id[normalized_refs["receipt_artifact_id"]]["sha256"]:
        raise AuditError("observation embedded receipt does not match retained descriptor")
    if (
        source["endpoint"] != receipt["endpoint"]
        or source["operation_name"] != receipt["operation_name"]
        or source["query_sha256"] != receipt["query_sha256"]
        or source["acquired_at"] != receipt["acquired_at"]
        or source["http_status"] != receipt["http_status"]
        or source["request_id"] != receipt["request_id"]
        or _sorted_unique_strings(source["limitations"], "observation.source.limitations") != receipt["limitations"]
    ):
        raise AuditError("observation source summary does not match embedded receipt")
    normalized_source = {
        "authority": source["authority"], "artifact_id": source["artifact_id"],
        "sha256": source["sha256"], "endpoint": source["endpoint"],
        "operation_name": source["operation_name"], "query_sha256": source["query_sha256"],
        "receipt_sha256": source["receipt_sha256"], "receipt": receipt, "acquired_at": acquired_at,
        "http_status": source["http_status"], "request_id": _expect_string(source["request_id"], "observation.source.request_id"),
        "limitations": _sorted_unique_strings(source["limitations"], "observation.source.limitations"),
    }
    pr = _expect_dict(obj["pull_request"], "observation.pull_request")
    _expect_keys(pr, required=("number", "url", "state", "is_draft", "merge_state_status", "review_decision", "updated_at", "base_commit_oid", "head_commit_oid", "reviews"), location="observation.pull_request")
    reviews = []
    review_ids: set[str] = set()
    for index, review_value in enumerate(_expect_list(pr["reviews"], "observation.pull_request.reviews")):
        review = _expect_dict(review_value, f"observation.pull_request.reviews[{index}]")
        _expect_keys(review, required=("id", "author", "state", "submitted_at", "commit_oid"), location=f"observation.pull_request.reviews[{index}]")
        review_id = _expect_string(review["id"], "review.id")
        if review_id in review_ids:
            raise AuditError(f"duplicate observation review id: {review_id}")
        review_ids.add(review_id)
        reviews.append({"id": review_id, "author": _expect_string(review["author"], "review.author"), "state": _expect_choice(review["state"], {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"}, "review.state"), "submitted_at": _expect_timestamp(review["submitted_at"], "review.submitted_at"), "commit_oid": _expect_oid(review["commit_oid"], "review.commit_oid")})
    reviews = _sort_dicts(reviews, ("submitted_at", "id", "author", "state", "commit_oid"))
    number = pr["number"]
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise AuditError("observation pull request number is invalid")
    normalized_pr = {"number": number, "url": _expect_https(pr["url"], "observation.pull_request.url"), "state": _expect_choice(pr["state"], {"OPEN", "CLOSED", "MERGED"}, "observation.pull_request.state"), "is_draft": _expect_bool(pr["is_draft"], "observation.pull_request.is_draft"), "merge_state_status": _expect_choice(pr["merge_state_status"], {"BEHIND", "BLOCKED", "CLEAN", "DIRTY", "DRAFT", "HAS_HOOKS", "UNKNOWN", "UNSTABLE"}, "observation.pull_request.merge_state_status"), "review_decision": None if pr["review_decision"] is None else _expect_choice(pr["review_decision"], {"APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED"}, "observation.pull_request.review_decision"), "updated_at": _expect_timestamp(pr["updated_at"], "observation.pull_request.updated_at"), "base_commit_oid": _expect_oid(pr["base_commit_oid"], "observation.pull_request.base_commit_oid"), "head_commit_oid": _expect_oid(pr["head_commit_oid"], "observation.pull_request.head_commit_oid"), "reviews": reviews}
    normalized = {"schema_version": OBSERVATION_SCHEMA_VERSION, "generator": generator, "core": normalized_core_ref, "inputs": {"manifest_sha256": manifest_digest, "artifact_root": artifact_root, "artifacts": descriptors, **normalized_refs, "provenance_artifact_ids": provenance_artifact_ids}, "observed_at": observed_at, "source": normalized_source, "pull_request": normalized_pr}
    if _expect_sha(obj["root"], "observation.root") != content_root(normalized):
        raise AuditError("observation root is invalid")
    return _with_root(normalized)


def render_markdown(core: Mapping[str, Any]) -> str:
    """Render a small escaped human view; the JSON record remains authoritative."""

    record = validate_core(core)
    def safe(value: Any) -> str:
        text = "".join(" " if ord(character) < 0x20 else character for character in str(value))
        text = html.escape(text, quote=True)
        text = re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", text)
        return text
    lines = [
        f"# PR {record['repository']['pull_request']['number']} audit example",
        "",
        f"Advisory disposition: **{safe(record['disposition']['advisory'])}**",
        "",
        "| Check | Property | Outcome |",
        "| --- | --- | --- |",
    ]
    for check in record["checks"]:
        lines.append(
            f"| {safe(check['id'])} | {safe(check['property'])} | {safe(check['outcome'])} |"
        )
    lines.extend(["", "## Evidence", ""])
    for check in record["checks"]:
        for item in check["evidence"]:
            detail = safe(item["statement"])
            witness = safe(item["witness"])
            suffix = f" Witness: {witness}" if witness else ""
            lines.append(f"- **{safe(check['id'])}:** {detail}{suffix}")
    lines.extend([
        "",
        f"Core root: `{safe(record['root'])}`",
        "",
        "This is advisory evidence, not a merge decision or a claim of mathematical truth.",
        "",
    ])
    return "\n".join(lines)


def write_canonical(path: str | os.PathLike[str], value: Any, *, sidecar: bool = False) -> None:
    """Write canonical bytes, optionally with a `<file>.sha256` content sidecar."""

    destination = Path(path)
    raw = canonical_bytes(value) + b"\n"
    destination.write_bytes(raw)
    if sidecar:
        destination.with_name(destination.name + ".sha256").write_text(
            sha256_digest(raw) + "\n", encoding="utf-8"
        )


__all__ = [
    "AuditError",
    "CORE_SCHEMA_VERSION",
    "OBSERVATION_SCHEMA_VERSION",
    "canonical_bytes",
    "classify_proof_target",
    "content_root",
    "generate_core",
    "generate_observation",
    "git_blob_oid",
    "parse_json_bytes",
    "render_markdown",
    "sha256_digest",
    "validate_core",
    "validate_observation",
    "write_canonical",
]
