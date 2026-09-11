# Proof submission

Target: `PackageExportFixture.plain` in `«FormalConjecturesTest».«PackageExport»`.
Source: https://github.com/williamjblair/formal-conjectures.git at `c5bd5601217cbcb889e1adc2f4987dfaa854dcb1`.

Read Challenge.lean and Submission.lean. Edit only Submission.lean and .lean files
under Submission/. Preserve the target, dependency pins, and verification policy.
Use `lake build` for development feedback in this scratch workspace. Compilation
alone is not verification. The verifier regenerates trusted files in a fresh workspace.

Run `conjectures verify . --json`, then follow the returned next action.
A configured Linux executor accepts local submissions. GitHub execution requires
an explicitly committed and pushed public workspace; do not publish automatically.
Inspect results with `conjectures run show RUN` and `conjectures run logs RUN`.

Report errors separately from rejection. Definition-hole answers need additional
semantic assessment. A passing proof does not establish source fidelity or maintainer acceptance.
