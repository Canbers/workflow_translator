#!/usr/bin/env bash
set -euo pipefail

IMAGE="ghcr.io/argosopentech/argos-translate:latest"
CONTAINER_NAME="libretranslate_local"
PORT="5000"

usage() {
  echo "Usage: $0 {start|stop|status} [port]"
  echo "Default port: 5000"
}

cmd=${1:-}
if [[ -n ${2:-} ]]; then
  PORT="$2"
fi

case "$cmd" in
  start)
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      echo "Container ${CONTAINER_NAME} already running on port ${PORT}."
      exit 0
    fi
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    fi
    echo "Starting LibreTranslate locally on http://localhost:${PORT} ..."
    docker run -d --name "${CONTAINER_NAME}" -p "${PORT}:5000" "${IMAGE}" >/dev/null
    echo "Waiting for service to become ready..."
    for i in {1..20}; do
      if curl -fsS "http://localhost:${PORT}/languages" >/dev/null 2>&1; then
        echo "LibreTranslate is up at http://localhost:${PORT}"
        exit 0
      fi
      sleep 1
    done
    echo "Started container, but readiness check failed. You can still try using it."
    ;;
  stop)
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 && echo "Stopped ${CONTAINER_NAME}" || echo "${CONTAINER_NAME} not running"
    ;;
  status)
    if docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -q "${CONTAINER_NAME}"; then
      docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep "${CONTAINER_NAME}"
    else
      echo "${CONTAINER_NAME} is not running"
    fi
    ;;
  *)
    usage
    exit 1
    ;;
esac


