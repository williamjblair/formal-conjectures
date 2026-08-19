# Security boundaries

## Credentials

- Model API credentials belong only in the trusted model job.
- GitHub App ID/private key belong only in the publication job.
- The model job never receives the App key or a write-capable installation token.
- The engine never reads credentials and stores no secret values or raw provider messages in its cost ledger.
- This repository contains secret names and interface documentation only. It contains no secret values.

## Publication

The engine produces payloads and offline create/update selections. The publisher must obtain a short-lived installation
token with repository-scoped `contents: read` and `pull requests: write`, re-read the live PR, refuse a changed head, and
then update one marker-bound summary. Inline findings are keyed, head/path/line-bound, and refused if an existing marker is
bound elsewhere. Publication has no approval, merge, label, or acceptance capability.

## Untrusted inputs

Contributor source, retained mathematical sources, and model output are data. The clean-room model gets read-only tools;
the validator uses strict JSON, bounded strings/arrays, exact keys, canonical hashes, and no stored result fallback.
