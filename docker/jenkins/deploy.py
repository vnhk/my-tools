"""Run in a local deployment container; never print runtime secrets to Jenkins."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.request import urlopen
import uuid

SERVICES = {"backend": "my-tools-app", "frontend": "my-tools-react"}
RELEASE = re.compile(r"b[0-9]+-[0-9a-f]{12}")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}")


def command(*args):
    # Inspect/Compose output can contain runtime credentials. Never echo it,
    # including stderr or exception representations, into the Jenkins console.
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} operation failed (exit {result.returncode}); inspect locally on the host")
    return result.stdout


def manifest_images(data):
    release = data.get("release", "")
    if not RELEASE.fullmatch(release):
        raise ValueError("Invalid release identifier")
    images = data.get("images", [])
    if len(images) != 2 or {i.get("component") for i in images} != set(SERVICES):
        raise ValueError("A release must contain exactly backend and frontend images")
    for image in images:
        if (not IMAGE.fullmatch(image.get("id", "")) or
                image.get("tag") != f"my-tools-{image['component']}:{release}"):
            raise ValueError("Invalid image identity/tag in release manifest")
    return {SERVICES[i["component"]]: i["id"] for i in images}


def receive_bundle(source, destination, max_bytes):
    names = set()
    total = 0
    with tarfile.open(fileobj=source, mode="r|") as bundle:
        for member in bundle:
            name = member.name
            valid = name == "release.json" or re.fullmatch(r"b[0-9]+-[0-9a-f]{12}\.tar\.gz(?:\.sha256)?", name)
            if not valid or not member.isfile() or name in names:
                raise ValueError("Unexpected/unsafe release bundle entry")
            total += member.size
            if total > max_bytes or (not name.endswith(".tar.gz") and member.size > 1024 * 1024):
                raise ValueError("Release bundle exceeds configured size limit")
            names.add(name)
            with bundle.extractfile(member) as incoming, (destination / name).open("wb") as target:
                while block := incoming.read(1024 * 1024):
                    target.write(block)
    data = json.loads((destination / "release.json").read_text())
    manifest_images(data)
    archive = f"{data['release']}.tar.gz"
    if names != {"release.json", archive, archive + ".sha256"}:
        raise ValueError("Release bundle is incomplete")
    checksum = (destination / (archive + ".sha256")).read_text().split()
    if len(checksum) != 2 or checksum[1] != archive:
        raise ValueError("Invalid image archive checksum file")
    digest = hashlib.sha256()
    with (destination / archive).open("rb") as incoming:
        while block := incoming.read(1024 * 1024):
            digest.update(block)
    if digest.hexdigest() != checksum[0]:
        raise ValueError("Image archive checksum mismatch")
    return data, destination / archive


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def mount_identity(mount):
    return (mount["Type"], mount.get("Name") if mount["Type"] == "volume" else mount["Source"],
            mount["Destination"], not mount["RW"])


class Deployment:
    def __init__(self, config):
        self.config = config
        self.production = Path(config.get("production_directory") or Path(__file__).resolve().parents[2]).resolve(strict=True)
        self.state = Path(config.get("state_directory", ".jenkins-deploy"))
        if not self.state.is_absolute():
            self.state = self.production / self.state
        if not self.state.is_absolute() or self.state.resolve() == self.production:
            raise ValueError("Use an absolute, separate deployment state directory")
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.state.stat().st_mode & 0o077:
            raise ValueError("Deployment state directory permissions must be 0700")
        self.project = config.get("project", "")
        self.env_file = Path(config["env_file"])
        if not self.env_file.is_absolute():
            self.env_file = self.production / self.env_file
        if not self.env_file.is_file():
            raise ValueError("Production runtime environment file does not exist")
        self.compose_file = self.production / config.get("compose_file", "docker-compose.yml")
        if not self.compose_file.is_file():
            raise ValueError("Production Compose file does not exist")
        for name in ["frontend_url", "backend_url"]:
            if not re.match(r"https?://[^/@\s]+(?:/|$)", config[name]):
                raise ValueError("Configure explicit unauthenticated HTTP(S) health URLs")

    def compose(self, *args, override=None):
        argv = ["docker", "--host", "unix:///var/run/docker.sock", "compose", "--project-name", self.project,
                "--project-directory", str(self.production), "--env-file", str(self.env_file),
                "--file", str(self.compose_file)]
        if override:
            argv += ["--file", str(override)]
        return command(*argv, *args)

    def docker(self, *args):
        return command("docker", "--host", "unix:///var/run/docker.sock", *args)

    def inspect(self, name):
        return json.loads(self.docker("inspect", name))[0]

    def preflight(self, action):
        self.apps = {service: self.inspect(service) for service in SERVICES.values()}
        projects = {c["Config"]["Labels"].get("com.docker.compose.project") for c in self.apps.values()}
        if len(projects) != 1 or None in projects:
            raise ValueError("Application containers must belong to one existing Compose project")
        detected = projects.pop()
        if not self.project:
            self.project = detected
        if self.project != detected or self.project == "my-tools-jenkins":
            raise ValueError("Configured production project does not match the running application")
        pin = self.state / "project.json"
        if pin.is_file() and json.loads(pin.read_text())["project"] != self.project:
            raise ValueError("Running Compose project differs from the previously verified production project")
        print(f"Production project: {self.project}", flush=True)
        for service, container in self.apps.items():
            if container["Config"]["Labels"].get("com.docker.compose.service") != service:
                raise ValueError("Unexpected application service ownership")
            if action != "rollback" and not container["State"]["Running"]:
                raise ValueError("Application containers must be running before deployment")
        self.rendered = json.loads(self.compose("config", "--format", "json"))
        self.check_runtime()
        ids = self.docker("ps", "--all", "--quiet", "--filter", f"label=com.docker.compose.project={self.project}").split()
        self.protected = {}
        for identifier in ids:
            container = self.inspect(identifier)
            service = container["Config"]["Labels"].get("com.docker.compose.service")
            if service not in SERVICES.values():
                self.protected[identifier] = sorted(mount_identity(m) for m in container["Mounts"])
        for service in ["my-tools-mariadb", "my-tools-rabbitmq", "caddy"]:
            if not any(self.inspect(i)["Config"]["Labels"].get("com.docker.compose.service") == service
                       and self.inspect(i)["State"]["Running"] for i in self.protected):
                raise ValueError(f"Required protected service is missing: {service}")
        print(f"Protected containers: {len(self.protected)}", flush=True)
        for service, container in self.apps.items():
            print(f"{service}: {container['Image']}; preserved mounts: {len(container['Mounts'])}", flush=True)
        # Validate routing/readiness URLs against the existing application before
        # touching images or containers, including on the first plan.
        if action != "rollback":
            self.health()
        write_json(pin, {"project": self.project})

    def check_runtime(self):
        for service, container in self.apps.items():
            wanted = self.rendered["services"][service]
            if wanted.get("container_name") != service:
                raise ValueError("Production Compose application container names differ")
            actual_env = dict(item.split("=", 1) for item in container["Config"]["Env"] if "=" in item)
            if any(actual_env.get(key) != str(value) for key, value in wanted.get("environment", {}).items()):
                raise ValueError(f"Runtime environment drift for {service}; reconcile locally before deploying")
            mounts = []
            for mount in wanted.get("volumes", []):
                source = mount.get("source")
                if mount["type"] == "volume":
                    source = self.rendered["volumes"][source]["name"]
                elif mount["type"] == "bind":
                    pass  # Host paths are checked after comparing mount identities.
                else:
                    raise ValueError("Unsupported application mount type")
                mounts.append((mount["type"], source, mount["target"], mount.get("read_only", False)))
            if sorted(mounts) != sorted(mount_identity(m) for m in container["Mounts"]):
                raise ValueError(f"Mount drift for {service}; refusing to change data mappings")
            for mount in wanted.get("volumes", []):
                if mount["type"] == "bind":
                    # --mount fails for a missing host path rather than creating it.
                    source = mount["source"]
                    self.docker("run", "--rm", "--pull", "never", "--network", "none",
                                "--mount", f"type=bind,src={source},dst=/check,readonly",
                                "--entrypoint", "python3", "my-tools-jenkins-agent:local",
                                "-c", "pass")
            expected_ports = {(str(p["target"]) + "/" + p.get("protocol", "tcp"), str(p["published"]), p.get("host_ip", "0.0.0.0"))
                              for p in wanted.get("ports", [])}
            actual_ports = {(key, p["HostPort"], p.get("HostIp") or "0.0.0.0") for key, values in container["HostConfig"].get("PortBindings", {}).items()
                            for p in (values or [])}
            if expected_ports != actual_ports:
                raise ValueError(f"Published port drift for {service}")
            expected_networks = {self.rendered["networks"][name]["name"] for name in wanted.get("networks", {})}
            if expected_networks != set(container["NetworkSettings"]["Networks"]):
                raise ValueError(f"Network drift for {service}")

    def health(self):
        context = ssl.create_default_context() if self.config.get("tls_verify", True) else ssl._create_unverified_context()
        deadline = time.monotonic() + self.config.get("health_timeout_seconds", 240)
        while time.monotonic() < deadline:
            try:
                for name in ["frontend_url", "backend_url"]:
                    with urlopen(self.config[name], timeout=5, context=context) as response:
                        if response.status != 200:
                            raise ValueError("Unexpected health HTTP status")
                        if name == "backend_url":
                            payload = json.loads(response.read(4 * 1024 * 1024))
                            if not isinstance(payload, dict) or not payload:
                                raise ValueError("Backend metadata response is not ready")
                if all(self.inspect(s)["State"]["Running"] for s in SERVICES.values()):
                    return
            except (OSError, ValueError):
                pass
            time.sleep(3)
        raise RuntimeError("Production HTTP readiness checks timed out")

    def check_protected(self):
        for identifier, mounts in self.protected.items():
            container = self.inspect(identifier)
            if mounts != sorted(mount_identity(m) for m in container["Mounts"]):
                raise RuntimeError("Protected service mount configuration changed")

    def services_to_update(self, images):
        changed = set()
        for service, image in images.items():
            try:
                container = self.inspect(service)
                if container["Image"] != image or not container["State"]["Running"]:
                    changed.add(service)
            except RuntimeError:
                changed.add(service)  # Also recover a missing/partially recreated container.
        if SERVICES["backend"] in changed:
            changed.add(SERVICES["frontend"])  # Refresh nginx's backend DNS resolution.
        return [service for service in SERVICES.values() if service in changed]

    def apply(self, images, operation):
        override = self.state / f"override-{operation}.json"
        write_json(override, {"services": {service: {"image": image} for service, image in images.items()}})
        services = self.services_to_update(images)
        if services:
            self.compose("up", "--detach", "--no-deps", "--no-build", "--pull", "never", "--force-recreate",
                         *services, override=override)
        self.health()
        for service, image in images.items():
            container = self.inspect(service)
            if container["Image"] != image:
                raise RuntimeError("Running application image does not match selected release")
            if sorted(mount_identity(m) for m in container["Mounts"]) != sorted(mount_identity(m) for m in self.apps[service]["Mounts"]):
                raise RuntimeError("Application data mounts changed after recreation")
        self.check_protected()

    def deploy(self, data, archive):
        images = manifest_images(data)
        self.docker("image", "load", "--input", str(archive))
        for image in data["images"]:
            if json.loads(self.docker("image", "inspect", image["tag"]))[0]["Id"] != image["id"]:
                raise ValueError("Loaded image does not match manifest image ID")
        self.transition(images, data["release"], data.get("integrationPassed", False))

    def rollback(self):
        record = json.loads((self.state / "current.json").read_text())
        if record["project"] != self.project or any(self.apps[s]["Image"] != image for s, image in record["images"].items()):
            raise ValueError("Live images differ from deployment record; refusing blind rollback")
        for image in record["previous"].values():
            self.docker("image", "inspect", image)
        self.transition(record["previous"], "rollback", None)

    def transition(self, images, release, integration_passed):
        previous = {s: c["Image"] for s, c in self.apps.items()}
        if images == previous and all(c["State"]["Running"] for c in self.apps.values()):
            self.health()
            print("Selected images are already running; no containers changed", flush=True)
            return
        operation = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
        for component, service in SERVICES.items():
            self.docker("tag", previous[service], f"my-tools-{component}:rollback-{operation}")
        record = {"operation": operation, "project": self.project, "release": release,
                  "images": images, "previous": previous, "integrationPassed": integration_passed,
                  "status": "started"}
        history = self.state / f"deployment-{operation}.json"
        write_json(history, record)
        try:
            self.apply(images, operation)
        except BaseException:
            print("Deployment failed; restoring previous application images", flush=True)
            try:
                self.apply(previous, operation + "-recovery")
                record["status"] = "recovered"
            except BaseException:
                record["status"] = "recovery-failed"
                print("Automatic recovery failed; operator intervention is required", flush=True)
            write_json(history, record)
            raise
        record["status"] = "success"
        write_json(history, record)
        write_json(self.state / "current.json", record)
        print(f"Production deployment successful: {release}", flush=True)


def main():
    os.umask(0o077)
    # Host deployment must not inherit a user's CI/remote Docker context.
    for key in list(os.environ):
        if key.startswith(("DOCKER_", "COMPOSE_")):
            os.environ.pop(key)
    args = argparse.ArgumentParser()
    args.add_argument("--config", default=str(Path(globals().get("__file__", "deploy.py")).with_name("deploy.config.json")))
    args.add_argument("--config-json", help="Non-secret repository deployment settings passed by Jenkins")
    args.add_argument("--production-directory", help="Production checkout detected by jenkins.sh")
    args.add_argument("action", choices=["plan", "deploy", "rollback"])
    options = args.parse_args()
    if options.config_json:
        config = json.loads(options.config_json)
    else:
        with open(options.config) as source:
            config = json.load(source)
    if options.production_directory:
        config["production_directory"] = options.production_directory
    deployment = Deployment(config)
    def interrupted(signum, frame):
        raise InterruptedError("Deployment interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    with (deployment.state / "deployment.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another production deployment holds the lock") from None
        deployment.preflight(options.action)
        if options.action == "rollback":
            deployment.rollback()
        else:
            with tempfile.TemporaryDirectory(prefix="incoming-", dir=deployment.state) as directory:
                data, archive = receive_bundle(sys.stdin.buffer, Path(directory),
                                               deployment.config.get("max_archive_bytes", 10 * 1024 ** 3))
                print(f"Selected release: {data['release']}; integration validated: {bool(data.get('integrationPassed'))}", flush=True)
                if options.action == "deploy":
                    deployment.deploy(data, archive)
                else:
                    print("Plan verified. No images loaded and no containers changed.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Deployment stopped: {error}", file=sys.stderr)
        sys.exit(1)
