#!/usr/bin/env python3
"""Preflight and render the exact isolated #4884 calibration environment.

This script never builds or runs the image. It validates the closed lock,
checks whether the pinned base and acquisition image are present in a working
local Docker daemon, and renders separate acquisition/build and
network-disabled execution commands. The execution command is withheld until
the caller supplies the acquisition image's exact verified ID.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT / "comparator/calibration/environment.lock.json"
DOCKERFILE = ROOT / "comparator/calibration/Dockerfile"
CONTRACT_PATH = ROOT / "comparator/calibration/erdos_427.toml"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class IsolationError(ValueError):
    pass


def load_lock(path: pathlib.Path = LOCK_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "formal-conjectures.calibration-environment-lock.v1":
        raise IsolationError("unsupported calibration environment lock")
    if value.get("platform") != "linux/amd64":
        raise IsolationError("calibration platform must be linux/amd64")
    container = value.get("container", {})
    if not re.fullmatch(r"ubuntu@sha256:[0-9a-f]{64}", container.get("base", "")):
        raise IsolationError("container base is not digest-pinned")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", container.get("index", "")):
        raise IsolationError("container index is not digest-pinned")
    expected_snapshot = (
        "https://snapshot.ubuntu.com/ubuntu/"
        + container.get("ubuntu_snapshot", "") + "/"
    )
    if container.get("ubuntu_snapshot_url") != expected_snapshot:
        raise IsolationError("Ubuntu snapshot URL/timestamp is not closed")
    if container.get("ca_bootstrap") != (
        "apt-signed-metadata-and-package-hashes-with-tls-peer-disabled"
    ):
        raise IsolationError("Ubuntu CA bootstrap is not explicitly locked")
    for name, archive in value.get("archives", {}).items():
        if not archive.get("url", "").startswith("https://") or not HEX64.fullmatch(
            archive.get("sha256", "")
        ):
            raise IsolationError(f"archive {name} is not URL/hash pinned")
    for name, repository in value.get("repositories", {}).items():
        if not repository.get("url", "").startswith("https://") or not HEX40.fullmatch(
            repository.get("commit", "")
        ):
            raise IsolationError(f"repository {name} is not commit-pinned")
    if not HEX64.fullmatch(value.get("input", {}).get("sha256", "")):
        raise IsolationError("calibration input is not hash-pinned")
    execution = value.get("execution", {})
    required = {
        "network": "none",
        "read_only_root": True,
        "cap_drop": "ALL",
        "no_new_privileges": True,
    }
    if any(execution.get(key) != expected for key, expected in required.items()):
        raise IsolationError("execution isolation settings are incomplete")
    return value


def lock_digest(lock: dict[str, Any]) -> str:
    raw = json.dumps(lock, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def image_tag(lock: dict[str, Any]) -> str:
    return "fc-calibration:" + lock_digest(lock)[:16]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True)


def preflight(output: pathlib.Path, *, image_id: str | None = None,
              runner: Callable[[list[str]],
              subprocess.CompletedProcess[str]] = _run) -> dict[str, Any]:
    lock = load_lock()
    if image_id is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise IsolationError("verified acquisition image ID must be sha256-pinned")
    gates: list[dict[str, Any]] = []

    def gate(name: str, satisfied: bool, observed: Any, expected: Any) -> None:
        gates.append({"name": name, "satisfied": satisfied,
                      "observed": observed, "expected": expected})

    gate("unused_output", not output.exists(), str(output), "path must not exist")
    docker = shutil.which("docker")
    gate("docker_client", docker is not None, docker, "docker on PATH")
    info = runner([docker, "info", "--format",
                   "server={{.ServerVersion}} architecture={{.Architecture}}"] ) \
        if docker else None
    server_ok = info is not None and info.returncode == 0
    gate("docker_daemon", server_ok,
         info.stdout.strip() if server_ok else (info.stderr.strip() if info else None),
         "reachable local daemon")
    base = lock["container"]["base"]
    inspect = runner([docker, "image", "inspect", base, "--format", "{{json .RepoDigests}}"] ) \
        if server_ok else None
    image_ok = inspect is not None and inspect.returncode == 0 and base.split("@", 1)[1] in inspect.stdout
    gate("pinned_image_local", image_ok,
         inspect.stdout.strip() if inspect and inspect.returncode == 0 else None, base)
    gate("dockerfile_present", DOCKERFILE.is_file(), str(DOCKERFILE), "regular file")
    gate("contract_present", CONTRACT_PATH.is_file(), str(CONTRACT_PATH), "regular file")
    build_ready = all(item["satisfied"] for item in gates)
    tag = image_tag(lock)
    built = runner([docker, "image", "inspect", tag, "--format", "{{.Id}}"] ) \
        if build_ready else None
    observed_id = built.stdout.strip() if built and built.returncode == 0 else None
    if image_id is not None:
        gate("verified_acquisition_image", observed_id == image_id,
             observed_id, image_id)
    execute_ready = image_id is not None and all(item["satisfied"] for item in gates)
    return {
        "schema": "formal-conjectures.calibration-isolation-preflight.v1",
        "lock_sha256": "sha256:" + lock_digest(lock),
        "build_ready": build_ready,
        "execute_ready": execute_ready,
        "next_action": (
            "execute_calibration" if execute_ready
            else "build_acquisition_image" if build_ready and observed_id is None
            else "verify_acquisition_image_id" if build_ready
            else "do_not_execute"
        ),
        "acquisition_image": {"tag": tag, "observed_id": observed_id},
        "gates": gates,
        "authority_effect": "none",
    }


def commands(output: pathlib.Path, *, image_id: str | None = None) -> dict[str, list[str]]:
    lock = load_lock()
    tag = image_tag(lock)
    build = [
        "docker", "build", "--platform", lock["platform"],
        "--file", str(DOCKERFILE), "--tag", tag, str(ROOT),
    ]
    execution = lock["execution"]
    result = {"build": build}
    if image_id is None:
        return result
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise IsolationError("verified acquisition image ID must be sha256-pinned")
    run = [
        "docker", "run", "--rm", "--platform", lock["platform"],
        "--network", execution["network"], "--read-only",
        "--cap-drop", execution["cap_drop"],
        "--security-opt", "no-new-privileges=true",
        "--pids-limit", str(execution["pids_limit"]),
        "--memory", execution["memory"], "--cpus", str(execution["cpus"]),
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=2g",
        "--tmpfs", "/root:rw,noexec,nosuid,size=64m",
        "--mount", (
            "type=volume,dst=/opt/formal-conjectures/.comparator/erdos_427/.lake"
        ),
        "--mount", f"type=bind,src={output},dst=/output",
        "--env", f"FC_CALIBRATION_IMAGE_ID={image_id}",
        image_id,
    ]
    result["execute"] = run
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--image-id")
    parser.add_argument("--render-commands", action="store_true")
    args = parser.parse_args(argv)
    report = preflight(args.output, image_id=args.image_id)
    if args.render_commands:
        report["commands"] = commands(args.output, image_id=args.image_id)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["execute_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
