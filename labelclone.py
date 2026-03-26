#!/usr/bin/env python3
"""Headless QR-to-label duplicator service."""

from __future__ import annotations

import errno
import importlib.util
import logging
import os
import stat
import time
from pathlib import Path

from evdev import InputDevice, categorize, ecodes

from keyboard_layouts import UnsupportedLayoutError, get_layout
from parser import parse_payload
from zpl import TemplateError, render_zpl

LOGGER = logging.getLogger("labelclone")


def _load_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_config():
    config_path = Path(__file__).with_name("config.py")
    if config_path.exists():
        return _load_module_from_path("runtime_config", config_path)

    example_path = Path(__file__).with_name("config.example.py")
    if example_path.exists():
        LOGGER.warning("config.py not found, falling back to config.example.py")
        return _load_module_from_path("default_config", example_path)

    raise FileNotFoundError("Neither config.py nor config.example.py could be loaded")


def detect_scanner_device(configured_device: str | None) -> str:
    if configured_device:
        configured_path = Path(configured_device)
        if configured_path.exists():
            return str(configured_path.resolve())
        raise FileNotFoundError(
            f"Configured scanner device not found: {configured_device}. "
            "Check udev rule/symlink or set SCANNER_DEVICE in config.py."
        )

    by_id_dir = Path("/dev/input/by-id")
    candidates = sorted(by_id_dir.glob("*event-kbd"))
    if not candidates:
        raise FileNotFoundError(
            "No scanner device found in /dev/input/by-id/*event-kbd. "
            "Set SCANNER_DEVICE in config.py."
        )

    return str(candidates[0].resolve())


def detect_printer_device(configured_device: str | None) -> str:
    if configured_device:
        configured_path = Path(configured_device)
        if configured_path.exists():
            return str(configured_path.resolve())
        LOGGER.warning(
            "Configured printer device not found: %s. Falling back to auto-detection.",
            configured_device,
        )

    candidates = sorted(Path("/dev/usb").glob("lp*"))
    if not candidates:
        raise FileNotFoundError(
            "No printer device found in /dev/usb/lp*. "
            "Set PRINTER_DEVICE in config.py or add a udev symlink."
        )

    return str(candidates[0].resolve())


def iter_scanned_payloads(device_path: str, layout_name: str):
    """Yield complete payloads from HID scanner events.

    German umlauts (ä ö ü Ä Ö Ü ß) are produced by the keyboard layout
    mapping and passed through without further transformation, so the yielded
    string is always valid UTF-8 text matching what was physically scanned.
    """

    layout = get_layout(layout_name)
    scanner = InputDevice(device_path)
    LOGGER.info("Listening to scanner device: %s", scanner.path)

    buffer: list[str] = []
    shift_pressed = False
    alt_pressed = False

    for event in scanner.read_loop():
        if event.type != ecodes.EV_KEY:
            continue

        key_event = categorize(event)
        keycode = key_event.scancode

        if keycode in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
            shift_pressed = key_event.keystate != key_event.key_up
            continue

        if keycode in (ecodes.KEY_RIGHTALT, ecodes.KEY_LEFTALT):
            alt_pressed = key_event.keystate != key_event.key_up
            continue

        if key_event.keystate != key_event.key_down:
            continue

        if keycode == ecodes.KEY_ENTER:
            payload = "".join(buffer)
            buffer.clear()
            if payload:
                yield payload
            continue

        if keycode == ecodes.KEY_BACKSPACE:
            if buffer:
                buffer.pop()
            continue

        if keycode not in layout:
            LOGGER.debug("Ignoring unmapped keycode: %s", keycode)
            continue

        normal, shifted, altgr = layout[keycode]
        if alt_pressed and altgr is not None:
            buffer.append(altgr)
        else:
            buffer.append(shifted if shift_pressed else normal)


def _normalize_zpl(zpl_text: str) -> bytes:
    content = zpl_text.strip()
    if not content.startswith("^XA"):
        raise ValueError("ZPL payload must start with ^XA")
    if not content.endswith("^XZ"):
        raise ValueError("ZPL payload must end with ^XZ")

    # Encode as UTF-8; the printer must be configured with ^CI28 (UTF-8) to
    # render multi-byte characters (umlauts etc.) correctly.
    return f"{content}\n".encode("utf-8")


def print_label(printer_device: str, zpl_text: str, retries: int = 1) -> None:
    payload = _normalize_zpl(zpl_text)

    last_error: OSError | None = None
    attempts = retries + 1

    for attempt in range(1, attempts + 1):
        fd = None
        try:
            fd = os.open(printer_device, os.O_WRONLY)
            bytes_written = 0
            while bytes_written < len(payload):
                written = os.write(fd, payload[bytes_written:])
                if written == 0:
                    raise OSError("Printer write returned 0 bytes")
                bytes_written += written

            mode = os.fstat(fd).st_mode
            if stat.S_ISCHR(mode):
                LOGGER.debug(
                    "Skipping fsync for character device printer %s", printer_device
                )
            else:
                os.fsync(fd)
            LOGGER.debug(
                "Sent %s bytes to printer device %s (attempt %s/%s)",
                bytes_written,
                printer_device,
                attempt,
                attempts,
            )
            return
        except OSError as exc:
            last_error = exc
            retryable_errno = {errno.EBUSY, errno.EAGAIN, errno.EINTR}
            if attempt >= attempts or getattr(exc, "errno", None) not in retryable_errno:
                raise
            time.sleep(0.05)
        finally:
            if fd is not None:
                os.close(fd)

    if last_error is not None:
        raise last_error


def save_latest_zpl(output_directory: Path, zpl_text: str) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    latest_path = output_directory / "latest.zpl"
    latest_path.write_text(zpl_text, encoding="utf-8")
    return latest_path


def _payload_log_context(payload: str) -> tuple[str, str, str]:
    """Return raw text, escaped text, and UTF-8 hex bytes for logs."""

    escaped = payload.encode("unicode_escape").decode("ascii")
    return payload, escaped, payload.encode("utf-8").hex(" ").upper()


def configure_logging(enable_log_file: bool, log_file_path: Path) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if enable_log_file:
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file_path, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def run() -> None:
    config = load_config()
    enable_test_log_file = bool(getattr(config, "ENABLE_TEST_LOG_FILE", False))
    test_log_file_path = Path(
        getattr(
            config,
            "TEST_LOG_FILE_PATH",
            Path("/tmp/labelclone-testing/labelclone.log"),
        )
    )
    enable_test_zpl_fallback = bool(getattr(config, "ENABLE_TEST_ZPL_FALLBACK", False))
    test_zpl_output_directory = Path(
        getattr(config, "TEST_ZPL_OUTPUT_DIR", Path("/tmp/labelclone-testing"))
    )
    configure_logging(enable_test_log_file, test_log_file_path)

    scanner_device = detect_scanner_device(getattr(config, "SCANNER_DEVICE", None))
    keyboard_layout = getattr(config, "KEYBOARD_LAYOUT", "de")
    printer_device = detect_printer_device(
        getattr(config, "PRINTER_DEVICE", "/dev/usb/lp0")
    )
    template_path = Path(
        getattr(config, "TEMPLATE_PATH", Path("templates/label_template.zpl"))
    )
    dedupe_window = float(getattr(config, "DUPLICATE_SUPPRESSION_SECONDS", 0.5))

    last_payload = None
    last_print_ts = 0.0

    LOGGER.info("Using keyboard layout: %s", keyboard_layout)
    LOGGER.info("Using printer device: %s", printer_device)
    LOGGER.info("Using template: %s", template_path)
    if enable_test_log_file:
        LOGGER.info("Test log file enabled: %s", test_log_file_path)
    if enable_test_zpl_fallback:
        LOGGER.info(
            "Test ZPL fallback enabled: %s/latest.zpl", test_zpl_output_directory
        )

    try:
        payload_stream = iter_scanned_payloads(scanner_device, keyboard_layout)

        for payload in payload_stream:
            try:
                payload_text, payload_escaped, payload_hex = _payload_log_context(
                    payload
                )
                LOGGER.info(
                    "Raw scanned input: %s (escaped=%s utf8_hex=%s)",
                    payload_text,
                    payload_escaped,
                    payload_hex,
                )

                now = time.monotonic()
                if payload == last_payload and now - last_print_ts < dedupe_window:
                    LOGGER.info(
                        "Duplicate payload suppressed: %s (escaped=%s utf8_hex=%s)",
                        payload_text,
                        payload_escaped,
                        payload_hex,
                    )
                    continue

                parsed = parse_payload(payload)
                zpl_text = render_zpl(template_path, parsed)
                printed_to_device = False
                try:
                    print_label(printer_device, zpl_text)
                    printed_to_device = True
                except (FileNotFoundError, OSError) as exc:
                    if not enable_test_zpl_fallback:
                        raise

                    latest_path = save_latest_zpl(test_zpl_output_directory, zpl_text)
                    LOGGER.warning(
                        "Printer unavailable (%s). Saved latest ZPL to %s",
                        exc,
                        latest_path,
                    )
                else:
                    if enable_test_zpl_fallback:
                        latest_path = save_latest_zpl(
                            test_zpl_output_directory, zpl_text
                        )
                        LOGGER.info("Saved latest ZPL to %s", latest_path)

                last_payload = payload
                last_print_ts = now
                if printed_to_device:
                    LOGGER.info(
                        "Printed payload: %s (escaped=%s utf8_hex=%s)",
                        payload_text,
                        payload_escaped,
                        payload_hex,
                    )
                else:
                    LOGGER.info(
                        "Rendered payload without printer output: %s (escaped=%s utf8_hex=%s)",
                        payload_text,
                        payload_escaped,
                        payload_hex,
                    )
            except Exception:
                payload_text, payload_escaped, payload_hex = _payload_log_context(
                    payload
                )
                LOGGER.exception(
                    "Failed processing payload %s (escaped=%s utf8_hex=%s). "
                    "Keeping service alive and waiting for next scan.",
                    payload_text,
                    payload_escaped,
                    payload_hex,
                )

    except (
        UnsupportedLayoutError,
        FileNotFoundError,
        PermissionError,
        TemplateError,
        ValueError,
    ) as exc:
        LOGGER.exception("Fatal configuration/runtime error: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    run()
