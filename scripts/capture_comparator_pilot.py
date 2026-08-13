#!/usr/bin/env python3
"""Capture the bounded FC-07 Comparator pilot from an exact public checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


REPOSITORY = Path(__file__).resolve().parents[1]
PILOT = REPOSITORY / "audit/pr-audit-v1/comparator-pilot"
CASES = PILOT / "cases"
OBSERVATIONS = PILOT / "observations"
COMPARATOR_COMMIT = "3927ad383f208ae977c340a91c48ac9b497d2097"
COMPARATOR_TREE = "4e7fb3e09de46dc9bb040b4d7e792f05ac324f64"
LEAN_TOOLCHAIN = "leanprover/lean4:v4.33.0"
LEAN4EXPORT_COMMIT = "15f6055e299ad5b89345e533cc2192f4cc00f659"

CASE_CONTRACT = {
    "clean-unconditional": {
        "expected_exit": 0,
        "expected_marker": "Your solution is okay!",
        "outcome": "pass",
        "scope": "same_statement_permitted_axioms_and_lean_kernel",
    },
    "conditional-permitted-axiom": {
        "expected_exit": 0,
        "expected_marker": "Your solution is okay!",
        "outcome": "pass_with_named_permitted_axiom",
        "scope": "same_statement_with_explicit_helper_axiom",
    },
    "target-mismatch": {
        "expected_exit": 1,
        "expected_marker": "Challenge and solution constant kind don't match: 'comm'",
        "outcome": "refused_target_mismatch",
        "scope": "challenge_solution_declaration_identity",
    },
    "definition-hole-semantic-gap": {
        "expected_exit": 0,
        "expected_marker": "Your solution is okay!",
        "outcome": "pass_requires_additional_semantic_verifier",
        "scope": "definition_hole_shape_axioms_and_kernel_only",
    },
}

UPSTREAM_CASES = {
    "clean-unconditional": "simple_match",
    "target-mismatch": "simple_mismatch",
    "definition-hole-semantic-gap": "def_hole",
}


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def normalize(text: str, checkout: Path, case_dir: Path) -> str:
    text = text.replace(str(checkout), "$COMPARATOR_CHECKOUT")
    text = text.replace(str(case_dir), "$CASE_DIR")
    text = re.sub(r"\((?:\d+(?:\.\d+)?)(?:ms|s)\)", "(<duration>)", text)
    return text


def descriptor(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(REPOSITORY).as_posix(),
        "raw_sha256": digest(data),
        "size": len(data),
    }


def validate_checkout(checkout: Path) -> None:
    if run(["git", "rev-parse", "HEAD"], checkout).stdout.strip() != COMPARATOR_COMMIT:
        raise SystemExit("Comparator checkout commit drift")
    if run(["git", "show", "-s", "--format=%T", "HEAD"], checkout).stdout.strip() != COMPARATOR_TREE:
        raise SystemExit("Comparator checkout tree drift")
    toolchain = (checkout / "lean-toolchain").read_text().strip()
    if toolchain != LEAN_TOOLCHAIN:
        raise SystemExit("Comparator Lean toolchain drift")
    manifest = json.loads((checkout / "lake-manifest.json").read_text())
    packages = {item["name"]: item for item in manifest["packages"]}
    if packages["lean4export"]["rev"] != LEAN4EXPORT_COMMIT:
        raise SystemExit("lean4export revision drift")


def capture(checkout: Path) -> None:
    validate_checkout(checkout)
    for case_id, upstream_id in UPSTREAM_CASES.items():
        for name in ("Challenge.lean", "Solution.lean", "config.json"):
            retained = (CASES / case_id / name).read_bytes()
            upstream = (checkout / "tests/projects" / upstream_id / name).read_bytes()
            if retained != upstream:
                raise SystemExit(f"{case_id}/{name}: retained input drifts from Comparator {upstream_id}")
    build = run(["elan", "run", LEAN_TOOLCHAIN, "lake", "build", "lean4export", "comparator"], checkout)
    if build.returncode != 0:
        raise SystemExit(build.stdout + build.stderr)

    comparator = checkout / ".lake/build/bin/comparator"
    lean4export = checkout / ".lake/packages/lean4export/.lake/build/bin/lean4export"
    fake_landrun = checkout / "scripts/fake-landrun.sh"
    OBSERVATIONS.mkdir(parents=True, exist_ok=True)

    for case_id, contract in CASE_CONTRACT.items():
        with tempfile.TemporaryDirectory(prefix=f"fc07-{case_id}-") as temporary:
            case_dir = Path(temporary)
            for name in ("Challenge.lean", "Solution.lean", "config.json"):
                shutil.copy2(CASES / case_id / name, case_dir / name)
            (case_dir / "lakefile.toml").write_text(
                'name = "fc07pilot"\nversion = "0.1.0"\n\n[[lean_lib]]\nname = "Challenge"\n\n[[lean_lib]]\nname = "Solution"\n'
            )
            env = os.environ.copy()
            env["COMPARATOR_LANDRUN"] = str(fake_landrun)
            env["COMPARATOR_LEAN4EXPORT"] = str(lean4export)
            env["ELAN_TOOLCHAIN"] = LEAN_TOOLCHAIN
            result = run(["elan", "run", LEAN_TOOLCHAIN, "lake", "env", str(comparator), "config.json"], case_dir, env)
            stdout = normalize(result.stdout, checkout, case_dir)
            stderr = normalize(result.stderr, checkout, case_dir)
            combined = stdout + stderr
            if result.returncode != contract["expected_exit"] or contract["expected_marker"] not in combined:
                raise SystemExit(f"{case_id}: unexpected Comparator result\n{combined}")
            inputs = [descriptor(CASES / case_id / name) for name in ("Challenge.lean", "Solution.lean", "config.json")]
            record = {
                "case_id": case_id,
                "execution": {
                    "capture_implementation": descriptor(Path(__file__).resolve()),
                    "comparator_commit": COMPARATOR_COMMIT,
                    "comparator_tree": COMPARATOR_TREE,
                    "development_fake_landrun": True,
                    "enable_nanoda": False,
                    "lean4export_commit": LEAN4EXPORT_COMMIT,
                    "lean_toolchain": LEAN_TOOLCHAIN,
                    "sandboxed": False,
                },
                "expected": contract,
                "inputs": inputs,
                "observed": {
                    "exit_code": result.returncode,
                    "stderr": stderr,
                    "stderr_sha256": digest(stderr.encode()),
                    "stdout": stdout,
                    "stdout_sha256": digest(stdout.encode()),
                },
                "nonclaims": [
                    "not_a_statement_fidelity_review",
                    "not_a_repository_acceptance_or_merge_decision",
                    "not_a_vela_verification_decision_or_standing_change",
                    "not_evidence_of_landrun_sandbox_isolation",
                    "not_a_nanoda_replay",
                ],
                "schema_version": "formal-conjectures.comparator-pilot-observation.v1",
            }
            record["root"] = digest(canonical(record))
            (OBSERVATIONS / f"{case_id}.json").write_bytes(canonical(record) + b"\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparator-checkout", type=Path, required=True)
    args = parser.parse_args()
    capture(args.comparator_checkout.resolve())


if __name__ == "__main__":
    main()
