#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
REPO_DIR="${SCRIPT_DIR:h}"
MODULE_DIR="${REPO_DIR}/module"
VENV_DIR="${REPO_DIR}/.venv"
ENV_FILE="${HOME}/.kospi-feargreedindex.env"
LOG_DIR="${MODULE_DIR}/db"
RUN_LOG="${LOG_DIR}/daily_update.log"
LOCK_DIR="${REPO_DIR}/.daily-update.lock"

mkdir -p "${LOG_DIR}"
exec >> "${RUN_LOG}" 2>&1

echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') KGF daily update start ====="

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "ERROR: another update is already running: ${LOCK_DIR}"
  exit 75
fi
cleanup() {
  local exit_code=$?
  rmdir "${LOCK_DIR}" 2>/dev/null || true
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') KGF daily update end exit=${exit_code} ====="
  exit "${exit_code}"
}
trap cleanup EXIT

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  source "${ENV_FILE}"
  set +a
else
  echo "ERROR: missing env file: ${ENV_FILE}"
  echo "Create it with: export GITHUB_TOKEN='...token...'"
  exit 78
fi

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GITHUB_TOKEN is not set in ${ENV_FILE}"
  exit 78
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "ERROR: missing Python virtualenv: ${VENV_DIR}"
  echo "Run: /usr/bin/python3 -m venv ${VENV_DIR} && ${VENV_DIR}/bin/pip install -r ${REPO_DIR}/requirements.txt"
  exit 69
fi

cd "${MODULE_DIR}"
ARGS=()
if [[ "${KGF_FORCE_UPDATE:-0}" == "1" || "${KGF_FORCE_UPDATE:-}" == "true" ]]; then
  ARGS+=(--force-update)
fi
"${VENV_DIR}/bin/python" main.py "${ARGS[@]}"
