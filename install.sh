#!/usr/bin/env bash
# install.sh – one-command installer for labelclone on Raspberry Pi OS Lite
#
# Usage:
#   sudo bash install.sh
#
# What it does:
#   1. Installs system dependencies (python3-venv, python3-dev, libevdev-dev)
#   2. Creates a dedicated system user/group "labelclone"
#   3. Copies service files to /opt/labelclone
#   4. Creates a Python virtualenv and installs python-evdev
#   5. Installs the default config to /etc/labelclone/
#   6. Installs udev rules and reloads udev
#   7. Enables and starts the systemd service
#
# After installation:
#   • Edit /etc/labelclone/labelclone.conf  to tune settings
#   • Edit /etc/udev/rules.d/99-labelclone.rules  to set your Vendor:Product IDs
#   • Run:  sudo udevadm control --reload-rules && sudo udevadm trigger
#   • Then: sudo systemctl restart labelclone
#
# Logs:  journalctl -u labelclone -f

set -euo pipefail

INSTALL_DIR="/opt/labelclone"
CONF_DIR="/etc/labelclone"
SERVICE_NAME="labelclone"
SERVICE_USER="labelclone"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Root check ───────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "This script must be run as root (sudo bash install.sh)"

# ── 1. System packages ───────────────────────────────────────────────────────
info "Updating package lists and installing dependencies..."
apt-get update -qq
apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-dev \
    python3-pip \
    libevdev-dev \
    udev

# ── 2. System user & group ───────────────────────────────────────────────────
info "Creating system user/group '${SERVICE_USER}'..."
if ! id "${SERVICE_USER}" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin \
        --groups input,lp "${SERVICE_USER}"
    info "User '${SERVICE_USER}' created."
else
    # Ensure the user belongs to input and lp groups
    usermod -aG input,lp "${SERVICE_USER}" || true
    info "User '${SERVICE_USER}' already exists – groups updated."
fi

# ── 3. Install service files ─────────────────────────────────────────────────
info "Installing service files to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
cp -f "${SCRIPT_DIR}/labelclone.py" "${INSTALL_DIR}/"
cp -f "${SCRIPT_DIR}/config.py"     "${INSTALL_DIR}/"
cp -f "${SCRIPT_DIR}/scanner.py"    "${INSTALL_DIR}/"
cp -f "${SCRIPT_DIR}/label.py"      "${INSTALL_DIR}/"
cp -f "${SCRIPT_DIR}/printer.py"    "${INSTALL_DIR}/"
chown -R root:root "${INSTALL_DIR}"
chmod 755 "${INSTALL_DIR}"
chmod 644 "${INSTALL_DIR}"/*.py
chmod +x  "${INSTALL_DIR}/labelclone.py"

# ── 4. Python virtualenv ─────────────────────────────────────────────────────
info "Creating Python virtualenv in ${INSTALL_DIR}/venv..."
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet evdev

info "Python packages installed:"
"${INSTALL_DIR}/venv/bin/pip" show evdev | grep -E "^(Name|Version):"

# ── 5. Configuration ─────────────────────────────────────────────────────────
info "Installing default config to ${CONF_DIR}/..."
mkdir -p "${CONF_DIR}"
if [[ -f "${CONF_DIR}/labelclone.conf" ]]; then
    warn "Config already exists at ${CONF_DIR}/labelclone.conf – skipping (not overwritten)."
else
    cp -f "${SCRIPT_DIR}/labelclone.conf" "${CONF_DIR}/labelclone.conf"
    chown root:"${SERVICE_USER}" "${CONF_DIR}/labelclone.conf"
    chmod 640 "${CONF_DIR}/labelclone.conf"
    info "Default config installed."
fi

# ── 6. udev rules ────────────────────────────────────────────────────────────
UDEV_RULES="/etc/udev/rules.d/99-labelclone.rules"
info "Installing udev rules to ${UDEV_RULES}..."
cp -f "${SCRIPT_DIR}/99-labelclone.rules" "${UDEV_RULES}"
chmod 644 "${UDEV_RULES}"
udevadm control --reload-rules
udevadm trigger
info "udev rules installed and reloaded."
warn "Remember to edit ${UDEV_RULES} with your scanner/printer Vendor:Product IDs!"

# ── 7. systemd service ───────────────────────────────────────────────────────
info "Installing systemd service..."
cp -f "${SCRIPT_DIR}/labelclone.service" "/etc/systemd/system/${SERVICE_NAME}.service"
chmod 644 "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"
systemctl restart "${SERVICE_NAME}.service"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  labelclone installed successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Status:  sudo systemctl status ${SERVICE_NAME}"
echo "  Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "  Next steps:"
echo "  1. Find your device IDs:"
echo "       udevadm info -a -n /dev/input/event0 | grep -E 'idVendor|idProduct'"
echo "       udevadm info -a -n /dev/usb/lp0       | grep -E 'idVendor|idProduct'"
echo "  2. Edit udev rules:"
echo "       sudo nano ${UDEV_RULES}"
echo "  3. Reload udev + restart:"
echo "       sudo udevadm control --reload-rules && sudo udevadm trigger"
echo "       sudo systemctl restart ${SERVICE_NAME}"
echo "  4. Tune label/printer settings:"
echo "       sudo nano ${CONF_DIR}/labelclone.conf"
echo ""
