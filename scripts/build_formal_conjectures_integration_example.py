#!/usr/bin/env python3
# Copyright 2026 The Formal Conjectures Authors.
# Licensed under the Apache License, Version 2.0.

"""Build or check the deterministic selected-declaration portable export."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from formal_conjectures_integration import IntegrationError, build_selected_export
from pr_audit import canonical_bytes, sha256_digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=".", help="repository root")
    parser.add_argument(
        "--output",
        default=".vela/examples/erdos-887.verification-input.json",
        help="repository-relative output path",
    )
    parser.add_argument(
        "--check", action="store_true", help="require committed bytes to match"
    )
    args = parser.parse_args(argv)
    root = Path(args.repository).resolve()
    output = root / args.output
    try:
        raw = canonical_bytes(build_selected_export(root)) + b"\n"
        sidecar = (sha256_digest(raw) + "\n").encode("utf-8")
        if args.check:
            if (
                output.read_bytes() != raw
                or output.with_name(output.name + ".sha256").read_bytes() != sidecar
            ):
                raise IntegrationError("portable selected-declaration export drift")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(raw)
            output.with_name(output.name + ".sha256").write_bytes(sidecar)
    except (IntegrationError, OSError) as error:
        print(f"formal-conjectures-integration: {error}", file=sys.stderr)
        return 2
    if args.check:
        print("formal-conjectures integration example regeneration: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
