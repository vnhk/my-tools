#!/usr/bin/env bash
set -euo pipefail
: "${WORKSPACE:?Run from the Jenkins pipeline}"
cd "$WORKSPACE/sources"
export CI=true
export MAVEN_OPTS="-Xmx768m"
export NODE_OPTIONS="--max-old-space-size=1024"
export npm_config_cache=/ci-cache/npm
export PLAYWRIGHT_BROWSERS_PATH=/ci-cache/playwright
maven_repo=/ci-cache/m2
# Existing Testcontainers uses an older Docker Java client; Docker 29 requires API 1.44.
# JAVA_TOOL_OPTIONS also reaches forked test JVMs and the Maven integration runner.
export JAVA_TOOL_OPTIONS="-Dmaven.repo.local=$maven_repo -Dapi.version=1.44 -Xmx768m"
planner="$WORKSPACE/sources/my-tools/docker/jenkins/incremental.py"
flag() { python3 "$planner" "$WORKSPACE/release/release.json" "$1"; }

case "${1:-}" in
  backend)
    if [[ "$(flag utils)" == true ]]; then
      cd "$WORKSPACE/sources/bervan-utils"
      mvn -B -ntp -Dmaven.repo.local="$maven_repo" clean install
    fi
    cd "$WORKSPACE/sources/my-tools"
    set --
    if [[ "$(flag full)" != true && "$(flag utils)" != true ]]; then
      set -- -pl "$(flag modules)"
    fi
    # The existing React suites are run in the dedicated integration stage.
    mvn -B -ntp -Dmaven.repo.local="$maven_repo" \
      '-Dtest=!*E2ETest,!*IT' -Dsurefire.failIfNoSpecifiedTests=false \
      -DfailIfNoTests=false -DargLine=-Xmx768m "$@" clean install -Pproduction
    ;;
  frontend)
    cd my-tools-react
    npm ci
    npm run build
    ;;
  integration)
    cd my-tools-react
    # The frontend may have reused its previous dist while its fresh checkout
    # still needs Node dependencies to run the integration suite.
    if [[ ! -d node_modules ]]; then npm ci; fi
    npx playwright install chromium
    npm run dev:integration &
    dev_pid=$!
    trap 'kill "$dev_pid" 2>/dev/null || true' EXIT
    ready=false
    for ((attempt=0; attempt<30; attempt++)); do
      if curl --fail --silent http://localhost:5173 > /dev/null; then
        ready=true
        break
      fi
      sleep 2
    done
    if [[ "$ready" != true ]]; then echo 'Integration frontend did not start' >&2; exit 1; fi
    cd ../my-tools
    # All dependency JARs are installed or restored. Avoid -am, which would
    # compile the complete dependency reactor again in a fresh checkout.
    mvn -B -ntp test -pl my-tools-app -DfailIfNoTests=false \
      -Dsurefire.failIfNoSpecifiedTests=false -Dtest=ReactRunAllE2ETest
    ;;
  *) echo "Unknown build step" >&2; exit 2 ;;
esac
