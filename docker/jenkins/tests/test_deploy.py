import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
import deploy

spec = importlib.util.spec_from_file_location("deploy_client", DIRECTORY / "deploy-client.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def manifest():
    release = "b17-abcdef012345"
    return {"release": release, "integrationPassed": False, "images": [
        {"component": component, "tag": f"my-tools-{component}:{release}", "id": "sha256:" + digit * 64}
        for component, digit in [("backend", "a"), ("frontend", "b")]]}


def bundle(extra=None, bad_checksum=False):
    data = manifest()
    archive = data["release"] + ".tar.gz"
    content = b"exported image archive"
    digest = "0" * 64 if bad_checksum else hashlib.sha256(content).hexdigest()
    files = {"release.json": json.dumps(data).encode(), archive: content,
             archive + ".sha256": f"{digest}  {archive}\n".encode()}
    if extra:
        files.update(extra)
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as output:
        for name, value in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(value)
            output.addfile(info, io.BytesIO(value))
    stream.seek(0)
    return stream


class DeploymentTests(unittest.TestCase):
    def test_transported_script_runs_plan_without_host_script_or_config_installation(self):
        namespace = {"__name__": "transported_deploy"}
        exec(compile((DIRECTORY / "deploy.py").read_text(), "<local deployment>", "exec"), namespace)
        self.assertNotIn("__file__", namespace)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env_my_tools").write_text("TEST_FIXTURE_ONLY=true\n")
            (root / "docker-compose.yml").write_text("services: {}\n")
            config = (DIRECTORY / "deploy.config.json").read_text()
            arguments = ["-c", "--production-directory", str(root), "--config-json", config, "plan"]
            mask = os.umask(0o077)
            handler = signal.getsignal(signal.SIGTERM)
            try:
                output = io.StringIO()
                with patch.object(sys, "argv", arguments), patch.object(sys, "stdin", Mock(buffer=bundle())), \
                        patch.dict(os.environ), patch.object(namespace["Deployment"], "preflight"), \
                        patch.object(namespace["Deployment"], "docker") as docker, contextlib.redirect_stdout(output):
                    namespace["main"]()
                docker.assert_not_called()
                self.assertIn("Plan verified", output.getvalue())
            finally:
                os.umask(mask)
                signal.signal(signal.SIGTERM, handler)

    def test_host_paths_and_private_state_are_derived_from_repo_without_reading_env_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env_my_tools").write_text("TEST_FIXTURE_ONLY=true\n")
            (root / "docker-compose.yml").write_text("services: {}\n")
            config = json.loads((DIRECTORY / "deploy.config.json").read_text())
            with patch.object(deploy, "__file__", str(root / "docker/jenkins/deploy.py")):
                deployment = deploy.Deployment(config)
            self.assertEqual(deployment.production, root.resolve())
            self.assertEqual(deployment.env_file, root.resolve() / ".env_my_tools")
            self.assertEqual(deployment.state, root.resolve() / ".jenkins-deploy")
            self.assertEqual(deployment.state.stat().st_mode & 0o777, 0o700)

    def test_release_bundle_is_verified_without_runtime_environment_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, archive = deploy.receive_bundle(bundle(), Path(tmp), 1024 * 1024)
            self.assertEqual(data, manifest())
            self.assertEqual(archive.read_bytes(), b"exported image archive")

    def test_bundle_rejects_traversal_environment_files_checksum_mismatch_and_size_limits(self):
        for content, limit in [(bundle({"../escape": b"bad"}), 1024 * 1024),
                               (bundle({".env_my_tools": b"bad"}), 1024 * 1024),
                               (bundle(bad_checksum=True), 1024 * 1024), (bundle(), 10)]:
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                deploy.receive_bundle(content, Path(tmp), limit)

    def test_manifest_requires_exact_components_tags_and_image_ids(self):
        for change in ["component", "tag", "id"]:
            data = manifest()
            data["images"][0][change] = "untrusted"
            with self.subTest(change=change), self.assertRaises(ValueError):
                deploy.manifest_images(data)

    def runtime_fixture(self):
        deployment = object.__new__(deploy.Deployment)
        deployment.rendered = {"services": {}, "networks": {"default": {"name": "existing_default"}}}
        deployment.apps = {}
        for service in deploy.SERVICES.values():
            deployment.rendered["services"][service] = {
                "container_name": service, "environment": {"PASSWORD": "secret-test-sentinel"},
                "networks": {"default": {}}, "volumes": [], "ports": []}
            deployment.apps[service] = {"Image": "sha256:" + "c" * 64, "Mounts": [],
                "State": {"Running": True},
                "Config": {"Env": ["PASSWORD=secret-test-sentinel"],
                           "Labels": {"com.docker.compose.project": "existing", "com.docker.compose.service": service}},
                "HostConfig": {"PortBindings": {}}, "NetworkSettings": {"Networks": {"existing_default": {}}}}
        return deployment

    def test_project_is_derived_from_existing_containers_and_mismatches_are_rejected(self):
        for action, project, allowed in [("plan", "", True), ("deploy", "", True),
                                          ("deploy", "other", False), ("deploy", "existing", True)]:
            with self.subTest(action=action, project=project), tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
                deployment = self.runtime_fixture()
                deployment.state = Path(tmp)
                deployment.project = project
                containers = dict(deployment.apps)
                for identifier, service in [("db-id", "my-tools-mariadb"), ("rabbit-id", "my-tools-rabbitmq"), ("caddy-id", "caddy")]:
                    containers[identifier] = {"Mounts": [], "State": {"Running": True}, "Config": {"Labels": {"com.docker.compose.service": service}}}
                deployment.inspect = Mock(side_effect=lambda name: containers[name])
                deployment.docker = Mock(return_value="db-id rabbit-id caddy-id")
                deployment.compose = Mock(return_value=json.dumps(deployment.rendered))
                deployment.health = Mock()
                if allowed:
                    deployment.preflight(action)
                    self.assertEqual(deployment.project, "existing")
                    self.assertEqual(set(deployment.protected), {"db-id", "rabbit-id", "caddy-id"})
                    self.assertEqual(json.loads((deployment.state / "project.json").read_text()), {"project": "existing"})
                    deploy.write_json(deployment.state / "project.json", {"project": "other"})
                    with self.assertRaisesRegex(ValueError, "previously verified"):
                        deployment.preflight(action)
                else:
                    with self.assertRaises(ValueError):
                        deployment.preflight(action)
                    deployment.compose.assert_not_called()

    def test_frontend_only_release_does_not_restart_backend_but_backend_change_refreshes_frontend(self):
        deployment = self.runtime_fixture()
        deployment.inspect = Mock(side_effect=lambda service: deployment.apps[service])
        unchanged = {s: c["Image"] for s, c in deployment.apps.items()}
        self.assertEqual(deployment.services_to_update(unchanged), [])
        self.assertEqual(deployment.services_to_update({**unchanged, "my-tools-react": "new"}), ["my-tools-react"])
        self.assertEqual(deployment.services_to_update({**unchanged, "my-tools-app": "new"}), ["my-tools-app", "my-tools-react"])
        deployment.apps["my-tools-app"]["State"]["Running"] = False
        self.assertEqual(deployment.services_to_update(unchanged), ["my-tools-app", "my-tools-react"])

    def test_rollback_preflight_allows_stopped_application_and_does_not_require_broken_http_route(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            deployment = self.runtime_fixture()
            deployment.state = Path(tmp)
            deployment.project = "existing"
            deployment.apps["my-tools-app"]["State"]["Running"] = False
            containers = dict(deployment.apps)
            for service in ["my-tools-mariadb", "my-tools-rabbitmq", "caddy"]:
                containers[service] = {"Mounts": [], "State": {"Running": True},
                                       "Config": {"Labels": {"com.docker.compose.service": service}}}
            deployment.inspect = Mock(side_effect=lambda name: containers[name])
            deployment.docker = Mock(return_value="my-tools-mariadb my-tools-rabbitmq caddy")
            deployment.compose = Mock(return_value=json.dumps(deployment.rendered))
            deployment.health = Mock(side_effect=RuntimeError("HTTP unavailable"))
            deployment.preflight("rollback")
            deployment.health.assert_not_called()

    def test_runtime_drift_blocks_mount_network_port_and_environment_changes(self):
        deployment = self.runtime_fixture()
        deployment.check_runtime()
        for field, value in [("environment", {"PASSWORD": "changed"}),
                             ("volumes", [{"type": "bind", "source": "/missing/path", "target": "/data"}]),
                             ("networks", {}), ("ports", [{"target": 80, "published": "8080"}])]:
            candidate = copy.deepcopy(deployment)
            candidate.rendered["services"]["my-tools-app"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError) as error:
                candidate.check_runtime()
            self.assertNotIn("secret-test-sentinel", str(error.exception))

    def test_failed_commands_do_not_leak_environment_or_inspect_output(self):
        result = Mock(returncode=1, stdout="secret-test-sentinel", stderr="PASSWORD=secret-test-sentinel")
        with patch.object(deploy.subprocess, "run", return_value=result), self.assertRaises(RuntimeError) as error:
            deploy.command("docker", "compose", "config")
        self.assertNotIn("secret-test-sentinel", str(error.exception))

    def test_compose_update_targets_only_application_services_and_existing_project(self):
        deployment = self.runtime_fixture()
        deployment.project = "existing"
        deployment.production = Path("/srv/current-production")
        deployment.env_file = deployment.production / ".env_my_tools"
        deployment.compose_file = deployment.production / "docker-compose.yml"
        with tempfile.TemporaryDirectory() as tmp:
            deployment.state = Path(tmp)
            images = {s: c["Image"] for s, c in deployment.apps.items()}
            deployment.inspect = Mock(side_effect=lambda service: deployment.apps[service])
            deployment.services_to_update = Mock(return_value=list(deploy.SERVICES.values()))
            deployment.health = Mock()
            deployment.check_protected = Mock()
            with patch.object(deploy, "command", return_value="") as command:
                deployment.apply(images, "test")
            args = command.call_args.args
            self.assertEqual(args[args.index("--project-name") + 1], "existing")
            self.assertIn("--no-deps", args)
            self.assertIn("--no-build", args)
            self.assertEqual(args[-2:], ("my-tools-app", "my-tools-react"))
            for prohibited in ["down", "prune", "--volumes", "--remove-orphans", "my-tools-mariadb", "caddy"]:
                self.assertNotIn(prohibited, args)

    def test_failure_restores_old_images_and_does_not_advance_current_record(self):
        deployment = self.runtime_fixture()
        deployment.project = "existing"
        deployment.docker = Mock()
        deployment.apply = Mock(side_effect=[RuntimeError("not ready"), None])
        with tempfile.TemporaryDirectory() as tmp:
            deployment.state = Path(tmp)
            current = deployment.state / "current.json"
            current.write_text('{"existing": true}')
            images = deploy.manifest_images(manifest())
            with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
                deployment.transition(images, "release", False)
            self.assertEqual(json.loads(current.read_text()), {"existing": True})
            recovered = deployment.apply.call_args_list[1].args[0]
            self.assertEqual(recovered, {s: c["Image"] for s, c in deployment.apps.items()})
            history = next(deployment.state.glob("deployment-*.json"))
            self.assertEqual(json.loads(history.read_text())["status"], "recovered")

    def test_success_records_both_versions_for_explicit_rollback(self):
        deployment = self.runtime_fixture()
        deployment.project = "existing"
        deployment.docker = Mock()
        deployment.apply = Mock()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            deployment.state = Path(tmp)
            images = deploy.manifest_images(manifest())
            deployment.transition(images, "release", False)
            record = json.loads((deployment.state / "current.json").read_text())
            self.assertEqual(record["images"], images)
            self.assertEqual(record["previous"], {s: c["Image"] for s, c in deployment.apps.items()})
            self.assertFalse(record["integrationPassed"])

    def test_rollback_refuses_unknown_manual_image_changes(self):
        deployment = self.runtime_fixture()
        deployment.project = "existing"
        deployment.docker = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            deployment.state = Path(tmp)
            deploy.write_json(deployment.state / "current.json", {
                "project": "existing", "images": deploy.manifest_images(manifest()), "previous": {}})
            with self.assertRaisesRegex(ValueError, "blind rollback"):
                deployment.rollback()
            deployment.docker.assert_not_called()

    def test_local_deployment_uses_host_docker_network_and_exact_production_path(self):
        env = {"MY_TOOLS_PRODUCTION_DIR": "/srv/My Tools"}
        command = client.deployment_command(env, "plan")
        self.assertEqual(command[:4], ["docker", "--host", "unix:///var/run/docker.sock", "run"])
        self.assertEqual(command[command.index("--network") + 1], "host")
        self.assertIn("type=bind,src=/srv/My Tools,dst=/srv/My Tools", command)
        self.assertIn("type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock", command)
        self.assertIn((DIRECTORY / "deploy.py").read_text(), command)
        self.assertEqual(command[-1], "plan")
        for path in ["/", "relative", "/opt/../../bad", "/srv/a,b", "/srv/bad\npath"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                client.deployment_command({"MY_TOOLS_PRODUCTION_DIR": path}, "deploy")

    def test_rollback_launcher_clears_ci_tls_environment_before_using_host_socket(self):
        env = {"DEPLOY_ACTION": "rollback", "MY_TOOLS_PRODUCTION_DIR": "/srv/my-tools",
               "DOCKER_HOST": "tcp://docker:2376", "DOCKER_TLS_VERIFY": "1",
               "DOCKER_CERT_PATH": "/certs/client", "COMPOSE_PROJECT_NAME": "ci"}
        with patch.dict(os.environ, env, clear=True), patch.object(client.subprocess, "run", return_value=Mock(returncode=0)) as run:
            client.main()
        self.assertFalse(any(key.startswith(("DOCKER_", "COMPOSE_")) for key in run.call_args.kwargs["env"]))
        self.assertIn("unix:///var/run/docker.sock", run.call_args.args[0])

    def test_external_bind_paths_are_validated_on_host_without_creating_directories(self):
        deployment = self.runtime_fixture()
        source = "/external/storage"
        deployment.rendered["services"]["my-tools-app"]["volumes"] = [
            {"type": "bind", "source": source, "target": "/data"}]
        deployment.apps["my-tools-app"]["Mounts"] = [
            {"Type": "bind", "Source": source, "Destination": "/data", "RW": True}]
        deployment.docker = Mock()
        deployment.check_runtime()
        self.assertIn(f"type=bind,src={source},dst=/check,readonly", deployment.docker.call_args.args)
        deployment.docker.side_effect = RuntimeError("missing host source")
        with self.assertRaisesRegex(RuntimeError, "missing host source"):
            deployment.check_runtime()


if __name__ == "__main__":
    unittest.main()
