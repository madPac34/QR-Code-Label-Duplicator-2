"""Example runtime configuration for labelclone.

Copy this file to config.py and adapt values for your hardware.
"""

from pathlib import Path

# Stable scanner symlink created by scripts/install.sh udev rule.
# Set to None to auto-detect from /dev/input/by-id/*event-kbd.
SCANNER_DEVICE = "/dev/labelclone-scanner"

# Keyboard layout used by the scanner ("de" or "us").
KEYBOARD_LAYOUT = "de"

# Stable printer symlink created by scripts/install.sh udev rule.
# If missing, labelclone falls back to first /dev/usb/lp* device.
# For a TSC TC300 over USB, keep this as /dev/labelclone-printer.
PRINTER_DEVICE = "/dev/labelclone-printer"

# Absolute or relative path to the ZPL template.
TEMPLATE_PATH = Path("/opt/labelclone/templates/label_template.zpl")

# Prevent immediate duplicate re-printing in this many seconds.
DUPLICATE_SUPPRESSION_SECONDS = 0.5

# --- Testing helpers (optional, disabled by default) ---
# Mirror service logs to a file when True.
ENABLE_TEST_LOG_FILE = False

# Log file used when ENABLE_TEST_LOG_FILE is enabled.
TEST_LOG_FILE_PATH = Path("/tmp/labelclone-testing/labelclone.log")

# If printer output fails and this flag is True, write the latest generated ZPL
# to TEST_ZPL_OUTPUT_DIR/latest.zpl (overwriting the previous file).
ENABLE_TEST_ZPL_FALLBACK = False

# Directory that stores latest.zpl when ENABLE_TEST_ZPL_FALLBACK is enabled.
TEST_ZPL_OUTPUT_DIR = Path("/tmp/labelclone-testing")
