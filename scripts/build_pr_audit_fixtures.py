#!/usr/bin/env python3
# Copyright 2026 The Formal Conjectures Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Rebuild the retained PR-audit v1 fixtures from their frozen identities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from capture_missing_tool_invocation import capture_missing_tool_invocation
from pr_audit import (
    content_root,
    generate_core,
    generate_observation,
    git_blob_oid,
    render_markdown,
    sha256_digest,
    write_canonical,
)


REPO = Path(__file__).resolve().parent.parent
PACKET = REPO / "audit" / "pr-audit-v1"
FIXTURES = PACKET / "fixtures"
BASELINE = {
    "commit_oid": "c9052e8577118ed0ada54462bd4ef1f3beff37d6",
    "tree_oid": "864ee77ee26a7cbd85b30558f8d9d2036f8717ed",
}
BUILD_WORKFLOW_IDENTITIES = {
    "fidelity-erdos-887-1237": {
        "git_blob_oid": "9b972a49fe75ece90ea984cf879d019d75d0b537",
        "sha256": "sha256:9654c8eff1eb84976e26b527f7dadc8c70267c9ed70fb9300e9e3fe8c2913202",
    },
    "unavailable-rupert-3959": {
        "git_blob_oid": "d621cc1d9221102d360b257e7add45234fd19701",
        "sha256": "sha256:8841d7fe334bc84abe5d72ae923be08510e5bf661edfc4e15ed135abffaac39c",
    },
}
REVIEW_GUIDE_ROOT = "sha256:bc10a92b25047a46225221c7ecb090a5b3e9ac174fd44f6d1f6042d7c6971700"
REVIEW_GUIDE_REVISION = "70e8ddfdb5095873e0fbb45447d3649d5412ff3a"
REVIEW_GUIDE_BLOB_OID = "de2bf123d126cd1803c1b47866b776420eda2f6b"
GRAPHQL_OPERATION = """query PullRequestAuditObservation($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){number url state isDraft mergeStateStatus reviewDecision updatedAt baseRefOid headRefOid reviews(first:100){nodes{id author{login} state submittedAt commit{oid}} pageInfo{hasNextPage endCursor}}}}}"""
CORE_GRAPHQL_OPERATION = """query PullRequestAuditCoreSnapshot($owner:String!,$name:String!,$number:Int!,$baseOid:GitObjectID!,$headOid:GitObjectID!,$baseExpression:String!,$headExpression:String!){repository(owner:$owner,name:$name){pullRequest(number:$number){number url baseRefOid headRefOid files(first:100){nodes{path changeType} pageInfo{hasNextPage endCursor}}} baseCommit:object(oid:$baseOid){... on Commit{oid tree{oid}}} headCommit:object(oid:$headOid){... on Commit{oid tree{oid}}} baseBlob:object(expression:$baseExpression){... on Blob{oid byteSize isBinary text}} headBlob:object(expression:$headExpression){... on Blob{oid byteSize isBinary text}}}}"""
CORE_ACQUIRED_AT = "2026-08-12T20:18:00Z"
OBSERVATION_RECEIPTS = {
    "fork-dogfood-erdos-430-2": {"acquired_at": "2026-08-18T18:20:00Z", "request_id": "not-retained"},
    "external-fork-erdos-430-7": {"acquired_at": "2026-08-18T17:10:00Z", "request_id": "not-retained"},
    "clean-source-faithful-min-modulus-4829": {"acquired_at": "2026-08-13T11:50:00Z", "request_id": "not-retained"},
    "conditional-erdos-427-4884": {"acquired_at": "2026-08-12T20:25:19Z", "request_id": "F0D9:4757A:17F52D1:51A205C:6A7CD6AF"},
    "fidelity-erdos-887-1237": {"acquired_at": "2026-08-12T20:25:21Z", "request_id": "DCB0:F4954:1718059:4EB15DF:6A7CD6B0"},
    "vacuity-erdos-80-4830": {"acquired_at": "2026-08-12T20:25:22Z", "request_id": "C5A9:3F5EEC:15B9084:4A06857:6A7CD6B2"},
    "unavailable-rupert-3959": {"acquired_at": "2026-08-12T20:25:24Z", "request_id": "BB68:146BF1:14E3716:479FD03:6A7CD6B3"},
}


def implementation(name: str, kind: str, locator: str, root: str) -> dict[str, str]:
    return {"name": name, "version": "1", "kind": kind, "locator": locator, "root": root}


def check_input(identifier: str, artifact_id: str, kind: str, locator: str, root: str) -> dict[str, str]:
    return {"id": identifier, "artifact_id": artifact_id, "kind": kind, "locator": locator, "root": root}


def evidence(kind: str, locator: str, root: str, statement: str, witness: str = "") -> dict[str, str]:
    return {"kind": kind, "locator": locator, "sha256": root, "statement": statement, "witness": witness}


def condition(declaration: str, statement: str, locator: str) -> dict[str, str]:
    return {"declaration": declaration, "statement": statement, "locator": locator}


def base_check(
    *,
    identifier: str,
    kind: str,
    mode: str,
    property_name: str,
    role: str,
    outcome: str,
    severity: str,
    path: str,
    declarations: list[str],
    implementation_value: dict[str, str],
    inputs: list[dict[str, str]],
    evidence_values: list[dict[str, str]],
    conditions: list[dict[str, str]] | None = None,
    assumptions: list[dict[str, str]] | None = None,
    proofs: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
    does_not_establish: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": kind,
        "mode": mode,
        "property": property_name,
        "role": role,
        "outcome": outcome,
        "severity": severity,
        "scope": {"revision": "head", "paths": [path], "declarations": declarations},
        "implementation": implementation_value,
        "inputs": inputs,
        "evidence": evidence_values,
        "conditions": conditions or [],
        "assumptions": assumptions or [],
        "proofs": proofs or [],
        "limitations": limitations or [],
        "does_not_establish": does_not_establish or ["merge_decision", "mathematical_truth"],
    }


CASES: dict[str, dict[str, Any]] = {
    "fork-dogfood-erdos-430-2": {
        "owner": "williamjblair",
        "name": "formal-conjectures",
        "pr": 2,
        "core_acquired_at": "2026-08-18T18:20:00Z",
        "base": {"commit_oid": "94a278e06a8bcbc2e4f2935e491c0c115ec832e0", "tree_oid": "3caf62b9e8c71e670ca6de049bb715c1c1f1c278"},
        "head": {"commit_oid": "84804da2e04a307be223f7dc067704619ca759c1", "tree_oid": "a222f6d2cc1c0269f202f37fa86390509096ab13"},
        "change": {
            "path": "FormalConjectures/ErdosProblems/430.lean", "status": "added",
            "base_blob_oid": None, "base_blob_sha256": None,
            "head_blob_oid": "093e45b558293abf3f587a68a164b603d143fa88",
            "head_blob_sha256": "sha256:3b3f938bdcfe5fc01a53bf3721b46e6c0e35ac1be394437d156a7ce5aab3c78d",
        },
        "checks": "external_advisory",
        "observation": {
            "state": "OPEN", "isDraft": True, "mergeStateStatus": "UNSTABLE", "reviewDecision": None,
            "updatedAt": "2026-08-18T18:07:57Z", "reviews": [],
        },
    },
    "external-fork-erdos-430-7": {
        "owner": "Paul-Lez",
        "name": "formal-conjectures",
        "pr": 7,
        "core_acquired_at": "2026-08-18T17:10:00Z",
        "base": {"commit_oid": "398958d3964d738886bd24433918c365df4a2aab", "tree_oid": "9c45eb302ab24c7d4fc949ce5a34bc499bfa8da5"},
        "head": {"commit_oid": "075c42c999c0c19224fd116d272637d7868df42a", "tree_oid": "fef90d7f2d905c4d95b75e96d19e01f200c64835"},
        "change": {
            "path": "FormalConjectures/ErdosProblems/430.lean", "status": "added",
            "base_blob_oid": None, "base_blob_sha256": None,
            "head_blob_oid": "093e45b558293abf3f587a68a164b603d143fa88",
            "head_blob_sha256": "sha256:3b3f938bdcfe5fc01a53bf3721b46e6c0e35ac1be394437d156a7ce5aab3c78d",
        },
        "checks": "external_advisory",
        "observation": {
            "state": "OPEN", "isDraft": True, "mergeStateStatus": "UNSTABLE", "reviewDecision": None,
            "updatedAt": "2026-08-18T17:03:52Z", "reviews": [],
        },
    },
    "clean-source-faithful-min-modulus-4829": {
        "pr": 4829,
        "core_acquired_at": "2026-08-13T11:50:00Z",
        "base": {"commit_oid": "5fe1f74ad497d950e4c2094879ab10708907f7c6", "tree_oid": "ab398d8cf338f90ca240c93b4a8a6d2583a93315"},
        "head": {"commit_oid": "0f8d60f1a5811eb00ad9f12cf8031ee5c1cc215c", "tree_oid": "8fab282d6af58b35db7d82ef02d53167dce0fe60"},
        "change": {
            "path": "FormalConjectures/Arxiv/2607.08366/MinModulus.lean",
            "status": "added",
            "base_blob_oid": None,
            "base_blob_sha256": None,
            "head_blob_oid": "4c68a8c3788f805e29588bfefdac1fec079e9193",
            "head_blob_sha256": "sha256:abb822a6dd603f95a9c9d773c199399222539c9cd91c8a124a3cc5429d9da416",
        },
        "checks": "clean_ground_truth",
        "observation": {
            "state": "MERGED", "isDraft": False, "mergeStateStatus": "UNKNOWN", "reviewDecision": "APPROVED",
            "updatedAt": "2026-08-11T21:39:27Z",
            "reviews": [
                {"id": "PRR_kwDOOogmB88AAAABJKwQiw", "author": "mo271", "state": "APPROVED", "submittedAt": "2026-08-11T19:58:39Z", "commitOid": "0f8d60f1a5811eb00ad9f12cf8031ee5c1cc215c"},
            ],
        },
    },
    "conditional-erdos-427-4884": {
        "pr": 4884,
        "base": {"commit_oid": "df1b7937d1d97e6acecb32dfa18b4381fc645c6a", "tree_oid": "4860e9006e43adca078a0f7ae2d9615627551583"},
        "head": {"commit_oid": "601aff40d6fa6c3150242144fadba5dbcc24c89c", "tree_oid": "c69df56ce3c6f27b39c64d74cafc2b0132faa1e2"},
        "change": {
            "path": "FormalConjectures/ErdosProblems/427.lean", "status": "modified",
            "base_blob_oid": "8473d6d80391c695667f4497953f44cf0f3b1d77",
            "base_blob_sha256": "sha256:5f3d76ab8db8212a2ff39a70b075ba31cbac912b5efb38797229ad6835cdcbc0",
            "head_blob_oid": "99d781c323fc09d49f688a5bd23722ea2011fd24",
            "head_blob_sha256": "sha256:be54dc1ed87c382e3ec3895f2568278e5c4fec186671b363ec8edd917ac60d71",
        },
        "checks": "conditional",
        "observation": {
            "state": "OPEN", "isDraft": False, "mergeStateStatus": "BLOCKED", "reviewDecision": "REVIEW_REQUIRED",
            "updatedAt": "2026-08-12T16:29:56Z", "reviews": [],
        },
    },
    "fidelity-erdos-887-1237": {
        "pr": 1237,
        "base": {"commit_oid": "a91ab6df34970fdd0fd8c919e693b2ba81fa4fbb", "tree_oid": "5113831f69da305cdcfbd971780cbdf23670fc20"},
        "head": {"commit_oid": "288608562e684a2f3c97ba0ce960a2649a71370b", "tree_oid": "db331ce2429aa6a53e30a66325493e0ad6b1d0b5"},
        "change": {
            "path": "FormalConjectures/ErdosProblems/887.lean", "status": "added",
            "base_blob_oid": None, "base_blob_sha256": None,
            "head_blob_oid": "6feb58b9272ce638aba6da5ca7ee8ebf7785e0b8",
            "head_blob_sha256": "sha256:3e4c9376ebfa464985a2da4ac3b8401b1b54d64be1075368032eced0700706c5",
        },
        "checks": "fidelity",
        "observation": {
            "state": "MERGED", "isDraft": False, "mergeStateStatus": "UNKNOWN", "reviewDecision": "APPROVED",
            "updatedAt": "2026-01-13T20:56:02Z",
            "reviews": [
                {"id": "PRR_kwDOOogmB87P5dwU", "author": "smmercuri", "state": "CHANGES_REQUESTED", "submittedAt": "2025-11-20T13:50:54Z", "commitOid": "b99a00bff3e76a112e3a00458c376acaaf1b4392"},
                {"id": "PRR_kwDOOogmB87Qeusx", "author": "smmercuri", "state": "CHANGES_REQUESTED", "submittedAt": "2025-11-23T12:29:13Z", "commitOid": "b99a00bff3e76a112e3a00458c376acaaf1b4392"},
                {"id": "PRR_kwDOOogmB87RUSCe", "author": "AlexBrodbelt", "state": "COMMENTED", "submittedAt": "2025-11-26T16:23:31Z", "commitOid": "b99a00bff3e76a112e3a00458c376acaaf1b4392"},
                {"id": "PRR_kwDOOogmB87RusrX", "author": "smmercuri", "state": "CHANGES_REQUESTED", "submittedAt": "2025-11-28T12:12:49Z", "commitOid": "c12b147ae907ac937b37e04fdb673df13379163b"},
                {"id": "PRR_kwDOOogmB87Y71tX", "author": "AlexBrodbelt", "state": "COMMENTED", "submittedAt": "2026-01-08T14:01:38Z", "commitOid": "c12b147ae907ac937b37e04fdb673df13379163b"},
                {"id": "PRR_kwDOOogmB87Y77Gg", "author": "AlexBrodbelt", "state": "COMMENTED", "submittedAt": "2026-01-08T14:06:33Z", "commitOid": "c12b147ae907ac937b37e04fdb673df13379163b"},
                {"id": "PRR_kwDOOogmB87Z7dqF", "author": "smmercuri", "state": "CHANGES_REQUESTED", "submittedAt": "2026-01-13T15:16:34Z", "commitOid": "c86f22dcbdd107aa90b97335e9e9674033fcfb88"},
                {"id": "PRR_kwDOOogmB87Z9oI-", "author": "AlexBrodbelt", "state": "COMMENTED", "submittedAt": "2026-01-13T16:45:24Z", "commitOid": "c86f22dcbdd107aa90b97335e9e9674033fcfb88"},
                {"id": "PRR_kwDOOogmB87Z-IWr", "author": "smmercuri", "state": "APPROVED", "submittedAt": "2026-01-13T17:14:06Z", "commitOid": "288608562e684a2f3c97ba0ce960a2649a71370b"},
            ],
        },
    },
    "vacuity-erdos-80-4830": {
        "pr": 4830,
        "base": {"commit_oid": "5fe1f74ad497d950e4c2094879ab10708907f7c6", "tree_oid": "ab398d8cf338f90ca240c93b4a8a6d2583a93315"},
        "head": {"commit_oid": "e2e2a6064b474781d3b5b4a32e3d77956d6968da", "tree_oid": "539454f905f7916b8ffe91724239203367614e0f"},
        "change": {
            "path": "FormalConjectures/ErdosProblems/80.lean", "status": "added",
            "base_blob_oid": None, "base_blob_sha256": None,
            "head_blob_oid": "9dd6a9933931fcfbeea61eac777d4155dacb9eb1",
            "head_blob_sha256": "sha256:519cc02b3389c89bc87c16d548c6b028e6bb2c1c3bad410a1758f470de18de4e",
        },
        "checks": "vacuity",
        "observation": {
            "state": "MERGED", "isDraft": False, "mergeStateStatus": "UNKNOWN", "reviewDecision": "APPROVED",
            "updatedAt": "2026-08-10T13:31:34Z",
            "reviews": [
                {"id": "PRR_kwDOOogmB88AAAABI2SldQ", "author": "mo271", "state": "COMMENTED", "submittedAt": "2026-08-08T12:02:53Z", "commitOid": "dea7123ec0e2bafd1c72ae6558a389d5083df76e"},
                {"id": "PRR_kwDOOogmB88AAAABI9jtug", "author": "mo271", "state": "APPROVED", "submittedAt": "2026-08-10T11:49:37Z", "commitOid": "e2e2a6064b474781d3b5b4a32e3d77956d6968da"},
            ],
        },
    },
    "unavailable-rupert-3959": {
        "pr": 3959,
        "base": {"commit_oid": "99ae49df4b27d9d95877c562ab9e1fd9b7ff1dc7", "tree_oid": "4d49db94887c2a560954b860fd29c57f19f2da4c"},
        "head": {"commit_oid": "868cc092aeb713dbf8027883c5fa575e550cfae9", "tree_oid": "b281db5858080340773cdf07b5a9ed625aef6acd"},
        "change": {
            "path": "FormalConjectures/Paper/Rupert.lean", "status": "modified",
            "base_blob_oid": "a3cb248507ad9a9bcb4c3af7620dabebcd304f3a",
            "base_blob_sha256": "sha256:fc118aad528350a7f9f8a59fa4a96969d51f381f82cf83b3586a337e67ab81c6",
            "head_blob_oid": "48c343f0d12c1dffb7953a5d2426e0d13a914bad",
            "head_blob_sha256": "sha256:49bec542e7c93319ca4a1c4a2b0b3a18bf72baaf7621416a30685e311a6ef7cf",
        },
        "checks": "unavailable",
        "observation": {
            "state": "MERGED", "isDraft": False, "mergeStateStatus": "UNKNOWN", "reviewDecision": "APPROVED",
            "updatedAt": "2026-05-09T23:30:38Z",
            "reviews": [
                {"id": "PRR_kwDOOogmB879jZVh", "author": "jcreedcmu", "state": "COMMENTED", "submittedAt": "2026-05-08T17:03:18Z", "commitOid": "30c63898f32c0c7d05a6830504195d7f896451f0"},
                {"id": "PRR_kwDOOogmB879kIEO", "author": "dwrensha", "state": "COMMENTED", "submittedAt": "2026-05-08T17:30:41Z", "commitOid": "30c63898f32c0c7d05a6830504195d7f896451f0"},
                {"id": "PRR_kwDOOogmB879wy6I", "author": "Paul-Lez", "state": "COMMENTED", "submittedAt": "2026-05-09T08:29:33Z", "commitOid": "30c63898f32c0c7d05a6830504195d7f896451f0"},
                {"id": "PRR_kwDOOogmB879wy92", "author": "Paul-Lez", "state": "APPROVED", "submittedAt": "2026-05-09T08:29:49Z", "commitOid": "30c63898f32c0c7d05a6830504195d7f896451f0"},
                {"id": "PRR_kwDOOogmB879xzi6", "author": "dwrensha", "state": "COMMENTED", "submittedAt": "2026-05-09T11:17:06Z", "commitOid": "30c63898f32c0c7d05a6830504195d7f896451f0"},
            ],
        },
    },
}


def repository_identity(case: dict[str, Any]) -> tuple[str, str, str]:
    owner = case.get("owner", "google-deepmind")
    name = case.get("name", "formal-conjectures")
    return owner, name, f"https://github.com/{owner}/{name}"


def generator_identity() -> dict[str, Any]:
    paths = [
        "scripts/pr_audit.py",
        "scripts/generate_pr_audit.py",
        "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit.v1.schema.json",
        "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit-observation.v1.schema.json",
    ]
    files = [
        {"path": path, "sha256": sha256_digest((REPO / path).read_bytes())}
        for path in sorted(paths)
    ]
    return {
        "schema_version": "formal-conjectures.pr-audit-generator.v1",
        "name": "formal-conjectures-pr-audit",
        "version": "1.0.0",
        "canonicalization": "fc-jcs-ijson-integer-v1",
        "source": {
            "kind": "git_baseline_with_content_addressed_overlay",
            "repository": "https://github.com/google-deepmind/formal-conjectures",
            "baseline": BASELINE,
            "overlay": {"files": files, "root": content_root({"files": files})},
        },
        "noncapabilities": ["git", "github", "lean", "model", "network", "subprocess"],
    }


def repository_snapshot(case: dict[str, Any]) -> dict[str, Any]:
    number = case["pr"]
    owner, name, url = repository_identity(case)
    return {
        "schema_version": "formal-conjectures.pr-audit-repository.v1",
        "repository": {
            "host": "github.com", "owner": owner, "name": name, "url": url,
        },
        "pull_request": {"number": number, "url": f"{url}/pull/{number}"},
        "comparison": {"kind": "github_pull_request_file_snapshot", "complete": True},
        "base": case["base"], "head": case["head"], "changes": [case["change"]],
    }


def checks_for(case: dict[str, Any], roots: dict[str, str]) -> dict[str, Any]:
    path = case["change"]["path"]
    head_root = case["change"]["head_blob_sha256"]
    head_locator = f"{path}@{case['head']['commit_oid']}"
    kind = case["checks"]
    if kind == "external_advisory":
        case_name = next(name for name, value in CASES.items() if value is case)
        owner, repository_name, _ = repository_identity(case)
        review = json.loads((FIXTURES / case_name / "inputs" / "source-fidelity-review.json").read_text())
        checks = [base_check(
            identifier="source-statement-fidelity", kind="semantic", mode="human_review",
            property_name="source-statement-fidelity", role="advisory",
            outcome=review["outcome"], severity=review["severity"],
            path=path, declarations=["Erdos430.erdos_430"],
            implementation_value=implementation(
                "retained-advisory-source-fidelity-review", "human_review_guide",
                "source-fidelity-method.json", roots["source-fidelity-method"],
            ),
            inputs=[
                check_input("head-source", "head-source", "git-blob", head_locator, head_root),
                check_input("source-current", "source-current", "source-reference", "https://www.erdosproblems.com/430", roots["source-current"]),
                check_input("source-history", "source-history", "source-reference", "https://www.erdosproblems.com/430/history", roots["source-history"]),
                check_input("source-original", "source-original", "source-reference", "ErdosGraham1980:p85", roots["source-original"]),
                check_input("source-fidelity-method", "source-fidelity-method", "human-review-guide", "source-fidelity-method.json", roots["source-fidelity-method"]),
                check_input("role-source-fidelity", "role-source-fidelity", "role-output", "clean-room/source-fidelity.json", roots["role-source-fidelity"]),
                check_input("role-lean-semantics", "role-lean-semantics", "role-output", "clean-room/lean-semantics.json", roots["role-lean-semantics"]),
                check_input("role-deterministic-verification", "role-deterministic-verification", "role-output", "clean-room/deterministic-verification.json", roots["role-deterministic-verification"]),
                check_input("role-adversarial-edge-cases", "role-adversarial-edge-cases", "role-output", "clean-room/adversarial-edge-cases.json", roots["role-adversarial-edge-cases"]),
                check_input("source-fidelity-review", "source-fidelity-review", "advisory-review-observation", "source-fidelity-review.json", roots["source-fidelity-review"]),
            ],
            evidence_values=[evidence(
                "advisory-review-observation", "source-fidelity-review.json",
                roots["source-fidelity-review"], review["finding"], review["witness"],
            )],
            limitations=[
                "The four clean-room role outputs and their aggregation are advisory pilot evidence, not independent maintainer review.",
                "The source references are retained exact bytes with descriptive locators; the locators are not cryptographic source signatures.",
            ],
            does_not_establish=["maintainer_disposition", "mathematical_truth", "merge_decision"],
        ), base_check(
            identifier="snapshot-identity", kind="mechanical", mode="retained_replay",
            property_name="immutable-input-identity", role="producer", outcome="pass", severity="none",
            path=path, declarations=["Erdos430.erdos_430"],
            implementation_value=implementation(
                "pr-audit-snapshot-validator", "retained_procedure",
                "scripts/pr_audit.py", roots["method-pr-audit"],
            ),
            inputs=[
                check_input("head-source", "head-source", "git-blob", head_locator, head_root),
                check_input("method", "method-pr-audit", "python-source", "scripts/pr_audit.py", roots["method-pr-audit"]),
            ],
            evidence_values=[evidence(
                "retained-snapshot", head_locator, head_root,
                f"The retained PR snapshot binds {owner}/{repository_name} PR {case['pr']} to its exact base, head, tree, path, declaration source, and Git blob identity.",
            )],
            limitations=["This deterministic identity check does not assess source fidelity or Lean semantics."],
        )]
        repository_provenance = [
            check_input("repository-authority", "repository-authority", "normalized-repository-result", "PullRequestAuditCoreSnapshot.result", roots["repository-authority"]),
            check_input("repository-query", "repository-query", "graphql-query", "PullRequestAuditCoreSnapshot", roots["repository-query"]),
            check_input("repository-request", "repository-request", "request-identity", "PullRequestAuditCoreSnapshot.request", roots["repository-request"]),
        ]
        for check in checks:
            check["inputs"].extend(repository_provenance)
        return {"schema_version": "formal-conjectures.pr-audit-checks.v1", "checks": checks}
    if kind == "clean_ground_truth":
        checks = [base_check(
            identifier="source-statement-fidelity", kind="semantic", mode="human_review",
            property_name="source-statement-fidelity", role="independent", outcome="pass", severity="none",
            path=path, declarations=["MinModulus.min_modulus"],
            implementation_value=implementation(
                "retained-source-fidelity-chain", "human_review_guide",
                "human-source-fidelity-method.json", roots["human-source-fidelity-method"],
            ),
            inputs=[
                check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                check_input("review-context-lean-blob", "review-context-source", "git-blob", f"{path}@61fd97db4c6533c007d6e7857b2eb94fcdf90463", roots["review-context-source"]),
                check_input("applied-lean-blob", "applied-source", "git-blob", f"{path}@225c54f1deb0a9e6043465a5c768295740895ccf", roots["applied-source"]),
                check_input("method", "human-source-fidelity-method", "human-review-guide", "human-source-fidelity-method.json", roots["human-source-fidelity-method"]),
                check_input("human-review", "human-source-fidelity-review", "human-review-observation", "https://github.com/google-deepmind/formal-conjectures/pull/4829#issuecomment-5227429390", roots["human-source-fidelity-review"]),
                check_input("source-author-review-body", "source-author-review-body", "human-review-body", "https://github.com/google-deepmind/formal-conjectures/pull/4829#issuecomment-5227429390", roots["source-author-review-body"]),
                check_input("applied-review-response-body", "applied-review-response-body", "human-review-body", "https://github.com/google-deepmind/formal-conjectures/pull/4829#issuecomment-5228066477", roots["applied-review-response-body"]),
                check_input("exact-head-approval-body", "exact-head-approval-body", "human-review-body", "https://github.com/google-deepmind/formal-conjectures/pull/4829#pullrequestreview-4910223499", roots["exact-head-approval-body"]),
            ],
            evidence_values=[evidence(
                "source-author-review",
                "https://github.com/google-deepmind/formal-conjectures/pull/4829#issuecomment-5227429390",
                roots["human-source-fidelity-review"],
                "The paper author explicitly found the open theorem statement faithful to Conjecture 1 and supplied the zero-modulus witness for its guard.",
                "The reviewed theorem block is unchanged through the applied revision and exact final head; the final head has a retained maintainer approval.",
            )],
            limitations=[
                "The source-author comment is a public GitHub observation, not a cryptographic signature; the packet binds its exact identity and text to retained source revisions.",
                "This check covers the open min_modulus declaration only, not every declaration or the truth of Conjecture 1.",
            ],
            does_not_establish=["lean_build", "mathematical_truth", "merge_decision", "proof_correctness"],
        ), base_check(
            identifier="snapshot-identity", kind="mechanical", mode="retained_replay",
            property_name="immutable-input-identity", role="producer", outcome="pass", severity="none",
            path=path, declarations=["MinModulus.min_modulus"],
            implementation_value=implementation(
                "pr-audit-snapshot-validator", "retained_procedure",
                "scripts/pr_audit.py", roots["method-pr-audit"],
            ),
            inputs=[
                check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                check_input("method", "method-pr-audit", "python-source", "scripts/pr_audit.py", roots["method-pr-audit"]),
            ],
            evidence_values=[evidence(
                "git-blob-identity", head_locator, head_root,
                "The retained final path has an exact Git blob OID and SHA-256 content root.",
            )],
            limitations=["Exact byte identity is separate from the human source-fidelity judgment."],
            does_not_establish=["lean_build", "mathematical_truth", "merge_decision", "source_fidelity"],
        )]
    elif kind == "conditional":
        assumption = condition(
            "Erdos427.erdos_427.variants.shiu",
            "The linked proof derives the result assuming Shiu's theorem.",
            "FormalConjectures/ErdosProblems/427.lean#Erdos427.erdos_427.variants.shiu",
        )
        proof = {
            "declaration": "Erdos427.erdos_427",
            "kind": "lean4",
            "locator": "https://gist.githubusercontent.com/JohnEdwardJennings/e2c6ef0daab55857b7cc9d340de7af84/raw/8ff97800e38582c71246a238e7541a9d69488cbd/Erdos427.lean",
            "conditions": [assumption],
        }
        checks = [base_check(
            identifier="conditional-proof-metadata", kind="proof", mode="human_review",
            property_name="formal-proof-conditions-retained", role="producer", outcome="pass", severity="none",
            path=path, declarations=["Erdos427.erdos_427", "Erdos427.erdos_427.variants.shiu"],
            implementation_value=implementation("retained-formal-proof-metadata-review", "retained_procedure", "metadata-review-procedure.json", roots["metadata-review-procedure"]),
                inputs=[
                    check_input("base-lean-blob", "base-source", "git-blob", f"{path}@{case['base']['commit_oid']}", case["change"]["base_blob_sha256"]),
                    check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                check_input("linked-proof", "linked-proof", "git-blob", proof["locator"], roots["linked-proof"]),
                check_input("method", "metadata-review-procedure", "review-procedure", "metadata-review-procedure.json", roots["metadata-review-procedure"]),
            ],
            evidence_values=[evidence("lean-attribute", head_locator, head_root, "The formal_proof tuple is explicitly conditional and names its assumption.")],
            conditions=[assumption], assumptions=[assumption], proofs=[proof],
            limitations=["This is a retained manual metadata review; it does not execute or compare the linked proof."],
            does_not_establish=["proof_correctness", "source_fidelity", "merge_decision"],
        )]
    elif kind == "fidelity":
        checks = [
            base_check(
                identifier="exact-head-build", kind="mechanical", mode="retained_replay",
                property_name="lean-build", role="producer", outcome="pass", severity="none",
                path=path, declarations=["Erdos887.erdos_887"],
                implementation_value=implementation("build-and-docs", "github_actions_workflow", f".github/workflows/build-and-docs.yml@{case['head']['commit_oid']}", roots["method-workflow"]),
                inputs=[
                    check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                    check_input("build-job", "build-job", "github-check-run", "https://github.com/google-deepmind/formal-conjectures/actions/runs/20965023898/job/60275340706", roots["build-job"]),
                    check_input("workflow", "method-workflow", "workflow", f".github/workflows/build-and-docs.yml@{case['head']['commit_oid']}", roots["method-workflow"]),
                    check_input("workflow-identity", "method-workflow-identity", "git-object-identity", f".github/workflows/build-and-docs.yml@{case['head']['commit_oid']}", roots["method-workflow-identity"]),
                ],
                evidence_values=[evidence("github-check-run", "https://github.com/google-deepmind/formal-conjectures/actions/runs/20965023898/job/60275340706", roots["build-job"], "The exact PR head completed the repository Build project job successfully.")],
                limitations=["A successful build does not establish answer-slot scope fidelity."],
                does_not_establish=["source_fidelity", "merge_decision"],
            ),
            base_check(
                identifier="answer-slot-scope", kind="semantic", mode="retained_replay",
                property_name="answer-slot-scope-fidelity", role="advisory", outcome="fail", severity="meaning",
                path=path, declarations=["Erdos887.erdos_887"],
                implementation_value=implementation("mathematical-review-guide", "human_review_guide", f"REVIEW_MATH.md@{REVIEW_GUIDE_REVISION}#L123-L129", REVIEW_GUIDE_ROOT),
                inputs=[
                    check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                    check_input("review-guide", "review-guide", "human-review-guide", f"REVIEW_MATH.md@{REVIEW_GUIDE_REVISION}", roots["review-guide"]),
                    check_input("review-guide-identity", "review-guide-identity", "git-object-identity", f"REVIEW_MATH.md@{REVIEW_GUIDE_REVISION}", roots["review-guide-identity"]),
                ],
                evidence_values=[evidence(
                    "binder-scope-witness", head_locator, head_root,
                    "At exact PR 1237 head 28860856/blob 6feb58b9, the docstring asks for one absolute K, but answer(sorry) occurs under the C and n binders.",
                    "For each bound instance the answer slot can take the left-hand divisor count, and le_refl closes that instance; the slot therefore does not choose one absolute K.",
                )],
                limitations=["The witness is exact-head and does not rely on later Erdős 887 rewrites.", "The clean-candidate ground-truth exit still requires a separate independent-human fidelity pass."],
                does_not_establish=["mathematical_truth", "merge_decision"],
            ),
        ]
    elif kind == "vacuity":
        checks = [base_check(
            identifier="vacuous-hypothesis", kind="semantic", mode="retained_replay",
            property_name="hypothesis-satisfiability", role="advisory", outcome="fail", severity="meaning",
            path=path, declarations=["Erdos80.Admissible", "Erdos80.erdos_80"],
            implementation_value=implementation("mathematical-review-guide", "human_review_guide", f"REVIEW_MATH.md@{REVIEW_GUIDE_REVISION}#L70-L84", REVIEW_GUIDE_ROOT),
            inputs=[
                check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                check_input("review-guide", "review-guide", "human-review-guide", f"REVIEW_MATH.md@{REVIEW_GUIDE_REVISION}", roots["review-guide"]),
                check_input("review-guide-identity", "review-guide-identity", "git-object-identity", f"REVIEW_MATH.md@{REVIEW_GUIDE_REVISION}", roots["review-guide-identity"]),
            ],
            evidence_values=[evidence(
                "finite-graph-witness", head_locator, head_root,
                "At exact PR 4830 head e2e2a606/blob 9dd6a993, Admissible requires c*n^2 edges in a simple n-vertex graph while the theorem quantifies over every c>0.",
                "At c=2 and n=100 the hypothesis needs 20000 edges, but a simple graph has at most 4950; the admissible set is empty and sInf is 0.",
            )],
            limitations=["The witness establishes the vacuity defect at the stated parameter, not a replacement theorem."],
            does_not_establish=["mathematical_truth", "merge_decision"],
        )]
    else:
        proof = {
            "declaration": "Rupert.is_every_convex_polyhedron_rupert",
            "kind": "lean4",
            "locator": "https://github.com/jcreedcmu/Noperthedron",
            "conditions": [],
        }
        checks = [
            base_check(
                identifier="exact-head-build", kind="mechanical", mode="retained_replay",
                property_name="lean-build", role="producer", outcome="pass", severity="none",
                path=path, declarations=["Rupert.is_every_convex_polyhedron_rupert"],
                implementation_value=implementation("build-and-docs", "github_actions_workflow", f".github/workflows/build-and-docs.yml@{case['head']['commit_oid']}", roots["method-workflow"]),
                inputs=[
                    check_input("base-lean-blob", "base-source", "git-blob", f"{path}@{case['base']['commit_oid']}", case["change"]["base_blob_sha256"]),
                    check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                    check_input("build-job", "build-job", "github-check-run", "https://github.com/google-deepmind/formal-conjectures/actions/runs/25608941188/job/75175625578", roots["build-job"]),
                    check_input("workflow", "method-workflow", "workflow", f".github/workflows/build-and-docs.yml@{case['head']['commit_oid']}", roots["method-workflow"]),
                    check_input("workflow-identity", "method-workflow-identity", "git-object-identity", f".github/workflows/build-and-docs.yml@{case['head']['commit_oid']}", roots["method-workflow-identity"]),
                ],
                evidence_values=[evidence(
                    "github-check-run", "https://github.com/google-deepmind/formal-conjectures/actions/runs/25608941188/job/75175625578", roots["build-job"],
                    "The exact PR head completed the repository Build project job successfully.",
                )],
                limitations=["A successful Lean build does not identify or compare the externally linked proof artifact."],
                does_not_establish=["proof_correctness", "source_fidelity", "merge_decision"],
            ),
            base_check(
                identifier="formal-proof-artifact-identity", kind="metadata", mode="native",
                property_name="exact-formal-proof-artifact-identity", role="producer", outcome="unavailable", severity="none",
                path=path, declarations=["Rupert.is_every_convex_polyhedron_rupert"],
                implementation_value=implementation("formal-proof-target-classifier", "retained_procedure", "scripts/pr_audit.py#classify_proof_target", roots["method-pr-audit"]),
                inputs=[
                    check_input("base-lean-blob", "base-source", "git-blob", f"{path}@{case['base']['commit_oid']}", case["change"]["base_blob_sha256"]),
                    check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                    check_input("method", "method-pr-audit", "python-source", "scripts/pr_audit.py#classify_proof_target", roots["method-pr-audit"]),
                ],
                evidence_values=[evidence(
                    "mutable-repository-root-metadata", head_locator, head_root,
                    "The head metadata points only to a mutable repository root with multiple candidate proof routes, not to an exact commit and file.",
                    "At PR 3959 head 868cc092, the formal_proof attribute does not identify immutable proof bytes for an independent consumer.",
                )],
                proofs=[proof],
                limitations=["Unavailable is scoped to exact artifact identity at this head; later metadata may pin an exact commit and file."],
                does_not_establish=["proof_absence", "proof_failure", "proof_incorrectness", "repository_has_no_matching_proof", "source_fidelity", "merge_decision"],
            ),
            base_check(
                identifier="comparator-packet-identity", kind="metadata", mode="retained_replay",
                property_name="comparator-packet-identity", role="producer", outcome="unavailable", severity="none",
                path=path, declarations=["Rupert.is_every_convex_polyhedron_rupert"],
                implementation_value=implementation("comparator-packet-inspection", "retained_procedure", "comparator-packet-procedure.json", roots["comparator-procedure"]),
                inputs=[
                    check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                    check_input("method", "comparator-procedure", "retained-procedure", "comparator-packet-procedure.json", roots["comparator-procedure"]),
                    check_input("observation", "comparator-observation", "packet-inspection-observation", "comparator-packet-observation.json", roots["comparator-observation"]),
                ],
                evidence_values=[evidence("packet-inspection-observation", "comparator-packet-observation.json", roots["comparator-observation"], "A retained packet inspection found no exact Comparator executable, toolchain lock, invocation, or execution result in scope.")],
                limitations=["This packet-inspection check alone does not establish attempted invocation; the separate Comparator tool-availability check carries the retained attempt."],
                does_not_establish=["attempted_invocation", "comparison_result", "proof_correctness", "source_fidelity", "merge_decision"],
            ),
            base_check(
                identifier="comparator-tool-availability", kind="mechanical", mode="retained_replay",
                property_name="comparator-tool-availability", role="producer", outcome="unavailable", severity="none",
                path=path, declarations=["Rupert.is_every_convex_polyhedron_rupert"],
                implementation_value=implementation(
                    "comparator-availability-preflight", "retained_procedure",
                    "missing-tool-invocation-procedure.py", roots["comparator-invocation-procedure"],
                ),
                inputs=[
                    check_input("head-lean-blob", "head-source", "git-blob", head_locator, head_root),
                    check_input(
                        "method", "comparator-invocation-procedure", "python-source",
                        "missing-tool-invocation-procedure.py", roots["comparator-invocation-procedure"],
                    ),
                    check_input(
                        "invocation-result", "comparator-invocation-result", "tool-invocation-result",
                        "comparator-missing-tool-invocation.json", roots["comparator-invocation-result"],
                    ),
                ],
                evidence_values=[evidence(
                    "tool-invocation-result", "comparator-missing-tool-invocation.json",
                    roots["comparator-invocation-result"],
                    "A real inert Comparator availability invocation was attempted under the declared closed PATH; no executable resolved and no process started.",
                )],
                limitations=[
                    "Unavailable is scoped to the Comparator executable in the declared environment; no proof comparison ran."
                ],
                does_not_establish=[
                    "comparison_result", "proof_absence", "proof_failure", "proof_incorrectness",
                    "source_fidelity", "merge_decision",
                ],
            ),
        ]
    repository_provenance = [
        check_input("repository-authority", "repository-authority", "normalized-repository-result", "PullRequestAuditCoreSnapshot.result", roots["repository-authority"]),
        check_input("repository-query", "repository-query", "graphql-query", "PullRequestAuditCoreSnapshot", roots["repository-query"]),
        check_input("repository-request", "repository-request", "request-identity", "PullRequestAuditCoreSnapshot.request", roots["repository-request"]),
    ]
    for check in checks:
        check["inputs"].extend(repository_provenance)
    return {"schema_version": "formal-conjectures.pr-audit-checks.v1", "checks": checks}


def observation_source(case: dict[str, Any]) -> dict[str, Any]:
    number = case["pr"]
    _, _, repository_url = repository_identity(case)
    observed = case["observation"]
    pr = {
        "number": number,
        "url": f"{repository_url}/pull/{number}",
        "state": observed["state"], "isDraft": observed["isDraft"],
        "mergeStateStatus": observed["mergeStateStatus"], "reviewDecision": observed["reviewDecision"],
        "updatedAt": observed["updatedAt"], "baseRefOid": case["base"]["commit_oid"],
        "headRefOid": case["head"]["commit_oid"],
        "reviews": {
            "nodes": [
                {
                    "id": review["id"],
                    "author": {"login": review["author"]},
                    "state": review["state"],
                    "submittedAt": review["submittedAt"],
                    "commit": {"oid": review["commitOid"]},
                }
                for review in observed["reviews"]
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": None if not observed["reviews"] else json.loads((FIXTURES / next(name for name, value in CASES.items() if value is case) / "inputs" / "github-graphql-response.json").read_text())["data"]["repository"]["pullRequest"]["reviews"]["pageInfo"]["endCursor"]},
        },
    }
    return {"data": {"repository": {"pullRequest": pr}}}


def write_json(path: Path, value: Any) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canonical(path, value)
    return path.read_bytes()


def descriptor(
    identifier: str, role: str, path: str, raw: bytes, media_type: str = "application/json"
) -> dict[str, str]:
    return {"id": identifier, "role": role, "media_type": media_type, "path": path, "sha256": sha256_digest(raw)}


def retained_core_artifacts(
    name: str, case: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, str]]:
    directory = FIXTURES / name
    inputs = directory / "inputs"
    owner, repository_name, repository_url = repository_identity(case)
    artifacts: list[dict[str, str]] = []
    provenance_artifacts: list[dict[str, str]] = []
    roots: dict[str, str] = {}

    def retain(identifier: str, role: str, filename: str, raw: bytes, media_type: str) -> None:
        path = f"inputs/{filename}"
        destination = inputs / filename
        if not destination.exists() or destination.read_bytes() != raw:
            destination.write_bytes(raw)
        item = descriptor(identifier, role, path, raw, media_type)
        artifacts.append(item)
        roots[identifier] = item["sha256"]

    def retain_provenance(identifier: str, filename: str, raw: bytes, media_type: str) -> None:
        path = f"inputs/{filename}"
        destination = inputs / filename
        if not destination.exists() or destination.read_bytes() != raw:
            destination.write_bytes(raw)
        provenance_artifacts.append(
            descriptor(identifier, "provenance_event", path, raw, media_type)
        )

    head_raw = (inputs / "head-source.lean").read_bytes()
    retain("head-source", "source_file", "head-source.lean", head_raw, "text/x-lean")
    if sha256_digest(head_raw) != case["change"]["head_blob_sha256"]:
        raise RuntimeError(f"head source bytes do not match frozen identity: {name}")
    if case["change"]["base_blob_sha256"] is not None:
        base_raw = (inputs / "base-source.lean").read_bytes()
        retain("base-source", "source_file", "base-source.lean", base_raw, "text/x-lean")
        if sha256_digest(base_raw) != case["change"]["base_blob_sha256"]:
            raise RuntimeError(f"base source bytes do not match frozen identity: {name}")

    if case["checks"] == "external_advisory":
        authority_capture = {"data": {"repository": {
            "pullRequest": {
                "number": case["pr"], "url": f"{repository_url}/pull/{case['pr']}",
                "baseRefOid": case["base"]["commit_oid"], "headRefOid": case["head"]["commit_oid"],
                "files": {"nodes": [{"path": case["change"]["path"], "changeType": "ADDED"}], "pageInfo": {"hasNextPage": False, "endCursor": "MQ"}},
            },
            "baseCommit": {"oid": case["base"]["commit_oid"], "tree": {"oid": case["base"]["tree_oid"]}},
            "headCommit": {"oid": case["head"]["commit_oid"], "tree": {"oid": case["head"]["tree_oid"]}},
            "baseBlob": None,
            "headBlob": {"oid": case["change"]["head_blob_oid"], "byteSize": len(head_raw), "isBinary": False, "text": head_raw.decode("utf-8")},
        }}}
        (inputs / "github-core-snapshot-response.json").write_bytes(
            json.dumps(authority_capture, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
    authority_raw = (inputs / "github-core-snapshot-response.json").read_bytes().removesuffix(b"\n")
    authority = json.loads(authority_raw)["data"]["repository"]
    pr = authority["pullRequest"]
    files = pr.pop("files")
    if pr != {
        "number": case["pr"],
        "url": f"{repository_url}/pull/{case['pr']}",
        "baseRefOid": case["base"]["commit_oid"],
        "headRefOid": case["head"]["commit_oid"],
    }:
        raise RuntimeError(f"retained GitHub core PR identity does not match frozen case: {name}")
    if files["pageInfo"]["hasNextPage"]:
        raise RuntimeError(f"retained GitHub changed-file response is paginated: {name}")
    expected_change_type = {"added": "ADDED", "modified": "MODIFIED", "deleted": "DELETED"}
    if files["nodes"] != [{
        "path": case["change"]["path"],
        "changeType": expected_change_type[case["change"]["status"]],
    }]:
        raise RuntimeError(f"retained GitHub changed-file inventory is not complete/exact: {name}")
    for revision in ("base", "head"):
        commit = authority[f"{revision}Commit"]
        if commit != {"oid": case[revision]["commit_oid"], "tree": {"oid": case[revision]["tree_oid"]}}:
            raise RuntimeError(f"retained GitHub {revision} commit/tree does not match frozen case: {name}")
        blob = authority[f"{revision}Blob"]
        expected_oid = case["change"][f"{revision}_blob_oid"]
        if expected_oid is None:
            if blob is not None:
                raise RuntimeError(f"retained GitHub {revision} blob should be absent: {name}")
            continue
        source_raw = (inputs / f"{revision}-source.lean").read_bytes()
        if blob["oid"] != expected_oid or blob["byteSize"] != len(source_raw) or blob["isBinary"] or blob["text"].encode() != source_raw:
            raise RuntimeError(f"retained GitHub {revision} blob response does not match source bytes: {name}")
    authority_result = {
        "schema_version": "formal-conjectures.pr-audit-repository-result.v1",
        "pull_request": {**pr, "files": files["nodes"]},
        "base_commit": authority["baseCommit"],
        "head_commit": authority["headCommit"],
        "base_blob": authority["baseBlob"],
        "head_blob": authority["headBlob"],
    }
    authority_result_raw = write_json(inputs / "github-core-snapshot-result.json", authority_result)
    retain("repository-authority", "tool_output", "github-core-snapshot-result.json", authority_result_raw, "application/json")
    retain_provenance(
        "provenance-core-snapshot-response", "github-core-snapshot-response.json",
        authority_raw, "application/vnd.github+json",
    )
    query_raw = CORE_GRAPHQL_OPERATION.encode("utf-8")
    retain("repository-query", "query", "github-core-snapshot-query.graphql", query_raw, "text/plain")
    variables = {
        "owner": owner, "name": repository_name, "number": case["pr"],
        "baseOid": case["base"]["commit_oid"], "headOid": case["head"]["commit_oid"],
        "baseExpression": f"{case['base']['commit_oid']}:{case['change']['path']}",
        "headExpression": f"{case['head']['commit_oid']}:{case['change']['path']}",
    }
    request_identity = {
        "schema_version": "formal-conjectures.pr-audit-request-identity.v1",
        "operation_name": "PullRequestAuditCoreSnapshot",
        "variables": variables,
        "query_sha256": sha256_digest(query_raw),
        "result_sha256": sha256_digest(authority_result_raw),
    }
    request_identity_raw = write_json(inputs / "github-core-request-identity.json", request_identity)
    retain("repository-request", "configuration", "github-core-request-identity.json", request_identity_raw, "application/json")
    receipt = {
        "schema_version": "formal-conjectures.pr-audit-acquisition-receipt.v1",
        "transport": "https",
        "endpoint": "https://api.github.com/graphql",
        "operation_name": "PullRequestAuditCoreSnapshot",
        "variables": variables,
        "acquired_at": case.get("core_acquired_at", CORE_ACQUIRED_AT),
        "response_sha256": sha256_digest(authority_raw),
        "query_sha256": sha256_digest(query_raw),
        "http_status": 200,
        "request_id": "not-retained",
        "limitations": ["The original transport request ID was not retained; endpoint, exact query, variables, response bytes, and acquisition time are retained, but this is not a cryptographic GitHub signature."],
    }
    receipt_raw = write_json(inputs / "github-core-acquisition-receipt.json", receipt)
    retain_provenance(
        "provenance-core-acquisition-receipt", "github-core-acquisition-receipt.json",
        receipt_raw, "application/json",
    )
    kind = case["checks"]
    if kind == "unavailable":
        retain("method-pr-audit", "method", "method-pr-audit.py", (REPO / "scripts/pr_audit.py").read_bytes(), "text/plain")
    if kind == "clean_ground_truth":
        retain("method-pr-audit", "method", "method-pr-audit.py", (REPO / "scripts/pr_audit.py").read_bytes(), "text/plain")
        review_context_raw = (inputs / "review-context-source.lean").read_bytes()
        applied_raw = (inputs / "applied-source.lean").read_bytes()
        retain("review-context-source", "source_file", "review-context-source.lean", review_context_raw, "text/x-lean")
        retain("applied-source", "source_file", "applied-source.lean", applied_raw, "text/x-lean")
        method_raw = (inputs / "human-source-fidelity-method.json").read_bytes()
        review_raw = (inputs / "human-source-fidelity-review.json").read_bytes()
        retain("human-source-fidelity-method", "method", "human-source-fidelity-method.json", method_raw, "application/json")
        retain("human-source-fidelity-review", "tool_output", "human-source-fidelity-review.json", review_raw, "application/json")
        retain("source-author-review-body", "tool_output", "source-author-review.txt", (inputs / "source-author-review.txt").read_bytes(), "text/plain")
        retain("applied-review-response-body", "tool_output", "applied-review-response.txt", (inputs / "applied-review-response.txt").read_bytes(), "text/plain")
        retain("exact-head-approval-body", "tool_output", "exact-head-approval.txt", (inputs / "exact-head-approval.txt").read_bytes(), "text/plain")
    if kind == "external_advisory":
        retain("method-pr-audit", "method", "method-pr-audit.py", (REPO / "scripts/pr_audit.py").read_bytes(), "text/plain")
        source_records = [
            ("source-current", "source-current.txt", "https://www.erdosproblems.com/430"),
            ("source-history", "source-history.txt", "https://www.erdosproblems.com/430/history"),
            ("source-original", "source-original.txt", "ErdosGraham1980:p85"),
        ]
        for identifier, filename, _ in source_records:
            retain(identifier, "source_file", filename, (inputs / filename).read_bytes(), "text/plain")
        method_value = {
            "schema_version": "formal-conjectures.pr-audit-advisory-source-fidelity-method.v1",
            "name": "retained-advisory-source-fidelity-review",
            "version": "1",
            "operation": "compare_exact_head_declaration_to_retained_sources",
            "authority": "advisory_packet_preparation_only",
            "repository": repository_snapshot(case)["repository"],
            "pull_request": {
                "number": case["pr"],
                "base_commit_oid": case["base"]["commit_oid"],
                "head_commit_oid": case["head"]["commit_oid"],
            },
            "scope": {"path": case["change"]["path"], "declaration": "Erdos430.erdos_430"},
            "source_inputs": [
                {"id": identifier, "locator": locator, "root": roots[identifier]}
                for identifier, _, locator in source_records
            ],
            "required_edge_cases": ["empty_or_vacuous_predicates", "smallest_inputs", "stated_interval_endpoints"],
            "nonclaims": ["maintainer_disposition", "mathematical_truth", "merge_decision"],
        }
        method_raw = write_json(inputs / "source-fidelity-method.json", method_value)
        retain("source-fidelity-method", "method", "source-fidelity-method.json", method_raw, "application/json")
        for identifier, filename in (
            ("role-source-fidelity", "clean-room-source-fidelity.json"),
            ("role-lean-semantics", "clean-room-lean-semantics.json"),
            ("role-deterministic-verification", "clean-room-deterministic-verification.json"),
            ("role-adversarial-edge-cases", "clean-room-adversarial-edge-cases.json"),
        ):
            retain(identifier, "tool_output", filename, (inputs / filename).read_bytes(), "application/json")
        retain("source-fidelity-review", "tool_output", "source-fidelity-review.json", (inputs / "source-fidelity-review.json").read_bytes(), "application/json")
    if kind == "unavailable":
        procedure = {
            "schema_version": "formal-conjectures.pr-audit-packet-inspection-procedure.v1",
            "name": "comparator-packet-inspection",
            "version": "1",
            "operation": "inspect_retained_packet_inventory_only",
            "required_identities": ["exact executable bytes", "exact invocation", "package or toolchain lock", "raw execution result"],
            "executes_tool": False,
        }
        observation = {
            "schema_version": "formal-conjectures.pr-audit-packet-inspection-observation.v1",
            "procedure": "comparator-packet-inspection",
            "preparer": "codex_ai_packet_preparer",
            "inventory_scope": "retained PR-audit packet and reviewed baseline overlay",
            "missing_identities": ["exact executable bytes", "exact invocation", "package or toolchain lock", "raw execution result"],
            "outcome": "unavailable",
            "tool_resolution_attempted": False,
            "tool_invocation_attempted": False,
            "authority": "advisory_packet_preparation_only",
        }
        procedure_raw = write_json(inputs / "comparator-packet-procedure.json", procedure)
        observation_raw = write_json(inputs / "comparator-packet-observation.json", observation)
        retain("comparator-procedure", "method", "comparator-packet-procedure.json", procedure_raw, "application/json")
        retain("comparator-observation", "tool_output", "comparator-packet-observation.json", observation_raw, "application/json")
        invocation_procedure_raw = (REPO / "scripts/capture_missing_tool_invocation.py").read_bytes()
        invocation_result = capture_missing_tool_invocation(REPO)
        if (
            invocation_result["outcome"] != "unavailable"
            or invocation_result["error"] is None
            or invocation_result["error"]["kind"] != "executable_not_found"
        ):
            raise RuntimeError("Comparator availability preflight did not produce the required unavailable result")
        invocation_result_raw = write_json(
            inputs / "comparator-missing-tool-invocation.json", invocation_result
        )
        retain(
            "comparator-invocation-procedure", "method", "missing-tool-invocation-procedure.py",
            invocation_procedure_raw, "text/plain",
        )
        retain(
            "comparator-invocation-result", "tool_output", "comparator-missing-tool-invocation.json",
            invocation_result_raw, "application/json",
        )
        preparation_event_raw = write_json(inputs / "comparator-packet-preparation-event.json", {
            "schema_version": "formal-conjectures.pr-audit-preparation-event.v1",
            "artifact": "comparator-packet-observation.json",
            "prepared_at": "2026-08-12T21:00:00Z",
        })
        retain_provenance(
            "provenance-comparator-preparation", "comparator-packet-preparation-event.json",
            preparation_event_raw, "application/json",
        )
    if kind == "conditional":
        procedure_raw = (inputs / "metadata-review-procedure.json").read_bytes()
        observation_raw = (inputs / "metadata-review-observation.json").read_bytes()
        observation = json.loads(observation_raw)
        if observation != {
            "schema_version": "formal-conjectures.pr-audit-retained-review-observation.v1",
            "review_kind": "manual_retained_metadata_review",
            "preparer": "codex_ai_packet_preparer",
            "prepared_at": "2026-08-12T21:00:00Z",
            "authority": "advisory_packet_preparation_only",
            "independent": False,
            "basis": "exact retained PR-head source and exact retained linked-proof bytes",
            "head_blob_oid": case["change"]["head_blob_oid"],
            "head_blob_sha256": case["change"]["head_blob_sha256"],
            "proof_declaration": "Erdos427.erdos_427",
            "proof_kind": "lean4",
            "linked_proof_locator": "https://gist.githubusercontent.com/JohnEdwardJennings/e2c6ef0daab55857b7cc9d340de7af84/raw/8ff97800e38582c71246a238e7541a9d69488cbd/Erdos427.lean",
            "linked_proof_sha256": "sha256:792a4b5fab29e5855fbcb1115d54e28a054d8fcf7ee2bd5589834a73b387c052",
            "conditions": ["Erdos427.erdos_427.variants.shiu"],
        }:
            raise RuntimeError("retained conditional metadata review does not match frozen inputs")
        retain("metadata-review-procedure", "method", "metadata-review-procedure.json", procedure_raw, "application/json")
        retain_provenance(
            "provenance-metadata-review-preparation", "metadata-review-observation.json",
            observation_raw, "application/json",
        )
        linked_proof_raw = (inputs / "linked-proof.lean").read_bytes()
        linked_proof_locator = observation["linked_proof_locator"]
        retain("linked-proof", "source_file", "linked-proof.lean", linked_proof_raw, "text/x-lean")
        linked_proof_receipt = {
            "schema_version": "formal-conjectures.pr-audit-http-artifact-receipt.v1",
            "transport": "https",
            "method": "GET",
            "requested_url": linked_proof_locator,
            "final_url": linked_proof_locator,
            "acquired_at": CORE_ACQUIRED_AT,
            "response_sha256": sha256_digest(linked_proof_raw),
            "http_status": 200,
            "request_id": "not-retained",
            "limitations": ["The original transport request ID and response headers were not retained; the immutable URL, exact response bytes, and packet acquisition time are retained, but this is not a cryptographic host signature."],
        }
        linked_receipt_raw = write_json(inputs / "linked-proof-acquisition-receipt.json", linked_proof_receipt)
        retain_provenance(
            "provenance-linked-proof-acquisition", "linked-proof-acquisition-receipt.json",
            linked_receipt_raw, "application/json",
        )
    if kind in {"fidelity", "unavailable"}:
        workflow_raw = (inputs / "method-build-and-docs.yml").read_bytes()
        workflow_identity = BUILD_WORKFLOW_IDENTITIES[name]
        if sha256_digest(workflow_raw) != workflow_identity["sha256"]:
            raise RuntimeError(f"retained workflow bytes do not match exact PR head: {name}")
        if git_blob_oid(workflow_raw) != workflow_identity["git_blob_oid"]:
            raise RuntimeError(f"retained workflow Git blob does not match exact PR head: {name}")
        retain("method-workflow", "configuration", "method-build-and-docs.yml", workflow_raw, "text/plain")
        workflow_identity_record = {
            "schema_version": "formal-conjectures.pr-audit-git-object-identity.v1",
            "repository": "https://github.com/google-deepmind/formal-conjectures",
            "commit_oid": case["head"]["commit_oid"],
            "tree_oid": case["head"]["tree_oid"],
            "path": ".github/workflows/build-and-docs.yml",
            "blob_oid": workflow_identity["git_blob_oid"],
            "sha256": workflow_identity["sha256"],
            "authority": "retained_exact_head_git_object_identity",
        }
        workflow_identity_raw = write_json(inputs / "method-build-and-docs.identity.json", workflow_identity_record)
        retain("method-workflow-identity", "tool_output", "method-build-and-docs.identity.json", workflow_identity_raw, "application/json")
        workflow_url = (
            "https://raw.githubusercontent.com/google-deepmind/formal-conjectures/"
            f"{case['head']['commit_oid']}/.github/workflows/build-and-docs.yml"
        )
        workflow_receipt = {
            "schema_version": "formal-conjectures.pr-audit-http-artifact-receipt.v1",
            "transport": "https", "method": "GET", "requested_url": workflow_url,
            "final_url": workflow_url, "acquired_at": CORE_ACQUIRED_AT,
            "response_sha256": sha256_digest(workflow_raw), "http_status": 200,
            "request_id": "not-retained",
            "limitations": ["The original transport request ID and response headers were not retained; the immutable commit-qualified raw URL, exact response bytes, and packet acquisition time are retained, but this is not a cryptographic GitHub signature."],
        }
        workflow_receipt_raw = write_json(inputs / "method-build-and-docs.acquisition-receipt.json", workflow_receipt)
        retain_provenance(
            "provenance-workflow-acquisition", "method-build-and-docs.acquisition-receipt.json",
            workflow_receipt_raw, "application/json",
        )
        job_raw = (inputs / "github-job-response.json").read_bytes().removesuffix(b"\n")
        job = json.loads(job_raw)
        job_id = 60275340706 if kind == "fidelity" else 75175625578
        if job["id"] != job_id or job["head_sha"] != case["head"]["commit_oid"] or job["conclusion"] != "success":
            raise RuntimeError(f"retained GitHub job response does not match frozen check: {name}")
        job_result = {
            "schema_version": "formal-conjectures.pr-audit-github-job-result.v1",
            "job_id": job["id"],
            "run_id": job["run_id"],
            "head_sha": job["head_sha"],
            "workflow_name": job["workflow_name"],
            "job_name": job["name"],
            "conclusion": job["conclusion"],
            "run_attempt": job["run_attempt"],
            "job_url": job["html_url"],
        }
        job_result_raw = write_json(inputs / "github-job-result.json", job_result)
        retain("build-job", "tool_output", "github-job-result.json", job_result_raw, "application/json")
        retain_provenance(
            "provenance-job-response", "github-job-response.json", job_raw,
            "application/vnd.github+json",
        )
        job_receipt = {
            "schema_version": "formal-conjectures.pr-audit-job-acquisition-receipt.v1",
            "transport": "https",
            "method": "GET",
            "endpoint": job["url"],
            "owner": "google-deepmind",
            "repository": "formal-conjectures",
            "job_id": job["id"],
            "run_id": job["run_id"],
            "acquired_at": CORE_ACQUIRED_AT,
            "response_sha256": sha256_digest(job_raw),
            "http_status": 200,
            "request_id": "not-retained",
            "trigger_event": "not-retained",
            "limitations": [
                "The original transport request ID and workflow trigger event were not retained; endpoint, exact response bytes, job/run identity, and packet acquisition time are retained, but this is not a cryptographic GitHub signature."
            ],
        }
        job_receipt_raw = write_json(inputs / "github-job-acquisition-receipt.json", job_receipt)
        retain_provenance(
            "provenance-job-acquisition",
            "github-job-acquisition-receipt.json", job_receipt_raw, "application/json",
        )
    if kind in {"fidelity", "vacuity"}:
        guide_raw = (inputs / "review-guide.md").read_bytes()
        if sha256_digest(guide_raw) != REVIEW_GUIDE_ROOT:
            raise RuntimeError("review guide bytes do not match frozen revision identity")
        if git_blob_oid(guide_raw) != REVIEW_GUIDE_BLOB_OID:
            raise RuntimeError("review guide Git blob does not match frozen revision identity")
        retain("review-guide", "method", "review-guide.md", guide_raw, "text/plain")
        guide_identity = {
            "schema_version": "formal-conjectures.pr-audit-git-object-identity.v1",
            "repository": "https://github.com/google-deepmind/formal-conjectures",
            "commit_oid": REVIEW_GUIDE_REVISION,
            "path": "REVIEW_MATH.md",
            "blob_oid": REVIEW_GUIDE_BLOB_OID,
            "sha256": REVIEW_GUIDE_ROOT,
            "authority": "retained_commit_qualified_git_object_identity",
        }
        guide_identity_raw = write_json(inputs / "review-guide.identity.json", guide_identity)
        retain("review-guide-identity", "tool_output", "review-guide.identity.json", guide_identity_raw, "application/json")
        guide_url = (
            "https://raw.githubusercontent.com/google-deepmind/formal-conjectures/"
            f"{REVIEW_GUIDE_REVISION}/REVIEW_MATH.md"
        )
        guide_receipt = {
            "schema_version": "formal-conjectures.pr-audit-http-artifact-receipt.v1",
            "transport": "https", "method": "GET", "requested_url": guide_url,
            "final_url": guide_url, "acquired_at": CORE_ACQUIRED_AT,
            "response_sha256": sha256_digest(guide_raw), "http_status": 200,
            "request_id": "not-retained",
            "limitations": ["The original transport request ID and response headers were not retained; the immutable commit-qualified raw URL, exact response bytes, and packet acquisition time are retained, but this is not a cryptographic GitHub signature."],
        }
        guide_receipt_raw = write_json(inputs / "review-guide.acquisition-receipt.json", guide_receipt)
        retain_provenance(
            "provenance-review-guide-acquisition", "review-guide.acquisition-receipt.json",
            guide_receipt_raw, "application/json",
        )
        review = {
            "schema_version": "formal-conjectures.pr-audit-human-review-observation.v1",
            "guide_revision": REVIEW_GUIDE_REVISION,
            "guide_sha256": REVIEW_GUIDE_ROOT,
            "scope": "L123-L129" if kind == "fidelity" else "L70-L84",
            "head_commit_oid": case["head"]["commit_oid"],
            "head_blob_oid": case["change"]["head_blob_oid"],
            "head_blob_sha256": case["change"]["head_blob_sha256"],
            "finding": (
                "answer slot is under C and n binders; le_refl witnesses instance-local choice"
                if kind == "fidelity"
                else "c=2,n=100 requires 20000 edges while a simple graph has at most 4950"
            ),
            "preparer": "codex_ai_packet_preparer",
            "prepared_at": "2026-08-12T21:00:00Z",
            "authority": "advisory_packet_preparation_only",
            "independent": False,
            "basis_author": "williamblair",
            "basis_revision": REVIEW_GUIDE_REVISION,
        }
        review_raw = write_json(inputs / "review-observation.json", review)
        retain_provenance(
            "provenance-semantic-review-preparation", "review-observation.json",
            review_raw, "application/json",
        )
    return artifacts, provenance_artifacts, roots


def manifest(version: str, artifacts: list[dict[str, str]], observed_at: str | None = None) -> dict[str, Any]:
    normalized = sorted(artifacts, key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]))
    value: dict[str, Any] = {"schema_version": version, "artifact_root": content_root({"artifacts": normalized}), "artifacts": normalized}
    if observed_at is not None:
        value["observed_at"] = observed_at
    return value


def attach_typed_results(
    directory: Path,
    case: dict[str, Any],
    checks_value: dict[str, Any],
    artifacts: list[dict[str, str]],
) -> None:
    inputs = directory / "inputs"
    for check in checks_value["checks"]:
        if check["kind"] == "semantic" and check["role"] == "independent":
            producer = {
                "kind": "human_reviewer",
                "id": "jarfo",
                "authority": "independent_human_review",
                "independent": True,
            }
        elif check["kind"] == "semantic" or check["mode"] == "human_review":
            producer = {
                "kind": "ai_review_preparer",
                "id": "codex_ai_packet_preparer",
                "authority": "advisory_packet_preparation_only",
                "independent": False,
            }
        else:
            producer = {
                "kind": "retained_external_result" if check["property"] == "lean-build" else "deterministic_adapter",
                "id": "github_actions" if check["property"] == "lean-build" else "formal_conjectures_pr_audit",
                "authority": "producer_evidence_only",
                "independent": False,
            }
        if check["kind"] == "semantic":
            finding = check["evidence"][0]
            semantic_review: dict[str, Any] | None = {
                "preparer": producer["id"],
                "reviewer": producer["id"] if producer["independent"] else None,
                "authority": producer["authority"],
                "independent": producer["independent"],
                "outcome": check["outcome"],
                "severity": check["severity"],
                "finding": finding["statement"],
                "witness": finding["witness"],
                "head_commit_oid": case["head"]["commit_oid"],
                "head_blob_oid": case["change"]["head_blob_oid"],
                "source_root": case["change"]["head_blob_sha256"],
                "scope": check["scope"],
                "declarations": check["scope"]["declarations"],
                "method": check["implementation"],
            }
        else:
            semantic_review = None
        result = {
            "schema_version": "formal-conjectures.pr-audit-typed-result.v1",
            "result_id": check["id"],
            "check": {key: value for key, value in check.items() if key != "inputs"},
            "artifacts": check["inputs"],
            "producer": producer,
            "semantic_review": semantic_review,
        }
        filename = f"typed-result-{check['id']}.json"
        raw = write_json(inputs / filename, result)
        artifact_id = f"typed-result-{check['id']}"
        artifacts.append(descriptor(artifact_id, "typed_result", f"inputs/{filename}", raw))
        check["inputs"].append(check_input(
            "typed-result",
            artifact_id,
            "typed-result",
            f"typed-result/{producer['kind']}/{producer['id']}",
            sha256_digest(raw),
        ))
        check["inputs"] = sorted(
            check["inputs"],
            key=lambda item: (item["id"], item["artifact_id"], item["kind"], item["locator"], item["root"]),
        )


def build_case(name: str, case: dict[str, Any], generator: dict[str, Any]) -> None:
    directory = FIXTURES / name
    inputs = directory / "inputs"
    owner, repository_name, _ = repository_identity(case)
    generator_raw = write_json(inputs / "generator.json", generator)
    repository_raw = write_json(inputs / "repository.json", repository_snapshot(case))
    retained_artifacts, provenance_artifacts, roots = retained_core_artifacts(name, case)
    checks_value = checks_for(case, roots)
    checks_value["checks"] = sorted(
        checks_value["checks"],
        key=lambda item: (item["id"], item["property"], item["role"], item["outcome"]),
    )
    for check in checks_value["checks"]:
        check["inputs"] = sorted(check["inputs"], key=lambda item: (item["id"], item["artifact_id"], item["kind"], item["locator"], item["root"]))
        check["does_not_establish"] = sorted(set(check["does_not_establish"]))
        check["limitations"] = sorted(set(check["limitations"]))
    attach_typed_results(directory, case, checks_value, retained_artifacts)
    checks_raw = write_json(inputs / "checks.json", checks_value)
    observation_path = inputs / "github-graphql-response.json"
    observation_raw = observation_path.read_bytes().removesuffix(b"\n")
    if observation_path.read_bytes() != observation_raw:
        observation_path.write_bytes(observation_raw)
    parse_value = observation_source(case)
    if json.loads(observation_raw) != parse_value:
        raise RuntimeError(f"retained GitHub GraphQL response does not match frozen observation: {name}")
    query_raw = GRAPHQL_OPERATION.encode("utf-8")
    (inputs / "github-graphql-query.graphql").write_bytes(query_raw)
    receipt = {
        "schema_version": "formal-conjectures.pr-audit-acquisition-receipt.v1",
        "transport": "https",
        "endpoint": "https://api.github.com/graphql",
        "operation_name": "PullRequestAuditObservation",
        "variables": {"owner": owner, "name": repository_name, "number": case["pr"]},
        "acquired_at": OBSERVATION_RECEIPTS[name]["acquired_at"],
        "response_sha256": sha256_digest(observation_raw),
        "query_sha256": sha256_digest(query_raw),
        "http_status": 200,
        "request_id": OBSERVATION_RECEIPTS[name]["request_id"],
        "limitations": ["The receipt records public GitHub response headers and bytes; it is not a cryptographic GitHub signature."],
    }
    receipt_raw = write_json(inputs / "github-acquisition-receipt.json", receipt)
    core_artifacts = [
        descriptor("generator", "generator_identity", "inputs/generator.json", generator_raw),
        descriptor("repository", "repository_snapshot", "inputs/repository.json", repository_raw),
        descriptor("checks", "check_results", "inputs/checks.json", checks_raw),
        *retained_artifacts,
    ]
    observation_artifacts = [
        descriptor("generator", "generator_identity", "inputs/generator.json", generator_raw),
        descriptor("github-observation", "authoritative_observation", "inputs/github-graphql-response.json", observation_raw, "application/vnd.github+json"),
        descriptor("github-query", "query", "inputs/github-graphql-query.graphql", query_raw, "text/plain"),
        descriptor("github-receipt", "acquisition_receipt", "inputs/github-acquisition-receipt.json", receipt_raw),
        *provenance_artifacts,
    ]
    core_manifest_path = directory / "core-input.json"
    observation_manifest_path = directory / "observation-input.json"
    write_json(core_manifest_path, manifest("formal-conjectures.pr-audit-input.v1", core_artifacts))
    write_json(
        observation_manifest_path,
        manifest("formal-conjectures.pr-audit-observation-input.v1", observation_artifacts, OBSERVATION_RECEIPTS[name]["acquired_at"]),
    )
    core_path = directory / "expected-core.json"
    write_canonical(core_path, generate_core(core_manifest_path), sidecar=True)
    write_canonical(
        directory / "expected-observation.json",
        generate_observation(observation_manifest_path, core_path),
        sidecar=True,
    )


def main() -> None:
    generator = generator_identity()
    for name, case in CASES.items():
        build_case(name, case, generator)
    clean_core = generate_core(FIXTURES / "clean-source-faithful-min-modulus-4829" / "core-input.json")
    (PACKET / "example-pr-4829.md").write_text(render_markdown(clean_core), encoding="utf-8")


if __name__ == "__main__":
    main()
