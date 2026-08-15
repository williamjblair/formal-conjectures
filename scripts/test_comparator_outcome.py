import unittest

from comparator_outcome import RESULT_SCHEMA, adapt


def result(outcome="pass", witnesses=None):
    return {
        "schema": RESULT_SCHEMA,
        "property": "statement_equivalence_and_permitted_axioms",
        "outcome": outcome,
        "witnesses": [] if witnesses is None else witnesses,
    }


class ComparatorOutcomeTest(unittest.TestCase):
    def test_uncaught_exception_is_invocation_error_not_policy_fail(self):
        report = adapt(
            1, b"uncaught exception: Illegal axiom detected: 'External.shiu'\n", b"")
        self.assertEqual(report["invocation"]["outcome"], "error")
        self.assertEqual(report["result_parse"]["outcome"], "not_attempted")
        self.assertEqual(report["policy_result"]["outcome"], "not_evaluated")

    def test_structured_witness_can_report_policy_failure(self):
        report = adapt(0, b"", b"", result("fail", ["External.shiu"]))
        self.assertEqual(report["invocation"]["outcome"], "pass")
        self.assertEqual(report["result_parse"]["outcome"], "pass")
        self.assertEqual(report["policy_result"]["outcome"], "fail")

    def test_missing_structured_result_is_parse_error(self):
        report = adapt(0, b"Your solution is okay!\n", b"")
        self.assertEqual(report["result_parse"]["outcome"], "error")
        self.assertEqual(report["policy_result"]["outcome"], "not_evaluated")

    def test_invalid_failure_without_witness_is_parse_error(self):
        report = adapt(0, b"", b"", result("fail"))
        self.assertEqual(report["result_parse"]["outcome"], "error")
        self.assertEqual(report["policy_result"]["outcome"], "not_evaluated")

    def test_missing_binary_is_unavailable(self):
        report = adapt(None, b"", b"", unavailable="missing comparator")
        self.assertEqual(report["invocation"]["outcome"], "unavailable")
        self.assertEqual(report["policy_result"]["outcome"], "not_evaluated")


if __name__ == "__main__":
    unittest.main()
