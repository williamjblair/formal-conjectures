#!/usr/bin/env python3
"""Execute the prepared workspace once and write a closed evidence directory."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, "/opt/operator")
import comparator_outcome  # noqa: E402

WORKSPACE = pathlib.Path("/opt/formal-conjectures/.comparator/erdos_427")
OUTPUT = pathlib.Path("/output")


def sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


if not OUTPUT.is_dir() or any(OUTPUT.iterdir()):
    raise SystemExit("/output must be a new empty mounted directory")

env = dict(os.environ)
env["COMPARATOR_LANDRUN"] = "/usr/local/bin/landrun"
env["COMPARATOR_LEAN4EXPORT"] = "/opt/lean4export/.lake/build/bin/lean4export"
env["PATH"] = (
    "/usr/local/bin:/opt/lean4export/.lake/build/bin:/opt/lean/bin:"
    + env.get("PATH", "")
)
command = [
    "lake", "env", "/opt/comparator/.lake/build/bin/comparator", "config.json"
]
report, stdout, stderr = comparator_outcome.run(
    command, None, 1800, cwd=WORKSPACE, env=env
)
(OUTPUT / "stdout.log").write_bytes(stdout)
(OUTPUT / "stderr.log").write_bytes(stderr)
(OUTPUT / "comparator-outcome.json").write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
preparation = pathlib.Path("/opt/calibration-preparation.json").read_bytes()
(OUTPUT / "preparation.json").write_bytes(preparation)
manifest = {
    "schema": "formal-conjectures.calibration-execution-manifest.v1",
    "image_id": os.environ.get("FC_CALIBRATION_IMAGE_ID"),
    "network": "none",
    "preparation_sha256": sha(preparation),
    "stdout_sha256": sha(stdout),
    "stderr_sha256": sha(stderr),
    "outcome_sha256": sha((OUTPUT / "comparator-outcome.json").read_bytes()),
    "authority_effect": "none",
}
(OUTPUT / "execution-manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
raise SystemExit(
    0 if report["invocation"]["outcome"] == "pass"
    and report["result_parse"]["outcome"] == "pass" else 2
)
