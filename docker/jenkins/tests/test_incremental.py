import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
import incremental as inc
from pipeline import Pipeline


class IncrementalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = inc.module_graph(DIRECTORY.parents[1])
        entries = json.loads((DIRECTORY / "repositories.json").read_text())
        cls.repositories = [{"path": "my-tools", "commit": "root1"}] + [
            {"path": e["path"], "commit": "old"} for e in entries]
        cls.previous = {"repositories": cls.repositories}

    def plan(self, *changed, previous=True, force=False):
        current = [{**r, "commit": "new" if r["path"] in changed else r["commit"]} for r in self.repositories]
        return inc.make_plan(current, self.previous if previous else None, self.graph, force)

    def test_first_build_or_missing_snapshot_builds_everything(self):
        plan = self.plan(previous=False)
        self.assertTrue(plan["utils"])
        self.assertTrue(plan["frontend"])
        self.assertEqual(set(plan["modules"]), set(self.graph))

    def test_streaming_change_builds_only_streaming_and_deployable_app(self):
        plan = self.plan("my-tools/streaming-platform-app")
        self.assertEqual(set(plan["modules"]), {"streaming-platform-app", "my-tools-app"})
        self.assertFalse(plan["utils"])
        self.assertFalse(plan["frontend"])
        self.assertTrue(plan["integration"])

    def test_frontend_only_skips_backend_and_utils(self):
        plan = self.plan("my-tools-react")
        self.assertFalse(plan["backend"])
        self.assertFalse(plan["utils"])
        self.assertTrue(plan["frontend"])
        self.assertTrue(plan["integration"])

    def test_unchanged_sources_skip_all_compilation_and_integration(self):
        plan = self.plan()
        for flag in ["backend", "frontend", "utils", "integration", "tools"]:
            self.assertFalse(plan[flag], flag)

    def test_utils_change_rebuilds_all_backend_but_reuses_frontend(self):
        plan = self.plan("bervan-utils")
        self.assertTrue(plan["utils"])
        self.assertEqual(set(plan["modules"]), set(self.graph))
        self.assertFalse(plan["frontend"])

    def test_common_change_rebuilds_transitive_consumers(self):
        plan = self.plan("my-tools/common")
        self.assertEqual(set(plan["modules"]), set(self.graph))
        self.assertFalse(plan["utils"])
        self.assertFalse(plan["frontend"])

    def test_file_storage_change_rebuilds_indirect_consumers(self):
        plan = self.plan("my-tools/file-storage-app")
        self.assertTrue({"file-storage-app", "streaming-platform-app", "invest-track-app", "photo-library-app", "my-tools-app"} <= set(plan["modules"]))
        self.assertNotIn("common", plan["modules"])
        self.assertNotIn("cook-book", plan["modules"])

    def test_root_change_or_force_rebuild_invalidates_both_components(self):
        for plan in [self.plan("my-tools"), self.plan(force=True)]:
            self.assertTrue(plan["full"])
            self.assertTrue(plan["utils"])
            self.assertTrue(plan["frontend"])

    def fixture_pipeline(self, path):
        pipeline = object.__new__(Pipeline)
        pipeline.workspace = path
        pipeline.repo = path / "sources/my-tools"
        pipeline.repo.mkdir(parents=True)
        pipeline.cache = path / ".cache"
        pipeline.release = path / "release"
        pipeline.release.mkdir()
        fixtures = {
            ".cache/m2/com/bervan/common/latest/common.jar": b"tested library",
            "package-contexts/backend/my-tools-app.jar": b"tested backend",
            "package-contexts/backend/configuration/application.properties": b"",
            "package-contexts/frontend/dist/index.html": b"frontend",
            "package-contexts/frontend/nginx.conf": b"nginx",
        }
        for name, content in fixtures.items():
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        pipeline.save({"release": "b1-root", "repositories": self.repositories,
                       "images": [{"component": "backend", "id": "sha256:backend"},
                                  {"component": "frontend", "id": "sha256:frontend"}],
                       "integrationTests": True})
        return pipeline

    def test_snapshot_integrity_detects_corruption_and_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = self.fixture_pipeline(Path(tmp))
            pipeline.promote()
            baseline = pipeline.cache / "successful"
            self.assertIsNotNone(inc.load_snapshot(baseline))
            jar = baseline / "contexts/backend/my-tools-app.jar"
            jar.write_bytes(b"corrupt")
            self.assertIsNone(inc.load_snapshot(baseline))
            jar.unlink()
            self.assertIsNone(inc.load_snapshot(baseline))

    def test_failed_build_artifacts_are_replaced_by_successful_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = self.fixture_pipeline(Path(tmp))
            pipeline.promote()
            jar = pipeline.cache / "m2/com/bervan/common/latest/common.jar"
            jar.write_bytes(b"artifacts left by failed build")
            with patch("pipeline.module_graph", return_value=self.graph):
                pipeline.plan()
            self.assertEqual(jar.read_bytes(), b"tested library")
            self.assertFalse(pipeline.metadata()["plan"]["backend"])
            self.assertEqual((pipeline.workspace / "package-contexts/backend/my-tools-app.jar").read_bytes(), b"tested backend")

    def test_disabled_integration_does_not_replace_tested_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = self.fixture_pipeline(Path(tmp))
            pipeline.promote()
            before = inc.inventory(pipeline.cache / "successful")
            data = pipeline.metadata()
            data.update(integrationTests=False, release="b2-untested")
            pipeline.save(data)
            pipeline.promote()
            self.assertEqual(inc.inventory(pipeline.cache / "successful"), before)

    def test_unchanged_images_are_reused_by_id_or_repackaged_if_daemon_cache_was_lost(self):
        for image_available in [True, False]:
            with self.subTest(image_available=image_available), tempfile.TemporaryDirectory() as tmp:
                pipeline = self.fixture_pipeline(Path(tmp))
                pipeline.config = pipeline.repo / "docker/jenkins"
                pipeline.promote()
                with patch("pipeline.module_graph", return_value=self.graph):
                    pipeline.plan()
                data = pipeline.metadata()
                data["release"] = "b2-root"
                pipeline.save(data)
                with patch("pipeline.subprocess.run", return_value=type("Result", (), {"returncode": 0 if image_available else 1})()), \
                        patch("pipeline.run", return_value="sha256:result") as execute:
                    pipeline.images()
                commands = [call.args for call in execute.call_args_list]
                builds = [c for c in commands if c[:2] == ("docker", "build")]
                tags = [c for c in commands if c[:2] == ("docker", "tag")]
                self.assertEqual(len(builds), 0 if image_available else 2)
                self.assertEqual(len(tags), 2 if image_available else 0)
                self.assertEqual([i["reused"] for i in pipeline.metadata()["images"]], [image_available] * 2)
                if image_available:
                    self.assertEqual(tags[0][2], "sha256:backend")

    def test_cli_flags_work_inside_tool_container_without_agent_docker_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            metadata = Path(tmp) / "release.json"
            metadata.write_text(json.dumps({"plan": self.plan("my-tools/streaming-platform-app")}))
            result = subprocess.run([sys.executable, str(DIRECTORY / "incremental.py"), str(metadata), "modules"],
                                    env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"},
                                    text=True, capture_output=True, check=True)
            self.assertEqual(set(result.stdout.strip().split(",")), {"streaming-platform-app", "my-tools-app"})

    def run_build_script(self, directory, step, plan):
        path = Path(directory)
        config = path / "sources/my-tools/docker/jenkins"
        config.mkdir(parents=True)
        (config / "incremental.py").write_text((DIRECTORY / "incremental.py").read_text())
        for name in ["sources/bervan-utils", "sources/my-tools-react", "release", "bin"]:
            (path / name).mkdir(parents=True, exist_ok=True)
        (path / "release/release.json").write_text(json.dumps({"plan": plan}))
        log = path / "commands.jsonl"
        executable = (f"#!{sys.executable}\nimport json, os, sys\n"
                      "with open(os.environ['CI_COMMAND_LOG'], 'a') as out:\n"
                      " out.write(json.dumps({'tool':os.path.basename(sys.argv[0]), 'args':sys.argv[1:], 'cwd':os.getcwd()})+'\\n')\n")
        for tool in ["mvn", "npm", "npx", "curl"]:
            script = path / "bin" / tool
            script.write_text(executable)
            script.chmod(0o755)
        env = {**os.environ, "WORKSPACE": str(path), "CI_COMMAND_LOG": str(log),
               "PATH": str(path / "bin") + os.pathsep + os.environ["PATH"]}
        subprocess.run(["bash", str(DIRECTORY / "build-step.sh"), step], env=env,
                       capture_output=True, text=True, check=True)
        return [json.loads(line) for line in log.read_text().splitlines()]

    def test_backend_shell_invokes_only_selected_modules_and_skips_utils(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands = self.run_build_script(tmp, "backend", self.plan("my-tools/streaming-platform-app"))
            self.assertEqual(len(commands), 1)
            command = commands[0]
            self.assertEqual(command["tool"], "mvn")
            selected = command["args"][command["args"].index("-pl") + 1]
            self.assertEqual(set(selected.split(",")), {"streaming-platform-app", "my-tools-app"})
            self.assertNotIn("-am", command["args"])
            self.assertNotIn("bervan-utils", command["cwd"])

    def test_full_backend_shell_builds_utils_before_complete_reactor(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands = self.run_build_script(tmp, "backend", self.plan(previous=False))
            self.assertEqual(len(commands), 2)
            self.assertTrue(commands[0]["cwd"].endswith("/sources/bervan-utils"))
            self.assertTrue(commands[1]["cwd"].endswith("/sources/my-tools"))
            self.assertNotIn("-pl", commands[1]["args"])

    def test_integration_installs_missing_node_dependencies_without_rebuilding_maven_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands = self.run_build_script(tmp, "integration", self.plan("my-tools/streaming-platform-app"))
            self.assertTrue(any(c["tool"] == "npm" and c["args"] == ["ci"] for c in commands))
            maven = next(c for c in commands if c["tool"] == "mvn")
            self.assertEqual(maven["args"][maven["args"].index("-pl") + 1], "my-tools-app")
            self.assertNotIn("-am", maven["args"])


if __name__ == "__main__":
    unittest.main()
