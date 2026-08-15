#!/usr/bin/env python3
"""Prepare the exact ClaudesCycles bridge in a generated FC workspace.

This copies only the pinned external library theorem source. It deliberately
does not copy the external Challenge/Solution pair whose trusted statement is
the product/triple formulation. Preparation is not a Comparator result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "comparator/pilots/claudes_cycles/Bridge.lean"
EXTERNAL_COMMIT = "bdda6025fb7954f614ed9a7ac7382455fd064940"
EXTERNAL_TOOLCHAIN = "leanprover/lean4:v4.28.0"
WORKSPACE_TOOLCHAIN = "leanprover/lean4:v4.27.0"
HASHES = {
    "KnuthClaudeLean/Basic.lean":
        "f697fff467799075f2bef8c9f0390461abb2f89d853adbba2a99f07f841adf9c",
    "Challenge.lean":
        "fe659a330306b944c0d7df0efd4cad864894bf2f18fd4cf15a9d4570db13b3b3",
    "Solution.lean":
        "89535b9282e5644d5af4e6e711d847a74ad0ba73e771055bacbb04f1a98d63c7",
}


class PilotPreparationError(ValueError):
    pass


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(repository: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True,
        capture_output=True, text=True).stdout.strip()


def prepare(workspace: pathlib.Path, external: pathlib.Path) -> dict[str, object]:
    workspace = workspace.resolve(strict=True)
    external = external.resolve(strict=True)
    if git_output(external, "rev-parse", "HEAD") != EXTERNAL_COMMIT:
        raise PilotPreparationError("external ClaudesCycles checkout commit drift")
    for relative, expected in HASHES.items():
        path = external / relative
        if not path.is_file() or sha256(path) != expected:
            raise PilotPreparationError(f"external source drift: {relative}")
    if (external / "lean-toolchain").read_text(encoding="utf-8").strip() != EXTERNAL_TOOLCHAIN:
        raise PilotPreparationError("external toolchain drift")
    if (workspace / "lean-toolchain").read_text(encoding="utf-8").strip() != WORKSPACE_TOOLCHAIN:
        raise PilotPreparationError("generated workspace toolchain drift")

    target_basic = workspace / "KnuthClaudeLean/Basic.lean"
    target_bridge = workspace / "ClaudesCyclesPilot.lean"
    manifest_path = workspace / "claudes-cycles-preparation.json"
    for target in (target_basic, target_bridge, manifest_path):
        if target.exists():
            raise PilotPreparationError(f"refusing to overwrite prepared target: {target}")
    target_basic.parent.mkdir(parents=True)
    shutil.copyfile(external / "KnuthClaudeLean/Basic.lean", target_basic)
    shutil.copyfile(BRIDGE, target_bridge)

    lakefile_path = workspace / "lakefile.toml"
    lakefile = lakefile_path.read_text(encoding="utf-8")
    addition = (
        "\n[[lean_lib]]\nname = \"KnuthClaudeLean\"\n"
        "\n[[lean_lib]]\nname = \"ClaudesCyclesPilot\"\n"
    )
    if "name = \"ClaudesCyclesPilot\"" in lakefile:
        raise PilotPreparationError("workspace already declares ClaudesCyclesPilot")
    lakefile_path.write_text(lakefile.rstrip() + "\n" + addition, encoding="utf-8")

    manifest: dict[str, object] = {
        "schema": "formal-conjectures.claudes-cycles-preparation.v1",
        "authority_effect": "none",
        "external_commit": EXTERNAL_COMMIT,
        "external_toolchain": EXTERNAL_TOOLCHAIN,
        "workspace_toolchain": WORKSPACE_TOOLCHAIN,
        "external_challenge_formulation": "product_triple_not_imported",
        "verified_external_sources": {
            relative: "sha256:" + expected for relative, expected in HASHES.items()
        },
        "copied_files": {
            "KnuthClaudeLean/Basic.lean": "sha256:" + sha256(target_basic),
            "ClaudesCyclesPilot.lean": "sha256:" + sha256(target_bridge),
        },
        "nonclaims": [
            "not_a_comparator_result",
            "not_maintainer_acceptance",
            "not_evidence_for_the_external_product_triple_challenge",
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=pathlib.Path)
    parser.add_argument("external", type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.workspace, args.external), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
