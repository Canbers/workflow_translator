#!/usr/bin/env bash
set -euo pipefail

IMAGE="ghcr.io/argosopentech/argos-translate:latest"
CONTAINER_NAME="libretranslate_local"
PORT="5000"
MODE="docker"
LT_VENV_DIR=".lt_service"
LT_LOG_FILE="${LT_VENV_DIR}/libretranslate.log"
LT_PID_FILE="${LT_VENV_DIR}/libretranslate.pid"

usage() {
  echo "Usage: $0 {start|stop|status} [port]"
  echo "Default port: 5000"
}

cmd=${1:-}
if [[ -n ${2:-} ]]; then
  PORT="$2"
fi

# Decide mode: docker if available, else pip
if ! command -v docker >/dev/null 2>&1; then
  MODE="pip"
fi

case "$cmd" in
  start)
    echo "Selected mode: ${MODE}"
    if [[ "${MODE}" == "docker" ]]; then
      if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Container ${CONTAINER_NAME} already running on port ${PORT}."
        exit 0
      fi
      if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
      fi
      echo "Starting LibreTranslate (Docker) on http://localhost:${PORT} ..."
      docker run -d --name "${CONTAINER_NAME}" -p "${PORT}:5000" "${IMAGE}" >/dev/null
    else
      echo "Starting LibreTranslate (pip) on http://localhost:${PORT} ..."
      if [[ ! -d "${LT_VENV_DIR}" ]]; then
        python3 -m venv "${LT_VENV_DIR}"
      fi
      source "${LT_VENV_DIR}/bin/activate"
      pip -q install --upgrade pip >/dev/null 2>&1 || true
      pip -q install libretranslate >/dev/null
      # Start in background
      nohup "${LT_VENV_DIR}/bin/libretranslate" --host 127.0.0.1 --port "${PORT}" --load-only en,es,fr >"${LT_LOG_FILE}" 2>&1 &
      echo $! > "${LT_PID_FILE}"
      deactivate || true
    fi
    echo "Waiting for service to become ready..."
    for i in {1..30}; do
      if curl -fsS "http://localhost:${PORT}/languages" >/dev/null 2>&1; then
        echo "LibreTranslate is up at http://localhost:${PORT}"
        exit 0
      fi
      sleep 1
    done
    echo "Started service, but readiness check failed. Check logs if using pip: ${LT_LOG_FILE}"
    ;;
  stop)
    if [[ "${MODE}" == "docker" ]]; then
      docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 && echo "Stopped ${CONTAINER_NAME}" || echo "${CONTAINER_NAME} not running"
    else
      if [[ -f "${LT_PID_FILE}" ]]; then
        PID=$(cat "${LT_PID_FILE}")
        if kill -0 "$PID" >/dev/null 2>&1; then
          kill "$PID" && echo "Stopped pip-based LibreTranslate (pid ${PID})" || true
        fi
        rm -f "${LT_PID_FILE}"
      else
        echo "No PID file found. Attempting to stop processes on port ${PORT}."
        lsof -ti tcp:"${PORT}" | xargs -r kill || true
      fi
    fi
    ;;
  status)
    if curl -fsS "http://localhost:${PORT}/languages" >/dev/null 2>&1; then
      echo "LibreTranslate responding at http://localhost:${PORT}"
    else
      if [[ "${MODE}" == "docker" ]]; then
        if docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -q "${CONTAINER_NAME}"; then
          docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep "${CONTAINER_NAME}"
        else
          echo "${CONTAINER_NAME} is not running"
        fi
      else
        if [[ -f "${LT_PID_FILE}" ]]; then
          echo "pip-based LibreTranslate started with PID $(cat "${LT_PID_FILE}") (check ${LT_LOG_FILE})"
        else
          echo "LibreTranslate is not running"
        fi
      fi
    fi
    ;;
  *)
    usage
    exit 1
    ;;
esac


