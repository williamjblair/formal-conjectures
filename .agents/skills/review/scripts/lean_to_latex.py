#!/usr/bin/env python3
"""Render a Lean file as LaTeX a mathematician can read.

This is a reading aid, not a translator. Reviewing a multi-thousand-line
generated proof means finding its skeleton: which statements it claims, which
intermediate facts each proof establishes, in what order. That structure is
syntactically visible in Lean (`have`, `suffices`, `show`, `calc`, `obtain`),
and this script lifts it out and typesets it next to the docstrings, with the
full Lean source in verbatim blocks below. What it does NOT do is translate
Lean terms into faithful mathematical notation; the token-level mapping it
applies to statements is best-effort and every rendered statement sits beside
the verbatim original so the reader never has to trust the rendering.

Usage:
  python lean_to_latex.py FILE.lean [-o OUT.tex] [--fragment]

`--fragment` emits only the body, for inclusion in a larger document.

Docstrings pass through as the LaTeX they already contain, so a docstring
whose own LaTeX is broken breaks the document at that spot: compile with
`-interaction=nonstopmode` and read the log, because the error is a finding
about the file, not about this script. `ErdosProblems/92.lean`'s `\\mathbb^2`
surfaced exactly this way.
"""

import argparse
import pathlib
import re
import sys

# Token-level Lean-to-LaTeX map for statement text. Order matters: longer
# tokens first, so `↔` does not decompose and `∑'` beats `∑`.
TOKEN_MAP = [
    ("∑'", r"\sum'"), ("∏'", r"\prod'"),
    ("∀ᶠ", r"\forall^{\mathrm{ev}}"), ("∃ᶠ", r"\exists^{\mathrm{freq}}"),
    ("∀ᵉ", r"\forall"), ("∀", r"\forall"), ("∃!", r"\exists!"),
    ("∃", r"\exists"), ("∑", r"\sum"), ("∏", r"\prod"),
    ("ℕ", r"\mathbb{N}"), ("ℤ", r"\mathbb{Z}"), ("ℚ", r"\mathbb{Q}"),
    ("ℝ", r"\mathbb{R}"), ("ℂ", r"\mathbb{C}"),
    ("≤", r"\le"), ("≥", r"\ge"), ("≠", r"\ne"), ("≡", r"\equiv"),
    ("∈", r"\in"), ("∉", r"\notin"), ("⊆", r"\subseteq"), ("⊂", r"\subset"),
    ("∪", r"\cup"), ("∩", r"\cap"), ("∅", r"\emptyset"),
    ("∧", r"\wedge"), ("∨", r"\vee"), ("¬", r"\neg"),
    ("↔", r"\iff"), ("→", r"\to"), ("↦", r"\mapsto"),
    ("∣", r"\mid"), ("∘", r"\circ"), ("⁻¹", r"^{-1}"),
    ("√", r"\sqrt{}"), ("×", r"\times"), ("⊤", r"\top"), ("⊥", r"\bot"),
    ("α", r"\alpha"), ("β", r"\beta"), ("γ", r"\gamma"), ("ε", r"\varepsilon"),
    ("σ", r"\sigma"), ("ω", r"\omega"), ("π", r"\pi"), ("ι", r"\iota"),
    ("≫", r"\gg"), ("≪", r"\ll"), ("↑", r"\uparrow "), ("𝓝", r"\mathcal{N}"),
    ("⟨", r"\langle "), ("⟩", r"\rangle "), ("⌈", r"\lceil "), ("⌉", r"\rceil "),
]

PROOF_STEP = re.compile(
    r"^\s*(have|suffices|show|obtain|refine|calc|induction|rcases|intro|use|exact)\b(.*)")

DECL = re.compile(
    r"^(?:noncomputable\s+)?(?:private\s+)?"
    r"(theorem|lemma|def|abbrev|structure|inductive|instance)\s+([\w.«»]+)")


def strip_license(text):
    return re.sub(r"\A/-\n?Copyright.*?-/\s*", "", text, flags=re.DOTALL)


def tex_escape(text):
    for ch, repl in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                     ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
                     ("^", r"\^{}"), ("~", r"\~{}")):
        text = text.replace(ch, repl)
    return text


def tokens_to_math(lean):
    """Best-effort token map into math mode. Flagged as such wherever shown."""
    out = lean
    for tok, repl in TOKEN_MAP:
        out = out.replace(tok, f" {repl} ")
    out = re.sub(r"\s+", " ", out).strip()
    # Identifiers become upright text so `Summable` does not typeset as a
    # product of six variables.
    out = re.sub(r"(?<![\\{])\b([A-Za-z][\w.']{2,})\b",
                 lambda m: r"\text{" + m.group(1).replace("_", r"\_") + "}", out)
    # A bare underscore left over is a tactic placeholder (`?_`, `⟨_, _⟩`),
    # which in math mode is a subscript with nothing to attach to.
    return re.sub(r"(?<!\\)_", r"\\_", out)


def docstring_to_tex(doc):
    """FC docstrings already carry $...$ LaTeX; convert the markdown residue.

    Prose outside the `$...$` segments gets its LaTeX-active characters
    escaped; the math segments pass through untouched. Reference lists write
    titles as `_italics_`, and a bare underscore in text mode is what broke
    the first compiled document.
    """
    doc = re.sub(r"\A/--\s*|\A/-!\s*|-/\s*\Z", "", doc.strip(), flags=re.DOTALL)
    doc = re.sub(r"`([^`]+)`", lambda m: r"\texttt{" + tex_escape(m.group(1)) + "}", doc)
    doc = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", doc)
    doc = re.sub(r"(?<![\w\\])_([^_\n]+)_(?!\w)", r"\\emph{\1}", doc)
    doc = re.sub(r"^\s*#+\s*(.+)$", r"\\subsection*{\1}", doc, flags=re.MULTILINE)
    doc = re.sub(r"^\s*[-*]\s+", r"\\item ", doc, flags=re.MULTILINE)
    if r"\item" in doc:
        doc = re.sub(r"((?:\\item .*\n?)+)",
                     lambda m: "\\begin{itemize}\n" + m.group(1) + "\\end{itemize}\n",
                     doc)
    # Escape active characters in the prose only: even-indexed segments of a
    # split on $ are outside math. Commands already emitted above are shielded
    # by never escaping a backslash-prefixed token.
    parts = doc.split("$")
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?<!\\)([_#%&])", r"\\\1", parts[i])
    return "$".join(parts)


def split_declarations(body):
    """Yield (docstring, attribute, header, statement, proof) per declaration.

    Line-oriented and comment-depth-aware, since Lean block comments nest and
    docstrings contain blank lines.
    """
    lines = body.split("\n")
    i, n, out = 0, len(lines), []
    depth = 0
    pending_doc, pending_attr = "", ""
    while i < n:
        line = lines[i]
        if depth == 0 and line.lstrip().startswith("/-"):
            start = i
            while i < n:
                depth += lines[i].count("/-") - lines[i].count("-/")
                i += 1
                if depth == 0:
                    break
            pending_doc = "\n".join(lines[start:i])
            continue
        if depth == 0 and line.lstrip().startswith("@["):
            start = i
            while i < n and "]" not in lines[i]:
                i += 1
            pending_attr = "\n".join(lines[start:i + 1])
            i += 1
            continue
        m = DECL.match(line)
        if m and depth == 0:
            start = i
            i += 1
            while i < n and (lines[i].startswith((" ", "\t")) or lines[i].strip() == ""):
                if lines[i].strip() == "" and i + 1 < n and \
                        not lines[i + 1].startswith((" ", "\t")):
                    break
                i += 1
            block = "\n".join(lines[start:i]).rstrip()
            proof = ""
            split = re.search(r":=\s*by\b", block)
            if split:
                statement, proof = block[:split.start()], block[split.end():]
            else:
                eq = re.search(r":=", block)
                statement = block[:eq.start()] if eq else block
                proof = block[eq.end():] if eq else ""
            out.append({
                "kind": m.group(1), "name": m.group(2),
                "doc": pending_doc, "attr": pending_attr,
                "statement": statement.strip(), "proof": proof.strip(),
                "lean": ((pending_doc + "\n") if pending_doc else "")
                        + ((pending_attr + "\n") if pending_attr else "") + block,
            })
            pending_doc, pending_attr = "", ""
            continue
        i += 1
    return out


def skeleton(proof):
    """The proof's stated intermediate facts, in order. Empty for `sorry`."""
    steps = []
    for line in proof.split("\n"):
        m = PROOF_STEP.match(line)
        if m:
            steps.append((m.group(1), m.group(2).strip().rstrip(":= by").strip()))
    return steps


def render(path, fragment):
    text = strip_license(path.read_text(encoding="utf-8"))
    module_doc = ""
    m = re.search(r"/-!(.*?)-/", text, flags=re.DOTALL)
    if m:
        module_doc = docstring_to_tex(m.group(0))
        text = text.replace(m.group(0), "", 1)
    decls = split_declarations(text)

    out = []
    if not fragment:
        out.append("\n".join([
            r"\documentclass{article}",
            r"\usepackage{amsmath,amssymb,amsthm,listings,xcolor,geometry}",
            r"\geometry{margin=1in}",
            r"\lstset{basicstyle=\ttfamily\small,breaklines=true,"
            r"literate={∀}{{$\forall$}}1 {∃}{{$\exists$}}1 {ℕ}{{$\mathbb{N}$}}1"
            r" {ℝ}{{$\mathbb{R}$}}1 {ℚ}{{$\mathbb{Q}$}}1 {ℤ}{{$\mathbb{Z}$}}1"
            r" {≤}{{$\le$}}1 {≥}{{$\ge$}}1 {≠}{{$\ne$}}1 {∈}{{$\in$}}1"
            r" {↔}{{$\iff$}}1 {→}{{$\to$}}1 {∧}{{$\wedge$}}1 {¬}{{$\neg$}}1"
            r" {∑}{{$\sum$}}1 {∣}{{$\mid$}}1 {ᶠ}{{}}1 {'}{{'}}1}",
            r"\newtheorem{statement}{Statement}",
            r"\begin{document}",
            rf"\title{{\texttt{{{tex_escape(path.name)}}}}}",
            r"\date{}",
            r"\maketitle",
        ]))
    if module_doc:
        out.append(module_doc)

    for d in decls:
        out.append(rf"\section*{{\texttt{{{tex_escape(d['name'])}}} "
                   rf"({tex_escape(d['kind'])})}}")
        if d["attr"]:
            out.append(rf"\noindent\texttt{{{tex_escape(d['attr'])}}}\par")
        if d["doc"]:
            out.append(docstring_to_tex(d["doc"]))
        out.append(r"\begin{statement}\ (best-effort rendering; the Lean below "
                   r"is the authority)")
        out.append(r"\[ " + tokens_to_math(d["statement"]) + r" \]")
        out.append(r"\end{statement}")
        steps = skeleton(d["proof"])
        if steps:
            out.append(r"\paragraph{Proof skeleton.}")
            out.append(r"\begin{enumerate}")
            for kind, stated in steps:
                shown = tokens_to_math(stated) if stated else ""
                out.append(rf"\item \textsf{{{kind}}}" +
                           (rf": ${shown}$" if shown else ""))
            out.append(r"\end{enumerate}")
        elif d["proof"].strip() == "sorry":
            out.append(r"\paragraph{Proof.} \texttt{sorry} (open in this file).")
        out.append(r"\begin{lstlisting}")
        out.append(d["lean"])
        out.append(r"\end{lstlisting}")

    if not fragment:
        out.append(r"\end{document}")
    return "\n\n".join(out) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=pathlib.Path)
    ap.add_argument("-o", "--out", type=pathlib.Path)
    ap.add_argument("--fragment", action="store_true")
    args = ap.parse_args(argv)
    tex = render(args.file, args.fragment)
    if args.out:
        args.out.write_text(tex, encoding="utf-8")
        print(args.out)
    else:
        sys.stdout.write(tex)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
