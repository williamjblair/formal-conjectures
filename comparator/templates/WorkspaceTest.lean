import Lean

open Lean

/-- Run comparator on this workspace's `config.json`, so that `lake test`
is the check. Adapted from `leanprover/lean-eval`'s workspace test template.
The binary comes from `PATH`, or from `COMPARATOR_BIN`. -/
def main : IO UInt32 := do
  let comparatorBin := (← IO.getEnv "COMPARATOR_BIN").getD "comparator"
  try
    let child ← IO.Process.spawn {
      cmd := "lake"
      args := #["env", comparatorBin, "config.json"]
    }
    child.wait
  catch err =>
    IO.eprintln s!"Failed to run comparator via `{comparatorBin}`."
    IO.eprintln "Install comparator, with landrun and lean4export, and put it \
on PATH, or set COMPARATOR_BIN. See leanprover/comparator's README."
    IO.eprintln s!"Original error: {err}"
    pure 1
