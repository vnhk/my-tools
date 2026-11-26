"""Run deployment tooling in a temporary container on the local production Docker."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

from deploy import manifest_images


def deployment_command(env, action):
    root = Path(env["MY_TOOLS_PRODUCTION_DIR"])
    if (not root.is_absolute() or ".." in root.parts or "," in str(root) or
            str(root) == "/" or any(ord(char) < 32 for char in str(root))):
        raise ValueError("Production repo path must be absolute; run jenkins.sh start from the server checkout")
    if action not in {"plan", "deploy", "rollback"}:
        raise ValueError("Unknown deployment action")
    directory = Path(__file__).resolve().parent
    source = (directory / "deploy.py").read_text()
    config = json.loads((directory / "deploy.config.json").read_text())
    # Match host paths exactly so Compose preserves existing bind mount sources.
    # Host networking makes loopback health checks reach production, not CI.
    return ["docker", "--host", "unix:///var/run/docker.sock", "run",
            "--rm", "--init", "--interactive", "--pull", "never", "--network", "host",
            "--user", "0:0", "--mount", "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
            "--mount", f"type=bind,src={root},dst={root}",
            "--entrypoint", "python3", "my-tools-jenkins-agent:local", "-c", source,
            "--production-directory", str(root), "--config-json", json.dumps(config), action]


def main():
    action = os.environ["DEPLOY_ACTION"]
    command = deployment_command(os.environ, action)
    local_env = {key: value for key, value in os.environ.items()
                 if not key.startswith(("DOCKER_", "COMPOSE_"))}
    if action == "rollback":
        if subprocess.run(command, stdin=subprocess.DEVNULL, env=local_env).returncode:
            raise RuntimeError("Production rollback failed; see host report above")
        return
    artifacts = Path("artifacts")
    metadata = artifacts / "release.json"
    if not metadata.is_file() or metadata.is_symlink():
        raise ValueError("Selected build has no regular release manifest")
    data = json.loads(metadata.read_text())
    manifest_images(data)
    archive = artifacts / f"{data['release']}.tar.gz"
    files = [artifacts / "release.json", archive, archive.with_suffix(archive.suffix + ".sha256")]
    if any(not path.is_file() or path.is_symlink() for path in files):
        raise ValueError("Selected build does not have a complete exported release")
    print(f"{action}: {data['release']}; integration validated: {bool(data.get('integrationPassed'))}", flush=True)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, env=local_env)
    try:
        with tarfile.open(fileobj=process.stdin, mode="w|") as bundle:
            for path in files:
                bundle.add(path, arcname=path.name, recursive=False)
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Production deployment command failed; see sanitized host report above")
    except BaseException:
        process.stdin.close()
        process.terminate()
        process.wait()
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Deployment client stopped: {error}", file=sys.stderr)
        sys.exit(1)
