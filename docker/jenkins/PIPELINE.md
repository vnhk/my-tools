# My Tools build and release pipeline

## What it does

Configure a Pipeline job with **Pipeline script from SCM**, the public main
repository URL and your chosen branch. Set Script Path to
`docker/jenkins/Jenkinsfile`. Use a job name such as `my-tools-build`.
Commit and push all the files in this change before running it.

The updated agent needs Python 3. On the server, after updating the files, run
`bash docker/jenkins/jenkins.sh start` to rebuild/recreate the CI agent if needed.
It keeps Jenkins home and agent workspace; it does not touch production services.

| Stage | Work |
| --- | --- |
| Main checkout | Clears only this job's `sources/` and `release/`, then checks out the SCM revision selected by Jenkins into `sources/my-tools`. |
| Other checkouts | Fetches the 15 Maven module repositories, `bervan-utils` and `my-tools-react`, in detached HEAD mode. Checks every module in the root POM exists. |
| Commit manifest | Writes the exact source commits to `release/release.json`. Branch references in `repositories.json` are resolved once per checkout; later stages do not pull again. |
| CI tool image | Prepares Java 17, Maven, Node.js and Playwright browser dependencies in the CI Docker daemon. |
| Backend | Builds/tests/installs the complete `bervan-utils` reactor first, then builds/tests/installs the backend reactor with the production build profile. React E2E suites are handled separately. |
| Frontend | Runs `npm ci` and `npm run build`, including the existing TypeScript checks. |
| Integration | Runs the existing `npm run test:integration` flow, starting Vite and the Java Testcontainers/Playwright suite against temporary CI services. |
| Images | Packages the already built JAR/configuration and frontend `dist`; it does not rebuild Java or TypeScript. Records image IDs and tags. |
| Export | Saves both application images as a gzip-compressed Docker archive and writes a SHA-256 checksum. Jenkins archives the release files. |

There is no deploy stage in this version. A green job means the enabled build
and test stages passed, not that production changed. The existing
`linux-build-script.sh` is never invoked.

## Repository configuration and repeatability

`repositories.json` maps checkout paths to public HTTPS repository URLs and
revisions. `main` is the initial setting, matching local repository branches.
Replace a revision with an exact commit SHA when selecting a fixed release.
Every run records all resolved SHAs, including the main repository SCM commit.
Two runs using moving `main` branches can produce different source manifests.

Workspace layout:

```text
workspace/
  sources/
    my-tools/                 # Main repo, with each Maven module checked out inside
    my-tools-react/
    bervan-utils/
  .cache/                     # Maven, npm and downloaded Playwright browser cache
  package-contexts/           # Only files required for the runtime images
  release/                    # Source manifest, image archive and checksum
```

The root checkout cannot be overwritten by an entry in the repository list.
Missing repositories/modules, invalid paths and unsafe URLs fail the job rather
than being silently skipped. A retry starts from clean source directories.
The cache remains separate. No command uses `git stash` or `git pull`.

## Secret files: build versus production runtime

The current production script runs:

```sh
docker-compose --env-file .env_my_tools up --build -d
```

That environment file supplies runtime credentials and configuration to Compose.
It stays on the production host at its existing location. This pipeline does not
open it, mount it, copy it, source it, archive it or pass it to any build command.
The same applies to MCP `.env`, Jenkins `.local/` secrets and production data.
Tracked runtime environment filenames fail the checkout checks without reading
their contents. Packaging contexts contain only the built JAR plus the existing
version-controlled application `configuration/`, or frontend `dist` and `nginx.conf`.
Keep runtime secrets out of those version-controlled files too.

The CI tool containers receive a fixed list of CI variables. They do not inherit
the Jenkins process's complete environment. Testcontainers gets the socket of the
**inner CI Docker daemon**, mounted by that daemon, never the server's production
Docker socket. Test servers use the inner daemon's host network namespace; this
does not expose their ports on the physical production host.

The CI Java processes explicitly select Docker API `1.44` for the existing
Testcontainers/docker-java version to communicate with Docker 29. This setting
applies to CI test JVMs only and does not change the production Docker daemon.

If a test needs service configuration, use isolated test settings. Do not solve
test failures by injecting the production environment file.

## Parameters and artifacts

- `RUN_INTEGRATION_TESTS`: enabled by default. Disabling it is useful while
  diagnosing the build but does not validate a production release. The manifest
  records whether integration testing was requested.
- `EXPORT_IMAGES`: enabled by default. Turning it off keeps images only in the
  CI daemon; no downloadable image archive is produced.

Release tags have the form `my-tools-backend:bBUILD-COMMIT` and
`my-tools-frontend:bBUILD-COMMIT`. The manifest records each full image ID and all
source SHAs. Tags are unique within this job's build history, not a registry-level
immutability guarantee. Use a single release job; future registry promotion should
use immutable digests.

Successful image exports and manifests are available under Jenkins **Artifacts**.
Only the last three builds' artifacts are retained, with ten build records. Image
archives can be large; ensure Jenkins home has enough disk space. The CI daemon
also retains its image/build cache; there is deliberately no global prune command.
Moving a selected image archive to the production daemon will be a separate,
explicit operation. Merely loading an image would not change a running container;
this pipeline does not even perform that step.

## Resource and validation limits

Build stages run sequentially on the one configured executor. Each CI tool
container has a 2300 MiB memory ceiling, no extra swap and two CPUs. Java build/test
processes and Node have additional heap limits. Integration tests also start
temporary MariaDB/RabbitMQ containers inside CI; monitor the first run on the
16 GiB host and adjust CI limits if necessary rather than weakening required tests.

Toolchain images use explicit version/release-family tags, not locked digests.
Playwright image `v1.59.1-noble` matches the inspected frontend lockfile; the test
step installs the browsers required by the checked-out package version. Review
the tool image when the frontend Playwright major/minor version changes.

Static checks and mocked/local tests do not prove Docker images build or that
the application suites pass. First real execution on the Jenkins Linux server is
required. Deploy remains deliberately unconfigured until production mount/data
inventory and an approved recovery procedure are complete. Existing containers,
databases, uploaded files and the production environment file are unchanged.
