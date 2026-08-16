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
"""Verify and materialize one content-addressed FC100 pilot bundle.

The source checkout must already be at the manifest's exact commit. This tool
does not fetch, choose a toolchain, run Comparator, or turn disclosure state
into an acceptance decision. Prepared cases get a LeanEval-shaped
`Submission.lean` plus sources under `Submission/`; blocked cases retain their
exact source bundle and gate without rewriting imports to manufacture a build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "comparator/pilots/fc100/cases.json"
SCHEMA = "formal-conjectures.fc100-pilot-cases.v1"
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BundleError(ValueError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git(checkout: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(checkout), *args], capture_output=True, text=True)
    if proc.returncode:
        raise BundleError(proc.stderr.strip() or "git command failed")
    return proc.stdout.strip()


def load_manifest(path: pathlib.Path = MANIFEST) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != SCHEMA or value.get("authority_effect") != "none":
        raise BundleError("unsupported or authoritative FC100 manifest")
    if not isinstance(value.get("cases"), list) or not value["cases"]:
        raise BundleError("FC100 manifest has no cases")
    ids: set[str] = set()
    for case in value["cases"]:
        validate_case(case)
        if case["id"] in ids:
            raise BundleError(f"duplicate case id: {case['id']}")
        ids.add(case["id"])
    required = {
        "not_a_comparator_result", "not_maintainer_or_upstream_acceptance",
        "not_a_benchmark_admission_decision",
    }
    if not required <= set(value.get("nonclaims", [])):
        raise BundleError("FC100 authority nonclaims are incomplete")
    return value


def validate_case(case: dict[str, Any]) -> None:
    required = {
        "id", "role", "fc_module", "fc_declaration", "source",
        "projection", "disclosure",
    }
    if set(case) != required:
        raise BundleError(f"{case.get('id', '<unknown>')}: invalid fields")
    source = case["source"]
    if not SHA1.fullmatch(source.get("commit", "")):
        raise BundleError(f"{case['id']}: source commit is not pinned")
    if not source.get("license") or not source.get("lean_toolchain"):
        raise BundleError(f"{case['id']}: source licence or toolchain missing")
    files = source.get("files")
    if not isinstance(files, list) or not files:
        raise BundleError(f"{case['id']}: source file list is empty")
    seen: set[str] = set()
    for item in files:
        source_path = pathlib.PurePosixPath(item.get("path", ""))
        if source_path.is_absolute() or ".." in source_path.parts or not source_path.parts:
            raise BundleError(f"{case['id']}: unsafe source path")
        if str(source_path) in seen:
            raise BundleError(f"{case['id']}: duplicate source path")
        seen.add(str(source_path))
        if not SHA1.fullmatch(item.get("git_blob_sha1", "")):
            raise BundleError(f"{case['id']}: invalid git blob id")
        if not SHA256.fullmatch(item.get("sha256", "")):
            raise BundleError(f"{case['id']}: invalid source SHA-256")
        target = item.get("submission_path")
        if target is not None and not re.fullmatch(r"Submission(?:/.*)?\.lean", target):
            raise BundleError(f"{case['id']}: source escapes Submission layout")
    projection = case["projection"]
    if projection.get("status") not in {"prepared", "blocked"}:
        raise BundleError(f"{case['id']}: invalid projection status")
    if projection["status"] == "prepared":
        if not projection.get("entrypoint_import"):
            raise BundleError(f"{case['id']}: prepared projection has no import")
        if any("submission_path" not in item for item in files):
            raise BundleError(f"{case['id']}: prepared source has no target path")
    elif projection.get("entrypoint_import") is not None:
        raise BundleError(f"{case['id']}: blocked projection names an import")
    disclosure = case["disclosure"]
    if set(disclosure) != {"visibility", "embargo_until", "release_at"}:
        raise BundleError(f"{case['id']}: invalid disclosure fields")
    visibility = disclosure["visibility"]
    if visibility not in {"private", "embargoed", "public"}:
        raise BundleError(f"{case['id']}: invalid disclosure visibility")
    if visibility == "embargoed" and not disclosure["embargo_until"]:
        raise BundleError(f"{case['id']}: embargoed source needs an end time")
    if visibility != "embargoed" and disclosure["embargo_until"] is not None:
        raise BundleError(f"{case['id']}: only embargoed sources have an end time")


def verify_source(case: dict[str, Any], checkout: pathlib.Path) -> list[dict[str, Any]]:
    checkout = checkout.resolve(strict=True)
    if git(checkout, "rev-parse", "HEAD") != case["source"]["commit"]:
        raise BundleError(f"{case['id']}: source checkout commit drift")
    verified = []
    for item in case["source"]["files"]:
        source_path = checkout / item["path"]
        if not source_path.is_file():
            raise BundleError(f"{case['id']}: source file missing: {item['path']}")
        actual_blob = git(checkout, "rev-parse", f"HEAD:{item['path']}")
        if actual_blob != item["git_blob_sha1"]:
            raise BundleError(f"{case['id']}: git blob drift: {item['path']}")
        actual_sha256 = digest(source_path.read_bytes())
        if actual_sha256 != item["sha256"]:
            raise BundleError(f"{case['id']}: SHA-256 drift: {item['path']}")
        verified.append({
            "path": item["path"],
            "git_blob_sha1": actual_blob,
            "sha256": "sha256:" + actual_sha256,
        })
    return verified


def materialize(case: dict[str, Any], checkout: pathlib.Path,
                output: pathlib.Path) -> dict[str, Any]:
    if output.exists():
        raise BundleError(f"refusing to overwrite bundle: {output}")
    verified = verify_source(case, checkout)
    output.mkdir(parents=True)
    for item in case["source"]["files"]:
        raw_target = output / "source" / item["path"]
        raw_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checkout / item["path"], raw_target)
        if case["projection"]["status"] == "prepared":
            submission_target = output / item["submission_path"]
            submission_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checkout / item["path"], submission_target)

    projected_files = []
    if case["projection"]["status"] == "prepared":
        entrypoint = (
            f"import {case['projection']['entrypoint_import']}\n\n"
            "/- The declaration bridge is deliberately separate and remains unchecked. -/\n"
        )
        entrypoint_path = output / "Submission.lean"
        entrypoint_path.write_text(entrypoint, encoding="utf-8")
        for candidate in sorted(output.glob("Submission/**/*.lean")) + [entrypoint_path]:
            if candidate.is_file():
                projected_files.append({
                    "path": str(candidate.relative_to(output)),
                    "sha256": "sha256:" + digest(candidate.read_bytes()),
                })

    public_claim_eligible = case["disclosure"]["visibility"] == "public"
    evidence = {
        "schema": "formal-conjectures.fc100-source-bundle.v1",
        "authority_effect": "none",
        "case": case["id"],
        "formal_conjectures": {
            "module": case["fc_module"],
            "declaration": case["fc_declaration"],
        },
        "source": {
            "repository": case["source"]["repository"],
            "commit": case["source"]["commit"],
            "license": case["source"]["license"],
            "lean_toolchain": case["source"]["lean_toolchain"],
            "files": verified,
        },
        "lean_eval_projection": {
            "status": case["projection"]["status"],
            "files": projected_files,
            "bridge_status": case["projection"]["bridge_status"],
            "gate": case["projection"]["gate"],
        },
        "stages": {
            "source_inspection": "pass",
            "native_build": "not_evaluated",
            "bridge_elaboration": "not_evaluated",
            "comparator": "not_evaluated",
            "review": "not_evaluated",
        },
        "disclosure": {
            **case["disclosure"],
            "public_claim_eligible": public_claim_eligible,
            "effect_on_comparator_or_acceptance": "none",
        },
        "nonclaims": [
            "not_a_comparator_result",
            "not_maintainer_or_upstream_acceptance",
            "not_a_benchmark_admission_decision",
        ],
    }
    (output / "bundle.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, default=MANIFEST)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--source", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    if args.validate:
        print(f"validated {len(manifest['cases'])} FC100 cases")
        return
    if not args.case or args.source is None or args.out is None:
        parser.error("materialization requires --case, --source, and --out")
    case = next((item for item in manifest["cases"] if item["id"] == args.case), None)
    if case is None:
        parser.error(f"unknown FC100 case: {args.case}")
    print(json.dumps(materialize(case, args.source, args.out), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
