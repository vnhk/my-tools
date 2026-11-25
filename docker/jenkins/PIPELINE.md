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
| Change plan | Compares commits with the last successful snapshot, validates cached artifact SHA-256 checksums and restores built Maven artifacts. Integration validation is tracked separately. Logs the selected modules and skipped components. |
| CI tool image | Prepares Java 17, Maven, Node.js and Playwright browser dependencies in the CI Docker daemon. |
| Backend | Builds `bervan-utils` only when required, then builds/tests/installs selected backend modules with the production build profile. React E2E suites are handled separately. |
| Frontend | Runs `npm ci` and `npm run build`, including TypeScript checks, only when the frontend requires rebuilding. |
| Integration | When application sources change, starts Vite and runs the existing `ReactRunAllE2ETest` Testcontainers/Playwright suite against temporary CI services. Calls Maven without `-am` because dependency JARs are already installed/restored. |
| Images | Packages the already built JAR/configuration and frontend `dist`; it does not rebuild Java or TypeScript. Records image IDs and tags. |
| Export | Saves both application images as a gzip-compressed Docker archive and writes a SHA-256 checksum. Jenkins archives the release files. |
| Successful snapshot | After successful stages and artifact archiving, saves verified reusable packages and Maven artifacts, including when integration is disabled. Records integration validation separately. |

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

## Incremental build decisions

Every run still checks out all repositories to resolve their exact commit SHAs
and inspect the current Maven dependency graph. Skipping compilation does not
mean skipping source/version verification.

| Change since the successful snapshot | Rebuild |
| --- | --- |
| First run, missing/corrupt snapshot, or `FORCE_REBUILD=true` | Utils, all backend modules, frontend and enabled integration tests. |
| Main repository commit or repository set changed | Full rebuild; this conservatively covers build scripts, toolchain, runtime Dockerfiles and root POM changes, including documentation-only commits. |
| `bervan-utils` | Utils and all backend modules; reuse frontend. |
| `streaming-platform-app` only | Streaming and `my-tools-app`; reuse utils, other module JARs and frontend. |
| Any other Maven module | Changed modules and all transitive consumers found in their POM dependencies; always repackage `my-tools-app`. |
| Frontend only | Frontend plus enabled integration tests; reuse backend and utils JARs. The integration runner still compiles its own app/test classes in the fresh checkout. |
| No source commits changed | Reuse backend/frontend artifacts and images. Skip integration only if the same inputs already passed it, or the user disables it. |

POM dependency edges include profile dependencies, dependency management and parent
references conservatively. Property-based artifact IDs or unsupported module
coordinates fail explicitly rather than guessing a partial dependency graph.
The current modules use literal `com.bervan` coordinates.

The successful snapshot lives under this job's persistent `.cache/successful/`.
It contains the manifest, packaging contexts, installed `com/bervan` Maven
artifacts and a SHA-256 inventory. Before each run, the working Maven cache's
`com/bervan` group is removed and restored from that verified snapshot. This
prevents a failed run's partially installed `latest` artifacts from contaminating
the next incremental build. Third-party dependency downloads remain cached.
Sources are still checked out cleanly; old `target` directories are never reused.

Unchanged runtime images are selected by the prior recorded image ID and retagged
for the new release. If that image is absent from the CI daemon, only its runtime
image is rebuilt using the verified cached JAR/dist, without recompiling sources.
Reused images retain their original release label; use the new release manifest
for the complete source-to-image mapping. Every export still includes both images.

The snapshot is a workspace cache, not a registry or remote backup. Deleting it
causes a full rebuild. A first successful build after introducing this feature
is also full. Use one release job for this shared CI daemon. For scheduled
revalidation of unchanged code, select `FORCE_REBUILD`. This forces source
compilation, not an upgrade of cached external dependencies or base images;
changing upstream dependencies without changing source commits is not detected
automatically.

Inspect the **Plan changes and restore successful artifacts** console output and
`release.json` (`plan.changed`, `plan.modules`, `baseline`, image `reused` fields)
to see exactly why stages ran or were skipped. The baseline advances only from
the successful post-build path. Failed or aborted builds do not replace it.

`integrationTests` records whether tests were requested in this run;
`integrationPassed` records whether these exact inputs passed integration, either
in this run or a previous successful run with identical inputs. Skipping tests
does not manufacture a passing result. Any source change or forced rebuild
invalidates the inherited result. Older snapshots without this field are treated
as not yet integration-validated, but their build artifacts remain reusable.

For example, a successful build with integration disabled saves compiled artifacts
with `integrationPassed=false`. Another run without code changes can reuse those
artifacts. Once integration is enabled, it prepares the CI tool image and runs
the integration suite without rebuilding utils, backend packages or frontend
dist. The integration runner may still compile its own app/test classes and
install Node dependencies in the fresh checkout. A failed integration suite
does not advance the snapshot; a successful suite records the passing result.

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
their contents. The exact root path `.env_my_tools_default` is allowed only in
the main source checkout for compatibility with the existing repository; its
contents are not inspected and the exception does not apply to image packaging.
Packaging contexts contain only the built JAR plus the existing
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
- `FORCE_REBUILD`: disabled by default. Bypasses incremental reuse and rebuilds
  all components, including utils, even when commits are unchanged.
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
