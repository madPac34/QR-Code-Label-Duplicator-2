"""
labelclone – raw ZPL printer output.

Writes ZPL bytes directly to the USB printer character device.
UTF-8 encoded bytes are sent verbatim – the printer firmware (ZPL ^CI28)
interprets them correctly.

Retries once on transient write errors.
"""

import logging
import time

log = logging.getLogger("labelclone.printer")

_WRITE_RETRIES = 2
_RETRY_DELAY_S = 1.0


def send_to_printer(cfg, zpl: str) -> bool:
    """
    Encode *zpl* as UTF-8 and write it to the configured printer device.

    Returns True on success, False on failure (after retries).
    """
    raw: bytes = zpl.encode("utf-8")
    device_path: str = cfg.printer_device

    for attempt in range(1, _WRITE_RETRIES + 1):
        try:
            with open(device_path, "wb") as f:
                f.write(raw)
                f.flush()
            log.debug(
                "Sent %d bytes to %s (attempt %d)",
                len(raw), device_path, attempt,
            )
            return True
        except OSError as exc:
            log.error(
                "Printer write error on %s (attempt %d/%d): %s",
                device_path, attempt, _WRITE_RETRIES, exc,
            )
            if attempt < _WRITE_RETRIES:
                time.sleep(_RETRY_DELAY_S)

    return False
