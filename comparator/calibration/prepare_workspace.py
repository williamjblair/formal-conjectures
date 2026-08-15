#!/usr/bin/env python3
"""Prepare the exact #4884 workspace during the network-enabled image build."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path("/opt/formal-conjectures")
WORKSPACE = ROOT / ".comparator/erdos_427"
INPUT = pathlib.Path("/opt/inputs/Erdos427.lean")
SOURCE_HEAD = "1f7b8ac102bbcac443288bc2f0620084db57422c"
FC_REV = "2411d22e1bd550d050d0eac6c1fb379a76a3e7c5"
MATHLIB_REV = "a3a10db0e9d66acbebf76c5e6a135066525ac900"
INPUT_SHA = "792a4b5fab29e5855fbcb1115d54e28a054d8fcf7ee2bd5589834a73b387c052"


def run(*command: str, cwd: pathlib.Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def output(*command: str, cwd: pathlib.Path = ROOT) -> str:
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if output("git", "rev-parse", "HEAD") != SOURCE_HEAD:
    raise SystemExit("calibration source checkout drift")
if output("git", "rev-parse", "refs/remotes/origin/main") != FC_REV:
    raise SystemExit("calibration origin/main pin drift")
if sha(INPUT) != INPUT_SHA:
    raise SystemExit("calibration proof input drift")

run("lake", "exe", "cache", "get")
run("lake", "build", "comparator_facts", "FormalConjectures.ErdosProblems.«427»")
run("python3", "scripts/make_comparator_workspace.py", "erdos_427",
    "--out", ".comparator")

lakefile = (WORKSPACE / "lakefile.toml").read_text(encoding="utf-8")
if f'rev = "{FC_REV}"' not in lakefile or f'rev = "{MATHLIB_REV}"' not in lakefile:
    raise SystemExit("generated workspace dependency pins drift")

body = INPUT.read_text(encoding="utf-8").replace("import Mathlib\n", "")
(WORKSPACE / "Submission/External.lean").write_text(
    "import Mathlib\n\nnamespace External\n\n" + body + "\nend External\n",
    encoding="utf-8",
)
submission = WORKSPACE / "Submission.lean"
text = submission.read_text(encoding="utf-8")
text = text.replace(
    "import Submission.Helpers",
    "import Submission.Helpers\nimport Submission.External",
)
proof = (
    ":= by\n"
    "  simp only [true_iff]\n"
    "  intro n d hd\n"
    "  obtain ⟨k, hk1, hkdvd⟩ := External.erdos427 n d "
    "(Nat.one_le_iff_ne_zero.mpr hd)\n"
    "  refine ⟨k, Nat.one_le_iff_ne_zero.mp hk1, ?_⟩\n"
    "  rwa [Finset.sum_Ico_eq_sum_range, Nat.add_sub_cancel_left]"
)
if text.count(":= by\n  sorry") != 1:
    raise SystemExit("generated submission hole shape drift")
submission.write_text(text.replace(":= by\n  sorry", proof), encoding="utf-8")

run("lake", "exe", "cache", "get", cwd=WORKSPACE)
run("lake", "build", cwd=WORKSPACE)

files = [
    "Challenge.lean", "Solution.lean", "Submission.lean",
    "Submission/External.lean", "config.json", "lakefile.toml",
    "lean-toolchain",
]
manifest = {
    "schema": "formal-conjectures.calibration-preparation.v1",
    "source_head": SOURCE_HEAD,
    "formal_conjectures_revision": FC_REV,
    "mathlib_revision": MATHLIB_REV,
    "input_sha256": "sha256:" + INPUT_SHA,
    "workspace_files": {
        relative: "sha256:" + sha(WORKSPACE / relative) for relative in files
    },
    "authority_effect": "none",
}
pathlib.Path("/opt/calibration-preparation.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
