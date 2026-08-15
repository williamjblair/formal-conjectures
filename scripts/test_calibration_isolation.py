import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

import calibration_isolation


class CalibrationIsolationTest(unittest.TestCase):
    def test_lock_is_closed_and_digest_stable(self):
        lock = calibration_isolation.load_lock()
        self.assertEqual(lock["platform"], "linux/amd64")
        self.assertEqual(
            calibration_isolation.lock_digest(lock),
            "95ac559ad151264997789a7434ea1ea4b029371f133666d346eacd60995a520b",
        )

    @mock.patch("calibration_isolation.shutil.which", return_value=None)
    def test_missing_daemon_is_do_not_execute(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / "new-output"
            report = calibration_isolation.preflight(output)
        self.assertFalse(report["build_ready"])
        self.assertEqual(report["next_action"], "do_not_execute")
        gates = {item["name"]: item for item in report["gates"]}
        self.assertTrue(gates["unused_output"]["satisfied"])
        self.assertFalse(gates["docker_client"]["satisfied"])

    @mock.patch("calibration_isolation.shutil.which", return_value="/usr/bin/docker")
    def test_exact_local_image_and_unused_output_can_pass(self, _which):
        lock = calibration_isolation.load_lock()
        base = lock["container"]["base"]

        def runner(command):
            if command[1] == "info":
                return subprocess.CompletedProcess(command, 0, "{}\n", "")
            return subprocess.CompletedProcess(command, 0, f'["{base}"]\n', "")

        with tempfile.TemporaryDirectory() as tmp:
            report = calibration_isolation.preflight(
                pathlib.Path(tmp) / "new-output", runner=runner)
        self.assertTrue(report["build_ready"])
        self.assertFalse(report["execute_ready"])
        self.assertNotIn(
            "execute", calibration_isolation.commands(pathlib.Path("/tmp/new")))

    def test_rendered_execution_is_networkless_and_read_only(self):
        image_id = "sha256:" + "a" * 64
        command = calibration_isolation.commands(
            pathlib.Path("/tmp/new"), image_id=image_id)["execute"]
        self.assertIn("--network", command)
        self.assertIn("none", command)
        self.assertIn("--read-only", command)
        self.assertIn("no-new-privileges=true", command)
        self.assertIn(f"FC_CALIBRATION_IMAGE_ID={image_id}", command)
        self.assertEqual(command[-1], image_id)

    @mock.patch("calibration_isolation.shutil.which", return_value="/usr/bin/docker")
    def test_execution_requires_matching_local_image_id(self, _which):
        lock = calibration_isolation.load_lock()
        base = lock["container"]["base"]
        image_id = "sha256:" + "b" * 64

        def runner(command):
            if command[1] == "info":
                return subprocess.CompletedProcess(command, 0, "{}\n", "")
            if command[-1] == "{{json .RepoDigests}}":
                return subprocess.CompletedProcess(command, 0, f'["{base}"]\n', "")
            return subprocess.CompletedProcess(command, 0, image_id + "\n", "")

        with tempfile.TemporaryDirectory() as tmp:
            report = calibration_isolation.preflight(
                pathlib.Path(tmp) / "new-output", image_id=image_id, runner=runner)
        self.assertTrue(report["execute_ready"])
        self.assertEqual(report["next_action"], "execute_calibration")


if __name__ == "__main__":
    unittest.main()
