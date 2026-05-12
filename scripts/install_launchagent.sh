#!/bin/zsh
set -euo pipefail

LABEL="com.kospi-feargreedindex.daily"
SCRIPT_DIR="${0:A:h}"
SOURCE_REPO="${SCRIPT_DIR:h}"
RUNTIME_DIR="${KGF_RUNTIME_DIR:-${HOME}/.local/share/kospi-feargreedindex}"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${PLIST_DIR}/${LABEL}.plist"
WRAPPER="${RUNTIME_DIR}/scripts/update_kgf_daily.sh"
OUT_LOG="${RUNTIME_DIR}/module/db/launchd.out.log"
ERR_LOG="${RUNTIME_DIR}/module/db/launchd.err.log"

mkdir -p "${PLIST_DIR}" "${RUNTIME_DIR}" "${RUNTIME_DIR}/module/db"

# Desktop is protected by macOS TCC for background launchd jobs. Keep a runtime
# mirror under ~/.local/share so the scheduled job can read code and data without
# requiring Full Disk Access for /bin/zsh.
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.daily-update.lock/' \
  --exclude 'module/db/*.log' \
  --exclude 'module/db/*.out.log' \
  --exclude 'module/db/*.err.log' \
  "${SOURCE_REPO}/" "${RUNTIME_DIR}/"
chmod +x "${WRAPPER}"

if [[ ! -x "${RUNTIME_DIR}/.venv/bin/python" ]]; then
  /usr/bin/python3 -m venv "${RUNTIME_DIR}/.venv"
fi
"${RUNTIME_DIR}/.venv/bin/python" -m pip install --upgrade pip >/dev/null
"${RUNTIME_DIR}/.venv/bin/pip" install -r "${RUNTIME_DIR}/requirements.txt" >/dev/null

cat > "${PLIST_PATH}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>${WRAPPER}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${RUNTIME_DIR}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>1</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${ERR_LOG}</string>
</dict>
</plist>
PLIST

plutil -lint "${PLIST_PATH}"
launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
launchctl enable "gui/$(id -u)/${LABEL}"
launchctl print "gui/$(id -u)/${LABEL}" | sed -n '1,80p'
