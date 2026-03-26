#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/labelclone"
SERVICE_NAME="labelclone.service"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UDEV_RULES_FILE="/etc/udev/rules.d/99-labelclone-devices.rules"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo ./scripts/install.sh"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip rsync

mkdir -p "${APP_DIR}"

if [[ -f "${APP_DIR}/config.py" ]]; then
  echo "Preserving existing ${APP_DIR}/config.py"
  rsync -a --delete \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '.venv' \
    --exclude 'config.py' \
    "${REPO_DIR}/" "${APP_DIR}/"
else
  rsync -a --delete \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '.venv' \
    "${REPO_DIR}/" "${APP_DIR}/"
  cp "${APP_DIR}/config.example.py" "${APP_DIR}/config.py"
fi

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

install -m 0644 "${APP_DIR}/systemd/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"

cat > "${UDEV_RULES_FILE}" <<'RULES'
# Stable scanner symlink for NT USB Keyboard in HID mode.
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="NT USB Keyboard", SYMLINK+="labelclone-scanner"

# Stable raw printer symlink for TSC label printers (including TC300) on USB.
SUBSYSTEM=="usbmisc", KERNEL=="lp[0-9]*", ATTRS{manufacturer}=="TSC*", SYMLINK+="labelclone-printer"

# Generic fallback symlink for environments without matching manufacturer metadata.
SUBSYSTEM=="usbmisc", KERNEL=="lp[0-9]*", SYMLINK+="labelclone-printer"
RULES

udevadm control --reload-rules
udevadm trigger --subsystem-match=input --subsystem-match=usb

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "Installation complete."
echo "Edit ${APP_DIR}/config.py if needed, then: systemctl restart ${SERVICE_NAME}"
echo "Device symlinks:"
echo "  Scanner: /dev/labelclone-scanner (NT USB Keyboard)"
echo "  Printer: /dev/labelclone-printer"
