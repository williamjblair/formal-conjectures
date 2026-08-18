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

"""Render an escaped advisory Markdown projection from an exact audit core."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pr_audit import AuditError, canonical_bytes, parse_json_bytes, render_markdown, validate_core


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--core", required=True, help="canonical immutable core JSON")
    result.add_argument("--output", required=True, help="output Markdown path, or - for stdout")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        path = Path(args.core)
        raw = path.read_bytes()
        core = validate_core(parse_json_bytes(raw, label=str(path)))
        if raw != canonical_bytes(core) + b"\n":
            raise AuditError("audit core is not canonical JSON with one LF framing byte")
        markdown = render_markdown(core)
        if args.output == "-":
            sys.stdout.write(markdown)
        else:
            Path(args.output).write_text(markdown, encoding="utf-8")
    except (AuditError, OSError, UnicodeError) as error:
        print(f"pr-audit-summary: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
