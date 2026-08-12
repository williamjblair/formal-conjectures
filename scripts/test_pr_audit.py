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

"""Regression tests for deterministic, offline pull-request audit records."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
import unicodedata
from pathlib import Path

from pr_audit import (
    AuditError,
    SUPPORTED_PROPERTIES,
    _validate_checks,
    canonical_bytes,
    classify_proof_target,
    content_root,
    generate_core,
    generate_observation,
    git_blob_oid,
    parse_json_bytes,
    render_markdown,
    sha256_digest,
    validate_core,
    validate_observation,
    write_canonical,
)


REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "audit" / "pr-audit-v1" / "fixtures"
NAMES = (
    "clean-candidate-dean-4878",
    "conditional-erdos-427-4884",
    "fidelity-erdos-887-1237",
    "vacuity-erdos-80-4830",
    "unavailable-rupert-3959",
)


def load(path: Path):
    return parse_json_bytes(path.read_bytes(), label=str(path))


def framed(value) -> bytes:
    return canonical_bytes(value) + b"\n"


def update_manifest_artifact(directory: Path, manifest_name: str, artifact_path: str) -> None:
    manifest_path = directory / manifest_name
    manifest = load(manifest_path)
    raw = (directory / artifact_path).read_bytes()
    found = False
    for descriptor in manifest["artifacts"]:
        if descriptor["path"] == artifact_path:
            descriptor["sha256"] = sha256_digest(raw)
            found = True
    if not found:
        raise AssertionError(f"artifact not in manifest: {artifact_path}")
    manifest["artifact_root"] = content_root({"artifacts": sorted(
        manifest["artifacts"],
        key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]),
    )})
    write_canonical(manifest_path, manifest)


def rewrite_checks_with_typed_results(directory: Path, transform) -> None:
    checks_path = directory / "inputs" / "checks.json"
    checks_value = load(checks_path)
    transform(checks_value)
    checks_value["checks"] = _validate_checks(checks_value)
    manifest_path = directory / "core-input.json"
    manifest = load(manifest_path)
    descriptors = {item["id"]: item for item in manifest["artifacts"]}
    for check in checks_value["checks"]:
        result_input = next(item for item in check["inputs"] if item["kind"] == "typed-result")
        result_descriptor = descriptors[result_input["artifact_id"]]
        result_path = directory / result_descriptor["path"]
        result = load(result_path)
        result["result_id"] = check["id"]
        result["check"] = {key: value for key, value in check.items() if key != "inputs"}
        result["artifacts"] = [item for item in check["inputs"] if item["kind"] != "typed-result"]
        if result["semantic_review"] is not None:
            review = result["semantic_review"]
            review.update({
                "outcome": check["outcome"],
                "severity": check["severity"],
                "finding": check["evidence"][0]["statement"],
                "witness": check["evidence"][0]["witness"],
                "scope": check["scope"],
                "declarations": check["scope"]["declarations"],
                "method": check["implementation"],
            })
        write_canonical(result_path, result)
        result_descriptor["sha256"] = sha256_digest(result_path.read_bytes())
        result_input["root"] = result_descriptor["sha256"]
    write_canonical(checks_path, checks_value)
    next(item for item in manifest["artifacts"] if item["id"] == "checks")["sha256"] = sha256_digest(checks_path.read_bytes())
    manifest["artifacts"] = sorted(
        manifest["artifacts"],
        key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]),
    )
    manifest["artifact_root"] = content_root({"artifacts": manifest["artifacts"]})
    write_canonical(manifest_path, manifest)


def rewrite_typed_result(directory: Path, check_id: str, transform, *, sync_relation: bool = True) -> None:
    manifest_path = directory / "core-input.json"
    manifest = load(manifest_path)
    checks_path = directory / "inputs" / "checks.json"
    checks = load(checks_path)
    check = next(item for item in checks["checks"] if item["id"] == check_id)
    relation = next(item for item in check["inputs"] if item["kind"] == "typed-result")
    descriptor = next(item for item in manifest["artifacts"] if item["id"] == relation["artifact_id"])
    result_path = directory / descriptor["path"]
    result = load(result_path)
    transform(result)
    write_canonical(result_path, result)
    descriptor["sha256"] = sha256_digest(result_path.read_bytes())
    if sync_relation:
        relation["root"] = descriptor["sha256"]
        write_canonical(checks_path, checks)
        next(item for item in manifest["artifacts"] if item["id"] == "checks")["sha256"] = sha256_digest(
            checks_path.read_bytes()
        )
    manifest["artifacts"] = sorted(
        manifest["artifacts"],
        key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]),
    )
    manifest["artifact_root"] = content_root({"artifacts": manifest["artifacts"]})
    write_canonical(manifest_path, manifest)


class CanonicalJsonTest(unittest.TestCase):

    def test_whitespace_and_object_order_are_canonically_equivalent(self):
        left = parse_json_bytes(b'{ "b" : 2, "a": [true, null] }')
        right = parse_json_bytes(b'{"a":[true,null],"b":2}')
        self.assertEqual(canonical_bytes(left), canonical_bytes(right))
        self.assertEqual(canonical_bytes(left), b'{"a":[true,null],"b":2}')

    def test_nfc_and_nfd_strings_remain_distinct(self):
        nfc = unicodedata.normalize("NFC", "e\u0301")
        nfd = unicodedata.normalize("NFD", "é")
        self.assertNotEqual(nfc, nfd)
        self.assertNotEqual(canonical_bytes({"value": nfc}), canonical_bytes({"value": nfd}))

    def test_keys_use_utf16_code_unit_order(self):
        # U+1F600 begins with surrogate D83D, which sorts before BMP U+E000.
        value = {"\ue000": 2, "😀": 1}
        self.assertEqual(canonical_bytes(value), '{"😀":1,"\ue000":2}'.encode())

    def test_canonical_bytes_are_unframed(self):
        self.assertEqual(canonical_bytes({"a": 1}), b'{"a":1}')

    def test_jcs_control_character_escaping_vector(self):
        self.assertEqual(
            canonical_bytes({"x": "\b\t\n\f\r\"\\\x00"}),
            b'{"x":"\\b\\t\\n\\f\\r\\"\\\\\\u0000"}',
        )

    def test_rejects_floats_out_of_range_integers_and_lone_surrogates(self):
        with self.assertRaises(AuditError):
            parse_json_bytes(b'{"x":1.5}')
        with self.assertRaises(AuditError):
            parse_json_bytes(b'{"x":9007199254740992}')
        with self.assertRaises(AuditError):
            canonical_bytes({"x": "\ud800"})

    def test_rejects_duplicate_keys_and_nonfinite_numbers(self):
        with self.assertRaises(AuditError):
            parse_json_bytes(b'{"x":1,"x":2}')
        with self.assertRaises(AuditError):
            parse_json_bytes(b'{"x":NaN}')
        with self.assertRaises(AuditError):
            parse_json_bytes(b'{"x":Infinity}')
        with self.assertRaises(AuditError):
            parse_json_bytes(b'{"x":-Infinity}')

    def test_rejects_excessive_json_depth(self):
        with self.assertRaisesRegex(AuditError, "nesting exceeds"):
            parse_json_bytes(("[" * 65 + "0" + "]" * 65).encode())

    def test_rfc3339_semantic_timestamp_validation(self):
        from pr_audit import _expect_timestamp
        self.assertEqual(_expect_timestamp("2024-02-29T23:59:59Z", "time"), "2024-02-29T23:59:59Z")
        self.assertEqual(_expect_timestamp("2026-08-12T20:25:18-04:00", "time"), "2026-08-12T20:25:18-04:00")
        for invalid in ("2026-02-30T20:00:00Z", "2026-99-99T99:99:99Z", "2026-08-12T25:61:61+99:99"):
            with self.subTest(invalid=invalid), self.assertRaises(AuditError):
                _expect_timestamp(invalid, "time")


class FrozenFixtureTest(unittest.TestCase):

    def test_all_five_fixtures_reproduce_exact_bytes_and_sidecars(self):
        for name in NAMES:
            with self.subTest(name=name):
                directory = FIXTURES / name
                core = generate_core(directory / "core-input.json")
                expected_core = directory / "expected-core.json"
                self.assertEqual(framed(core), expected_core.read_bytes())
                self.assertEqual(
                    expected_core.with_name(expected_core.name + ".sha256").read_text(),
                    sha256_digest(expected_core.read_bytes()) + "\n",
                )
                observation = generate_observation(
                    directory / "observation-input.json", expected_core
                )
                expected_observation = directory / "expected-observation.json"
                self.assertEqual(framed(observation), expected_observation.read_bytes())
                self.assertEqual(
                    expected_observation.with_name(expected_observation.name + ".sha256").read_text(),
                    sha256_digest(expected_observation.read_bytes()) + "\n",
                )

    def test_generator_identity_is_complete_and_matches_executable_overlay(self):
        core = load(FIXTURES / NAMES[0] / "expected-core.json")
        source = core["generator"]["source"]
        self.assertEqual(source["baseline"], {
            "commit_oid": "c9052e8577118ed0ada54462bd4ef1f3beff37d6",
            "tree_oid": "864ee77ee26a7cbd85b30558f8d9d2036f8717ed",
        })
        files = source["overlay"]["files"]
        self.assertEqual(source["overlay"]["root"], content_root({"files": files}))
        self.assertEqual(
            {entry["path"] for entry in files},
            {
                "scripts/pr_audit.py",
                "scripts/generate_pr_audit.py",
                "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit.v1.schema.json",
                "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit-observation.v1.schema.json",
            },
        )
        for entry in files:
            self.assertEqual(entry["sha256"], sha256_digest((REPO / entry["path"]).read_bytes()))

    def test_generator_overlay_claim_cannot_drift_from_executing_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "fixture"
            shutil.copytree(FIXTURES / "conditional-erdos-427-4884", directory)
            generator_path = directory / "inputs" / "generator.json"
            generator = load(generator_path)
            generator["source"]["overlay"]["files"][0]["sha256"] = "sha256:" + "0" * 64
            generator["source"]["overlay"]["root"] = content_root({
                "files": sorted(generator["source"]["overlay"]["files"], key=lambda item: item["path"])
            })
            write_canonical(generator_path, generator)
            update_manifest_artifact(directory, "core-input.json", "inputs/generator.json")
            with self.assertRaisesRegex(AuditError, "does not match executing local bytes"):
                generate_core(directory / "core-input.json")

    def test_generator_baseline_claim_is_bound_during_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "fixture"
            shutil.copytree(FIXTURES / "conditional-erdos-427-4884", directory)
            generator_path = directory / "inputs" / "generator.json"
            generator = load(generator_path)
            generator["source"]["baseline"]["commit_oid"] = "0" * 40
            write_canonical(generator_path, generator)
            update_manifest_artifact(directory, "core-input.json", "inputs/generator.json")
            with self.assertRaisesRegex(AuditError, "reviewed local build identity"):
                generate_core(directory / "core-input.json")

    def test_generator_name_and_version_are_bound_during_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "fixture"
            shutil.copytree(FIXTURES / "conditional-erdos-427-4884", directory)
            generator_path = directory / "inputs" / "generator.json"
            generator = load(generator_path)
            generator["name"] = "forged-generator"
            generator["version"] = "9"
            write_canonical(generator_path, generator)
            update_manifest_artifact(directory, "core-input.json", "inputs/generator.json")
            with self.assertRaisesRegex(AuditError, "generator metadata"):
                generate_core(directory / "core-input.json")

    def test_every_fixture_has_a_complete_retained_input_inventory(self):
        for name in NAMES:
            with self.subTest(name=name):
                directory = FIXTURES / name
                manifest = load(directory / "core-input.json")
                roles = {artifact["role"] for artifact in manifest["artifacts"]}
                self.assertTrue({"generator_identity", "repository_snapshot", "check_results", "source_file"}.issubset(roles))
                self.assertTrue(bool(roles & {"method", "configuration"}))
                artifacts = {artifact["id"]: artifact for artifact in manifest["artifacts"]}
                core = generate_core(directory / "core-input.json")
                referenced = {
                    input_record["artifact_id"]
                    for check in core["checks"]
                    for input_record in check["inputs"]
                }
                expected = {
                    identifier for identifier, artifact in artifacts.items()
                    if artifact["role"] in {"source_file", "method", "configuration", "tool_output", "query", "typed_result"}
                }
                self.assertEqual(referenced, expected)
                for identifier in referenced:
                    self.assertEqual(
                        sha256_digest((directory / artifacts[identifier]["path"]).read_bytes()),
                        artifacts[identifier]["sha256"],
                    )
                observation_manifest = load(directory / "observation-input.json")
                observation_roles = {artifact["role"] for artifact in observation_manifest["artifacts"]}
                self.assertEqual(
                    observation_roles,
                    {
                        "generator_identity", "authoritative_observation", "acquisition_receipt",
                        "query", "provenance_event",
                    },
                )
                observation = generate_observation(
                    directory / "observation-input.json", directory / "expected-core.json"
                )
                self.assertEqual(observation["source"]["endpoint"], "https://api.github.com/graphql")
                self.assertEqual(observation["source"]["operation_name"], "PullRequestAuditObservation")

    def test_every_supported_property_has_one_typed_retained_result(self):
        covered_properties: set[str] = set()
        for name in NAMES:
            with self.subTest(name=name):
                directory = FIXTURES / name
                manifest = load(directory / "core-input.json")
                descriptors = {item["id"]: item for item in manifest["artifacts"]}
                checks = load(directory / "inputs" / "checks.json")["checks"]
                for check in checks:
                    covered_properties.add(check["property"])
                    relations = [item for item in check["inputs"] if item["kind"] == "typed-result"]
                    self.assertEqual(len(relations), 1)
                    descriptor = descriptors[relations[0]["artifact_id"]]
                    self.assertEqual(descriptor["role"], "typed_result")
                    self.assertEqual(relations[0]["root"], descriptor["sha256"])
                    result = load(directory / descriptor["path"])
                    self.assertEqual(result["result_id"], check["id"])
                    self.assertEqual(result["check"], {key: value for key, value in check.items() if key != "inputs"})
                    self.assertEqual(result["artifacts"], [item for item in check["inputs"] if item["kind"] != "typed-result"])
        self.assertEqual(covered_properties, set(SUPPORTED_PROPERTIES))

    def test_build_claims_are_backed_by_raw_authoritative_job_responses(self):
        cases = {
            "fidelity-erdos-887-1237": (60275340706, "288608562e684a2f3c97ba0ce960a2649a71370b"),
            "unavailable-rupert-3959": (75175625578, "868cc092aeb713dbf8027883c5fa575e550cfae9"),
        }
        for name, (job_id, head_oid) in cases.items():
            with self.subTest(name=name):
                directory = FIXTURES / name
                response = load(directory / "inputs" / "github-job-response.json")
                self.assertEqual(response["id"], job_id)
                self.assertEqual(response["head_sha"], head_oid)
                self.assertEqual(response["name"], "Build project")
                self.assertEqual(response["status"], "completed")
                self.assertEqual(response["conclusion"], "success")

    def test_methods_are_exact_historical_head_bytes(self):
        workflows = {
            "fidelity-erdos-887-1237": (
                "9b972a49fe75ece90ea984cf879d019d75d0b537",
                "sha256:9654c8eff1eb84976e26b527f7dadc8c70267c9ed70fb9300e9e3fe8c2913202",
            ),
            "unavailable-rupert-3959": (
                "d621cc1d9221102d360b257e7add45234fd19701",
                "sha256:8841d7fe334bc84abe5d72ae923be08510e5bf661edfc4e15ed135abffaac39c",
            ),
        }
        for name, (blob_oid, root) in workflows.items():
            with self.subTest(name=name):
                raw = (FIXTURES / name / "inputs" / "method-build-and-docs.yml").read_bytes()
                self.assertEqual(git_blob_oid(raw), blob_oid)
                self.assertEqual(sha256_digest(raw), root)
                core = generate_core(FIXTURES / name / "core-input.json")
                check = next(item for item in core["checks"] if item["property"] == "lean-build")
                self.assertEqual(check["implementation"]["root"], root)
                self.assertTrue(check["implementation"]["locator"].endswith(core["repository"]["head"]["commit_oid"]))

        conditional = generate_core(FIXTURES / "conditional-erdos-427-4884" / "core-input.json")
        self.assertEqual(conditional["checks"][0]["mode"], "human_review")
        self.assertIn("manual metadata review", conditional["checks"][0]["limitations"][0])

        for name in ("fidelity-erdos-887-1237", "vacuity-erdos-80-4830"):
            raw = (FIXTURES / name / "inputs" / "review-guide.md").read_bytes()
            self.assertEqual(git_blob_oid(raw), "de2bf123d126cd1803c1b47866b776420eda2f6b")
            self.assertEqual(sha256_digest(raw), "sha256:bc10a92b25047a46225221c7ecb090a5b3e9ac174fd44f6d1f6042d7c6971700")

    def test_five_fixture_distinctions(self):
        cores = {name: generate_core(FIXTURES / name / "core-input.json") for name in NAMES}
        self.assertEqual(cores["clean-candidate-dean-4878"]["disposition"]["advisory"], "inconclusive")
        self.assertEqual(cores["conditional-erdos-427-4884"]["disposition"]["advisory"], "inconclusive")
        self.assertEqual(cores["fidelity-erdos-887-1237"]["disposition"]["advisory"], "needs_revision")
        self.assertEqual(cores["vacuity-erdos-80-4830"]["disposition"]["advisory"], "needs_revision")
        self.assertEqual(cores["unavailable-rupert-3959"]["disposition"]["advisory"], "unavailable")
        self.assertIn("answer-slot-scope-fidelity", {check["property"] for check in cores["fidelity-erdos-887-1237"]["checks"]})
        self.assertEqual(cores["vacuity-erdos-80-4830"]["checks"][0]["property"], "hypothesis-satisfiability")

    def test_unavailable_is_not_fail(self):
        unavailable = generate_core(FIXTURES / "unavailable-rupert-3959" / "core-input.json")
        failure = generate_core(FIXTURES / "fidelity-erdos-887-1237" / "core-input.json")
        unavailable_check = next(check for check in unavailable["checks"] if check["property"] == "exact-formal-proof-artifact-identity")
        self.assertEqual(unavailable_check["property"], "exact-formal-proof-artifact-identity")
        self.assertNotEqual(unavailable["disposition"]["advisory"], failure["disposition"]["advisory"])
        self.assertIn("proof_failure", unavailable_check["does_not_establish"])
        comparator = next(check for check in unavailable["checks"] if check["property"] == "comparator-packet-identity")
        self.assertEqual(comparator["outcome"], "unavailable")
        self.assertIn("missing-tool execution gate remains unmet", comparator["limitations"][0])

    def test_proof_target_negative_controls(self):
        self.assertEqual(
            classify_proof_target(
                "lean4",
                "https://www.erdosproblems.com/forum/thread/38#post-6131",
                ["https://gist.githubusercontent.com/madeve-unipi/690d2bd8f6e8304ba8b456f9db559747/raw/481e3c35de8dce7af70ec440e4e121f084a61860/Erdos38.lean"],
            ),
            "resolvable",
        )
        self.assertEqual(classify_proof_target("formal_conjectures", ""), "in_source")
        self.assertEqual(
            classify_proof_target("lean4", "https://github.com/jcreedcmu/Noperthedron"),
            "unavailable",
        )

    def test_error_is_supported_and_maps_to_inconclusive_not_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "fixture"
            shutil.copytree(FIXTURES / "conditional-erdos-427-4884", directory)
            rewrite_checks_with_typed_results(directory, lambda checks: checks["checks"][0].update({
                "outcome": "error", "severity": "none"
            }))
            core = generate_core(directory / "core-input.json")
            self.assertEqual(core["checks"][0]["outcome"], "error")
            self.assertEqual(core["disposition"]["advisory"], "inconclusive")

    def test_unrooted_model_error_is_refused_and_deterministic_core_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "fixture"
            shutil.copytree(FIXTURES / "conditional-erdos-427-4884", directory)
            expected = generate_core(directory / "core-input.json")
            checks_path = directory / "inputs" / "checks.json"
            checks = load(checks_path)
            deterministic = copy.deepcopy(checks["checks"][0])
            model = copy.deepcopy(deterministic)
            model.update({
                "id": "advisory-model-review",
                "kind": "semantic",
                "mode": "comparator",
                "property": "model-source-review",
                "role": "advisory",
                "outcome": "error",
                "severity": "none",
            })
            checks["checks"].append(model)
            write_canonical(checks_path, checks)
            update_manifest_artifact(directory, "core-input.json", "inputs/checks.json")
            with self.assertRaisesRegex(AuditError, "unsupported or unimplemented"):
                generate_core(directory / "core-input.json")
            self.assertEqual(
                generate_core(FIXTURES / "conditional-erdos-427-4884" / "core-input.json"),
                expected,
            )

    def test_conditional_assumption_and_complete_proof_tuple_are_retained(self):
        core = generate_core(FIXTURES / "conditional-erdos-427-4884" / "core-input.json")
        check = core["checks"][0]
        self.assertEqual(check["assumptions"], check["conditions"])
        self.assertEqual(check["proofs"][0]["conditions"], check["assumptions"])
        self.assertEqual(check["proofs"][0]["declaration"], "Erdos427.erdos_427")
        self.assertEqual(check["proofs"][0]["kind"], "lean4")
        self.assertTrue(check["proofs"][0]["locator"].startswith("https://gist.githubusercontent.com/"))

    def test_fidelity_fixture_is_exact_head_and_has_no_later_drift(self):
        core = generate_core(FIXTURES / "fidelity-erdos-887-1237" / "core-input.json")
        self.assertEqual(core["repository"]["pull_request"]["number"], 1237)
        self.assertEqual(core["repository"]["head"]["commit_oid"], "288608562e684a2f3c97ba0ce960a2649a71370b")
        self.assertEqual(core["repository"]["changes"][0]["head_blob_oid"], "6feb58b9272ce638aba6da5ca7ee8ebf7785e0b8")
        encoded = canonical_bytes(core)
        for drifted_identity in (b"5cbe3d57171b0a9f733e5052e041ee40c1e98fac", b"433a5e215d741e43455a41bde59ae82b26edb73e", b"59f30", b"b6e079"):
            self.assertNotIn(drifted_identity, encoded)

    def test_disposition_nonclaims_are_complete(self):
        core = generate_core(FIXTURES / "clean-candidate-dean-4878" / "core-input.json")
        self.assertEqual(core["disposition"]["nonclaims"], [
            "not_a_claim_of_mathematical_truth",
            "not_a_claim_that_unlisted_checks_ran",
            "not_an_acceptance_or_merge_decision",
            "not_source_fidelity_beyond_the_listed_checks",
        ])
        for name in NAMES:
            for check in generate_core(FIXTURES / name / "core-input.json")["checks"]:
                self.assertIn("does_not_establish", check)
                self.assertNotIn("nonclaims", check)
        validate_core(core)


class MutationAndRefusalTest(unittest.TestCase):

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "fixture"
        shutil.copytree(FIXTURES / "conditional-erdos-427-4884", self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def rewrite_checks(self, transform, *, sync_typed_result: bool = False) -> None:
        if sync_typed_result:
            rewrite_checks_with_typed_results(self.directory, transform)
            return
        path = self.directory / "inputs" / "checks.json"
        value = load(path)
        transform(value)
        write_canonical(path, value)
        update_manifest_artifact(self.directory, "core-input.json", "inputs/checks.json")

    def rewrite_observation(self, transform) -> None:
        path = self.directory / "inputs" / "github-graphql-response.json"
        value = load(path)
        transform(value)
        write_canonical(path, value)
        update_manifest_artifact(
            self.directory, "observation-input.json", "inputs/github-graphql-response.json"
        )

    def test_same_input_is_byte_deterministic(self):
        first = generate_core(self.directory / "core-input.json")
        second = generate_core(self.directory / "core-input.json")
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))

    def test_core_input_change_changes_core_root(self):
        before = generate_core(self.directory / "core-input.json")
        proof_path = self.directory / "inputs" / "linked-proof.lean"
        proof_path.write_bytes(proof_path.read_bytes() + b"\n")
        update_manifest_artifact(self.directory, "core-input.json", "inputs/linked-proof.lean")
        proof_root = sha256_digest(proof_path.read_bytes())
        self.rewrite_checks(lambda value: next(
            item for item in value["checks"][0]["inputs"] if item["artifact_id"] == "linked-proof"
        ).update({"root": proof_root}), sync_typed_result=True)
        after = generate_core(self.directory / "core-input.json")
        self.assertNotEqual(before["root"], after["root"])
        self.assertNotEqual(canonical_bytes(before), canonical_bytes(after))

    def test_normalized_result_change_changes_core_root(self):
        self.directory = Path(self.temporary.name) / "fidelity-result-change"
        shutil.copytree(FIXTURES / "fidelity-erdos-887-1237", self.directory)
        before = generate_core(self.directory / "core-input.json")
        result_path = self.directory / "inputs" / "github-job-result.json"
        result = load(result_path)
        result["run_attempt"] += 1
        write_canonical(result_path, result)
        update_manifest_artifact(self.directory, "core-input.json", "inputs/github-job-result.json")
        result_root = sha256_digest(result_path.read_bytes())
        def update_result_root(value):
            check = next(item for item in value["checks"] if item["property"] == "lean-build")
            next(item for item in check["inputs"] if item["artifact_id"] == "build-job")["root"] = result_root
            check["evidence"][0]["sha256"] = result_root
        self.rewrite_checks(update_result_root, sync_typed_result=True)
        after = generate_core(self.directory / "core-input.json")
        self.assertNotEqual(before["root"], after["root"])
        self.assertEqual(before["disposition"], after["disposition"])

    def test_observation_only_change_does_not_change_core(self):
        before_core = generate_core(self.directory / "core-input.json")
        before_observation = generate_observation(
            self.directory / "observation-input.json", self.directory / "expected-core.json"
        )
        def change(value):
            pr = value["data"]["repository"]["pullRequest"]
            pr["mergeStateStatus"] = "CLEAN"
            pr["updatedAt"] = "2026-08-12T21:00:00Z"
        self.rewrite_observation(change)
        receipt_path = self.directory / "inputs" / "github-acquisition-receipt.json"
        receipt = load(receipt_path)
        response_path = self.directory / "inputs" / "github-graphql-response.json"
        receipt["response_sha256"] = sha256_digest(response_path.read_bytes())
        write_canonical(receipt_path, receipt)
        update_manifest_artifact(
            self.directory, "observation-input.json", "inputs/github-acquisition-receipt.json"
        )
        after_core = generate_core(self.directory / "core-input.json")
        after_observation = generate_observation(
            self.directory / "observation-input.json", self.directory / "expected-core.json"
        )
        self.assertEqual(canonical_bytes(before_core), canonical_bytes(after_core))
        self.assertNotEqual(before_observation["root"], after_observation["root"])
        self.assertEqual(after_observation["core"]["root"], before_core["root"])

    def test_all_acquisition_and_presentation_noise_is_core_invariant(self):
        self.directory = Path(self.temporary.name) / "fidelity"
        shutil.copytree(FIXTURES / "fidelity-erdos-887-1237", self.directory)
        before_core = generate_core(self.directory / "core-input.json")
        before_observation = generate_observation(
            self.directory / "observation-input.json", self.directory / "expected-core.json"
        )

        def rewrite_provenance(filename: str, transform) -> None:
            path = self.directory / "inputs" / filename
            value = load(path)
            transform(value)
            write_canonical(path, value)
            update_manifest_artifact(self.directory, "observation-input.json", f"inputs/{filename}")

        rewrite_provenance("github-core-acquisition-receipt.json", lambda value: value.update({
            "acquired_at": "2026-08-13T01:02:03Z",
            "request_id": "changed-request",
            "transport": "retained-offline-copy",
            "http_status": 299,
            "limitations": ["changed presentation prose"],
            "headers": {"x-request-id": "changed"},
            "redirect_chain": ["https://example.invalid/changed"],
        }))
        rewrite_provenance("github-core-snapshot-response.json", lambda value: value["data"]["repository"]["pullRequest"]["files"]["pageInfo"].update({
            "endCursor": "changed-cursor"
        }))
        rewrite_provenance("github-job-response.json", lambda value: value.update({
            "head_branch": "changed-branch",
            "runner_id": 1,
            "runner_name": "changed-runner",
            "runner_group_id": 2,
            "runner_group_name": "changed-group",
            "created_at": "2026-08-13T01:00:00Z",
            "started_at": "2026-08-13T01:00:01Z",
            "completed_at": "2026-08-13T01:00:02Z",
            "steps": [{"name": "presentation-only", "status": "completed"}],
        }))
        rewrite_provenance("github-job-acquisition-receipt.json", lambda value: value.update({
            "acquired_at": "2026-08-13T01:02:03Z",
            "request_id": "changed-request",
            "transport": "retained-offline-copy",
            "http_status": 299,
            "trigger_event": "changed-event",
            "limitations": ["changed presentation prose"],
            "headers": {"x-request-id": "changed"},
        }))
        rewrite_provenance("method-build-and-docs.acquisition-receipt.json", lambda value: value.update({
            "acquired_at": "2026-08-13T01:02:03Z",
            "request_id": "changed-request",
            "final_url": "https://example.invalid/redirected",
            "limitations": ["changed presentation prose"],
        }))
        rewrite_provenance("review-observation.json", lambda value: value.update({
            "prepared_at": "2026-08-13T01:02:03Z"
        }))

        after_core = generate_core(self.directory / "core-input.json")
        after_observation = generate_observation(
            self.directory / "observation-input.json", self.directory / "expected-core.json"
        )
        self.assertEqual(before_core["root"], after_core["root"])
        self.assertEqual(canonical_bytes(before_core), canonical_bytes(after_core))
        self.assertNotEqual(before_observation["root"], after_observation["root"])
        self.assertEqual(after_observation["core"]["root"], before_core["root"])

    def test_observation_refuses_noncanonical_core_file_framing(self):
        core_path = self.directory / "pretty-core.json"
        core = load(self.directory / "expected-core.json")
        core_path.write_text(json.dumps(core, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(AuditError, "canonical file framing"):
            generate_observation(self.directory / "observation-input.json", core_path)
        core_path.write_bytes(canonical_bytes(core))
        with self.assertRaisesRegex(AuditError, "canonical file framing"):
            generate_observation(self.directory / "observation-input.json", core_path)

    def test_set_like_fields_and_full_proof_tuples_are_ordered(self):
        def change(value):
            check = value["checks"][0]
            check["scope"]["declarations"].reverse()
            second = copy.deepcopy(check["proofs"][0])
            second["declaration"] = "Zeta.second_proof"
            second["conditions"] = list(reversed(second["conditions"]))
            check["proofs"] = [second, check["proofs"][0]]
        self.rewrite_checks(change, sync_typed_result=True)
        core = generate_core(self.directory / "core-input.json")
        proofs = core["checks"][0]["proofs"]
        self.assertEqual(
            [(proof["declaration"], proof["kind"], proof["locator"], proof["conditions"]) for proof in proofs],
            sorted(
                [(proof["declaration"], proof["kind"], proof["locator"], proof["conditions"]) for proof in proofs],
                key=lambda item: (item[0].encode("utf-16-be"), item[1].encode("utf-16-be"), item[2].encode("utf-16-be"), canonical_bytes(item[3])),
            ),
        )

    def test_unsupported_input_version_is_refused(self):
        path = self.directory / "core-input.json"
        value = load(path)
        value["schema_version"] = "formal-conjectures.pr-audit-input.v2"
        write_canonical(path, value)
        with self.assertRaisesRegex(AuditError, "unsupported input schema"):
            generate_core(path)

    def test_same_semantic_manifest_must_use_canonical_framing(self):
        path = self.directory / "core-input.json"
        value = load(path)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(AuditError, "manifest must use canonical file framing"):
            generate_core(path)

    def test_structured_core_artifacts_require_canonical_framing(self):
        for artifact_path in (
            "inputs/generator.json",
            "inputs/repository.json",
            "inputs/checks.json",
            "inputs/github-core-snapshot-result.json",
            "inputs/typed-result-conditional-proof-metadata.json",
        ):
            with self.subTest(path=artifact_path), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary) / "fixture"
                shutil.copytree(FIXTURES / "conditional-erdos-427-4884", directory)
                path = directory / artifact_path
                path.write_text(json.dumps(load(path), indent=2), encoding="utf-8")
                update_manifest_artifact(directory, "core-input.json", artifact_path)
                with self.assertRaisesRegex(AuditError, "structured artifact must use canonical"):
                    generate_core(directory / "core-input.json")

    def test_structured_observation_receipt_requires_canonical_framing(self):
        path = self.directory / "inputs" / "github-acquisition-receipt.json"
        path.write_bytes(canonical_bytes(load(path)))
        update_manifest_artifact(
            self.directory, "observation-input.json", "inputs/github-acquisition-receipt.json"
        )
        with self.assertRaisesRegex(AuditError, "structured artifact must use canonical"):
            generate_observation(
                self.directory / "observation-input.json", self.directory / "expected-core.json"
            )

    def test_empty_proof_locator_is_only_valid_for_in_source_proofs(self):
        self.rewrite_checks(lambda value: value["checks"][0]["proofs"][0].update({
            "kind": "formal_conjectures", "locator": ""
        }), sync_typed_result=True)
        core = generate_core(self.directory / "core-input.json")
        self.assertEqual(core["checks"][0]["proofs"][0]["locator"], "")

        self.rewrite_checks(lambda value: value["checks"][0]["proofs"][0].update({
            "kind": "lean4"
        }))
        with self.assertRaises(AuditError):
            generate_core(self.directory / "core-input.json")

    def test_missing_and_malformed_inputs_are_refused(self):
        missing = self.directory / "inputs" / "checks.json"
        missing.unlink()
        with self.assertRaisesRegex(AuditError, "artifact is missing"):
            generate_core(self.directory / "core-input.json")
        shutil.copy2(FIXTURES / "conditional-erdos-427-4884" / "inputs" / "checks.json", missing)
        missing.write_bytes(b'{"broken":')
        update_manifest_artifact(self.directory, "core-input.json", "inputs/checks.json")
        with self.assertRaisesRegex(AuditError, "malformed JSON"):
            generate_core(self.directory / "core-input.json")

    def test_missing_required_method_is_refused_as_missing_not_unavailable(self):
        method = self.directory / "inputs" / "metadata-review-procedure.json"
        method.unlink()
        with self.assertRaisesRegex(AuditError, "artifact is missing"):
            generate_core(self.directory / "core-input.json")

    def test_duplicate_check_ids_are_refused(self):
        self.rewrite_checks(lambda value: value["checks"].append(copy.deepcopy(value["checks"][0])))
        with self.assertRaisesRegex(AuditError, "duplicate check ids"):
            generate_core(self.directory / "core-input.json")

    def test_empty_does_not_establish_is_refused(self):
        self.rewrite_checks(lambda value: value["checks"][0].update({"does_not_establish": []}))
        with self.assertRaisesRegex(AuditError, "does_not_establish"):
            generate_core(self.directory / "core-input.json")

    def test_fail_with_none_severity_cannot_be_hidden_by_human_pass(self):
        def mutate(value):
            human = value["checks"][0]
            human.update({
                "id": "independent-human-source-fidelity",
                "kind": "semantic",
                "mode": "human_review",
                "property": "source-fidelity",
                "role": "independent",
                "outcome": "pass",
                "severity": "none",
            })
            mechanical = copy.deepcopy(human)
            mechanical.update({
                "id": "mechanical-failure",
                "kind": "mechanical",
                "mode": "retained_replay",
                "property": "mechanical-check",
                "role": "producer",
                "outcome": "fail",
                "severity": "none",
            })
            value["checks"].append(mechanical)
        self.rewrite_checks(mutate)
        with self.assertRaisesRegex(AuditError, "fail outcome requires"):
            generate_core(self.directory / "core-input.json")

    def test_nit_failure_uses_neutral_nonacceptance_vocabulary(self):
        self.rewrite_checks(lambda value: value["checks"][0].update({
            "outcome": "fail", "severity": "nit"
        }), sync_typed_result=True)
        core = generate_core(self.directory / "core-input.json")
        self.assertEqual(core["disposition"]["advisory"], "nits_found")
        self.assertNotIn("accept", core["disposition"]["advisory"])

    def test_core_manifest_and_published_core_refuse_provenance_roles(self):
        event_path = self.directory / "inputs" / "presentation-event.json"
        write_canonical(event_path, {"prepared_at": "2026-08-12T21:00:00Z"})
        manifest_path = self.directory / "core-input.json"
        manifest = load(manifest_path)
        event_descriptor = {
            "id": "presentation-event",
            "role": "provenance_event",
            "media_type": "application/json",
            "path": "inputs/presentation-event.json",
            "sha256": sha256_digest(event_path.read_bytes()),
        }
        manifest["artifacts"].append(event_descriptor)
        manifest["artifacts"] = sorted(
            manifest["artifacts"],
            key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]),
        )
        manifest["artifact_root"] = content_root({"artifacts": manifest["artifacts"]})
        write_canonical(manifest_path, manifest)
        with self.assertRaisesRegex(AuditError, "observation/provenance roles"):
            generate_core(manifest_path)

        core = generate_core(FIXTURES / "conditional-erdos-427-4884" / "core-input.json")
        core["inputs"]["artifacts"].append(event_descriptor)
        core["inputs"]["artifacts"] = sorted(
            core["inputs"]["artifacts"],
            key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]),
        )
        core["inputs"]["artifact_root"] = content_root({"artifacts": core["inputs"]["artifacts"]})
        reconstructed = {
            "schema_version": "formal-conjectures.pr-audit-input.v1",
            "artifact_root": core["inputs"]["artifact_root"],
            "artifacts": core["inputs"]["artifacts"],
        }
        core["inputs"]["manifest_sha256"] = sha256_digest(framed(reconstructed))
        core["root"] = content_root({key: value for key, value in core.items() if key != "root"})
        with self.assertRaisesRegex(AuditError, "observation/provenance roles"):
            validate_core(core)

    def test_each_check_requires_one_retained_typed_result_artifact(self):
        checks_path = self.directory / "inputs" / "checks.json"
        checks = load(checks_path)
        relation = next(item for item in checks["checks"][0]["inputs"] if item["kind"] == "typed-result")
        checks["checks"][0]["inputs"].remove(relation)
        write_canonical(checks_path, checks)
        manifest_path = self.directory / "core-input.json"
        manifest = load(manifest_path)
        manifest["artifacts"] = [
            item for item in manifest["artifacts"] if item["id"] != relation["artifact_id"]
        ]
        next(item for item in manifest["artifacts"] if item["id"] == "checks")["sha256"] = sha256_digest(
            checks_path.read_bytes()
        )
        manifest["artifacts"] = sorted(
            manifest["artifacts"],
            key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]),
        )
        manifest["artifact_root"] = content_root({"artifacts": manifest["artifacts"]})
        write_canonical(manifest_path, manifest)
        with self.assertRaisesRegex(AuditError, "exactly one typed result"):
            generate_core(manifest_path)

    def test_check_only_reroot_cannot_override_typed_result(self):
        self.rewrite_checks(
            lambda value: value["checks"][0]["evidence"][0].update({"statement": "check-only forgery"})
        )
        with self.assertRaisesRegex(AuditError, "complete check projection"):
            generate_core(self.directory / "core-input.json")

    def test_published_core_check_only_reroot_cannot_override_typed_result(self):
        core = generate_core(self.directory / "core-input.json")
        core["checks"][0]["evidence"][0]["statement"] = "published check-only forgery"
        checks_value = {
            "schema_version": "formal-conjectures.pr-audit-checks.v1",
            "checks": core["checks"],
        }
        next(
            item for item in core["inputs"]["artifacts"] if item["role"] == "check_results"
        )["sha256"] = sha256_digest(framed(checks_value))
        core["inputs"]["artifact_root"] = content_root({"artifacts": core["inputs"]["artifacts"]})
        reconstructed = {
            "schema_version": "formal-conjectures.pr-audit-input.v1",
            "artifact_root": core["inputs"]["artifact_root"],
            "artifacts": core["inputs"]["artifacts"],
        }
        core["inputs"]["manifest_sha256"] = sha256_digest(framed(reconstructed))
        core["root"] = content_root({key: value for key, value in core.items() if key != "root"})
        with self.assertRaisesRegex(AuditError, "typed result digest"):
            validate_core(core)

    def test_typed_result_only_reroot_cannot_override_check(self):
        rewrite_typed_result(
            self.directory,
            "conditional-proof-metadata",
            lambda result: result["check"]["evidence"][0].update({"statement": "result-only forgery"}),
        )
        with self.assertRaisesRegex(AuditError, "complete check projection"):
            generate_core(self.directory / "core-input.json")

    def test_semantic_outcome_and_severity_mismatches_are_symmetric(self):
        variants = (
            ("nit", "fail", "nit"),
            ("inconclusive", "inconclusive", "none"),
            ("error", "error", "none"),
            ("pass", "pass", "none"),
        )
        for direction in ("check", "result"):
            for label, outcome, severity in variants:
                with self.subTest(direction=direction, variant=label):
                    directory = Path(self.temporary.name) / f"semantic-{direction}-{label}"
                    shutil.copytree(FIXTURES / "fidelity-erdos-887-1237", directory)
                    if direction == "check":
                        original = self.directory
                        self.directory = directory
                        self.rewrite_checks(lambda value: next(
                            item for item in value["checks"] if item["id"] == "answer-slot-scope"
                        ).update({"outcome": outcome, "severity": severity}))
                        self.directory = original
                    else:
                        def mutate(result):
                            result["check"].update({"outcome": outcome, "severity": severity})
                            result["semantic_review"].update({"outcome": outcome, "severity": severity})
                        rewrite_typed_result(directory, "answer-slot-scope", mutate)
                    with self.assertRaisesRegex(AuditError, "complete check projection"):
                        generate_core(directory / "core-input.json")

    def test_semantic_review_binds_every_claimed_field_and_artifact_relation(self):
        mutations = {
            "preparer": lambda review: review.update({"preparer": "forged_preparer"}),
            "reviewer": lambda review: review.update({"reviewer": "forged_reviewer"}),
            "authority": lambda review: review.update({"authority": "independent_human_review"}),
            "independent": lambda review: review.update({"independent": True}),
            "outcome": lambda review: review.update({"outcome": "inconclusive"}),
            "severity": lambda review: review.update({"severity": "nit"}),
            "finding": lambda review: review.update({"finding": "forged finding"}),
            "witness": lambda review: review.update({"witness": "forged witness"}),
            "head_commit_oid": lambda review: review.update({"head_commit_oid": "0" * 40}),
            "head_blob_oid": lambda review: review.update({"head_blob_oid": "0" * 40}),
            "source_root": lambda review: review.update({"source_root": "sha256:" + "0" * 64}),
            "scope": lambda review: review["scope"].update({"declarations": ["Forged.declaration"]}),
            "declarations": lambda review: review.update({"declarations": ["Forged.declaration"]}),
            "method": lambda review: review["method"].update({"version": "forged"}),
        }
        for label, mutate_review in mutations.items():
            with self.subTest(field=label):
                directory = Path(self.temporary.name) / f"semantic-field-{label}"
                shutil.copytree(FIXTURES / "fidelity-erdos-887-1237", directory)
                rewrite_typed_result(
                    directory,
                    "answer-slot-scope",
                    lambda result, mutate_review=mutate_review: mutate_review(result["semantic_review"]),
                )
                with self.assertRaisesRegex(AuditError, "semantic (?:review|result)"):
                    generate_core(directory / "core-input.json")

        directory = Path(self.temporary.name) / "semantic-artifact-relation"
        shutil.copytree(FIXTURES / "fidelity-erdos-887-1237", directory)
        rewrite_typed_result(
            directory,
            "answer-slot-scope",
            lambda result: result["artifacts"].pop(0),
        )
        with self.assertRaisesRegex(AuditError, "artifact relations"):
            generate_core(directory / "core-input.json")

    def test_ai_prepared_pass_stays_inconclusive_and_cannot_claim_human_clean(self):
        self.directory = Path(self.temporary.name) / "ai-clean"
        shutil.copytree(FIXTURES / "fidelity-erdos-887-1237", self.directory)
        self.rewrite_checks(lambda value: next(
            item for item in value["checks"] if item["id"] == "answer-slot-scope"
        ).update({"outcome": "pass", "severity": "none"}), sync_typed_result=True)
        core = generate_core(self.directory / "core-input.json")
        self.assertEqual(core["disposition"]["advisory"], "inconclusive")

        self.rewrite_checks(lambda value: next(
            item for item in value["checks"] if item["id"] == "answer-slot-scope"
        ).update({"mode": "human_review", "role": "independent"}), sync_typed_result=True)
        rewrite_typed_result(
            self.directory,
            "answer-slot-scope",
            lambda result: (
                result["producer"].update({
                    "authority": "independent_human_review", "independent": True,
                }),
                result["semantic_review"].update({
                    "authority": "independent_human_review", "independent": True,
                    "reviewer": "forged_human_reviewer",
                }),
            ),
        )
        with self.assertRaisesRegex(AuditError, "(?:kind cannot claim|supported producer profile)"):
            generate_core(self.directory / "core-input.json")

    def test_digest_mismatch_is_refused(self):
        path = self.directory / "inputs" / "checks.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(AuditError, "artifact digest mismatch"):
            generate_core(self.directory / "core-input.json")

    def test_unreferenced_or_mismatched_retained_input_is_refused(self):
        manifest_path = self.directory / "core-input.json"
        manifest = load(manifest_path)
        extra_path = self.directory / "inputs" / "unreferenced.txt"
        extra_path.write_text("unreferenced retained input\n", encoding="utf-8")
        manifest["artifacts"].append({
            "id": "unreferenced",
            "role": "method",
            "media_type": "text/plain",
            "path": "inputs/unreferenced.txt",
            "sha256": sha256_digest(extra_path.read_bytes()),
        })
        manifest["artifact_root"] = content_root({"artifacts": sorted(
            manifest["artifacts"],
            key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]),
        )})
        write_canonical(manifest_path, manifest)
        with self.assertRaisesRegex(AuditError, "inventory mismatch"):
            generate_core(manifest_path)

        extra_path.unlink()
        shutil.copy2(FIXTURES / "conditional-erdos-427-4884" / "core-input.json", manifest_path)
        self.rewrite_checks(lambda value: value["checks"][0]["inputs"][0].update({
            "root": "sha256:" + "0" * 64
        }), sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "root does not match retained artifact"):
            generate_core(manifest_path)

    def test_implementation_root_must_match_retained_method(self):
        self.rewrite_checks(lambda value: value["checks"][0]["implementation"].update({
            "root": value["checks"][0]["inputs"][0]["root"]
        }), sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "implementation root"):
            generate_core(self.directory / "core-input.json")

    def test_retained_internal_method_must_match_generator_overlay(self):
        self.directory = Path(self.temporary.name) / "internal-method"
        shutil.copytree(FIXTURES / "clean-candidate-dean-4878", self.directory)
        method_path = self.directory / "inputs" / "method-pr-audit.py"
        method_path.write_bytes(method_path.read_bytes() + b"\n# forged method\n")
        update_manifest_artifact(self.directory, "core-input.json", "inputs/method-pr-audit.py")
        method_root = sha256_digest(method_path.read_bytes())
        def update_method(value):
            check = value["checks"][0]
            check["implementation"]["root"] = method_root
            next(item for item in check["inputs"] if item["artifact_id"] == "method-pr-audit")["root"] = method_root
        self.rewrite_checks(update_method, sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "generator overlay"):
            generate_core(self.directory / "core-input.json")

    def test_evidence_root_must_match_a_retained_check_input(self):
        self.rewrite_checks(lambda value: value["checks"][0]["evidence"][0].update({
            "sha256": "sha256:" + "0" * 64
        }), sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "evidence locator/root tuple"):
            generate_core(self.directory / "core-input.json")

    def test_evidence_locator_and_root_must_bind_to_the_same_input(self):
        self.rewrite_checks(lambda value: value["checks"][0]["evidence"][0].update({
            "locator": "https://attacker.example/unbound-context"
        }), sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "evidence locator/root tuple"):
            generate_core(self.directory / "core-input.json")

    def test_unavailable_outcome_must_match_retained_classifier(self):
        self.directory = Path(self.temporary.name) / "unavailable"
        shutil.copytree(FIXTURES / "unavailable-rupert-3959", self.directory)
        self.rewrite_checks(lambda value: next(
            check for check in value["checks"] if check["property"] == "exact-formal-proof-artifact-identity"
        ).update({"outcome": "pass"}), sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "mutable or ambiguous"):
            generate_core(self.directory / "core-input.json")

    def test_comparator_packet_identity_cannot_pose_as_attempted_invocation(self):
        self.directory = Path(self.temporary.name) / "tool-unavailable"
        shutil.copytree(FIXTURES / "unavailable-rupert-3959", self.directory)
        observation_path = self.directory / "inputs" / "comparator-packet-observation.json"
        observation = load(observation_path)
        observation["tool_invocation_attempted"] = True
        write_canonical(observation_path, observation)
        update_manifest_artifact(self.directory, "core-input.json", "inputs/comparator-packet-observation.json")
        root = sha256_digest(observation_path.read_bytes())
        def update_observation_root(value):
            check = next(item for item in value["checks"] if item["property"] == "comparator-packet-identity")
            input_record = next(item for item in check["inputs"] if item["artifact_id"] == "comparator-observation")
            input_record["root"] = root
            check["evidence"][0]["sha256"] = root
        self.rewrite_checks(update_observation_root, sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "inspection observation is invalid"):
            generate_core(self.directory / "core-input.json")

    def test_missing_tool_execution_claim_is_deferred_without_real_invocation(self):
        self.directory = Path(self.temporary.name) / "missing-tool"
        shutil.copytree(FIXTURES / "unavailable-rupert-3959", self.directory)
        self.rewrite_checks(lambda value: next(
            item for item in value["checks"] if item["property"] == "comparator-packet-identity"
        ).update({"property": "comparator-tool-availability"}))
        with self.assertRaisesRegex(AuditError, "unsupported or unimplemented"):
            generate_core(self.directory / "core-input.json")

    def test_passing_external_proof_must_be_immutable_and_retained(self):
        self.rewrite_checks(lambda value: value["checks"][0]["proofs"][0].update({
            "locator": "https://github.com/attacker/mutable-proof"
        }), sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "mutable or ambiguous"):
            generate_core(self.directory / "core-input.json")

        self.directory = Path(self.temporary.name) / "unbound"
        shutil.copytree(FIXTURES / "conditional-erdos-427-4884", self.directory)
        self.rewrite_checks(lambda value: value["checks"][0]["proofs"][0].update({
            "locator": "https://github.com/google-deepmind/formal-conjectures/blob/601aff40d6fa6c3150242144fadba5dbcc24c89c/FormalConjectures/ErdosProblems/427.lean"
        }), sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "not bound to retained source bytes"):
            generate_core(self.directory / "core-input.json")

    def test_published_core_refuses_ghost_identity_artifacts(self):
        core = generate_core(self.directory / "core-input.json")
        core["inputs"]["artifacts"] = [
            artifact for artifact in core["inputs"]["artifacts"]
            if artifact["role"] not in {"generator_identity", "repository_snapshot"}
        ]
        core["inputs"]["generator_artifact_id"] = "ghost-generator"
        core["inputs"]["repository_artifact_id"] = "ghost-repository"
        core["inputs"]["artifact_root"] = content_root({"artifacts": core["inputs"]["artifacts"]})
        unrooted = {key: value for key, value in core.items() if key != "root"}
        core["root"] = content_root(unrooted)
        with self.assertRaisesRegex(AuditError, "manifest digest"):
            validate_core(core)

    def test_published_core_refuses_duplicate_artifact_ids_and_paths(self):
        core = generate_core(self.directory / "core-input.json")
        duplicate = copy.deepcopy(core["inputs"]["artifacts"][0])
        core["inputs"]["artifacts"].append(duplicate)
        core["inputs"]["artifact_root"] = content_root({"artifacts": sorted(
            core["inputs"]["artifacts"],
            key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]),
        )})
        unrooted = {key: value for key, value in core.items() if key != "root"}
        core["root"] = content_root(unrooted)
        with self.assertRaisesRegex(AuditError, "duplicate artifact ids"):
            validate_core(core)

    def test_published_core_refuses_unretained_implementation_root(self):
        core = generate_core(self.directory / "core-input.json")
        core["checks"][0]["implementation"]["root"] = core["checks"][0]["inputs"][0]["root"]
        unrooted = {key: value for key, value in core.items() if key != "root"}
        core["root"] = content_root(unrooted)
        with self.assertRaisesRegex(AuditError, "checks value"):
            validate_core(core)

    def test_published_core_refuses_implementation_locator_drift(self):
        core = generate_core(self.directory / "core-input.json")
        core["checks"][0]["implementation"]["locator"] = "https://attacker.example/evil"
        unrooted = {key: value for key, value in core.items() if key != "root"}
        core["root"] = content_root(unrooted)
        with self.assertRaisesRegex(AuditError, "checks value"):
            validate_core(core)

    def test_published_core_recomputes_proof_identity_outcome(self):
        core = generate_core(FIXTURES / "unavailable-rupert-3959" / "core-input.json")
        identity = next(check for check in core["checks"] if check["property"] == "exact-formal-proof-artifact-identity")
        identity["outcome"] = "pass"
        core["disposition"]["advisory"] = "inconclusive"
        core["disposition"]["basis_check_ids"] = [check["id"] for check in core["checks"]]
        unrooted = {key: value for key, value in core.items() if key != "root"}
        core["root"] = content_root(unrooted)
        with self.assertRaisesRegex(AuditError, "checks value"):
            validate_core(core)

    def test_published_core_refuses_scope_outside_pr_comparison(self):
        core = generate_core(self.directory / "core-input.json")
        core["checks"][0]["scope"]["paths"] = ["FormalConjectures/Attacker.lean"]
        unrooted = {key: value for key, value in core.items() if key != "root"}
        core["root"] = content_root(unrooted)
        with self.assertRaisesRegex(AuditError, "checks value"):
            validate_core(core)

    def test_published_core_values_match_retained_descriptors(self):
        mutations = (
            ("generator", lambda core: core["generator"].update({"version": "forged"})),
            ("repository", lambda core: core["repository"]["pull_request"].update({"number": 4885, "url": "https://github.com/google-deepmind/formal-conjectures/pull/4885"})),
            ("checks", lambda core: core["checks"][0]["limitations"].append("forged limitation")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                core = generate_core(self.directory / "core-input.json")
                mutate(core)
                unrooted = {key: value for key, value in core.items() if key != "root"}
                core["root"] = content_root(unrooted)
                with self.assertRaisesRegex(AuditError, "does not match retained descriptor"):
                    validate_core(core)

    def test_validate_observation_recomputes_root_and_bindings(self):
        observation = generate_observation(self.directory / "observation-input.json", self.directory / "expected-core.json")
        self.assertEqual(validate_observation(observation), observation)
        observation["source"]["sha256"] = "sha256:" + "0" * 64
        unrooted = {key: value for key, value in observation.items() if key != "root"}
        observation["root"] = content_root(unrooted)
        with self.assertRaisesRegex(AuditError, "source artifact binding"):
            validate_observation(observation)

    def test_published_observation_binds_generator_and_receipt_fields(self):
        original = generate_observation(
            self.directory / "observation-input.json", self.directory / "expected-core.json"
        )
        for label, mutate, message in (
            ("generator", lambda value: value["generator"].update({"version": "forged"}), "generator value"),
            ("request-id", lambda value: value["source"].update({"request_id": "forged"}), "source summary"),
            ("limitations", lambda value: value["source"].update({"limitations": ["forged"]}), "source summary"),
        ):
            with self.subTest(label=label):
                observation = copy.deepcopy(original)
                mutate(observation)
                observation["root"] = content_root({key: value for key, value in observation.items() if key != "root"})
                with self.assertRaisesRegex(AuditError, message):
                    validate_observation(observation)

    def test_published_observation_refuses_extra_roles_and_duplicate_reviews(self):
        original = generate_observation(
            self.directory / "observation-input.json", self.directory / "expected-core.json"
        )
        observation = copy.deepcopy(original)
        observation["inputs"]["artifacts"].append({
            "id": "extra-source",
            "role": "source_file",
            "media_type": "text/plain",
            "path": "inputs/extra-source.txt",
            "sha256": "sha256:" + "0" * 64,
        })
        observation["inputs"]["artifacts"] = sorted(
            observation["inputs"]["artifacts"],
            key=lambda item: (item["id"], item["role"], item["path"], item["sha256"]),
        )
        observation["inputs"]["artifact_root"] = content_root({"artifacts": observation["inputs"]["artifacts"]})
        observation["inputs"]["manifest_sha256"] = sha256_digest(framed({
            "schema_version": "formal-conjectures.pr-audit-observation-input.v1",
            "artifact_root": observation["inputs"]["artifact_root"],
            "artifacts": observation["inputs"]["artifacts"],
            "observed_at": observation["observed_at"],
        }))
        observation["root"] = content_root({key: value for key, value in observation.items() if key != "root"})
        with self.assertRaisesRegex(AuditError, "unsupported input role"):
            validate_observation(observation)

        observation = generate_observation(
            FIXTURES / "clean-candidate-dean-4878" / "observation-input.json",
            FIXTURES / "clean-candidate-dean-4878" / "expected-core.json",
        )
        observation["pull_request"]["reviews"].append(copy.deepcopy(observation["pull_request"]["reviews"][0]))
        observation["root"] = content_root({key: value for key, value in observation.items() if key != "root"})
        with self.assertRaisesRegex(AuditError, "duplicate observation review id"):
            validate_observation(observation)

    def test_observation_review_order_is_chronological_then_identity(self):
        observation = generate_observation(
            FIXTURES / "clean-candidate-dean-4878" / "observation-input.json",
            FIXTURES / "clean-candidate-dean-4878" / "expected-core.json",
        )
        reviews = observation["pull_request"]["reviews"]
        self.assertLess(reviews[0]["submitted_at"], reviews[1]["submitted_at"])
        reversed_ids = copy.deepcopy(observation)
        reversed_ids["pull_request"]["reviews"][0]["id"] = "z-later-lexically"
        reversed_ids["pull_request"]["reviews"][1]["id"] = "a-earlier-lexically"
        reversed_ids["root"] = content_root({key: value for key, value in reversed_ids.items() if key != "root"})
        self.assertEqual(
            validate_observation(reversed_ids)["pull_request"]["reviews"][0]["id"],
            "z-later-lexically",
        )
        self.assertEqual(validate_observation(observation), observation)

    def test_frozen_git_blob_identities_are_derived_from_retained_bytes(self):
        for name in NAMES:
            with self.subTest(name=name):
                directory = FIXTURES / name
                core = generate_core(directory / "core-input.json")
                for change in core["repository"]["changes"]:
                    for revision in ("base", "head"):
                        oid = change[f"{revision}_blob_oid"]
                        if oid is None:
                            continue
                        raw = (directory / "inputs" / f"{revision}-source.lean").read_bytes()
                        self.assertEqual(git_blob_oid(raw), oid)
                        self.assertEqual(sha256_digest(raw), change[f"{revision}_blob_sha256"])

    def test_observation_receipt_and_query_are_verified(self):
        receipt_path = self.directory / "inputs" / "github-acquisition-receipt.json"
        receipt = load(receipt_path)
        receipt["response_sha256"] = "sha256:" + "0" * 64
        write_canonical(receipt_path, receipt)
        update_manifest_artifact(
            self.directory, "observation-input.json", "inputs/github-acquisition-receipt.json"
        )
        with self.assertRaisesRegex(AuditError, "response digest"):
            generate_observation(
                self.directory / "observation-input.json", self.directory / "expected-core.json"
            )

    def test_core_authority_response_semantic_drift_is_refused(self):
        response_path = self.directory / "inputs" / "github-core-snapshot-result.json"
        response = load(response_path)
        response["head_commit"]["tree"]["oid"] = "0" * 40
        write_canonical(response_path, response)
        update_manifest_artifact(
            self.directory, "core-input.json", "inputs/github-core-snapshot-result.json"
        )
        response_root = sha256_digest(response_path.read_bytes())
        request_path = self.directory / "inputs" / "github-core-request-identity.json"
        request = load(request_path)
        request["result_sha256"] = response_root
        write_canonical(request_path, request)
        update_manifest_artifact(
            self.directory, "core-input.json", "inputs/github-core-request-identity.json"
        )
        request_root = sha256_digest(request_path.read_bytes())
        def update_roots(value):
            for check in value["checks"]:
                for input_record in check["inputs"]:
                    if input_record["artifact_id"] == "repository-authority":
                        input_record["root"] = response_root
                    if input_record["artifact_id"] == "repository-request":
                        input_record["root"] = request_root
        self.rewrite_checks(update_roots, sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "head commit/tree mismatch"):
            generate_core(self.directory / "core-input.json")

    def test_graphql_query_must_be_exact_not_substring_match(self):
        query_path = self.directory / "inputs" / "github-core-snapshot-query.graphql"
        query_path.write_text("# query PullRequestAuditCoreSnapshot\nquery Other { viewer { login } }", encoding="utf-8")
        update_manifest_artifact(self.directory, "core-input.json", "inputs/github-core-snapshot-query.graphql")
        query_root = sha256_digest(query_path.read_bytes())
        request_path = self.directory / "inputs" / "github-core-request-identity.json"
        request = load(request_path)
        request["query_sha256"] = query_root
        write_canonical(request_path, request)
        update_manifest_artifact(
            self.directory, "core-input.json", "inputs/github-core-request-identity.json"
        )
        request_root = sha256_digest(request_path.read_bytes())
        def update_query_root(value):
            for check in value["checks"]:
                for input_record in check["inputs"]:
                    if input_record["artifact_id"] == "repository-query":
                        input_record["root"] = query_root
                    if input_record["artifact_id"] == "repository-request":
                        input_record["root"] = request_root
        self.rewrite_checks(update_query_root, sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "exact v1 operation"):
            generate_core(self.directory / "core-input.json")

    def test_repository_components_urls_and_authority_cannot_diverge(self):
        repository_path = self.directory / "inputs" / "repository.json"
        repository = load(repository_path)
        repository["repository"]["owner"] = "attacker"
        repository["repository"]["name"] = "other"
        write_canonical(repository_path, repository)
        update_manifest_artifact(self.directory, "core-input.json", "inputs/repository.json")
        with self.assertRaisesRegex(AuditError, "repository.url"):
            generate_core(self.directory / "core-input.json")

    def test_lean_build_job_name_is_bound_to_repository_workflow(self):
        self.directory = Path(self.temporary.name) / "fidelity"
        shutil.copytree(FIXTURES / "fidelity-erdos-887-1237", self.directory)
        job_path = self.directory / "inputs" / "github-job-result.json"
        job = load(job_path)
        job["job_name"] = "No-op"
        write_canonical(job_path, job)
        update_manifest_artifact(self.directory, "core-input.json", "inputs/github-job-result.json")
        job_root = sha256_digest(job_path.read_bytes())
        def update_job_roots(value):
            check = next(item for item in value["checks"] if item["property"] == "lean-build")
            for input_record in check["inputs"]:
                if input_record["artifact_id"] == "build-job":
                    input_record["root"] = job_root
            check["evidence"][0]["sha256"] = job_root
        self.rewrite_checks(update_job_roots, sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "exact repository Lean build job"):
            generate_core(self.directory / "core-input.json")

    def test_commit_qualified_method_identity_and_receipt_are_bound(self):
        self.directory = Path(self.temporary.name) / "fidelity"
        shutil.copytree(FIXTURES / "fidelity-erdos-887-1237", self.directory)
        identity_path = self.directory / "inputs" / "method-build-and-docs.identity.json"
        identity = load(identity_path)
        identity["commit_oid"] = "0" * 40
        write_canonical(identity_path, identity)
        update_manifest_artifact(
            self.directory, "core-input.json", "inputs/method-build-and-docs.identity.json"
        )
        identity_root = sha256_digest(identity_path.read_bytes())
        self.rewrite_checks(lambda value: next(
            input_record
            for check in value["checks"] if check["property"] == "lean-build"
            for input_record in check["inputs"] if input_record["artifact_id"] == "method-workflow-identity"
        ).update({"root": identity_root}), sync_typed_result=True)
        with self.assertRaisesRegex(AuditError, "exact head method bytes"):
            generate_core(self.directory / "core-input.json")

    def test_external_proof_acquisition_receipt_is_observation_provenance(self):
        before_core = generate_core(self.directory / "core-input.json")
        before_observation = generate_observation(
            self.directory / "observation-input.json", self.directory / "expected-core.json"
        )
        core_paths = {item["path"] for item in load(self.directory / "core-input.json")["artifacts"]}
        self.assertNotIn("inputs/linked-proof-acquisition-receipt.json", core_paths)
        receipt_path = self.directory / "inputs" / "linked-proof-acquisition-receipt.json"
        receipt = load(receipt_path)
        receipt["final_url"] = "https://attacker.example/mutable-proof"
        write_canonical(receipt_path, receipt)
        update_manifest_artifact(
            self.directory, "observation-input.json", "inputs/linked-proof-acquisition-receipt.json"
        )
        after_core = generate_core(self.directory / "core-input.json")
        after_observation = generate_observation(
            self.directory / "observation-input.json", self.directory / "expected-core.json"
        )
        self.assertEqual(before_core["root"], after_core["root"])
        self.assertNotEqual(before_observation["root"], after_observation["root"])

    def test_artifact_root_mismatch_is_refused(self):
        path = self.directory / "core-input.json"
        value = load(path)
        value["artifact_root"] = "sha256:" + "0" * 64
        write_canonical(path, value)
        with self.assertRaisesRegex(AuditError, "artifact root"):
            generate_core(path)

    def test_path_traversal_is_refused(self):
        path = self.directory / "core-input.json"
        value = load(path)
        value["artifacts"][0]["path"] = "../generator.json"
        value["artifact_root"] = content_root({"artifacts": sorted(
            value["artifacts"], key=lambda item: (item["id"], item["role"], item["path"], item["sha256"])
        )})
        write_canonical(path, value)
        with self.assertRaisesRegex(AuditError, "normalized relative path"):
            generate_core(path)

    def test_noncanonical_and_symlink_artifact_paths_are_refused(self):
        path = self.directory / "core-input.json"
        value = load(path)
        value["artifacts"][0]["path"] = "inputs//generator.json"
        value["artifact_root"] = content_root({"artifacts": sorted(
            value["artifacts"], key=lambda item: (item["id"], item["role"], item["path"], item["sha256"])
        )})
        write_canonical(path, value)
        with self.assertRaisesRegex(AuditError, "normalized relative path"):
            generate_core(path)

        shutil.copy2(FIXTURES / "conditional-erdos-427-4884" / "core-input.json", path)
        target = self.directory / "inputs" / "generator-target.json"
        generator = self.directory / "inputs" / "generator.json"
        generator.rename(target)
        generator.symlink_to(target.name)
        with self.assertRaisesRegex(AuditError, "symlink"):
            generate_core(path)

    def test_untrusted_strings_are_escaped_in_human_projection(self):
        malicious = '<script>alert("x")</script>|row\nnext [click](javascript:alert(1)) **bold**'
        self.rewrite_checks(
            lambda value: value["checks"][0]["evidence"][0].update({"statement": malicious}),
            sync_typed_result=True,
        )
        core = generate_core(self.directory / "core-input.json")
        markdown = render_markdown(core)
        self.assertNotIn("<script>", markdown)
        self.assertIn("&lt;script&gt;", markdown)
        self.assertIn("\\|row next", markdown)
        self.assertNotIn("[click](javascript:alert(1))", markdown)
        self.assertIn(r"\[click\]\(javascript:alert\(1\)\)", markdown)
        self.assertIn(r"\*\*bold\*\*", markdown)


class SchemaAndBoundaryTest(unittest.TestCase):

    def test_schema_declares_complete_check_contract(self):
        schema = json.loads((REPO / "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit.v1.schema.json").read_text())
        check = schema["$defs"]["check"]
        for field in (
            "id", "kind", "mode", "property", "role", "scope", "inputs", "implementation", "outcome",
            "evidence", "conditions", "assumptions", "limitations", "does_not_establish",
        ):
            self.assertIn(field, check["required"])
        self.assertEqual(
            set(check["properties"]["outcome"]["enum"]),
            {"pass", "fail", "inconclusive", "error", "unavailable"},
        )
        self.assertEqual(check["properties"]["does_not_establish"]["minItems"], 1)
        self.assertEqual(set(check["properties"]["property"]["enum"]), set(SUPPORTED_PROPERTIES))
        typed_constraints = [
            item["properties"]["inputs"]
            for item in check["allOf"]
            if "properties" in item and "inputs" in item["properties"]
        ]
        self.assertEqual(len(typed_constraints), 1)
        self.assertEqual(typed_constraints[0]["minContains"], 1)
        self.assertEqual(typed_constraints[0]["maxContains"], 1)
        core_roles = set(
            schema["$defs"]["coreArtifact"]["allOf"][1]["properties"]["role"]["enum"]
        )
        self.assertNotIn("provenance_event", core_roles)
        self.assertNotIn("acquisition_receipt", core_roles)
        self.assertTrue(check["allOf"])

    def test_offline_schema_registry_validates_all_fixture_records(self):
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError as error:
            self.skipTest(f"optional schema validator unavailable: {error}")
        schema_dir = REPO / "audit/pr-audit-v1/schemas"
        core_schema = json.loads((schema_dir / "formal-conjectures.pr-audit.v1.schema.json").read_text())
        observation_schema = json.loads((schema_dir / "formal-conjectures.pr-audit-observation.v1.schema.json").read_text())
        registry = Registry().with_resources([
            (core_schema["$id"], Resource.from_contents(core_schema)),
            (observation_schema["$id"], Resource.from_contents(observation_schema)),
        ])
        core_validator = Draft202012Validator(core_schema, registry=registry)
        observation_validator = Draft202012Validator(observation_schema, registry=registry)
        for name in NAMES:
            with self.subTest(name=name, record="core"):
                core_validator.validate(load(FIXTURES / name / "expected-core.json"))
            with self.subTest(name=name, record="observation"):
                observation_validator.validate(load(FIXTURES / name / "expected-observation.json"))

    def test_observation_schema_requires_time_status_and_core_root(self):
        schema = json.loads((REPO / "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit-observation.v1.schema.json").read_text())
        self.assertIn("observed_at", schema["required"])
        self.assertIn("core", schema["required"])
        self.assertIn("pull_request", schema["required"])

    def test_core_module_has_no_execution_or_network_adapter_imports(self):
        source = (REPO / "scripts/pr_audit.py").read_text()
        for forbidden in (
            "import subprocess", "import socket", "import urllib", "import requests", "import http",
            "os.system(", "os.popen(", "subprocess.", "eval(", "exec(", "__import__(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
