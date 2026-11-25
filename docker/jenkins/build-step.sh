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

case "${1:-}" in
  backend)
    cd bervan-utils
    mvn -B -ntp -Dmaven.repo.local="$maven_repo" clean install
    cd ../my-tools
    # The existing React suites are run in the dedicated integration stage.
    mvn -B -ntp -Dmaven.repo.local="$maven_repo" \
      '-Dtest=!*E2ETest,!*IT' -Dsurefire.failIfNoSpecifiedTests=false \
      -DfailIfNoTests=false -DargLine=-Xmx768m clean install -Pproduction
    ;;
  frontend)
    cd my-tools-react
    npm ci
    npm run build
    ;;
  integration)
    cd my-tools-react
    npx playwright install chromium
    npm run test:integration
    ;;
  *) echo "Unknown build step" >&2; exit 2 ;;
esac
