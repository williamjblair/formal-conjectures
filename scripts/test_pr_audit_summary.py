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

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "project_pr_audit_summary.py"
CORE = (
    REPO
    / "audit"
    / "pr-audit-v1"
    / "fixtures"
    / "fidelity-erdos-887-1237"
    / "expected-core.json"
)


class PrAuditSummaryProjectionTest(unittest.TestCase):
    def command(self, core: Path, output: Path | str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--core", str(core), "--output", str(output)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_summary_is_escaped_advisory_and_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            one = Path(temporary) / "one.md"
            two = Path(temporary) / "two.md"
            self.assertEqual(self.command(CORE, one).returncode, 0)
            self.assertEqual(self.command(CORE, two).returncode, 0)
            self.assertEqual(one.read_bytes(), two.read_bytes())
            text = one.read_text()
            self.assertIn("Advisory disposition: **needs\\_revision**", text)
            self.assertIn("This is advisory evidence, not a merge decision", text)
            self.assertNotIn("<script>", text)

    def test_stdout_matches_file_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "summary.md"
            self.assertEqual(self.command(CORE, output).returncode, 0)
            stdout = self.command(CORE, "-")
            self.assertEqual(stdout.returncode, 0)
            self.assertEqual(stdout.stdout.encode(), output.read_bytes())

    def test_noncanonical_or_rewritten_core_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pretty = Path(temporary) / "pretty.json"
            pretty.write_text(json.dumps(json.loads(CORE.read_text()), indent=2) + "\n")
            result = self.command(pretty, Path(temporary) / "summary.md")
            self.assertEqual(result.returncode, 2)
            self.assertIn("not canonical JSON", result.stderr)

            changed = json.loads(CORE.read_text())
            changed["disposition"]["advisory"] = "clean"
            rewritten = Path(temporary) / "rewritten.json"
            rewritten.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n")
            result = self.command(rewritten, Path(temporary) / "changed.md")
            self.assertEqual(result.returncode, 2)
            self.assertIn("disposition does not follow", result.stderr)


if __name__ == "__main__":
    unittest.main()
