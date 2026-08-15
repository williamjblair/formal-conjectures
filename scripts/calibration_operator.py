#!/usr/bin/env python3
"""Check whether the immutable #4884 calibration execution gate is satisfied.

This operator does not run Comparator. It emits a gate record and refuses to
claim readiness unless the exact source, Linux runner identity, tools, input,
and a never-before-used output directory are all established.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tomllib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT = ROOT / "comparator/calibration/erdos_427.toml"


def git_head(path: pathlib.Path) -> str | None:
    proc = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def check(contract: dict, output: pathlib.Path, tool_roots: dict[str, pathlib.Path],
          acquire: bool) -> dict:
    gates = []
    def gate(name, ok, observed, expected):
        gates.append({"name": name, "satisfied": bool(ok),
                      "observed": observed, "expected": expected})

    gate("unused_output", not output.exists(), str(output), "path must not exist")
    head = git_head(ROOT)
    gate("source_commit", head == contract["source_commit"], head,
         contract["source_commit"])
    gate("linux", platform.system() == "Linux", platform.system(), "Linux")
    runner = os.environ.get("FC_CALIBRATION_RUNNER_IMAGE")
    gate("runner_image", runner == contract["runner_image"], runner,
         contract["runner_image"])
    go_path = shutil.which("go")
    go = subprocess.run([go_path, "version"], capture_output=True, text=True) \
        if go_path else None
    observed_go = (
        go.stdout.split()[2]
        if go is not None and go.returncode == 0 and len(go.stdout.split()) > 2
        else None
    )
    gate("go_version", observed_go == contract["go_version"], observed_go,
         contract["go_version"])
    for name, expected in contract["tools"].items():
        root = tool_roots.get(name)
        observed = git_head(root) if root else None
        gate(f"tool_{name}", observed == expected, observed, expected)
    if acquire:
        raw = urllib.request.urlopen(contract["gist_url"], timeout=30).read()
        observed = hashlib.sha256(raw).hexdigest()
    else:
        observed = None
    gate("gist_bytes", observed == contract["gist_sha256"], observed,
         contract["gist_sha256"])
    ready = all(item["satisfied"] for item in gates)
    return {
        "schema": "formal-conjectures.calibration-gate.v1",
        "calibration": contract["id"],
        "ready": ready,
        "gates": gates,
        "next_action": "execute_in_new_output_directory" if ready else "do_not_execute",
        "authority_effect": "none",
    }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=pathlib.Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=pathlib.Path, required=True,
                        help="immutable run directory; it must not exist")
    parser.add_argument("--tool-root", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--acquire", action="store_true",
                        help="fetch and hash the pinned gist; does not execute proof code")
    args = parser.parse_args(argv)
    with args.contract.open("rb") as handle:
        contract = tomllib.load(handle)
    roots = {}
    for item in args.tool_root:
        name, sep, path = item.partition("=")
        if not sep:
            parser.error("--tool-root must be NAME=PATH")
        roots[name] = pathlib.Path(path)
    report = check(contract, args.output, roots, args.acquire)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
