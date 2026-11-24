# On-demand Jenkins on the production host

This is the installation/bootstrap stage of JNKS. It does not deploy My Tools or
run `linux-build-script.sh`. Existing production containers, configuration and
volumes are not used by this stack. The application build/release pipeline is
the next stage, after the smoke job and repository/commit manifest are verified.

## Isolation and resources

The fixed Compose project name is `my-tools-jenkins`. Its named volumes store
Jenkins configuration/history, agent workspace and the **separate CI Docker
daemon's** images/cache. No host Docker socket, production data directory or
production volume is mounted into CI. No CI Docker ports are published.

Build commands sent to `tcp://docker:2376` act on the CI daemon, not production
Docker. This first version intentionally cannot deploy to production or change
production containers. CI images also are not production-host images: transferring
an approved image will require an explicit later release/deployment step.

| Service | Memory ceiling | CPU ceiling | Purpose |
| --- | --- | --- | --- |
| Jenkins controller | 1 GiB (512 MiB heap) | 1 CPU | UI, scheduling, configuration |
| Agent | 512 MiB (256 MiB heap) | 1 CPU | One executor, Git and Docker CLI |
| CI Docker daemon | 3 GiB, no additional swap | 2 CPUs | Container builds and their cache |

Build backend and frontend sequentially. The nominal CI budget is 4.5 GiB, but
resource ceilings are not a guarantee that the entire server fits in RAM.
The current production application permits a 9 GiB Java heap, in addition to JVM
overhead, MariaDB, RabbitMQ and the OS. Monitor the first real build using
`docker stats` and `free -h`. On Linux, verify memory accounting for nested build
containers before relying on the CI daemon's limit as an aggregate build limit.

Docker-in-Docker requires a privileged container. This avoids sharing production
Docker control, but is not a security boundary against malicious pipelines:
restrict Jenkins to trusted administrators and trusted code. Stop the stack
when not in use. None of the services restart automatically after host reboot.

## Requirements

- Linux server, Docker Engine, Docker Compose v2, Bash and OpenSSL.
- Internet access for official Jenkins/Docker images and Jenkins plugins.
- Space for an additional copy of images, caches and build workspaces.
- The files in this directory on the server; run all lifecycle commands **there**.

Image tags initially select supported release families (Jenkins LTS/Java 21 and
Docker 29). After a successful first boot, record and pin tested image digests and
plugin versions before treating installation as reproducible across upgrades.
`start` does not request pulls of newer base images; image/plugin rebuilds still
depend on the build cache. Schedule and test upgrades deliberately.

## First start

From any directory, using the correct path to this checkout:

```sh
bash docker/jenkins/jenkins.sh start
bash docker/jenkins/jenkins.sh status
```

The first start builds and starts only the controller. Local generated secrets
are under `.local/` next to this README, excluded from Git. Existing files are
never overwritten. Neither application nor MCP `.env` files are read by the wrapper.
An optional exported `JENKINS_LOCAL_DIR` can select another absolute secret directory.

For access from your computer, forward the loopback-only port:

```sh
ssh -N -L 8092:127.0.0.1:8092 USER@PRODUCTION_HOST
```

Open `http://localhost:8092`. Username: `admin`. Read the generated password
locally from `docker/jenkins/.local/admin-password`; do not paste it into chat,
commits or pipeline definitions. This bootstrap credential remains configured by
`jenkins.yaml` on each start. Password rotation must update its secret source too.

### Connect the one-time build agent

1. In Jenkins, open **Manage Jenkins → Nodes → my-tools-builder**.
2. Copy its inbound agent secret to `docker/jenkins/.local/agent-secret` on the
   server, replacing the empty file. Keep its enclosing `.local/` directory private
   (mode 0700). The wrapper makes the mounted secret files readable by the
   containers while other host users cannot traverse that directory.
   Do not copy the whole command from the node page, only its secret value.
3. Run `bash docker/jenkins/jenkins.sh start` again. It detects a nonempty secret
   and starts the CI daemon and agent as well as the controller.
4. Confirm the `my-tools-builder` node is online. Create a Pipeline job and paste
   the contents of `Jenkinsfile.smoke` as its script. Run it once.

The agent connects via WebSocket; no additional Jenkins agent port is exposed.
The smoke job verifies tooling/access only. It does not build or deploy the app.

## Nightly manual usage

```sh
# Start CI; it restores existing configuration and cache.
bash docker/jenkins/jenkins.sh start

# Run your job in Jenkins and wait for it to finish before stopping CI.
bash docker/jenkins/jenkins.sh stop
```

`stop` targets only `agent`, `jenkins`, and `docker` in `my-tools-jenkins`.
It does not execute `down`, remove volumes, prune Docker or touch the production
Compose stack. Stopping during a running job interrupts that job; it is not
an automatic drain/wait command. Source changes are never stashed, reset or pulled
by the lifecycle script.

Use `logs agent`, `logs docker`, `logs jenkins` and `status` for diagnosis. Logs
can include sensitive plugin/job diagnostics; inspect them locally before sharing.

## Persistence, backups and next steps

Keep the named volumes and `.local/` secrets when stopping or updating CI.
Back up Jenkins home and the generated admin credential while CI is stopped,
encrypt backups and verify a restore into an isolated instance. Never run global
`docker system prune --volumes` or Compose `down -v` as a CI cleanup step on this host.

Next: confirm all repository locations and access, select exact commit revisions,
implement clean disposable checkouts, build `bervan-utils`, backend and frontend
sequentially, add tests, and retain uniquely versioned release artifacts. Before
adding deployment, inventory production bind mounts, named volumes and any data
in container writable layers. Do not replace a production container until that
data and recovery path have been verified with the owner.

## Local checks

```sh
bash -n docker/jenkins/jenkins.sh
bash docker/jenkins/jenkins.sh validate
python3 -m unittest discover -s docker/jenkins/tests -v
```

Configuration rendering and wrapper tests do not prove images boot successfully.
Validate the real Linux installation and smoke job before closing JNKS-0003/0005.
