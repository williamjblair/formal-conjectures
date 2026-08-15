# ClaudesCycles Phase One pilot

Status: checked source design, not a Comparator result and not maintainer acceptance.

The pinned external source is `kim-em/KnuthClaudeLean` at
`bdda6025fb7954f614ed9a7ac7382455fd064940`. Its library theorem uses
`Fin 3 → ZMod m`, matching Formal Conjectures. Its separate trusted
`Challenge.lean`, however, uses the product
`ZMod m × ZMod m × ZMod m`. A successful build of that external challenge is
therefore not evidence for the FC declaration.

`Bridge.lean` deliberately imports the external library theorem, not the
external product/triple challenge, and unfolds every representation boundary:
FC adjacency is a predicate while the external library packages it in a
`Digraph`. The candidate bridge must be compiled in a generated workspace
before any Comparator invocation.

Pinned source evidence:

- `Challenge.lean`: `sha256:fe659a330306b944c0d7df0efd4cad864894bf2f18fd4cf15a9d4570db13b3b3`
- `Solution.lean`: `sha256:89535b9282e5644d5af4e6e711d847a74ad0ba73e771055bacbb04f1a98d63c7`
- `KnuthClaudeLean/Basic.lean`: `sha256:f697fff467799075f2bef8c9f0390461abb2f89d853adbba2a99f07f841adf9c`
- external toolchain: `leanprover/lean4:v4.28.0`
- this draft branch toolchain: `leanprover/lean4:v4.27.0`

`scripts/prepare_claudes_cycles_pilot.py` makes the cross-toolchain test
deterministic: it verifies the exact external commit, both declared
toolchains, and the Basic/Challenge/Solution source hashes, then copies only
`KnuthClaudeLean/Basic.lean` and this bridge into a new generated FC workspace.
It never imports the product/triple challenge or copies `.olean` files. A
focused build of `ClaudesCyclesPilot` is the next gate; even a passing build is
bridge compatibility evidence, not a Comparator result or proof acceptance.

The 2026-08-15 focused build reached that gate and stopped deterministically:
the pinned v4.28 `KnuthClaudeLean.Basic` source does not compile in the pinned
v4.27 FC workspace. The first error is `Basic.lean:123:67: unknown tactic`,
followed by unsolved algebra goals; Lean exits after its 100-error limit. The
FC dependency itself builds, but `Bridge.lean` is not elaborated because the
external library fails first. See `bridge-gate.json` for the bounded command
and typed boundary. Do not patch the external theorem source in this workspace,
invoke Comparator, or report a bridge result until one exact toolchain can
compile both sources.
