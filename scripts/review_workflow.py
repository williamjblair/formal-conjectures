#!/usr/bin/env python3
"""Opt-in Actions review pilot. Trusted controller; project code runs only in Docker."""
import argparse
import json
import os
import re
import resource
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import review_report as rr
from conjectures.execution import container_args, isolated, execute, build_targets, model_review

MARKER = "<!-- fc-advisory-review -->"
MAX_CALLS = 20
MAX_SECONDS = 420


def api(path, data=None, method=None):
    request = urllib.request.Request(
        "https://api.github.com/" + path,
        data=rr.encode(data) if data is not None else None,
        method=method,
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, timeout=120, **kwargs).stdout


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rr.encode(value))


def emit(**values):
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in values.items():
            rr.require("\n" not in str(value), "invalid workflow output")
            output.write(f"{key}={value}\n")


def authorize(event, permission):
    rr.require(
        event.get("action") == "created" and event["comment"]["body"].strip() == "/review",
        "expected an exact /review comment",
    )
    rr.require("pull_request" in event["issue"], "review requires a pull request")
    rr.require(permission in ("admin", "maintain", "write"), "review requires write permission")


def prepare(root):
    event = rr.read_json(Path(os.environ["GITHUB_EVENT_PATH"]))
    repo = os.environ["GITHUB_REPOSITORY"]
    permission = api(f"repos/{repo}/collaborators/{event['comment']['user']['login']}/permission")
    authorize(event, permission["permission"])
    number = event["issue"]["number"]
    pr = api(f"repos/{repo}/pulls/{number}")
    rr.require(pr["state"] == "open", "PR is closed")
    for sha in (pr["head"]["sha"], pr["base"]["sha"]):
        rr.require(re.fullmatch("[0-9a-f]{40}", sha), "invalid GitHub commit")
    checkout = root / "checkout"
    run("git", "init", str(checkout))
    remote = f"https://github.com/{repo}.git"
    run(
        "git",
        "-C",
        str(checkout),
        "fetch",
        "--no-tags",
        remote,
        f"+refs/pull/{number}/head:refs/review/head",
        pr["base"]["sha"],
    )
    run("git", "-C", str(checkout), "checkout", "--detach", "refs/review/head")
    rr.require(
        rr.git(checkout, "rev-parse", "HEAD").decode().strip() == pr["head"]["sha"],
        "PR changed during preparation",
    )
    sources = root / "sources"
    sources.mkdir()
    files = rr.prepare(
        checkout, repo, pr["base"]["sha"], Path(".agents/skills/formal-conjectures-review"), sources, []
    )
    rr.write_directory(root / "input", files)
    ticket = {
        "repository": repo,
        "pr": number,
        "comment_id": event["comment"]["id"],
        "head": pr["head"]["sha"],
        "base": pr["base"]["sha"],
        "request_id": json.loads(files["request.json"])["id"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "tooling": os.environ["GITHUB_SHA"],
    }
    write(root / "input/ticket.json", ticket)
    emit(ticket_sha256=rr.digest(rr.encode(ticket)), pr=number)












def review(root):
    request, _ = rr.load_request(root / "input")
    ticket = rr.read_json(root / "input/ticket.json")
    rr.require(rr.digest(rr.encode(ticket)) == os.environ["TICKET_SHA256"], "request ticket mismatch")
    image = os.environ["REVIEW_IMAGE"]
    run("docker", "pull", image)
    snapshot = root / "snapshot"
    rr.restore(root / "input", snapshot)
    targets = build_targets(request["scope"], snapshot)
    # Reject dependency drift before any project code runs.
    for name in ("lean-toolchain", "lake-manifest.json", "lakefile.toml"):
        expected = run(
            "docker", "run", "--rm", "--network=none", "--entrypoint=cat", image, "/opt/review-cache/" + name
        )
        rr.require((snapshot / name).read_bytes() == expected, "review image environment mismatch: " + name)
    evidence = root / "evidence/evidence"
    evidence.mkdir(parents=True)
    build = isolated(image, snapshot)
    try:
        receipt = execute(build, ["lake", "--wfail", "build", *targets], 180)
    finally:
        run("docker", "rm", "-f", build)
    receipt.update(
        {
            "request_id": request["id"],
            "image": image,
            "ticket": ticket,
            "policy": "scoped-build.v1",
            "targets": targets,
        }
    )
    write(evidence / "build.json", receipt)
    # The model receives a different scratch container after the build container is destroyed.
    procedure = snapshot / "procedure"
    procedure.mkdir()
    for item in request["procedure"]:
        p = snapshot / item["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(rr.read_artifact(root / "input", item["path"]))
    scratch = isolated(image, snapshot)
    try:
        result = model_review(request, scratch, evidence, os.environ["REVIEW_MODEL"])
    finally:
        run("docker", "rm", "-f", scratch)
    rr.require(
        result["coverage"]["source-fidelity"] == "incomplete",
        "cited sources were not supplied; source-fidelity coverage must remain incomplete",
    )
    write(root / "review.json", result)
    status = (
        "pass"
        if receipt["exit_code"] == 0
        else (
            "error"
            if receipt["exit_code"] in (None, 124, 125, 126, 127, 137) or receipt["exit_code"] < 0
            else "fail"
        )
    )
    manifest = {
        "request_id": request["id"],
        "artifacts": rr.descriptors(rr.collect(evidence, "evidence")),
        "checks": [
            {
                "kind": "build",
                "status": status,
                "producer": f"actions/{ticket['run_id']}/attempts/{ticket['attempt']}",
                "policy": "scoped-build.v1",
                "detail": "Independent isolated build; no proof verification.",
                "evidence": ["evidence/build.json"],
            }
        ],
    }
    write(root / "evidence/checks.json", manifest)
    rr.write_directory(
        root / "bundle", rr.assemble(root / "input", root / "input", root / "review.json", root / "evidence")
    )
    write(root / "bundle/ticket.json", ticket)
    emit(bundle_sha256=rr.digest((root / "bundle/report.json").read_bytes()))


def freshness(ticket, pr, tooling):
    return (
        "current"
        if (
            pr["state"] == "open"
            and pr["head"]["sha"] == ticket["head"]
            and pr["base"]["sha"] == ticket["base"]
            and tooling == ticket["tooling"]
        )
        else "STALE"
    )


def publish(root):
    ticket = rr.read_json(root / "ticket.json")
    rr.require(rr.digest(rr.encode(ticket)) == os.environ["TICKET_SHA256"], "publisher ticket mismatch")
    rr.require(
        ticket["run_id"] == os.environ["GITHUB_RUN_ID"]
        and ticket["attempt"] == os.environ["GITHUB_RUN_ATTEMPT"]
        and ticket["repository"] == os.environ["GITHUB_REPOSITORY"],
        "wrong producer run",
    )
    report = rr.read_json(root / "report.json")
    rr.require(
        rr.digest((root / "report.json").read_bytes()) == os.environ["BUNDLE_SHA256"],
        "publisher report mismatch",
    )
    rebuilt = rr.assemble(root, root, root / "review.json", root)
    rr.require(rebuilt["report.json"] == (root / "report.json").read_bytes(), "bundle failed reconstruction")
    rr.require(report["request"]["id"] == ticket["request_id"], "bundle request mismatch")
    repo, number = ticket["repository"], ticket["pr"]
    pr = api(f"repos/{repo}/pulls/{number}")
    default = api(f"repos/{repo}")["default_branch"]
    tip = api(f"repos/{repo}/commits/{default}")["sha"]
    state = freshness(ticket, pr, tip)
    url = f'https://github.com/{repo}/actions/runs/{ticket["run_id"]}/attempts/{ticket["attempt"]}'
    body = (
        f'{MARKER}\n## Advisory FC review\n\n**{state}** — reviewed `{ticket["head"]}`. '
        "Freshness is checked at publication; compare the commit before relying on this report.\n\n"
        f'**{report["semantic_verdict"]}**; coverage {report["completeness"]}. '
        "Maintainers decide acceptance.\n\n"
    )
    for finding in report["review"]["findings"][:20]:
        body += f"- {rr.escape(finding['severity'])}: {rr.escape(finding['file'])}:{finding['line']} — {rr.escape(finding['message'][:1500])}\n"
    body += (
        f"\n[Full JSON, Markdown and evidence bundle]({url}) in the `review-bundle-"
        f'{ticket["attempt"]}` artifact. Retained for 30 days; no durable archive. '
        "Build evidence is separate from semantic review; no proof verification runs in this pilot.\n"
    )
    comments = []
    for page in range(1, 101):
        batch = api(f"repos/{repo}/issues/{number}/comments?per_page=100&page={page}")
        comments += batch
        if len(batch) < 100:
            break
    else:
        raise ValueError("comment pagination limit exceeded")
    existing = [
        c for c in comments if c["user"]["login"] == "github-actions[bot]" and c["body"].startswith(MARKER)
    ]
    rr.require(len(existing) <= 1, "multiple review comments require reconciliation")
    if existing:
        order = re.search(r"<!-- fc-review-order: (\d+) (\d+) -->", existing[0]["body"])
        if order and tuple(map(int, order.groups())) > (int(ticket["comment_id"]), int(ticket["attempt"])):
            return  # An older rerun cannot replace a newer request's review.
        api(f"repos/{repo}/issues/comments/{existing[0]['id']}", {"body": body}, "PATCH")
    else:
        api(f"repos/{repo}/issues/{number}/comments", {"body": body})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "review", "publish"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    globals()[args.command](args.root.resolve())
