#!/usr/bin/env python3
# Copyright 2026 The Formal Conjectures Authors.
# Licensed under the Apache License, Version 2.0.

"""Validate the source-owned Formal Conjectures Vela integration offline."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from formal_conjectures_integration import IntegrationError, validate_repository
from pr_audit import canonical_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=".", help="repository root")
    args = parser.parse_args(argv)
    try:
        packet = validate_repository(Path(args.repository))
    except IntegrationError as error:
        print(f"formal-conjectures-integration: {error}", file=sys.stderr)
        return 2
    summary = {
        "schema": "formal-conjectures.integration-validation.v0.1",
        "authority_effect": "none",
        "manifest_root": packet["manifest"]["manifest_root"],
        "profiles": sorted(
            profile["profile_root"] for profile in packet["profiles"].values()
        ),
        "bindings": sorted(
            binding["binding_root"] for binding in packet["bindings"].values()
        ),
        "methods": sorted(
            method["method_root"] for method in packet["methods"].values()
        ),
        "result": "pass",
        "nonclaims": [
            "Validation is not acceptance, a Decision, an Event, or Standing."
        ],
    }
    sys.stdout.buffer.write(canonical_bytes(summary) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
