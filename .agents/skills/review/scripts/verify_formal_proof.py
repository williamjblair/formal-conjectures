#!/usr/bin/env python3
"""Verify a linked `formal_proof` end to end: fetch it, build it, audit its axioms.

`check_proof_links.py` answers "does the link resolve". This answers the question a
reviewer actually has: does the linked code build, does the named theorem exist, does
its proof depend on `sorryAx` or on axioms beyond the standard three, and does the
repository smuggle in `axiom` declarations or `native_decide`. A single-file gist is
easy to paste into Lean Web; a 20k-line multi-file project is not, and those are the
links this exists for.

Stages, each reported separately so a partial run still says something:

  resolve      the link parses into something fetchable
  materialise  shallow clone at the pinned commit, or gist files into a directory
  static       grep-level audit: `sorry`, `axiom`, `native_decide`, counted per file
  build        `lake exe cache get` when Mathlib is a dependency, then `lake build`
  probe        `#print axioms <decl>` for each target declaration, parsed

Usage:
  python verify_formal_proof.py --link URL [--theorem NAME ...] [--static-only]
  python verify_formal_proof.py FILE.lean ...      # audit every link in these files
  python verify_formal_proof.py --link URL --json  # machine-readable report

Validated end to end against `Shashi456/erdos-formalizations` at
`Erdos/P750/Proof.lean`, which Erdős 750 cites as a `conditional formal_proof`:
the build succeeds, and the probe reports `erdos_750_FC` and
`erdos_750_independence` as sorry-free but resting on
`Erdos750.stiebitz_lower_bound`, while `finite_oct_profile` in the same module
rests on nothing beyond the standard three. That split matches the trust
boundary the file's own author documents, and a file-level `axiom` count cannot
make it.

The static stage never lies in one direction: zero `sorry` in the sources means the
build cannot manufacture one. The converse needs the probe, because a clean grep says
nothing about which axioms a proof term actually reaches. Both are reported.

A bare `.lean` file with no lakefile is run against this repository's own toolchain
via `lake env lean`. That is a toolchain substitution and the report says so: a file
written for another Mathlib may fail here without being wrong, and pass here without
its own project building.
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent

# `formal_proof using <kind> at "<link>"`, with the attribute free to wrap
# across lines the way it does in the problem files. This mirrors the regex in
# the repository's own `scripts/check_proof_links.py`; the duplication is
# deliberate, because a bundled skill tool must run without a checkout of that
# repository. If the two ever disagree, that script is the definition.
LINK_IN_SOURCE = re.compile(
    r'formal_proof\s+using\s+\w+\s+at\s*\n?\s*"([^"]*)"',
    re.MULTILINE,
)

STANDARD_AXIOMS = {"propext", "Quot.sound", "Classical.choice"}

# `sorry` as a token, not as a substring of an identifier or a word in a comment
# line that happens to say "sorry-free". Comments are stripped first, below.
SORRY = re.compile(r"(?<![\w.])sorry(?![\w.])")
AXIOM_DECL = re.compile(r"^\s*(?:@\[[^\]]*\]\s*)*axiom\s", re.MULTILINE)
NATIVE_DECIDE = re.compile(r"(?<![\w.])native_decide(?![\w.])")

TIMEOUT_FETCH = 60
HEADERS = {"User-Agent": "formal-conjectures-proof-verify"}


def strip_comments(text):
    """Remove line and block comments so the static audit reads only code.

    Lean block comments nest, so a regex cannot do this half; a depth counter can.
    """
    out, i, depth, n = [], 0, 0, len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "/-":
            depth += 1
            i += 2
        elif two == "-/" and depth:
            depth -= 1
            i += 2
        elif depth:
            i += 1
        elif two == "--":
            while i < n and text[i] != "\n":
                i += 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


# --------------------------------------------------------------------------- resolve


def resolve(link):
    """Classify a link into a fetch plan. Returns a dict or raises ValueError.

    Shapes handled, matching what the repository's links actually look like:
      https://github.com/OWNER/REPO                        repo, default branch
      https://github.com/OWNER/REPO/tree/REF[/DIR]         repo at ref
      https://github.com/OWNER/REPO/blob/REF/PATH          repo at ref, target file
      https://github.com/OWNER/REPO/commit/SHA             repo at commit
      https://github.com/OWNER/REPO/pull/N/commits/SHA     repo at commit (pull ref)
      https://gist.github.com/OWNER/ID                     gist
    """
    link = link.split("#", 1)[0].rstrip("/")
    m = re.match(r"https://gist\.github\.com/[^/]+/([0-9a-f]+)", link)
    if m:
        return {"kind": "gist", "id": m.group(1), "link": link}
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)(?:/(.*))?$", link)
    if not m:
        raise ValueError(f"not a github.com or gist.github.com link: {link}")
    owner, repo, rest = m.group(1), m.group(2), m.group(3) or ""
    plan = {
        "kind": "repo",
        "clone": f"https://github.com/{owner}/{repo}",
        "ref": None,
        "file": None,
        "link": link,
    }
    parts = rest.split("/") if rest else []
    if not parts:
        return plan
    if parts[0] in ("tree", "blob", "commit") and len(parts) >= 2:
        plan["ref"] = parts[1]
        if parts[0] == "blob" and len(parts) > 2:
            plan["file"] = "/".join(parts[2:])
        return plan
    if parts[0] == "pull" and "commits" in parts:
        plan["ref"] = parts[parts.index("commits") + 1]
        return plan
    raise ValueError(f"unrecognised github path shape: {link}")


# ----------------------------------------------------------------------- materialise


def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT_FETCH) as r:
        return json.load(r)


def materialise(plan, dest):
    """Fetch the code into `dest`. Returns the checkout root as a Path."""
    dest = pathlib.Path(dest)
    if plan["kind"] == "gist":
        data = fetch_json(f"https://api.github.com/gists/{plan['id']}")
        for name, meta in data.get("files", {}).items():
            content = meta.get("content")
            if content is None:
                req = urllib.request.Request(meta["raw_url"], headers=HEADERS)
                with urllib.request.urlopen(req, timeout=TIMEOUT_FETCH) as r:
                    content = r.read().decode("utf-8", "replace")
            (dest / name).write_text(content, encoding="utf-8")
        return dest
    run(["git", "clone", "--quiet", "--filter=blob:none", plan["clone"], str(dest)])
    if plan["ref"]:
        # A pull-request commit is not on any branch; fetch it explicitly first.
        if run(["git", "-C", str(dest), "checkout", "--quiet", plan["ref"]],
               check=False).returncode != 0:
            run(["git", "-C", str(dest), "fetch", "--quiet", "origin", plan["ref"]])
            run(["git", "-C", str(dest), "checkout", "--quiet", "FETCH_HEAD"])
    return dest


def run(cmd, cwd=None, check=True, timeout=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{proc.stderr[-2000:]}")
    return proc


# ---------------------------------------------------------------------------- static


def static_audit_file(path, root=None):
    """Count sorry / axiom / native_decide in one file, comments stripped."""
    code = strip_comments(pathlib.Path(path).read_text(encoding="utf-8",
                                                       errors="replace"))
    return {key: len(pattern.findall(code))
            for key, pattern in (("sorry", SORRY), ("axiom", AXIOM_DECL),
                                 ("native_decide", NATIVE_DECIDE))}


def static_audit(root):
    """Count sorry / axiom / native_decide per .lean file, comments stripped."""
    report = {"files": 0, "sorry": {}, "axiom": {}, "native_decide": {}}
    for path in sorted(pathlib.Path(root).rglob("*.lean")):
        if ".lake" in path.parts:
            continue
        report["files"] += 1
        code = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        rel = str(path.relative_to(root))
        for key, pattern in (("sorry", SORRY), ("axiom", AXIOM_DECL),
                             ("native_decide", NATIVE_DECIDE)):
            n = len(pattern.findall(code))
            if n:
                report[key][rel] = n
    return report


# ----------------------------------------------------------------------------- build


def detect_project(root):
    root = pathlib.Path(root)
    has_lakefile = any((root / n).exists() for n in ("lakefile.toml", "lakefile.lean"))
    lean_files = [p for p in root.rglob("*.lean") if ".lake" not in p.parts]
    return {"lakefile": has_lakefile, "lean_files": len(lean_files)}


def build(root, timeout):
    """Build a lake project. Returns (ok, transcript_tail)."""
    manifest = pathlib.Path(root) / "lake-manifest.json"
    uses_mathlib = manifest.exists() and "mathlib" in manifest.read_text()
    if uses_mathlib:
        run(["lake", "exe", "cache", "get"], cwd=root, check=False, timeout=timeout)
    proc = run(["lake", "build"], cwd=root, check=False, timeout=timeout)
    tail = (proc.stdout + proc.stderr)[-4000:]
    return proc.returncode == 0, tail


def check_bare_file(path, timeout):
    """Elaborate a single file against this repository's toolchain.

    Substitution, not verification: the file's own project, if it has one, is not
    what runs here. The caller labels the result accordingly.
    """
    proc = run(["lake", "env", "lean", str(path)], cwd=ROOT, check=False,
               timeout=timeout)
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-4000:]


# ----------------------------------------------------------------------------- probe


def find_declarations(root):
    """Best-effort scan for theorem names, used when --theorem is not given."""
    names = []
    pattern = re.compile(r"^(?:@\[[^\]]*\]\s*)*(?:theorem|lemma)\s+([\w.«»]+)",
                         re.MULTILINE)
    for path in sorted(pathlib.Path(root).rglob("*.lean")):
        if ".lake" in path.parts:
            continue
        code = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        names.extend(pattern.findall(code))
    return names


def module_names(root):
    """Modules a probe file can import, from the project's own tree."""
    out = []
    for path in sorted(pathlib.Path(root).rglob("*.lean")):
        if ".lake" in path.parts or path.name in ("lakefile.lean",):
            continue
        out.append(".".join(path.relative_to(root).with_suffix("").parts))
    return out


def namespaces_in(root):
    """Namespaces the project opens, so a short declaration name resolves.

    `#print axioms erdos_750_FC` fails when the declaration is really
    `Erdos750.erdos_750_FC`; the probe has to open the namespace or name it
    in full. A reviewer reads short names off the source, so open them.
    """
    found = []
    for path in sorted(pathlib.Path(root).rglob("*.lean")):
        if ".lake" in path.parts:
            continue
        code = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        found.extend(re.findall(r"^namespace\s+([\w.«»]+)", code, re.MULTILINE))
    return list(dict.fromkeys(found))


def run_probe(root, imports, theorems, timeout, opens=()):
    body = "\n".join(f"#print axioms {t}" for t in theorems)
    text = ("\n".join(f"import {m}" for m in imports)
            + ("\n" + "\n".join(f"open {n}" for n in opens) if opens else "")
            + f"\n\n{body}\n")
    probe_file = pathlib.Path(root) / "VerifyProbe.lean"
    probe_file.write_text(text, encoding="utf-8")
    try:
        proc = run(["lake", "env", "lean", "VerifyProbe.lean"], cwd=root,
                   check=False, timeout=timeout)
    finally:
        probe_file.unlink(missing_ok=True)
    return parse_axioms(proc.stdout + proc.stderr, theorems)


def probe(root, theorems, timeout):
    """Run `#print axioms` on each target inside the project's own toolchain.

    Importing every module at once is the cheap path, but a comparator-shaped
    repository declares the same theorem in both its Challenge and its
    Solution, and importing both is a name clash. When the joint probe leaves
    targets unresolved, retry per module, and prefer a sorry-free resolution
    over a sorried one: the sorried Challenge restatement and the proved
    Solution genuinely both exist, and the reviewer's question is whether a
    proof exists at all.
    """
    modules = module_names(root)
    opens = namespaces_in(root)
    results = run_probe(root, modules, theorems, timeout, opens)
    unresolved = [t for t, r in results.items()
                  if "error" in r or not r.get("sorry_free", False)]
    if unresolved:
        for mod in modules:
            partial = run_probe(root, [mod], unresolved, timeout, opens)
            for t, r in partial.items():
                if "error" in r:
                    continue
                best = results.get(t, {})
                if "error" in best or (
                        r.get("sorry_free") and not best.get("sorry_free")):
                    results[t] = dict(r, module=mod)
            unresolved = [t for t in unresolved
                          if "error" in results.get(t, {"error": 1})
                          or not results[t].get("sorry_free", False)]
            if not unresolved:
                break
    return results


def parse_axioms(output, theorems):
    """Parse `'name' depends on axioms: [...]` lines into a verdict per theorem."""
    results = {}
    for t in theorems:
        short = t.rsplit(".", 1)[-1]
        m = re.search(
            rf"'([\w.«»]*{re.escape(short)})' depends on axioms: \[([^\]]*)\]",
            output)
        if not m:
            if re.search(rf"'[\w.«»]*{re.escape(short)}' does not depend on any axioms",
                         output):
                results[t] = {"axioms": [], "sorry_free": True, "extra": []}
            else:
                results[t] = {"error": "no #print axioms output found"}
            continue
        axioms = [a.strip() for a in m.group(2).split(",") if a.strip()]
        results[t] = {
            "axioms": axioms,
            "sorry_free": "sorryAx" not in axioms,
            "extra": sorted(set(axioms) - STANDARD_AXIOMS - {"sorryAx"}),
        }
    return results


# ---------------------------------------------------------------------------- driver


def verify(link, theorems, static_only, build_timeout):
    report = {"link": link, "stages": {}}
    try:
        plan = resolve(link)
        report["stages"]["resolve"] = {"ok": True, "kind": plan["kind"]}
    except ValueError as e:
        report["stages"]["resolve"] = {"ok": False, "error": str(e)}
        return report

    tmp = tempfile.mkdtemp(prefix="fc-verify-")
    try:
        try:
            root = materialise(plan, tmp)
            report["stages"]["materialise"] = {"ok": True}
        except Exception as e:  # noqa: BLE001 - report, do not crash the batch
            report["stages"]["materialise"] = {"ok": False, "error": str(e)[:500]}
            return report

        shape = detect_project(root)
        report["project"] = shape
        report["stages"]["static"] = static_audit(root)
        # A link that names a file is a claim about that file. Auditing the
        # whole clone and reporting one number buries it: a link into a
        # multi-problem repository reported 89 `sorry` from other people's
        # unrelated problems while the cited file had none. Scope it.
        if plan.get("file"):
            named = pathlib.Path(root) / plan["file"]
            if named.is_file():
                report["stages"]["static_named_file"] = dict(
                    static_audit_file(named, root), file=plan["file"])

        if static_only:
            return report

        if shape["lakefile"]:
            ok, tail = build(root, build_timeout)
            report["stages"]["build"] = {"ok": ok, "tail": tail if not ok else ""}
            if ok:
                targets = theorems or find_declarations(root)
                if targets:
                    report["stages"]["probe"] = probe(root, targets, build_timeout)
        else:
            # No lakefile: elaborate each file against this repo's toolchain and
            # say so, because that is a substitution.
            files = sorted(p for p in pathlib.Path(root).glob("*.lean"))
            results = {}
            for f in files:
                ok, tail = check_bare_file(f, build_timeout)
                results[f.name] = {"ok": ok, "tail": tail if not ok else ""}
            report["stages"]["build"] = {
                "ok": all(r["ok"] for r in results.values()),
                "toolchain_substituted": True,
                "files": results,
            }
        return report
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def summarise(report):
    """One paragraph a reviewer can paste into a PR comment."""
    lines = [f"verify_formal_proof: {report['link']}"]
    stages = report["stages"]
    if not stages.get("resolve", {}).get("ok"):
        return lines[0] + f"\n  UNRESOLVED: {stages['resolve']['error']}"
    if not stages.get("materialise", {}).get("ok"):
        return lines[0] + f"\n  FETCH FAILED: {stages['materialise']['error']}"
    named = stages.get("static_named_file")
    if named:
        lines.append(
            f"  the file this link names: {named['file']}"
            f"\n    sorry={named['sorry']} axiom={named['axiom']} "
            f"native_decide={named['native_decide']}"
        )
    st = stages["static"]
    label = "  rest of the clone, for context: " if named else "  static: "
    lines.append(
        f"{label}{st['files']} lean files, "
        f"{sum(st['sorry'].values())} sorry, "
        f"{sum(st['axiom'].values())} axiom decls, "
        f"{sum(st['native_decide'].values())} native_decide"
    )
    if named:
        lines.append("    a repository may hold unrelated work; these counts "
                     "are not about the cited file")
    for key in ("sorry", "axiom", "native_decide"):
        for rel, n in st[key].items():
            lines.append(f"    {key} x{n}  {rel}")
    b = stages.get("build")
    if b is None:
        lines.append("  build: skipped (--static-only)")
    else:
        note = " (against this repo's toolchain, not the project's own)" \
            if b.get("toolchain_substituted") else ""
        lines.append(f"  build: {'ok' if b['ok'] else 'FAILED'}{note}")
        if not b["ok"] and b.get("tail"):
            lines.append("    " + b["tail"].strip().splitlines()[-1])
    for t, r in stages.get("probe", {}).items():
        if "error" in r:
            lines.append(f"  probe {t}: {r['error']}")
        else:
            verdict = "sorry-free" if r["sorry_free"] else "DEPENDS ON sorryAx"
            extra = f", extra axioms: {r['extra']}" if r["extra"] else ""
            lines.append(f"  probe {t}: {verdict}{extra}")
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", type=pathlib.Path,
                    help=".lean files whose formal_proof links to verify")
    ap.add_argument("--link", action="append", default=[],
                    help="verify this link directly (repeatable)")
    ap.add_argument("--theorem", action="append", default=[],
                    help="declaration to probe (repeatable; default: scan)")
    ap.add_argument("--static-only", action="store_true",
                    help="stop after the grep audit; no clone build")
    ap.add_argument("--build-timeout", type=int, default=3600)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    links = list(args.link)
    for path in args.files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in LINK_IN_SOURCE.finditer(text):
            if m.group(1).startswith("http"):
                links.append(m.group(1))
    if not links:
        ap.error("nothing to verify: give --link or files containing formal_proof links")

    reports = [verify(link, args.theorem, args.static_only, args.build_timeout)
               for link in links]
    if args.as_json:
        print(json.dumps(reports, indent=2))
    else:
        for r in reports:
            print(summarise(r))

    bad = any(
        not r["stages"].get("resolve", {}).get("ok")
        or not r["stages"].get("materialise", {}).get("ok", True)
        or (r["stages"].get("build") or {}).get("ok") is False
        or any("error" in p or not p.get("sorry_free", True)
               for p in r["stages"].get("probe", {}).values())
        for r in reports
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
