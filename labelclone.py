#!/usr/bin/env python3
"""
labelclone – headless Raspberry Pi label-duplication service.

Listens to a USB QR/barcode scanner (HID/keyboard mode) via Linux evdev,
parses the scanned payload, renders a ZPL label from a template, and sends
raw ZPL bytes to a USB label printer.

Payload format:  <labornummer>_<matrix>_<date>
Example:         FL26-031347_CitroSäurEste_24.03.26
"""

import os
import re
import sys
import time
import logging
import argparse
import threading
from pathlib import Path
from typing import Optional

import evdev  # python-evdev

from config import Config
from scanner import ScannerReader
from label import render_label
from printer import send_to_printer

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("labelclone")


# ---------------------------------------------------------------------------
# Duplicate-scan suppression
# ---------------------------------------------------------------------------

class DuplicateGuard:
    """Ignores the same payload scanned again within *window* seconds."""

    def __init__(self, window: float):
        self._window = window
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_duplicate(self, payload: str) -> bool:
        now = time.monotonic()
        with self._lock:
            last_seen = self._last.get(payload)
            if last_seen is not None and (now - last_seen) < self._window:
                return True
            self._last[payload] = now
            # Prune old entries to avoid unbounded growth
            self._last = {k: v for k, v in self._last.items()
                          if (now - v) < self._window * 10}
        return False


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------

PAYLOAD_RE = re.compile(
    r"^(?P<labornummer>[^_]+)_(?P<matrix>[^_]+)_(?P<date>[^_]+)$"
)


def parse_payload(raw: str) -> Optional[dict]:
    """Return dict with labornummer/matrix/date, or None if format doesn't match."""
    m = PAYLOAD_RE.match(raw.strip())
    if not m:
        return None
    return m.groupdict()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(cfg: Config) -> None:
    guard = DuplicateGuard(cfg.duplicate_window_seconds)

    log.info("labelclone starting up")
    log.info("  scanner device : %s", cfg.scanner_device)
    log.info("  printer device : %s", cfg.printer_device)
    log.info("  keyboard layout: %s", cfg.keyboard_layout)
    log.info("  dup. window    : %.1f s", cfg.duplicate_window_seconds)

    reader = ScannerReader(cfg)

    for raw_payload in reader.scans():
        log.info("SCAN  raw=%r", raw_payload)

        if guard.is_duplicate(raw_payload):
            log.info("SKIP  duplicate within %.1f s window", cfg.duplicate_window_seconds)
            continue

        fields = parse_payload(raw_payload)
        if fields is None:
            log.warning("SKIP  payload does not match expected format: %r", raw_payload)
            continue

        log.info(
            "PARSE labornummer=%r  matrix=%r  date=%r",
            fields["labornummer"], fields["matrix"], fields["date"],
        )

        zpl = render_label(cfg, raw_payload, fields)
        log.debug("ZPL\n%s", zpl)

        ok = send_to_printer(cfg, zpl)
        if ok:
            log.info("PRINT ok")
        else:
            log.error("PRINT failed – check printer connection")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="labelclone – duplicate label printer service"
    )
    parser.add_argument(
        "--config", default="/etc/labelclone/labelclone.conf",
        help="Path to config file (default: /etc/labelclone/labelclone.conf)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable DEBUG logging"
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    cfg = Config(args.config)

    try:
        run(cfg)
    except KeyboardInterrupt:
        log.info("Interrupted – exiting")
    except Exception:
        log.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
