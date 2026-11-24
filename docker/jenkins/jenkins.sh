#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$script_dir/jenkins.local.conf" ]]; then
  # Dedicated, operator-owned shell configuration; never load application .env.
  set -a
  source "$script_dir/jenkins.local.conf"
  set +a
fi
export JENKINS_LOCAL_DIR="${JENKINS_LOCAL_DIR:-$script_dir/.local}"
export JENKINS_PORT="${JENKINS_PORT:-8092}"
if [[ "${1:-}" == start || "${1:-}" == validate ]]; then
  if [[ -z "${JENKINS_BIND_ADDRESS:-}" ]]; then
    echo "Set JENKINS_BIND_ADDRESS in jenkins.local.conf or export it before starting Jenkins." >&2
    exit 2
  fi
fi
# For read/stop commands only, these placeholders let Compose render without a
# network configuration. They never create or update a container.
export JENKINS_BIND_ADDRESS="${JENKINS_BIND_ADDRESS:-127.0.0.1}"
export JENKINS_PUBLIC_URL="${JENKINS_PUBLIC_URL:-http://${JENKINS_BIND_ADDRESS}:${JENKINS_PORT}/}"

compose() {
  # Do not load the repository's .env or production Compose configuration.
  docker compose --env-file /dev/null --project-name my-tools-jenkins \
    --file "$script_dir/compose.yml" "$@"
}

case "${1:-}" in
  start)
    umask 077
    mkdir -p "$JENKINS_LOCAL_DIR"
    chmod 700 "$JENKINS_LOCAL_DIR"
    if [[ ! -f "$JENKINS_LOCAL_DIR/admin-password" ]]; then
      openssl rand -hex 32 > "$JENKINS_LOCAL_DIR/admin-password"
    fi
    # An empty file lets Compose validate the optional, not-yet-configured agent.
    if [[ ! -f "$JENKINS_LOCAL_DIR/agent-secret" ]]; then
      touch "$JENKINS_LOCAL_DIR/agent-secret"
    fi
    # File-backed Compose secrets preserve host ownership. Container users need
    # read access; the enclosing 0700 directory protects these files on the host.
    chmod 644 "$JENKINS_LOCAL_DIR/admin-password" "$JENKINS_LOCAL_DIR/agent-secret"
    if [[ -s "$JENKINS_LOCAL_DIR/agent-secret" ]]; then
      compose --profile build up --build --detach
    else
      compose up --build --detach jenkins
      echo "Controller started. Configure the agent secret using README.md, then run start again."
    fi
    echo "Jenkins: $JENKINS_PUBLIC_URL"
    echo "Admin password is in $JENKINS_LOCAL_DIR/admin-password; it is not printed automatically."
    ;;
  stop)
    # Only stop CI services. Never remove containers, images or volumes.
    compose --profile build stop --timeout 60 agent jenkins docker
    ;;
  status)
    compose --profile build ps --all
    ;;
  logs)
    compose --profile build logs --tail 100 "${2:-jenkins}"
    ;;
  validate)
    compose --profile build config --quiet
    ;;
  *)
    echo "Usage: bash docker/jenkins/jenkins.sh {start|stop|status|logs [jenkins|agent|docker]|validate}" >&2
    exit 2
    ;;
esac
