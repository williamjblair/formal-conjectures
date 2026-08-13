#!/usr/bin/env python3
"""Build the canonical FC-07 Comparator pilot index from retained observations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
PILOT = REPOSITORY / "audit/pr-audit-v1/comparator-pilot"


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def load_canonical(path: Path) -> tuple[dict[str, object], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if raw != canonical(value) + b"\n":
        raise SystemExit(f"noncanonical JSON framing: {path}")
    return value, raw


def main() -> None:
    cases = []
    for path in sorted((PILOT / "observations").glob("*.json")):
        value, raw = load_canonical(path)
        unrooted = dict(value)
        claimed_root = unrooted.pop("root")
        if claimed_root != digest(canonical(unrooted)):
            raise SystemExit(f"observation root drift: {path}")
        cases.append({
            "case_id": value["case_id"],
            "observation_path": path.relative_to(REPOSITORY).as_posix(),
            "observation_raw_sha256": digest(raw),
            "observation_root": claimed_root,
        })

    if {case["case_id"] for case in cases} != {
        "clean-unconditional", "conditional-permitted-axiom", "target-mismatch", "definition-hole-semantic-gap"
    }:
        raise SystemExit("Comparator execution case inventory drift")

    missing_core = REPOSITORY / "audit/pr-audit-v1/fixtures/unavailable-rupert-3959/expected-core.json"
    missing_observation = REPOSITORY / "audit/pr-audit-v1/fixtures/unavailable-rupert-3959/expected-observation.json"
    missing_core_value, missing_core_raw = load_canonical(missing_core)
    missing_observation_value, missing_observation_raw = load_canonical(missing_observation)

    record = {
        "cases": cases,
        "composed_cases": [{
            "case_id": "missing-or-ambiguous-target",
            "core_path": missing_core.relative_to(REPOSITORY).as_posix(),
            "core_raw_sha256": digest(missing_core_raw),
            "core_root": missing_core_value["root"],
            "observation_path": missing_observation.relative_to(REPOSITORY).as_posix(),
            "observation_raw_sha256": digest(missing_observation_raw),
            "observation_root": missing_observation_value["root"],
            "outcome": "unavailable",
            "scope": "exact_formal_proof_artifact_and_comparator_execution_identity",
        }],
        "nonclaims": [
            "Comparator does not establish statement fidelity.",
            "A permitted-axiom pass is conditional on that exact policy.",
            "A definition-hole pass requires an additional semantic verifier.",
            "The development fake-landrun run does not establish sandbox isolation.",
            "The packet is not an FC acceptance or merge decision.",
            "The packet is not a Vela Verification, Decision, or Standing change.",
        ],
        "schema_version": "formal-conjectures.comparator-pilot.v1",
        "source": {
            "comparator_commit": "3927ad383f208ae977c340a91c48ac9b497d2097",
            "comparator_repository": "https://github.com/leanprover/comparator",
            "comparator_tag": "v4.33.0",
            "comparator_tree": "4e7fb3e09de46dc9bb040b4d7e792f05ac324f64",
            "lean4export_commit": "15f6055e299ad5b89345e533cc2192f4cc00f659",
            "lean_toolchain": "leanprover/lean4:v4.33.0",
        },
    }
    record["root"] = digest(canonical(record))
    (PILOT / "pilot.json").write_bytes(canonical(record) + b"\n")


if __name__ == "__main__":
    main()
