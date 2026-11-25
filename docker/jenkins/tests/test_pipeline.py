import importlib.util
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET


DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location("ci_pipeline", DIRECTORY / "pipeline.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class PipelineTests(unittest.TestCase):
    def test_manifest_covers_all_maven_modules_and_external_repositories(self):
        entries = json.loads((DIRECTORY / "repositories.json").read_text())
        paths = [e["path"] for e in entries]
        self.assertEqual(len(paths), len(set(paths)))
        for entry in entries:
            ci.validate_repository(entry)
        ns = {"m": "http://maven.apache.org/POM/4.0.0"}
        pom = ET.parse(DIRECTORY.parents[1] / "pom.xml")
        modules = {"my-tools/" + m.text.strip() for m in pom.findall("m:modules/m:module", ns)}
        self.assertEqual(set(paths), modules | {"bervan-utils", "my-tools-react"})

    def test_repository_destinations_cannot_escape_sources_or_overwrite_main_checkout(self):
        entry = {"path": "my-tools/common", "url": "https://github.com/vnhk/common.git", "revision": "main"}
        for path in ["../production", "/production", "my-tools", "my-tools/../production", "my-tools/.local"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                ci.validate_repository({**entry, "path": path})

    def test_checkout_rejects_credential_urls_and_unsafe_revisions(self):
        entry = {"path": "bervan-utils", "url": "https://github.com/vnhk/bervan-utils.git", "revision": "main"}
        for url in ["https://token@github.com/vnhk/repo.git", "http://github.com/vnhk/repo.git", "https://github.com/vnhk/repo.git?token=secret"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                ci.validate_repository({**entry, "url": url})
        with self.assertRaises(ValueError):
            ci.validate_repository({**entry, "revision": "--upload-pack=bad"})

    def test_secret_paths_rejected_without_reading_file_contents(self):
        for path in [".env", ".env_my_tools", "module/.env.local", "env_my_tools", "configuration/.local/key", "jenkins.local.conf"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                ci.reject_secret_names([path])
        ci.reject_secret_names([".env.example", "module/.env.local.example", "configuration/app.properties"])

    def test_cannot_run_from_local_production_checkout_or_production_docker(self):
        with patch.dict(os.environ, {"WORKSPACE": "/not-a-jenkins-workspace"}):
            with self.assertRaisesRegex(ValueError, "Run only"):
                ci.Pipeline()
        for env in [{}, {"DOCKER_HOST": "unix:///var/run/docker.sock"},
                    {"DOCKER_HOST": "tcp://docker:2376", "DOCKER_TLS_VERIFY": "0"}]:
            with self.subTest(env=env), self.assertRaisesRegex(ValueError, "CI Docker"):
                ci.require_ci_endpoint(env)
        ci.require_ci_endpoint({"DOCKER_HOST": "tcp://docker:2376", "DOCKER_TLS_VERIFY": "1"})

    def test_build_containers_use_only_ci_socket_and_do_not_inherit_host_secrets(self):
        pipeline = object.__new__(ci.Pipeline)
        pipeline.workspace = Path("/home/jenkins/agent/workspace/my-tools-build")
        pipeline.cache = pipeline.workspace / ".cache"
        pipeline.config = pipeline.workspace / "sources/my-tools/docker/jenkins"
        command = pipeline.container_command("backend")
        self.assertIn("--memory=2300m", command)
        self.assertIn("DOCKER_HOST=unix:///var/run/docker.sock", command)
        self.assertIn("TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1", command)
        self.assertNotIn("--env-file", command)
        self.assertFalse(any(".env" in arg or "OPENAI_API_KEY" in arg for arg in command))
        self.assertIn("type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock", command)

    def test_maven_module_validation_detects_incomplete_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "pom.xml").write_text('<project xmlns="http://maven.apache.org/POM/4.0.0"><modules><module>common</module></modules></project>')
            with self.assertRaisesRegex(ValueError, "manifest"):
                ci.verify_modules(repo, [])
            with self.assertRaisesRegex(ValueError, "Missing Maven module"):
                ci.verify_modules(repo, [{"path": "my-tools/common"}])
            (repo / "common").mkdir()
            (repo / "common/pom.xml").write_text("<project/>")
            ci.verify_modules(repo, [{"path": "my-tools/common"}])

    def test_export_creates_verifiable_archive_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = object.__new__(ci.Pipeline)
            pipeline.release = Path(directory)
            pipeline.save({"release": "b1-abc", "images": [{"tag": "backend:b1"}, {"tag": "frontend:b1"}]})
            process = Mock(stdout=io.BytesIO(b"docker image archive"))
            process.wait.return_value = 0
            with patch.object(ci.subprocess, "Popen", return_value=process) as popen:
                pipeline.export()
            self.assertEqual(popen.call_args.args[0], ["docker", "image", "save", "backend:b1", "frontend:b1"])
            archive = pipeline.release / "b1-abc.tar.gz"
            self.assertEqual(gzip.decompress(archive.read_bytes()), b"docker image archive")
            self.assertEqual((pipeline.release / "b1-abc.tar.gz.sha256").read_text(),
                             f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  b1-abc.tar.gz\n")

    def test_failed_export_does_not_leave_a_publishable_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = object.__new__(ci.Pipeline)
            pipeline.release = Path(directory)
            pipeline.save({"release": "b2-abc", "images": [{"tag": "backend:b2"}]})
            process = Mock(stdout=io.BytesIO(b"incomplete"))
            process.wait.return_value = 1
            with patch.object(ci.subprocess, "Popen", return_value=process):
                with self.assertRaisesRegex(RuntimeError, "export failed"):
                    pipeline.export()
            self.assertFalse((pipeline.release / "b2-abc.tar.gz").exists())
            self.assertFalse((pipeline.release / "b2-abc.tar.gz.sha256").exists())


if __name__ == "__main__":
    unittest.main()
