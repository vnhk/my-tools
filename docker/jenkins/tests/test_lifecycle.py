import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "jenkins.sh"


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="jenkins lifecycle ")
        self.root = Path(self.directory.name)
        self.secrets = self.root / "secrets"
        self.calls = self.root / "docker-calls.jsonl"
        docker = self.root / "docker"
        docker.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['DOCKER_CALLS'], 'a') as f:\n"
            "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        )
        docker.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{self.root}{os.pathsep}{os.environ['PATH']}",
            "JENKINS_LOCAL_DIR": str(self.secrets),
            "JENKINS_BIND_ADDRESS": "192.0.2.10",
            "JENKINS_PORT": "18092",
            "JENKINS_PUBLIC_URL": "",
            "DOCKER_CALLS": str(self.calls),
            "COMPOSE_FILE": "/should-not-use-production.yml",
            "COMPOSE_PROJECT_NAME": "production-must-not-be-touched",
        }

    def tearDown(self):
        self.directory.cleanup()

    def run_command(self, *args):
        result = subprocess.run(
            ["bash", str(SCRIPT), *args], cwd=self.root, env=self.env,
            text=True, capture_output=True, check=True,
        )
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        for call in calls:
            self.assertEqual(call[:5], ["compose", "--env-file", "/dev/null", "--project-name", "my-tools-jenkins"])
            self.assertEqual(call[5:7], ["--file", str(SCRIPT.parent / "compose.yml")])
            self.assertNotIn("production-must-not-be-touched", call)
            self.assertFalse(set(call) & {"down", "prune", "rm", "--volumes"})
        return result, calls

    def test_first_start_only_bootstraps_controller(self):
        result, calls = self.run_command("start")
        self.assertEqual(calls[0][7:], ["up", "--build", "--detach", "jenkins"])
        self.assertTrue((self.secrets / "admin-password").stat().st_size > 0)
        self.assertEqual((self.secrets / "agent-secret").read_text(), "")
        self.assertEqual(self.secrets.stat().st_mode & 0o777, 0o700)
        password = (self.secrets / "admin-password").read_text().strip()
        self.assertNotIn(password, result.stdout + result.stderr)
        self.assertIn("http://192.0.2.10:18092/", result.stdout)

    def test_configured_start_preserves_secrets_and_starts_build_profile(self):
        self.secrets.mkdir()
        (self.secrets / "admin-password").write_text("existing-admin-test-secret")
        (self.secrets / "agent-secret").write_text("existing-agent-test-secret")
        result, calls = self.run_command("start")
        self.assertEqual(calls[0][7:], ["--profile", "build", "up", "--build", "--detach"])
        self.assertEqual((self.secrets / "admin-password").read_text(), "existing-admin-test-secret")
        self.assertNotIn("existing-admin-test-secret", result.stdout + result.stderr)
        self.assertNotIn("existing-agent-test-secret", result.stdout + result.stderr)

    def test_stop_targets_ci_services_only_and_keeps_secrets(self):
        self.secrets.mkdir()
        secret = self.secrets / "admin-password"
        secret.write_text("existing-admin-test-secret")
        _, calls = self.run_command("stop")
        self.assertEqual(calls[0][7:], ["--profile", "build", "stop", "--timeout", "60", "agent", "jenkins", "docker"])
        self.assertEqual(secret.read_text(), "existing-admin-test-secret")

    def test_unknown_command_cannot_forward_destructive_compose_actions(self):
        result = subprocess.run(["bash", str(SCRIPT), "down", "-v"], env=self.env, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.calls.exists())

    def test_start_requires_an_explicit_bind_address_before_creating_secrets(self):
        self.env.pop("JENKINS_BIND_ADDRESS")
        result = subprocess.run(["bash", str(SCRIPT), "start"], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Set JENKINS_BIND_ADDRESS", result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.secrets.exists())

    def test_stop_still_works_without_network_configuration(self):
        self.env.pop("JENKINS_BIND_ADDRESS")
        self.run_command("stop")

    def test_explicit_public_url_overrides_derived_address(self):
        self.env["JENKINS_PUBLIC_URL"] = "https://ci.example.com/"
        result, _ = self.run_command("start")
        self.assertIn("https://ci.example.com/", result.stdout)


if __name__ == "__main__":
    unittest.main()
