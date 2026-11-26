# Jenkins: setup and deployment

## Requirements

Linux, Docker Engine + Compose v2, Git, Bash, OpenSSL, Docker permissions,
internet access and disk/RAM capacity for CI alongside production.
Java, Maven, Node.js and Python run in containers.
Deployment updates an existing application on the same server, using its
`docker-compose.yml`, `.env_my_tools` and data. Only trusted jobs may use host Docker.

## Install once

1. Use the existing production repo and run `git pull --ff-only`.
   If no checkout exists, clone it (this alone does not install the application):
   ```sh
   git clone https://github.com/vnhk/my-tools.git
   cd my-tools
   ```
   Run remaining commands from the repo. Jenkins clones all build modules itself.
2. Create settings and set `JENKINS_BIND_ADDRESS` to the server's LAN IP:
   ```sh
   cp -n docker/jenkins/jenkins.config.example docker/jenkins/jenkins.local.conf
   nano docker/jenkins/jenkins.local.conf
   bash docker/jenkins/jenkins.sh start
   ```
   If CI uses a separate checkout, set `MY_TOOLS_PRODUCTION_DIR` to production there.
3. Open the printed URL (default port `8092`, trusted LAN only). User: `admin`.
   Read the password: `cat docker/jenkins/.local/admin-password`.
4. **Manage Jenkins → Nodes → my-tools-builder**: copy its inbound secret into
   `docker/jenkins/.local/agent-secret`. Run `jenkins.sh start` again and check the
   node is online. No SSH keys are needed. Keep local settings/secrets out of Git.
5. Create Pipeline jobs: **Pipeline script from SCM → Git**,
   URL `https://github.com/vnhk/my-tools.git`, branch `*/main`:

   | Job name | Script Path |
   | --- | --- |
   | `my-tools-build` | `docker/jenkins/Jenkinsfile` |
   | `my-tools-deploy` | `docker/jenkins/Jenkinsfile.deploy` |

## Build and deploy

1. Commit/push code. Run `my-tools-build` with `EXPORT_IMAGES=true` and wait for
   **Finished: SUCCESS**. `RUN_INTEGRATION_TESTS` can be disabled;
   `FORCE_REBUILD=true` bypasses cache. If parameters are missing, run the job once.
2. Run `my-tools-deploy`: select `plan`, then `deploy`. Blank `SOURCE_BUILD` selects
   the latest successful build; enter a number for a specific release.
3. To restore previous images, select `rollback`. Failed deployment also attempts
   automatic recovery. **Image rollback does not undo database changes: keep backups.**

The existing `.env_my_tools` is loaded automatically; no per-release file copying.
Only application containers are replaced, briefly interrupting service; data and
infrastructure remain. Frontend-only changes do not restart backend.
Health URLs/settings: `deploy.config.json`. Deployment state: `.jenkins-deploy/`.
Successful builds cache artifacts even without integration; enabling it later tests
unvalidated inputs. Changed modules and POM consumers rebuild; failed runs keep cache.

## Start, stop and update CI

Use `bash docker/jenkins/jenkins.sh start` before jobs, `stop` after they finish.
Use `status` or `logs agent` / `logs docker` / `logs jenkins` for diagnostics.
After updating CI tooling in the server repo, rerun `start`. Production stays running.
Keep Jenkins volumes and `.local/`; do not run volume deletion or global Docker prune.
