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

"""Generate an immutable PR-audit core or a mutable observation envelope."""

from __future__ import annotations

import argparse
import sys

from pr_audit import AuditError, generate_core, generate_observation, write_canonical


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    core = subparsers.add_parser("core", help="generate a deterministic audit core")
    core.add_argument("--input", required=True, help="content-addressed core input manifest")
    core.add_argument("--output", required=True, help="output JSON path")
    core.add_argument("--sha256-sidecar", action="store_true", help="write <output>.sha256")

    observation = subparsers.add_parser(
        "observation", help="generate a mutable observation around an immutable core"
    )
    observation.add_argument("--input", required=True, help="observation input manifest")
    observation.add_argument("--core", required=True, help="validated immutable core JSON")
    observation.add_argument("--output", required=True, help="output JSON path")
    observation.add_argument("--sha256-sidecar", action="store_true", help="write <output>.sha256")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "core":
            value = generate_core(args.input)
        else:
            value = generate_observation(args.input, args.core)
        write_canonical(args.output, value, sidecar=args.sha256_sidecar)
    except (AuditError, OSError) as error:
        print(f"pr-audit: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
