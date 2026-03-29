"""
labelclone – configuration loader.

Reads an INI-style config file and exposes typed attributes.
Falls back to sensible defaults so the service works out of the box.
"""

import configparser
import logging
import os
from pathlib import Path

log = logging.getLogger("labelclone.config")

# Stable udev symlinks created by the installer's udev rules
_DEFAULT_SCANNER_SYMLINK = "/dev/labelclone-scanner"
_DEFAULT_PRINTER_SYMLINK = "/dev/labelclone-printer"


class Config:
    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------
    scanner_symlink: str = _DEFAULT_SCANNER_SYMLINK
    printer_symlink: str = _DEFAULT_PRINTER_SYMLINK

    # Resolved at runtime (may differ from symlink if auto-detected)
    scanner_device: str = _DEFAULT_SCANNER_SYMLINK
    printer_device: str = _DEFAULT_PRINTER_SYMLINK

    keyboard_layout: str = "de"           # "de" or "us"
    duplicate_window_seconds: float = 0.5

    # ZPL / label geometry
    label_width_dots: int = 600           # 50 mm × 12 dpmm (TC300, 300 dpi)
    label_height_dots: int = 456          # 38 mm × 12 dpmm (TC300, 300 dpi)
    label_dpmm: int = 12                  # 12 dpmm = 300 dpi (TC300)
    print_speed: int = 4
    print_darkness: int = 28              # 0-30

    # QR code
    qr_magnification: int = 5            # 1-10; each module N×N dots (5 suits 300 dpi)
    qr_model: int = 2                    # 1 = original, 2 = enhanced

    def __init__(self, path: str | None = None):
        self._path = path
        cp = configparser.ConfigParser()

        if path and os.path.isfile(path):
            cp.read(path, encoding="utf-8")
            log.info("Config loaded from %s", path)
        else:
            if path:
                log.warning("Config file not found (%s), using defaults", path)

        s = cp["labelclone"] if "labelclone" in cp else {}

        self.scanner_symlink = s.get("scanner_symlink", self.scanner_symlink)
        self.printer_symlink = s.get("printer_symlink", self.printer_symlink)
        self.keyboard_layout = s.get("keyboard_layout", self.keyboard_layout).lower()
        self.duplicate_window_seconds = float(
            s.get("duplicate_window_seconds", self.duplicate_window_seconds)
        )
        self.label_width_dots = int(s.get("label_width_dots", self.label_width_dots))
        self.label_height_dots = int(s.get("label_height_dots", self.label_height_dots))
        self.label_dpmm = int(s.get("label_dpmm", self.label_dpmm))
        self.print_speed = int(s.get("print_speed", self.print_speed))
        self.print_darkness = int(s.get("print_darkness", self.print_darkness))
        self.qr_magnification = int(s.get("qr_magnification", self.qr_magnification))
        self.qr_model = int(s.get("qr_model", self.qr_model))

        if self.keyboard_layout not in ("de", "us"):
            log.warning(
                "Unknown keyboard_layout %r – falling back to 'de'",
                self.keyboard_layout,
            )
            self.keyboard_layout = "de"

        # Resolve actual devices (may trigger auto-detection)
        self.scanner_device = self._resolve_scanner()
        self.printer_device = self._resolve_printer()

    # ------------------------------------------------------------------
    # Device resolution
    # ------------------------------------------------------------------

    def _resolve_scanner(self) -> str:
        """Return evdev path for scanner: symlink → by-id auto-detect."""
        if Path(self.scanner_symlink).exists():
            log.info("Scanner: using symlink %s", self.scanner_symlink)
            return self.scanner_symlink

        log.warning(
            "Scanner symlink %s not found – auto-detecting from /dev/input/by-id/",
            self.scanner_symlink,
        )
        by_id = Path("/dev/input/by-id")
        if by_id.is_dir():
            candidates = sorted(by_id.glob("*event-kbd"))
            if candidates:
                chosen = str(candidates[0])
                log.info("Scanner auto-detected: %s", chosen)
                return chosen
        # Last resort: scan /dev/input/event* for any keyboard
        for i in range(32):
            p = Path(f"/dev/input/event{i}")
            if p.exists():
                log.info("Scanner fallback: using %s", p)
                return str(p)
        raise RuntimeError(
            "No scanner/keyboard input device found. "
            "Check udev rules or set scanner_symlink in the config."
        )

    def _resolve_printer(self) -> str:
        """Return device path for printer: symlink → /dev/usb/lp* auto-detect."""
        if Path(self.printer_symlink).exists():
            log.info("Printer: using symlink %s", self.printer_symlink)
            return self.printer_symlink

        log.warning(
            "Printer path %s not found – auto-detecting from /dev/usb/lp*",
            self.printer_symlink,
        )
        candidates = sorted(Path("/dev/usb").glob("lp*")) if Path("/dev/usb").is_dir() else []
        if candidates:
            chosen = str(candidates[0])
            log.info("Printer auto-detected: %s", chosen)
            return chosen

        raise RuntimeError(
            "No USB label printer found. "
            "Check udev rules or set printer_symlink in the config."
        )
