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

That toolchain mismatch is an execution gate. Do not copy generated `.olean`
files across it, silently retarget Mathlib, or report green until a single
fully pinned workspace compiles FC, the external source, and `Bridge.lean`.
