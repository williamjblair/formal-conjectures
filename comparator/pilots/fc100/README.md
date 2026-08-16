# FC100 source-bundle pilot

This pilot pins three real proof sources: a theorem case, a definition-answer
case, and a genuine multi-file case. `cases.json` records exact commits, Git
blob IDs, SHA-256 digests, licences, toolchains, and the current bridge gate.
The bridge entries name both declarations and record the first exact semantic
adapter still needed; locating a theorem is not reported as elaborating the FC
statement.

Validate the contract:

```bash
python3 scripts/fc100_bundle.py --validate
```

Materialize one source bundle from an exact checkout:

```bash
python3 scripts/fc100_bundle.py \
  --case erdos-164 --source /path/to/exact/checkout --out /new/output/path
```

The tool refuses an existing output path or any source drift. A prepared case
gets the LeanEval submission shape; a blocked case keeps only the immutable
source bundle and its explicit gate. It never runs Comparator or converts a
build, visibility choice, or terminal message into acceptance.
