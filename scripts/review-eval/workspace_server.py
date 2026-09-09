#!/usr/bin/env python3
"""Evaluation adapter for the shared isolated workspace tools."""
import runpy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "toolkit"))
from conjectures.eval_workspace import *
if __name__ == "__main__":
    runpy.run_module("conjectures.eval_workspace", run_name="__main__")
