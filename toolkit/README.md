# Formal Conjectures toolkit

Install an exact revision with `uv tool install git+https://github.com/williamjblair/formal-conjectures.git@COMMIT`.
Run `conjectures doctor --json` inside your FC checkout. The pilot uses local Codex OAuth.

Configuration lives in `~/.config/conjectures/config.json` or `.conjectures/config.json`:

```json
{"backend":"codex","model":"YOUR_CONFIGURED_MODEL","image":"sha256:PINNED_IMAGE_ID","executor":null,"evidence":null,"limits":{"seconds":420,"tools":20}}
```

The review image uses `scripts/review-report/Dockerfile` and must contain the target's exact
Lean toolchain, Lake configuration, dependency manifest, and trusted dependency cache.
Candidate code runs without host credentials or networking. Model events remain local.

Use `conjectures find erdos/730`, then `conjectures show Erdos730.erdos_730`.
Review a PR with `conjectures review --pr NUMBER --model MODEL`, or local changes with
`conjectures review --changed --base origin/main`. Supply downloaded source documents with
`--sources DIR`. Otherwise the controller retrieves directly cited public sources.

Inspect `conjectures status`, `conjectures run list`, and `conjectures run show RUN`.
Reports are advisory. Missing source coverage remains incomplete. Compilation does not
verify a proof's assumptions. Maintainers decide whether to accept contributions.

Runs, credentials configuration, and raw artifacts stay in the gitignored `.conjectures/`
directory. Publication is a separate explicit operation. Never commit that directory.
The API adapter additionally requires `CONJECTURES_ENABLE_API=1`; leave it disabled for the OAuth pilot.
