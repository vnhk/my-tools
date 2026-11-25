"""Build/release artifacts on the CI Docker daemon; never deploy production."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from incremental import SCHEMA, inventory, load_snapshot, make_plan, module_graph, plan_flag


TOOLS_IMAGE = "my-tools-ci-tools:local"


def run(*args, cwd=None, capture=False):
    result = subprocess.run(args, cwd=cwd, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def validate_repository(entry):
    path = entry["path"]
    if not re.fullmatch(r"(?:my-tools/[a-z0-9-]+|my-tools-react|bervan-utils)", path):
        raise ValueError("Invalid repository destination")
    url = urlsplit(entry["url"])
    if (url.scheme != "https" or url.netloc != "github.com" or
            url.query or url.fragment or not re.fullmatch(r"/[\w.-]+/[\w.-]+", url.path)):
        raise ValueError("Only public GitHub HTTPS URLs without credentials are supported")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", entry["revision"]):
        raise ValueError("Invalid repository revision")


def reject_secret_names(paths):
    for path in paths:
        for name in Path(path).parts:
            if (name in {".local", "jenkins.local.conf", "env_my_tools"} or
                    name.startswith(".env")) and not name.endswith(".example"):
                raise ValueError("A runtime configuration/secret file was found in source or package context")


def verify_modules(repo, entries):
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    modules = [m.text.strip() for m in ET.parse(repo / "pom.xml").findall("m:modules/m:module", ns)]
    configured = {e["path"] for e in entries}
    if not modules or any(f"my-tools/{m}" not in configured for m in modules):
        raise ValueError("The checkout manifest does not cover every Maven module")
    for module in modules:
        if not (repo / module / "pom.xml").is_file():
            raise ValueError(f"Missing Maven module: {module}")


def require_ci_endpoint(env):
    if env.get("DOCKER_HOST") != "tcp://docker:2376" or env.get("DOCKER_TLS_VERIFY") != "1":
        raise ValueError("CI Docker TLS endpoint required; production Docker is not supported")


class Pipeline:
    def __init__(self):
        self.repo = Path(__file__).resolve().parents[2]
        self.workspace = Path(os.environ["WORKSPACE"]).resolve()
        if self.repo != self.workspace / "sources/my-tools":
            raise ValueError("Run only from the Jenkins sources/my-tools checkout")
        require_ci_endpoint(os.environ)
        self.release = self.workspace / "release"
        self.cache = self.workspace / ".cache"
        self.release.mkdir(exist_ok=True)
        self.cache.mkdir(exist_ok=True)
        self.config = self.repo / "docker/jenkins"

    def metadata(self):
        return json.loads((self.release / "release.json").read_text())

    def save(self, data):
        (self.release / "release.json").write_text(json.dumps(data, indent=2) + "\n")

    def checkout(self):
        entries = json.loads((self.config / "repositories.json").read_text())
        paths = set()
        for entry in entries:
            validate_repository(entry)
            target = self.workspace / "sources" / entry["path"]
            if entry["path"] in paths or target.exists() or target.is_symlink():
                raise ValueError("Duplicate or nonempty checkout destination; start a new build")
            paths.add(entry["path"])
        main_commit = run("git", "rev-parse", "HEAD", cwd=self.repo, capture=True)
        number = os.environ.get("BUILD_NUMBER", "0")
        if not number.isdigit():
            raise ValueError("Invalid build number")
        data = {"release": f"b{number}-{main_commit[:12]}",
                "repositories": [{"path": "my-tools", "commit": main_commit}],
                "integrationTests": os.environ.get("RUN_INTEGRATION_TESTS", "true") == "true"}
        reject_secret_names(run("git", "ls-files", cwd=self.repo, capture=True).splitlines())
        for entry in entries:
            target = self.workspace / "sources" / entry["path"]
            target.mkdir(parents=True)
            run("git", "init", "--quiet", str(target))
            run("git", "remote", "add", "origin", entry["url"], cwd=target)
            run("git", "fetch", "--depth=1", "origin", entry["revision"], cwd=target)
            run("git", "checkout", "--detach", "FETCH_HEAD", cwd=target)
            reject_secret_names(run("git", "ls-files", cwd=target, capture=True).splitlines())
            data["repositories"].append({**entry, "commit": run("git", "rev-parse", "HEAD", cwd=target, capture=True)})
        verify_modules(self.repo, entries)
        self.save(data)
        print(f"Recorded {len(data['repositories'])} repository commits for {data['release']}")

    def tools(self):
        run("docker", "build", "--file", str(self.config / "build.Dockerfile"),
            "--tag", TOOLS_IMAGE, str(self.config))

    def plan(self):
        data = self.metadata()
        baseline = self.cache / "successful"
        previous = load_snapshot(baseline)
        plan = make_plan(data["repositories"], previous, module_graph(self.repo),
                         os.environ.get("FORCE_REBUILD", "false") == "true")
        # Failed builds may have installed partial/latest artifacts. Restore only
        # our own Maven group from the verified successful snapshot every time.
        local = self.cache / "m2/com/bervan"
        if local.exists():
            shutil.rmtree(local)
        if previous and not plan["full"]:
            shutil.copytree(baseline / "maven/com/bervan", local)
        contexts = self.workspace / "package-contexts"
        if contexts.exists():
            shutil.rmtree(contexts)
        if previous and not plan["full"]:
            shutil.copytree(baseline / "contexts", contexts)
        data["plan"] = plan
        data["baseline"] = previous["release"] if previous else None
        self.save(data)
        print(json.dumps(plan, indent=2))

    def flag(self, name):
        print(plan_flag(self.metadata(), name))

    def promote(self):
        data = self.metadata()
        if not data["integrationTests"]:
            print("Integration tests disabled: retaining the last fully tested snapshot")
            return
        data["snapshotSchema"] = SCHEMA
        staging = self.cache / "successful-next"
        backup = self.cache / "successful-old"
        for path in [staging, backup]:
            if path.exists():
                shutil.rmtree(path)
        staging.mkdir()
        shutil.copytree(self.cache / "m2/com/bervan", staging / "maven/com/bervan")
        shutil.copytree(self.workspace / "package-contexts", staging / "contexts")
        (staging / "release.json").write_text(json.dumps(data, indent=2) + "\n")
        (staging / "checksums.json").write_text(json.dumps(inventory(staging), indent=2) + "\n")
        if not load_snapshot(staging):
            raise ValueError("Incomplete successful snapshot; previous baseline retained")
        baseline = self.cache / "successful"
        if baseline.exists():
            baseline.rename(backup)
        staging.rename(baseline)
        if backup.exists():
            shutil.rmtree(backup)
        print(f"Recorded successful snapshot: {data['release']}")

    def container_command(self, step):
        return ["docker", "run", "--rm", "--init", "--memory=2300m", "--memory-swap=2300m", "--cpus=2",
                "--name", self.container_name(),
                "--user", f"{os.getuid()}:{os.getgid()}", "--group-add", "0",
                # This is the nested CI daemon's host network and socket, not the production daemon.
                "--network", "host", "--mount", f"type=bind,src={self.workspace},dst={self.workspace}",
                "--mount", f"type=bind,src={self.cache},dst=/ci-cache",
                "--mount", "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
                "--workdir", str(self.workspace), "--env", f"WORKSPACE={self.workspace}",
                "--env", "HOME=/ci-cache/home", "--env", "DOCKER_HOST=unix:///var/run/docker.sock",
                "--env", "TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1", "--env", "CI=true",
                TOOLS_IMAGE, "bash", str(self.config / "build-step.sh"), step]

    def build(self, step):
        (self.cache / "home").mkdir(exist_ok=True)
        try:
            run(*self.container_command(step))
        finally:
            # Only the explicitly named tool container on the guarded CI daemon.
            subprocess.run(["docker", "rm", "--force", self.container_name()],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def container_name(self):
        identity = f"{self.workspace}:{os.environ.get('BUILD_NUMBER', '0')}"
        return "my-tools-ci-" + hashlib.sha256(identity.encode()).hexdigest()[:16]

    def images(self):
        data = self.metadata()
        contexts = self.workspace / "package-contexts"
        backend = contexts / "backend"
        frontend = contexts / "frontend"
        plan = data["plan"]
        if plan["backend"]:
            if backend.exists():
                shutil.rmtree(backend)
            backend.mkdir(parents=True)
            shutil.copy2(self.repo / "my-tools-app/target/my-tools-app.jar", backend / "my-tools-app.jar")
            shutil.copytree(self.repo / "my-tools-app/configuration", backend / "configuration")
        if plan["frontend"]:
            if frontend.exists():
                shutil.rmtree(frontend)
            frontend.mkdir(parents=True)
            react = self.workspace / "sources/my-tools-react"
            shutil.copytree(react / "dist", frontend / "dist")
            shutil.copy2(react / "nginx.conf", frontend / "nginx.conf")
        reject_secret_names([p.relative_to(contexts) for p in contexts.rglob("*")])
        images = []
        for component, context in [("backend", backend), ("frontend", frontend)]:
            tag = f"my-tools-{component}:{data['release']}"
            reused = False
            if not plan[component]:
                baseline = load_snapshot(self.cache / "successful")
                previous_image = next(i for i in baseline["images"] if i["component"] == component)
                exists = subprocess.run(["docker", "image", "inspect", previous_image["id"]],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                if exists:
                    run("docker", "tag", previous_image["id"], tag)
                    reused = True
            if not reused:
                # Missing CI image: rebuild only its runtime package from verified artifacts.
                run("docker", "build", "--label", f"com.bervan.release={data['release']}",
                    "--file", str(self.config / f"{component}.Dockerfile"), "--tag", tag, str(context))
            images.append({"component": component, "tag": tag,
                           "reused": reused,
                           "id": run("docker", "image", "inspect", "--format", "{{.Id}}", tag, capture=True)})
        data["images"] = images
        self.save(data)

    def export(self):
        data = self.metadata()
        output = self.release / f"{data['release']}.tar.gz"
        process = subprocess.Popen(["docker", "image", "save", *[i["tag"] for i in data["images"]]], stdout=subprocess.PIPE)
        try:
            with gzip.open(output, "wb", compresslevel=1) as archive:
                shutil.copyfileobj(process.stdout, archive)
        except BaseException:
            process.kill()
            process.wait()
            output.unlink(missing_ok=True)
            raise
        finally:
            process.stdout.close()
        if process.wait() != 0:
            output.unlink(missing_ok=True)
            raise RuntimeError("Image export failed")
        digest = hashlib.sha256()
        with output.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        output.with_suffix(output.suffix + ".sha256").write_text(f"{digest.hexdigest()}  {output.name}\n")


def main():
    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    pipeline = Pipeline()
    stage = sys.argv[1]
    if stage in {"backend", "frontend", "integration"}:
        pipeline.build(stage)
    elif stage == "flag":
        pipeline.flag(sys.argv[2])
    elif stage in {"checkout", "plan", "tools", "images", "export", "promote"}:
        getattr(pipeline, stage)()
    else:
        raise ValueError("Unknown pipeline stage")


if __name__ == "__main__":
    main()
