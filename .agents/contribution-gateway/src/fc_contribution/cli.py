from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import SCHEMA_VERSION, bind_advisory_review, build_packet, check_manifest, sha256_bytes


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise SystemExit("manifest must be a JSON object")
    return value


def _write(path: str, value: dict) -> None:
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def cmd_init(args: argparse.Namespace) -> int:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "authority": {
            "repository": args.repository,
            "revision": args.revision,
            "target": args.target,
        },
        "producer": {"name": args.producer, "type": args.producer_type},
        "contribution": {
            "kind": args.kind,
            "relationship": args.relationship,
            "artifact": args.artifact,
        },
        "gates": {
            name: {"status": "unresolved", "evidence": []}
            for name in (
                "mechanical_validity",
                "semantic_fidelity",
                "resolution_validity",
                "priority",
                "provenance",
                "dependency_impact",
            )
        },
    }
    _write(args.out, manifest)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    result = check_manifest(_load(args.manifest), args.root)
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 2


def cmd_packet(args: argparse.Namespace) -> int:
    manifest = _load(args.manifest)
    packet = build_packet(manifest, args.root)
    _write(args.out, packet)
    print(packet["recommendation"])
    return 0 if packet["checks"]["ok"] else 2


def cmd_bind_review(args: argparse.Namespace) -> int:
    manifest = _load(args.manifest)
    review_path = Path(args.root) / args.review
    review = _load(str(review_path))
    digest = sha256_bytes(review_path.read_bytes())
    try:
        updated = bind_advisory_review(
            manifest,
            args.gate,
            review,
            evidence_path=args.review,
            evidence_sha256=digest,
            replace=args.replace,
        )
    except ValueError as exc:
        print(str(exc))
        return 2
    _write(args.out or args.manifest, updated)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fc-contribution",
        description="Build evidence-gated contribution packets for Formal Conjectures.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create an unresolved Contribution v0 manifest")
    p_init.add_argument("--repository", required=True)
    p_init.add_argument("--revision", required=True)
    p_init.add_argument("--target", required=True)
    p_init.add_argument("--artifact", required=True)
    p_init.add_argument("--producer", required=True)
    p_init.add_argument("--producer-type", default="agent")
    p_init.add_argument("--kind", default="formal_proof")
    p_init.add_argument("--relationship", default="claims_to_resolve")
    p_init.add_argument("--out", default="contribution.json")
    p_init.set_defaults(func=cmd_init)

    p_check = sub.add_parser("check", help="validate structure and evidence bindings")
    p_check.add_argument("manifest")
    p_check.add_argument("--root", default=".")
    p_check.set_defaults(func=cmd_check)

    p_packet = sub.add_parser("packet", help="emit a content-addressed acceptance packet")
    p_packet.add_argument("manifest")
    p_packet.add_argument("--root", default=".")
    p_packet.add_argument("--out", default="contribution-packet.json")
    p_packet.set_defaults(func=cmd_packet)

    p_bind = sub.add_parser("bind-review", help="bind an independent fc-review-bot result to a semantic gate")
    p_bind.add_argument("manifest")
    p_bind.add_argument(
        "--gate",
        required=True,
        choices=["semantic_fidelity", "resolution_validity", "priority", "provenance"],
    )
    p_bind.add_argument("--review", required=True, help="review JSON path relative to --root")
    p_bind.add_argument("--root", default=".")
    p_bind.add_argument("--out")
    p_bind.add_argument("--replace", action="store_true")
    p_bind.set_defaults(func=cmd_bind_review)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
