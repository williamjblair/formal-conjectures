#!/usr/bin/env python3
"""Build the source-owned Formal Conjectures Problem collection snapshot.

Copyright 2026 The Formal Conjectures Authors.
Licensed under the Apache License, Version 2.0.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


PROFILE_PATH = "problem-collection/profile-v1.json"
REGISTRY_PATH = "problem-collection/pilot/registry.json"
INVENTORY_PATH = "problem-collection/pilot/candidate-metadata-v2.json"
SCHEMA_PATH = "problem-collection/schema/problem-collection-snapshot-v1.schema.json"
BUILDER_PATH = "scripts/build_problem_collection.py"
LICENSING_PATH = "README.md"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PROBLEM_ID_RE = re.compile(r"^formal-conjectures:[A-Za-z0-9][A-Za-z0-9:._-]*$")
DECLARATION_RE = re.compile(
    r"/--(?P<doc>(?:(?!/--).)*?)-/\s*"
    r"@\[(?P<attributes>.*?)\]\s*"
    r"(?:theorem|lemma)\s+(?P<name>[A-Za-z_][A-Za-z0-9_'.]*)",
    re.DOTALL,
)
HISTORY_EVENTS = {"registered", "renamed", "split", "merged", "superseded"}
RELATIONSHIPS = {"primary", "part", "variant", "generalization"}
PROBLEM_RELATIONS = {"composed_of", "part_of", "variant_of"}
EXCLUDED_CATEGORIES = {"research solved", "textbook", "API", "infrastructure", "test"}


class ValidationError(ValueError):
    """Raised when a candidate registry violates the collection profile."""


class Reader(Protocol):
    def read(self, path: str) -> bytes: ...


@dataclass(frozen=True)
class GitReader:
    repo: Path
    commit: str

    def read(self, path: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(self.repo), "show", f"{self.commit}:{path}"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ValidationError(f"tracked input unavailable at {self.commit}:{path}: {detail}")
        return result.stdout


@dataclass(frozen=True)
class TreeReader:
    """Read an uncommitted tree for tests; never used by the publishing CLI."""

    root: Path

    def read(self, path: str) -> bytes:
        candidate = (self.root / path).resolve()
        root = self.root.resolve()
        if root not in candidate.parents:
            raise ValidationError(f"path escapes source root: {path}")
        try:
            return candidate.read_bytes()
        except OSError as error:
            raise ValidationError(f"source input unavailable: {path}: {error}") from error


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest_bytes(domain: str, value: bytes) -> str:
    framed = domain.encode() + b"\0" + len(value).to_bytes(8, "big") + value
    return "sha256:" + hashlib.sha256(framed).hexdigest()


def digest_object(domain: str, value: Any) -> str:
    return digest_bytes(domain, canonical_bytes(value))


def parse_json(reader: Reader, path: str) -> dict[str, Any]:
    try:
        value = json.loads(reader.read(path))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid JSON at {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"top-level JSON must be an object: {path}")
    return value


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be an array")
    return value


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value


def normalize_docstring(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(line.rstrip() for line in lines).strip()


def scan_declarations(source: bytes, path: str) -> dict[str, dict[str, str]]:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(f"Lean source is not UTF-8: {path}") from error
    namespaces = re.findall(r"^namespace\s+([^\s]+)", text, flags=re.MULTILINE)
    if len(namespaces) != 1:
        raise ValidationError(f"pilot source must have exactly one namespace: {path}")
    namespace = namespaces[0]
    declarations: dict[str, dict[str, str]] = {}
    for match in DECLARATION_RE.finditer(text):
        attributes = match.group("attributes")
        category_match = re.search(r"(?:^|,)\s*category\s+([^,\]\n]+)", attributes)
        if not category_match:
            continue
        short_name = match.group("name")
        full_name = f"{namespace}.{short_name}"
        if full_name in declarations:
            raise ValidationError(f"duplicate declaration while scanning {path}: {full_name}")
        declarations[full_name] = {
            "category": category_match.group(1).strip(),
            "docstring": normalize_docstring(match.group("doc")),
        }
    return declarations


def scan_module_heading(source: bytes, path: str) -> str:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(f"Lean source is not UTF-8: {path}") from error
    match = re.search(r"/-!\s*\n?#\s+([^\n]+)", text)
    if not match:
        raise ValidationError(f"tracked module has no H1 heading: {path}")
    return match.group(1).strip()


def source_collection_identity(path: str) -> tuple[str, str, str]:
    patterns = (
        (r"^FormalConjectures/OEIS/(\d+)\.lean$", "OEIS", "oeis", lambda value: f"A{value}"),
        (r"^FormalConjectures/Mathoverflow/(\d+)\.lean$", "MathOverflow", "mathoverflow", str),
        (r"^FormalConjectures/Wikipedia/([A-Za-z0-9_]+)\.lean$", "Wikipedia", "wikipedia", str),
    )
    for pattern, provider, slug, transform in patterns:
        match = re.fullmatch(pattern, path)
        if match:
            return provider, slug, transform(match.group(1))
    raise ValidationError(f"pilot source path has no validated source identity rule: {path}")


def module_to_source_path(module: str) -> str:
    tokens: list[str] = []
    for quoted, plain in re.findall(r"«([^»]+)»|([^.]+)", module):
        tokens.append(quoted or plain)
    if not tokens or tokens[0] != "FormalConjectures":
        raise ValidationError(f"metadata-v2 module is outside FormalConjectures: {module}")
    return "/".join(tokens) + ".lean"


def kebab_identifier(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()


def source_declaration_component(declaration: str, external_id: str) -> str:
    short_name = declaration.split(".", 1)[1]
    if ".parts." in short_name:
        return "part-" + kebab_identifier(short_name.rsplit(".parts.", 1)[1])
    if ".variants." in short_name:
        return kebab_identifier(short_name.rsplit(".variants.", 1)[1])
    component = kebab_identifier(short_name)
    external_component = kebab_identifier(external_id)
    prefix = external_component + "-"
    if component.startswith(prefix) and component != external_component:
        return component[len(prefix):]
    return component


def validate_rights(rights_value: Any, problem_id: str) -> dict[str, Any]:
    rights = require_object(rights_value, f"{problem_id}.rights")
    expected = {"formal_conjectures_record", "lean_source", "question_text", "third_party_source"}
    if set(rights) != expected:
        raise ValidationError(f"{problem_id}.rights must separate record, Lean, question, and source rights")
    for kind in ("formal_conjectures_record", "lean_source"):
        entry = require_object(rights[kind], f"{problem_id}.rights.{kind}")
        for field in ("license_spdx", "attribution", "retention_permission"):
            require_text(entry.get(field), f"{problem_id}.rights.{kind}.{field}")
    if rights["formal_conjectures_record"]["license_spdx"] != "CC-BY-4.0":
        raise ValidationError(f"{problem_id} record data must use the repository's CC-BY-4.0 grant")
    if rights["lean_source"]["license_spdx"] != "Apache-2.0":
        raise ValidationError(f"{problem_id} Lean software must use Apache-2.0")
    question = require_object(rights["question_text"], f"{problem_id}.rights.question_text")
    for field in ("license_spdx", "attribution", "retention_permission", "source_locator", "derivation", "source_rights_class"):
        require_text(question.get(field), f"{problem_id}.rights.question_text.{field}")
    if question["license_spdx"] not in {"CC-BY-4.0", "CC-BY-SA-4.0", "Apache-2.0"}:
        raise ValidationError(f"{problem_id} question text has no permitted explicit rights basis")
    if question.get("retained_bytes") is not True:
        raise ValidationError(f"{problem_id} retained question text must say retained_bytes true")
    if question["retention_permission"] != "redistribution-permitted-under-license":
        raise ValidationError(f"{problem_id} question text must name its redistribution basis")
    third_party = require_object(rights["third_party_source"], f"{problem_id}.rights.third_party_source")
    for field in ("license_spdx", "attribution", "retention_permission", "locator", "caveat"):
        require_text(third_party.get(field), f"{problem_id}.rights.third_party_source.{field}")
    if third_party.get("retained_bytes") is not False:
        raise ValidationError(f"{problem_id} must not retain third-party source bytes")
    if third_party.get("retention_permission") != "not-retained":
        raise ValidationError(f"{problem_id} third-party retention status must be not-retained")
    return copy.deepcopy(rights)


def validate_history(history_value: Any, problem_id: str, all_problem_ids: set[str]) -> list[dict[str, Any]]:
    history = require_list(history_value, f"{problem_id}.history")
    if not history:
        raise ValidationError(f"{problem_id}.history must include its registration")
    result: list[dict[str, Any]] = []
    for index, event_value in enumerate(history):
        event = require_object(event_value, f"{problem_id}.history[{index}]")
        event_kind = require_text(event.get("event"), f"{problem_id}.history[{index}].event")
        if event_kind not in HISTORY_EVENTS:
            raise ValidationError(f"unknown history event for {problem_id}: {event_kind}")
        require_text(event.get("date"), f"{problem_id}.history[{index}].date")
        require_text(event.get("note"), f"{problem_id}.history[{index}].note")
        if index == 0 and event_kind != "registered":
            raise ValidationError(f"{problem_id} history must begin with registered")
        if event_kind == "renamed":
            previous = require_text(event.get("from_problem_id"), f"{problem_id}.history[{index}].from_problem_id")
            if previous == problem_id:
                raise ValidationError(f"{problem_id} cannot be renamed from itself")
        elif event_kind == "split":
            previous = require_text(event.get("from_problem_id"), f"{problem_id}.history[{index}].from_problem_id")
            results = require_list(event.get("resulting_problem_ids"), f"{problem_id}.history[{index}].resulting_problem_ids")
            if previous == problem_id or len(results) < 2 or problem_id not in results:
                raise ValidationError(f"invalid split history for {problem_id}")
            if not set(results).issubset(all_problem_ids):
                raise ValidationError(f"split history for {problem_id} references an unregistered result")
        elif event_kind == "merged":
            previous = require_list(event.get("from_problem_ids"), f"{problem_id}.history[{index}].from_problem_ids")
            if len(previous) < 2 or problem_id in previous:
                raise ValidationError(f"invalid merge history for {problem_id}")
            if event.get("result_problem_id") != problem_id:
                raise ValidationError(f"merge history result must be {problem_id}")
        elif event_kind == "superseded":
            successor = require_text(event.get("superseded_by"), f"{problem_id}.history[{index}].superseded_by")
            if successor == problem_id or successor not in all_problem_ids:
                raise ValidationError(f"invalid supersession history for {problem_id}")
        result.append(copy.deepcopy(event))
    return result


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("schema_version") != 1:
        raise ValidationError("profile schema_version must be 1")
    if profile.get("authority_effect") != "none":
        raise ValidationError("authority_effect must be none")
    inclusion = require_object(profile.get("inclusion_policy"), "profile.inclusion_policy")
    if inclusion.get("included_categories") != ["research open"]:
        raise ValidationError("the pilot may include only research open declarations")
    excluded = set(require_list(inclusion.get("excluded_categories"), "profile.inclusion_policy.excluded_categories"))
    if excluded != EXCLUDED_CATEGORIES:
        raise ValidationError("excluded category policy is incomplete")
    history_types = set(require_list(profile.get("history_event_types"), "profile.history_event_types"))
    if history_types != HISTORY_EVENTS:
        raise ValidationError("history event policy must cover rename, split, merge, and supersession")
    rights = require_object(profile.get("rights_policy"), "profile.rights_policy")
    if rights.get("record_license") != "CC-BY-4.0" or rights.get("software_license") != "Apache-2.0":
        raise ValidationError("profile must distinguish data and software licenses")
    if rights.get("third_party_bytes_retained") is not False:
        raise ValidationError("third-party source bytes must not be retained")
    if rights.get("question_text_requires_explicit_retention_basis") is not True:
        raise ValidationError("question text retention must require an explicit rights basis")


def resolve_declaration_route(routes: list[dict[str, Any]], declaration: str) -> dict[str, Any]:
    matches = [route for route in routes if route["declaration"] == declaration]
    if len(matches) != 1:
        raise ValidationError(
            f"machine declaration has no unique durable registry route; refusing ghost Problem: {declaration}"
        )
    return matches[0]


def validate_and_expand(reader: Reader, profile: dict[str, Any], registry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    validate_profile(profile)
    if registry.get("schema_version") != 1:
        raise ValidationError("registry schema_version must be 1")
    problem_values = require_list(registry.get("problems"), "registry.problems")
    if not 5 <= len(problem_values) <= 10:
        raise ValidationError("the pilot must contain between 5 and 10 Problems")
    problem_ids = [require_text(require_object(item, "problem").get("problem_id"), "problem.problem_id") for item in problem_values]
    if len(problem_ids) != len(set(problem_ids)):
        raise ValidationError("problem_id values must be unique")
    if any(not PROBLEM_ID_RE.fullmatch(problem_id) for problem_id in problem_ids):
        raise ValidationError("problem_id is outside the source-owned Formal Conjectures namespace")
    inventory = parse_json(reader, INVENTORY_PATH)
    if inventory.get("schemaVersion") != 2:
        raise ValidationError("candidate machine inventory must use metadata schema v2")
    expected_projection = {
        "fields": ["theorem", "module", "category"],
        "format": "extract_names-v2-field-projection",
        "selection": "reviewed pilot candidates only",
        "source": "scripts/extract_names.lean",
    }
    if inventory.get("projection") != expected_projection:
        raise ValidationError("candidate inventory must declare the exact rooted extract_names v2 projection")
    inventory_values = require_list(inventory.get("problems"), "candidate inventory.problems")
    inventory_by_name: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(inventory_values):
        entry = require_object(value, f"candidate inventory.problems[{index}]")
        name = require_text(entry.get("theorem"), f"candidate inventory.problems[{index}].theorem")
        require_text(entry.get("category"), f"candidate inventory.problems[{index}].category")
        require_text(entry.get("module"), f"candidate inventory.problems[{index}].module")
        if name in inventory_by_name:
            raise ValidationError(f"duplicate candidate machine declaration: {name}")
        inventory_by_name[name] = entry

    source_cache: dict[str, tuple[bytes, dict[str, dict[str, str]]]] = {}

    def declarations_at(path: str) -> dict[str, dict[str, str]]:
        if path not in source_cache:
            source = reader.read(path)
            source_cache[path] = (source, scan_declarations(source, path))
        return source_cache[path][1]

    expanded: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    source_identity_keys: set[tuple[str, str, str]] = set()
    for problem_value in problem_values:
        problem = require_object(problem_value, "problem")
        problem_id = require_text(problem.get("problem_id"), "problem.problem_id")
        title = require_text(problem.get("title"), f"{problem_id}.title")
        declaration_values = require_list(problem.get("declarations"), f"{problem_id}.declarations")
        if not declaration_values:
            raise ValidationError(f"{problem_id} must group at least one declaration")
        if len(declaration_values) != 1:
            raise ValidationError(f"{problem_id} must retain one declaration identity; use a group for parts/variants")
        names: set[str] = set()
        expanded_declarations: list[dict[str, Any]] = []
        for declaration_value in declaration_values:
            declaration = require_object(declaration_value, f"{problem_id}.declaration")
            name = require_text(declaration.get("name"), f"{problem_id}.declaration.name")
            path = require_text(declaration.get("source_path"), f"{problem_id}.{name}.source_path")
            relationship = require_text(declaration.get("relationship"), f"{problem_id}.{name}.relationship")
            if relationship not in RELATIONSHIPS:
                raise ValidationError(f"unknown declaration relationship for {name}: {relationship}")
            if name in names:
                raise ValidationError(f"duplicate declaration in {problem_id}: {name}")
            names.add(name)
            source_declaration = declarations_at(path).get(name)
            if source_declaration is None:
                raise ValidationError(f"listed declaration is absent from {path}: {name}")
            if source_declaration["category"] != "research open":
                raise ValidationError(f"included declaration is not research open: {name} ({source_declaration['category']})")
            if not source_declaration["docstring"]:
                raise ValidationError(f"included declaration has no human-readable docstring: {name}")
            inventory_entry = inventory_by_name.get(name)
            if inventory_entry is None:
                raise ValidationError(f"included declaration has no reviewed metadata-v2 route: {name}")
            if inventory_entry["category"] != source_declaration["category"] or module_to_source_path(inventory_entry["module"]) != path:
                raise ValidationError(f"metadata-v2 evidence disagrees with tracked source: {name}")
            if relationship == "part":
                require_text(declaration.get("relationship_label"), f"{problem_id}.{name}.relationship_label")
            if relationship in {"variant", "generalization"}:
                require_text(declaration.get("variant_of"), f"{problem_id}.{name}.variant_of")
            expanded_declaration = copy.deepcopy(declaration)
            expanded_declaration["category"] = source_declaration["category"]
            expanded_declaration["docstring_sha256"] = digest_bytes(
                "formal-conjectures/problem-docstring/v1", source_declaration["docstring"].encode()
            )
            expanded_declarations.append(expanded_declaration)
            routes.append({"declaration": name, "disposition": "included", "problem_id": problem_id})

        for declaration in declaration_values:
            if declaration.get("relationship") in {"variant", "generalization"} and declaration.get("variant_of") not in names:
                raise ValidationError(f"variant_of must name a declaration in {problem_id}")
        relationships = {declaration["relationship"] for declaration in declaration_values}
        if "primary" not in relationships and relationships != {"part"}:
            raise ValidationError(f"{problem_id} needs a primary declaration or an all-part grouping")

        question_names = require_list(problem.get("question_declarations"), f"{problem_id}.question_declarations")
        if not question_names or len(question_names) != len(set(question_names)):
            raise ValidationError(f"{problem_id}.question_declarations must be non-empty and unique")
        if not set(question_names).issubset(names):
            raise ValidationError(f"{problem_id}.question_declarations must belong to the Problem")
        questions: list[dict[str, str]] = []
        by_name = {declaration["name"]: declaration for declaration in declaration_values}
        for name in question_names:
            path = by_name[name]["source_path"]
            questions.append({"declaration": name, "text": declarations_at(path)[name]["docstring"]})

        status = require_object(problem.get("status_assertion"), f"{problem_id}.status_assertion")
        if status.get("value") != "source-asserted-research-open":
            raise ValidationError(f"{problem_id} must use the bounded source-asserted open status")
        if status.get("asserted_by") != "Formal Conjectures tracked category metadata":
            raise ValidationError(f"{problem_id} status must identify the tracked source assertion")
        if status.get("metadata_schema_version") != 2:
            raise ValidationError(f"{problem_id} status must identify metadata schema v2")
        expected_method = "Fresh metadata-v2 extraction after a focused module build, followed by declaration-source and source-locator review."
        if status.get("method") != expected_method:
            raise ValidationError(f"{problem_id} status method is not the reviewed pilot method")
        for field in ("asserted_by", "method", "reviewed_on", "reviewer_kind", "reviewer_name"):
            require_text(status.get(field), f"{problem_id}.status_assertion.{field}")
        if status["reviewer_kind"] not in {"human", "AI"}:
            raise ValidationError(f"{problem_id} reviewer_kind must be human or AI")

        title_basis = require_object(problem.get("title_basis"), f"{problem_id}.title_basis")
        title_path = require_text(title_basis.get("source_path"), f"{problem_id}.title_basis.source_path")
        source_paths = {item["source_path"] for item in declaration_values}
        if title_path not in source_paths:
            raise ValidationError(f"{problem_id} title basis must be one of its declaration sources")
        title_kind = require_text(title_basis.get("kind"), f"{problem_id}.title_basis.kind")
        if title_kind == "module_heading":
            if scan_module_heading(source_cache[title_path][0], title_path) != title:
                raise ValidationError(f"{problem_id} title does not match the tracked module heading")
        elif title_kind == "declaration_docstring":
            title_declaration = require_text(
                title_basis.get("declaration"), f"{problem_id}.title_basis.declaration"
            )
            if title_declaration not in names:
                raise ValidationError(f"{problem_id} title basis declaration is outside the Problem")
            source_docstring = declarations_at(title_path)[title_declaration]["docstring"]
            plain_docstring = re.sub(r"[*`#]", "", source_docstring).lower()
            if title.lower() not in plain_docstring:
                raise ValidationError(f"{problem_id} title is absent from its tracked declaration docstring")
        else:
            raise ValidationError(f"{problem_id} has an unknown title basis: {title_kind}")

        expanded_status = copy.deepcopy(status)
        expanded_status["evidence"] = [
            {
                "declaration": item["name"],
                "metadata_module": inventory_by_name[item["name"]]["module"],
                "source_category": "research open",
                "source_path": item["source_path"],
            }
            for item in declaration_values
        ]
        validated_rights = validate_rights(problem.get("rights"), problem_id)
        expanded_problem: dict[str, Any] = {
            "declarations": expanded_declarations,
            "history": validate_history(problem.get("history"), problem_id, set(problem_ids)),
            "problem_id": problem_id,
            "question": {
                "kind": "verbatim_normalized_docstrings",
                "parts": questions,
                "retention_basis": copy.deepcopy(validated_rights["question_text"]),
            },
            "rights": validated_rights,
            "status": expanded_status,
            "title": title,
            "title_basis": copy.deepcopy(title_basis),
        }
        source_paths = {item["source_path"] for item in declaration_values}
        for locator_field, locator in (
            ("question", validated_rights["question_text"]["source_locator"]),
            ("third-party", validated_rights["third_party_source"]["locator"]),
        ):
            if not any(locator.encode() in source_cache[path][0] for path in source_paths):
                raise ValidationError(f"{problem_id} {locator_field} source locator is not in tracked Lean source")
        source_identity = require_object(problem.get("source_identity"), f"{problem_id}.source_identity")
        provider = require_text(
            source_identity.get("source_collection"), f"{problem_id}.source_identity.source_collection"
        )
        external_id = require_text(source_identity.get("source_key"), f"{problem_id}.source_identity.source_key")
        component = require_text(source_identity.get("component"), f"{problem_id}.source_identity.component")
        identity_basis = require_object(problem.get("identity_basis"), f"{problem_id}.identity_basis")
        identity_path = require_text(identity_basis.get("source_path"), f"{problem_id}.identity_basis.source_path")
        if source_paths != {identity_path}:
            raise ValidationError(f"{problem_id} identity basis must be its one tracked source module")
        expected_provider, provider_slug, expected_external_id = source_collection_identity(identity_path)
        if (provider, external_id) != (expected_provider, expected_external_id):
            raise ValidationError(f"{problem_id} source identity does not match its tracked module path")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", component):
            raise ValidationError(f"{problem_id} source identity component is invalid")
        expected_component = source_declaration_component(declaration_values[0]["name"], external_id)
        if component != expected_component:
            raise ValidationError(
                f"{problem_id} identity component does not match its source declaration: expected {expected_component}"
            )
        expected_problem_id = f"formal-conjectures:{provider_slug}:{external_id}:{component}"
        if problem_id != expected_problem_id:
            raise ValidationError(f"problem_id does not match its source identity: expected {expected_problem_id}")
        source_identity_key = (provider, external_id, component)
        if source_identity_key in source_identity_keys:
            raise ValidationError(f"duplicate source identity component: {source_identity_key}")
        source_identity_keys.add(source_identity_key)
        expanded_problem["source_identity"] = copy.deepcopy(source_identity)
        expanded_problem["identity_basis"] = copy.deepcopy(identity_basis)
        upstream = problem.get("upstream_identity")
        if provider in {"OEIS", "MathOverflow"}:
            upstream_identity = require_object(upstream, f"{problem_id}.upstream_identity")
            if upstream_identity != {"id": external_id, "provider": provider}:
                raise ValidationError(f"{problem_id} upstream identity must match its source locator class")
            expanded_problem["upstream_identity"] = copy.deepcopy(upstream_identity)
        elif upstream is not None:
            raise ValidationError(f"{problem_id} must not label an FC Wikipedia module key as upstream identity")
        if "relations" in problem:
            relations = require_list(problem["relations"], f"{problem_id}.relations")
            expanded_relations: list[dict[str, str]] = []
            for index, relation_value in enumerate(relations):
                relation = require_object(relation_value, f"{problem_id}.relations[{index}]")
                kind = require_text(relation.get("kind"), f"{problem_id}.relations[{index}].kind")
                target = require_text(
                    relation.get("problem_id"), f"{problem_id}.relations[{index}].problem_id"
                )
                if kind not in PROBLEM_RELATIONS or target == problem_id or target not in set(problem_ids):
                    raise ValidationError(f"invalid Problem relation for {problem_id}: {kind} {target}")
                expanded_relations.append({"kind": kind, "problem_id": target})
            expanded_problem["relations"] = expanded_relations
        if "group_ids" in problem:
            expanded_problem["group_ids"] = copy.deepcopy(
                require_list(problem["group_ids"], f"{problem_id}.group_ids")
            )
        expanded.append(expanded_problem)

    exclusions: list[dict[str, Any]] = []
    for index, exclusion_value in enumerate(require_list(registry.get("exclusions"), "registry.exclusions")):
        exclusion = require_object(exclusion_value, f"registry.exclusions[{index}]")
        name = require_text(exclusion.get("declaration"), f"exclusion[{index}].declaration")
        path = require_text(exclusion.get("source_path"), f"exclusion[{index}].source_path")
        category = require_text(exclusion.get("category"), f"exclusion[{index}].category")
        reason_code = require_text(exclusion.get("reason_code"), f"exclusion[{index}].reason_code")
        require_text(exclusion.get("reason"), f"exclusion[{index}].reason")
        actual = declarations_at(path).get(name)
        if actual is None:
            raise ValidationError(f"excluded declaration is absent from {path}: {name}")
        if actual["category"] != category:
            raise ValidationError(f"excluded declaration category drifted: {name} ({actual['category']} != {category})")
        if reason_code == "excluded_category" and category not in EXCLUDED_CATEGORIES:
            raise ValidationError(f"excluded_category reason does not match category for {name}")
        if reason_code in {"question_text_rights_unresolved", "source_locator_missing"}:
            if exclusion.get("rights_status") != "NOASSERTION":
                raise ValidationError(f"unresolved rights/source exclusion must say NOASSERTION: {name}")
        inventory_entry = inventory_by_name.get(name)
        if inventory_entry is None:
            raise ValidationError(f"excluded declaration has no reviewed metadata-v2 route: {name}")
        if inventory_entry["category"] != category or module_to_source_path(inventory_entry["module"]) != path:
            raise ValidationError(f"excluded metadata-v2 evidence disagrees with tracked source: {name}")
        exclusions.append(copy.deepcopy(exclusion))
        routes.append({"declaration": name, "disposition": "excluded", "reason_code": reason_code})

    route_names = [route["declaration"] for route in routes]
    if len(route_names) != len(set(route_names)):
        raise ValidationError("a declaration cannot have more than one durable registry route")
    if set(route_names) != set(inventory_by_name):
        missing = sorted(set(inventory_by_name) - set(route_names))
        extra = sorted(set(route_names) - set(inventory_by_name))
        raise ValidationError(f"candidate metadata routes must be exact; ghost={missing}, unrouted_registry={extra}")
    for name in inventory_by_name:
        resolve_declaration_route(routes, name)

    expanded_groups: list[dict[str, Any]] = []
    group_values = require_list(registry.get("groups"), "registry.groups")
    group_ids = [require_text(require_object(value, "group").get("group_id"), "group.group_id") for value in group_values]
    if len(group_ids) != len(set(group_ids)):
        raise ValidationError("group_id values must be unique")
    problem_by_id = {problem["problem_id"]: problem for problem in expanded}
    for index, group_value in enumerate(group_values):
        group = require_object(group_value, f"registry.groups[{index}]")
        group_id = require_text(group.get("group_id"), f"registry.groups[{index}].group_id")
        kind = require_text(group.get("kind"), f"{group_id}.kind")
        if kind not in {"multipart", "variant-set"}:
            raise ValidationError(f"unknown group kind: {kind}")
        members = require_list(group.get("member_problem_ids"), f"{group_id}.member_problem_ids")
        if len(members) < 2 or len(members) != len(set(members)) or not set(members).issubset(problem_by_id):
            raise ValidationError(f"{group_id} has invalid member Problem identities")
        for member in members:
            if group_id not in problem_by_id[member].get("group_ids", []):
                raise ValidationError(f"{member} does not explicitly retain membership in {group_id}")
        member_identities = {
            (problem_by_id[member]["source_identity"]["source_collection"],
             problem_by_id[member]["source_identity"]["source_key"])
            for member in members
        }
        if len(member_identities) != 1:
            raise ValidationError(f"{group_id} cannot group unrelated external identities")
        representative = problem_by_id[members[0]]
        _, provider_slug, external_id = source_collection_identity(
            representative["identity_basis"]["source_path"]
        )
        expected_group_id = f"formal-conjectures:group:{provider_slug}:{external_id}"
        if group_id != expected_group_id:
            raise ValidationError(f"group_id does not match its member source identity: expected {expected_group_id}")
        require_text(group.get("title"), f"{group_id}.title")
        expanded_groups.append({
            "group_id": group_id,
            "history": validate_history(group.get("history"), group_id, set(group_ids)),
            "kind": kind,
            "member_problem_ids": copy.deepcopy(members),
            "title": group["title"],
        })
    declared_group_memberships = {
        group_id
        for problem in expanded
        for group_id in problem.get("group_ids", [])
    }
    if declared_group_memberships != set(group_ids):
        raise ValidationError("Problem group memberships and registry groups must match exactly")
    members_by_group = {group["group_id"]: set(group["member_problem_ids"]) for group in expanded_groups}
    for problem in expanded:
        for group_id in problem.get("group_ids", []):
            if problem["problem_id"] not in members_by_group[group_id]:
                raise ValidationError(
                    f"{problem['problem_id']} declares {group_id}, but the group erases that member identity"
                )
    paths = sorted(source_cache)
    return (
        sorted(expanded, key=lambda item: item["problem_id"]),
        sorted(expanded_groups, key=lambda item: item["group_id"]),
        sorted(exclusions, key=lambda item: item["declaration"]),
        sorted(routes, key=lambda item: item["declaration"]),
        paths,
    )


def build_snapshot(reader: Reader, commit: str) -> dict[str, Any]:
    if not COMMIT_RE.fullmatch(commit):
        raise ValidationError("source commit must be an exact 40-character lowercase Git object ID")
    profile_bytes = reader.read(PROFILE_PATH)
    registry_bytes = reader.read(REGISTRY_PATH)
    profile = parse_json(reader, PROFILE_PATH)
    registry = parse_json(reader, REGISTRY_PATH)
    problems, groups, exclusions, routes, lean_paths = validate_and_expand(reader, profile, registry)
    for problem in problems:
        problem["status"]["last_checked_revision"] = commit
    data = {"declaration_routes": routes, "exclusions": exclusions, "groups": groups, "problems": problems}

    input_paths = sorted({PROFILE_PATH, REGISTRY_PATH, INVENTORY_PATH, SCHEMA_PATH, BUILDER_PATH, LICENSING_PATH, *lean_paths})
    inputs = [{"path": path, "sha256": digest_bytes("formal-conjectures/tracked-file/v1", reader.read(path))} for path in input_paths]
    roots = {
        "data_root": digest_object("formal-conjectures/problem-data/v1", data),
        "profile_root": digest_bytes("formal-conjectures/problem-profile/v1", profile_bytes),
        "registry_root": digest_bytes("formal-conjectures/problem-registry/v1", registry_bytes),
        "tracked_input_root": digest_object("formal-conjectures/problem-inputs/v1", inputs),
    }
    snapshot: dict[str, Any] = {
        "authority_effect": "none",
        "collection_id": profile["collection_id"],
        "data": data,
        "nonclaims": copy.deepcopy(profile["nonclaims"]),
        "roots": roots,
        "schema_version": 1,
        "source_snapshot": {
            "commit": commit,
            "data_paths": lean_paths,
            "generator_path": BUILDER_PATH,
            "inventory_path": INVENTORY_PATH,
            "profile_path": PROFILE_PATH,
            "registry_path": REGISTRY_PATH,
            "schema_path": SCHEMA_PATH,
            "tags": [],
            "tracked_inputs": inputs,
        },
    }
    snapshot["roots"]["snapshot_root"] = digest_object(
        "formal-conjectures/problem-snapshot/v1", snapshot
    )
    return snapshot


def resolve_commit(repo: Path, source_commit: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{source_commit}^{{commit}}"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise ValidationError(result.stderr.strip() or f"cannot resolve commit: {source_commit}")
    commit = result.stdout.strip()
    if not COMMIT_RE.fullmatch(commit):
        raise ValidationError(f"git returned a non-canonical commit ID: {commit}")
    return commit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Formal Conjectures Git repository")
    parser.add_argument("--source-commit", required=True, help="exact commit or ref to bind")
    parser.add_argument("--check", type=Path, help="require byte-for-byte equality with a tracked snapshot")
    args = parser.parse_args(argv)
    try:
        repo = args.repo.resolve()
        commit = resolve_commit(repo, args.source_commit)
        reader = GitReader(repo, commit)
        if Path(__file__).resolve().read_bytes() != reader.read(BUILDER_PATH):
            raise ValidationError(
                "running builder bytes differ from the builder at source commit; execute the bound version"
            )
        output = canonical_bytes(build_snapshot(reader, commit))
        if args.check:
            expected = args.check.read_bytes()
            if expected != output:
                raise ValidationError(f"snapshot does not reproduce exactly: {args.check}")
            print(f"snapshot verified: {args.check} ({commit})")
        else:
            sys.stdout.buffer.write(output)
    except (OSError, subprocess.SubprocessError, ValidationError) as error:
        print(f"problem collection build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
