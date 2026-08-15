# Isolated #4884 calibration environment

This directory specifies a new replay environment. It does not overwrite or
reinterpret the historical run, and it does not make a maintainer decision.

`environment.lock.json` closes the execution inputs: linux/amd64 Ubuntu base
manifest, Ubuntu package snapshot, Go and Lean archives, four source commits,
the fetched proof bytes, and the sandbox limits. `Dockerfile` has a
network-enabled acquisition/build phase. The rendered execution command is a
separate container with no network, a read-only root, no capabilities, no new
privileges, bounded processes/memory/CPU, and one new output bind mount.

The minimal pinned Ubuntu base has no CA bundle before package installation.
For the CA bootstrap only, apt disables TLS peer verification while still
verifying Ubuntu's signed `InRelease` metadata and package hashes. It then
installs `ca-certificates` and repeats the snapshot update with normal HTTPS
verification before installing any other package. The exact endpoint,
timestamp, and bootstrap exception are part of the lock.

Run the local preflight without building or executing anything:

```bash
python3 scripts/calibration_isolation.py \
  --output /an/absolute/path/that/does/not/exist \
  --render-commands
```

The preflight requires a working Docker daemon and the exact pinned base image
already present. It never pulls, builds, creates the output directory, or runs
proof code. It first renders only the acquisition build. After the build,
inspect its image ID and repeat the preflight with `--image-id sha256:...`.
Only an exact match to the locally tagged image unlocks rendering the execution
command, which names the immutable image ID rather than the mutable tag;
preflight otherwise exits 2.

The build command is only an acquisition recipe. It prepares and builds the
workspace at the exact historical FC/Mathlib revisions inside the image. Before
an actual replay, inspect the resulting image ID and pass it explicitly to the
preflight. The output directory must then be created once, mounted only at
`/output`, and never reused. The image root is
read-only at execution; Docker initializes a fresh anonymous writable volume
from the prepared workspace's `.lake` tree, and removes it with the container.
Comparator output must pass through
`scripts/comparator_outcome.py`; terminal text alone cannot produce a property
`pass` or `fail`.
