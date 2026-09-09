# Evaluation overhaul records

- `attempt-1/`: invalid/stopped protocol iteration. Baseline procedure receipt was missing,
  evidence fields allowed prose, and host plugin resource discovery was not fully disabled.
  Do not score this as a skill comparison. Outputs and stopped jobs are retained.
- `routing-before-isolation/`: exploratory routing runs before plugin-discovery isolation was
  confirmed. No description tuning followed the validation queries. Later runs supersede these.
  These early runs did not freeze exact tooling; do not treat them as fully reproducible runs.
- `isolation-probe/`: explicit diagnostic, not a benchmark query. Its resource catalog is empty.
  The then-current strict tool allowlist marked built-in discovery unexpected; the corrected
  harness accepts only an empty catalog. The diagnostic is retained unchanged.
- `fixture-builds/`: all 20 exact historical candidate files built with Lean 4.33.1 and --wfail.
- `setup-logs/`: retained Docker setup failures and successful image/build logs.

Model judgements are provisional. No human adjudication has been performed.
