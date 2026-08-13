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

"""Capture a safe, time-free Comparator availability preflight."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


DECLARED_PATH = "/usr/bin:/bin"
COMMAND = ["comparator", "--help"]
ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "PATH": DECLARED_PATH}


def capture_missing_tool_invocation(repository_root: Path) -> dict[str, Any]:
    """Attempt one inert Comparator invocation under a closed environment."""

    resolved = shutil.which(COMMAND[0], path=DECLARED_PATH)
    try:
        completed = subprocess.run(
            COMMAND,
            cwd=repository_root,
            env=ENVIRONMENT,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except FileNotFoundError as error:
        return {
            "schema_version": "formal-conjectures.pr-audit-tool-invocation.v1",
            "tool": "leanprover/comparator",
            "operation": "availability_preflight_only",
            "command": COMMAND,
            "resolved_executable": resolved,
            "cwd": "repository-root",
            "environment": ENVIRONMENT,
            "resolution_attempted": True,
            "invocation_attempted": True,
            "process_started": False,
            "exit_status": None,
            "signal": None,
            "stdout": "",
            "stderr": "",
            "error": {
                "kind": "executable_not_found",
                "errno": error.errno,
                "message": "executable not found under declared PATH",
            },
            "outcome": "unavailable",
            "authority": "producer_evidence_only",
            "nonclaims": [
                "no proof comparison ran",
                "no proof failure was observed",
                "no source-fidelity conclusion follows",
                "no merge or acceptance decision follows",
            ],
        }
    except subprocess.TimeoutExpired as error:
        return {
            "schema_version": "formal-conjectures.pr-audit-tool-invocation.v1",
            "tool": "leanprover/comparator",
            "operation": "availability_preflight_only",
            "command": COMMAND,
            "resolved_executable": resolved,
            "cwd": "repository-root",
            "environment": ENVIRONMENT,
            "resolution_attempted": True,
            "invocation_attempted": True,
            "process_started": True,
            "exit_status": None,
            "signal": None,
            "stdout": (error.stdout or b"").decode("utf-8", errors="replace"),
            "stderr": (error.stderr or b"").decode("utf-8", errors="replace"),
            "error": {"kind": "timeout", "errno": None, "message": "availability preflight timed out"},
            "outcome": "error",
            "authority": "producer_evidence_only",
            "nonclaims": ["no proof comparison result follows"],
        }

    return {
        "schema_version": "formal-conjectures.pr-audit-tool-invocation.v1",
        "tool": "leanprover/comparator",
        "operation": "availability_preflight_only",
        "command": COMMAND,
        "resolved_executable": resolved,
        "cwd": "repository-root",
        "environment": ENVIRONMENT,
        "resolution_attempted": True,
        "invocation_attempted": True,
        "process_started": True,
        "exit_status": completed.returncode,
        "signal": -completed.returncode if completed.returncode < 0 else None,
        "stdout": completed.stdout.decode("utf-8", errors="replace"),
        "stderr": completed.stderr.decode("utf-8", errors="replace"),
        "error": None,
        "outcome": "pass" if completed.returncode == 0 else "error",
        "authority": "producer_evidence_only",
        "nonclaims": ["availability does not establish a proof comparison result"],
    }


def main() -> None:
    value = capture_missing_tool_invocation(Path.cwd())
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
