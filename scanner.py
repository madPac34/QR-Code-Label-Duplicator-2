"""
labelclone – evdev scanner reader.

Reads raw key events from the Linux input subsystem, maps scan codes to
characters using a configurable keyboard layout, and yields complete scan
payloads terminated by KEY_ENTER.

Supports layouts: de (German QWERTZ), us (US QWERTY).
UTF-8 / umlaut characters are handled correctly end-to-end.
"""

import logging
import time
from typing import Iterator

import evdev
from evdev import categorize, ecodes

log = logging.getLogger("labelclone.scanner")

# ---------------------------------------------------------------------------
# Keyboard layout tables
# ---------------------------------------------------------------------------
# Each entry: keycode → (unshifted_char, shifted_char)
# Only printable characters that can appear in a barcode payload are needed.

_LAYOUT_US: dict[int, tuple[str, str]] = {
    ecodes.KEY_A: ("a", "A"),
    ecodes.KEY_B: ("b", "B"),
    ecodes.KEY_C: ("c", "C"),
    ecodes.KEY_D: ("d", "D"),
    ecodes.KEY_E: ("e", "E"),
    ecodes.KEY_F: ("f", "F"),
    ecodes.KEY_G: ("g", "G"),
    ecodes.KEY_H: ("h", "H"),
    ecodes.KEY_I: ("i", "I"),
    ecodes.KEY_J: ("j", "J"),
    ecodes.KEY_K: ("k", "K"),
    ecodes.KEY_L: ("l", "L"),
    ecodes.KEY_M: ("m", "M"),
    ecodes.KEY_N: ("n", "N"),
    ecodes.KEY_O: ("o", "O"),
    ecodes.KEY_P: ("p", "P"),
    ecodes.KEY_Q: ("q", "Q"),
    ecodes.KEY_R: ("r", "R"),
    ecodes.KEY_S: ("s", "S"),
    ecodes.KEY_T: ("t", "T"),
    ecodes.KEY_U: ("u", "U"),
    ecodes.KEY_V: ("v", "V"),
    ecodes.KEY_W: ("w", "W"),
    ecodes.KEY_X: ("x", "X"),
    ecodes.KEY_Y: ("y", "Y"),
    ecodes.KEY_Z: ("z", "Z"),
    ecodes.KEY_0: ("0", ")"),
    ecodes.KEY_1: ("1", "!"),
    ecodes.KEY_2: ("2", "@"),
    ecodes.KEY_3: ("3", "#"),
    ecodes.KEY_4: ("4", "$"),
    ecodes.KEY_5: ("5", "%"),
    ecodes.KEY_6: ("6", "^"),
    ecodes.KEY_7: ("7", "&"),
    ecodes.KEY_8: ("8", "*"),
    ecodes.KEY_9: ("9", "("),
    ecodes.KEY_SPACE: (" ", " "),
    ecodes.KEY_MINUS: ("-", "_"),
    ecodes.KEY_EQUAL: ("=", "+"),
    ecodes.KEY_LEFTBRACE: ("[", "{"),
    ecodes.KEY_RIGHTBRACE: ("]", "}"),
    ecodes.KEY_SEMICOLON: (";", ":"),
    ecodes.KEY_APOSTROPHE: ("'", '"'),
    ecodes.KEY_GRAVE: ("`", "~"),
    ecodes.KEY_BACKSLASH: ("\\", "|"),
    ecodes.KEY_COMMA: (",", "<"),
    ecodes.KEY_DOT: (".", ">"),
    ecodes.KEY_SLASH: ("/", "?"),
}

# German QWERTZ – positions that differ from US QWERTY, plus umlaut dead-keys.
# Many scanners in DE mode send the HID usage codes as if on a US keyboard,
# so the OS layout remaps them.  We replicate that mapping here for evdev.
#
# Important differences (physical key → HID code → DE character):
#   KEY_Y  → z / Z    (Y and Z swapped)
#   KEY_Z  → y / Y
#   KEY_MINUS   → ß / ?
#   KEY_EQUAL   → ´ / `   (dead keys – rarely in barcodes)
#   KEY_LEFTBRACE  → ü / Ü
#   KEY_RIGHTBRACE → + / *
#   KEY_SEMICOLON  → ö / Ö
#   KEY_APOSTROPHE → ä / Ä
#   KEY_GRAVE      → ^ / °
#   KEY_BACKSLASH  → # / '
#   KEY_COMMA      → , / ;
#   KEY_DOT        → . / :
#   KEY_SLASH      → - / _

_LAYOUT_DE: dict[int, tuple[str, str]] = {
    # Letters (A-X, W same as US; Y↔Z swapped)
    ecodes.KEY_A: ("a", "A"),
    ecodes.KEY_B: ("b", "B"),
    ecodes.KEY_C: ("c", "C"),
    ecodes.KEY_D: ("d", "D"),
    ecodes.KEY_E: ("e", "E"),
    ecodes.KEY_F: ("f", "F"),
    ecodes.KEY_G: ("g", "G"),
    ecodes.KEY_H: ("h", "H"),
    ecodes.KEY_I: ("i", "I"),
    ecodes.KEY_J: ("j", "J"),
    ecodes.KEY_K: ("k", "K"),
    ecodes.KEY_L: ("l", "L"),
    ecodes.KEY_M: ("m", "M"),
    ecodes.KEY_N: ("n", "N"),
    ecodes.KEY_O: ("o", "O"),
    ecodes.KEY_P: ("p", "P"),
    ecodes.KEY_Q: ("q", "Q"),
    ecodes.KEY_R: ("r", "R"),
    ecodes.KEY_S: ("s", "S"),
    ecodes.KEY_T: ("t", "T"),
    ecodes.KEY_U: ("u", "U"),
    ecodes.KEY_V: ("v", "V"),
    ecodes.KEY_W: ("w", "W"),
    ecodes.KEY_X: ("x", "X"),
    ecodes.KEY_Y: ("z", "Z"),   # Y physical → z on DE
    ecodes.KEY_Z: ("y", "Y"),   # Z physical → y on DE
    # Digits
    ecodes.KEY_0: ("0", "="),
    ecodes.KEY_1: ("1", "!"),
    ecodes.KEY_2: ("2", '"'),
    ecodes.KEY_3: ("3", "§"),
    ecodes.KEY_4: ("4", "$"),
    ecodes.KEY_5: ("5", "%"),
    ecodes.KEY_6: ("6", "&"),
    ecodes.KEY_7: ("7", "/"),
    ecodes.KEY_8: ("8", "("),
    ecodes.KEY_9: ("9", ")"),
    ecodes.KEY_SPACE: (" ", " "),
    # Punctuation / special
    ecodes.KEY_MINUS: ("ß", "?"),
    ecodes.KEY_EQUAL: ("+", "*"),        # ´ dead-key skipped; + common
    ecodes.KEY_LEFTBRACE: ("ü", "Ü"),
    ecodes.KEY_RIGHTBRACE: ("+", "*"),
    ecodes.KEY_SEMICOLON: ("ö", "Ö"),
    ecodes.KEY_APOSTROPHE: ("ä", "Ä"),
    ecodes.KEY_GRAVE: ("^", "°"),
    ecodes.KEY_BACKSLASH: ("#", "'"),
    ecodes.KEY_COMMA: (",", ";"),
    ecodes.KEY_DOT: (".", ":"),
    ecodes.KEY_SLASH: ("-", "_"),
}

LAYOUTS: dict[str, dict[int, tuple[str, str]]] = {
    "us": _LAYOUT_US,
    "de": _LAYOUT_DE,
}

# Modifier key codes
_SHIFT_KEYS = {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
_ALTGR_KEYS = {ecodes.KEY_RIGHTALT}  # AltGr on DE keyboards

# AltGr combinations for DE layout (AltGr + key → character)
# These cover umlauts and ß when sent as AltGr sequences rather than
# direct keycode mappings.
_ALTGR_DE: dict[int, str] = {
    ecodes.KEY_A: "ä",
    ecodes.KEY_O: "ö",
    ecodes.KEY_U: "ü",
    ecodes.KEY_S: "ß",
    ecodes.KEY_Q: "@",
    ecodes.KEY_E: "€",
}

# ---------------------------------------------------------------------------
# ScannerReader
# ---------------------------------------------------------------------------

class ScannerReader:
    """
    Opens the evdev device and yields complete scan payloads as str.
    Retries automatically if the device disappears (e.g. USB re-plug).
    """

    def __init__(self, cfg):
        self._device_path = cfg.scanner_device
        self._layout = LAYOUTS.get(cfg.keyboard_layout, _LAYOUT_DE)
        self._layout_name = cfg.keyboard_layout
        self._retry_delay = 3.0  # seconds between reconnect attempts

    def scans(self) -> Iterator[str]:
        """Infinite generator of complete scan payloads (str, UTF-8 decoded)."""
        while True:
            try:
                yield from self._read_loop()
            except OSError as exc:
                log.error(
                    "Scanner device error (%s) – retrying in %.0f s",
                    exc, self._retry_delay,
                )
                time.sleep(self._retry_delay)
            except Exception:
                log.exception("Unexpected scanner error – retrying in %.0f s", self._retry_delay)
                time.sleep(self._retry_delay)

    def _read_loop(self) -> Iterator[str]:
        log.info("Opening scanner device: %s", self._device_path)
        device = evdev.InputDevice(self._device_path)
        # Grab the device so it doesn't also type into a TTY/console
        device.grab()
        log.info(
            "Scanner grabbed: %s  (layout=%s)",
            device.name, self._layout_name,
        )

        buffer: list[str] = []
        shift_held = False
        altgr_held = False

        try:
            for event in device.read_loop():
                if event.type != ecodes.EV_KEY:
                    continue
                key_event = categorize(event)

                # Track shift state
                if key_event.scancode in _SHIFT_KEYS:
                    shift_held = (key_event.keystate != key_event.key_up)
                    continue

                # Track AltGr state
                if key_event.scancode in _ALTGR_KEYS:
                    altgr_held = (key_event.keystate != key_event.key_up)
                    continue

                # Only act on key-down (keystate == 1) and key-repeat (2)
                if key_event.keystate == key_event.key_up:
                    continue

                code = key_event.scancode

                if code == ecodes.KEY_ENTER:
                    payload = "".join(buffer)
                    buffer.clear()
                    if payload:
                        yield payload
                    continue

                if code == ecodes.KEY_BACKSPACE and buffer:
                    buffer.pop()
                    continue

                # AltGr combination (DE umlauts etc.)
                if altgr_held and self._layout_name == "de":
                    altgr_ch = _ALTGR_DE.get(code)
                    if altgr_ch:
                        log.debug("ALTGR code=%d → %r", code, altgr_ch)
                        buffer.append(altgr_ch)
                        continue

                mapping = self._layout.get(code)
                if mapping is None:
                    key_name = ecodes.KEY.get(code, f"KEY_{code}")
                    log.debug("Unmapped key code %d (%s) – ignored", code, key_name)
                    continue

                ch = mapping[1] if shift_held else mapping[0]
                log.debug("KEY code=%d shift=%s → %r", code, shift_held, ch)
                buffer.append(ch)

        finally:
            try:
                device.ungrab()
            except Exception:
                pass
            device.close()
