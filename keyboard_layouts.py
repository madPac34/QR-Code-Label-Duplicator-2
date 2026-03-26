"""Keyboard mappings for scanner HID events."""

from __future__ import annotations

from evdev import ecodes


_LAYOUT_DE = {
    "KEY_SPACE": (" ", " "),
    "KEY_MINUS": ("ß", "?"),
    "KEY_EQUAL": ("´", "`"),
    "KEY_LEFTBRACE": ("ü", "Ü"),
    "KEY_RIGHTBRACE": ("+", "*"),
    "KEY_BACKSLASH": ("#", "'"),
    "KEY_SEMICOLON": ("ö", "Ö"),
    "KEY_APOSTROPHE": ("ä", "Ä"),
    "KEY_GRAVE": ("^", "°"),
    "KEY_COMMA": (",", ";"),
    "KEY_DOT": (".", ":"),
    "KEY_SLASH": ("-", "_"),
    "KEY_102ND": ("<", ">"),
}

_ALTGR_DE = {
    "KEY_Q": "@",
    "KEY_E": "€",
    "KEY_7": "{",
    "KEY_8": "[",
    "KEY_9": "]",
    "KEY_0": "}",
    "KEY_MINUS": "\\",
    "KEY_RIGHTBRACE": "~",
    "KEY_BACKSLASH": "|",
    "KEY_102ND": "|",
    "KEY_M": "µ",
}

_LAYOUT_US = {
    "KEY_SPACE": (" ", " "),
    "KEY_MINUS": ("-", "_"),
    "KEY_EQUAL": ("=", "+"),
    "KEY_LEFTBRACE": ("[", "{"),
    "KEY_RIGHTBRACE": ("]", "}"),
    "KEY_BACKSLASH": ("\\", "|"),
    "KEY_SEMICOLON": (";", ":"),
    "KEY_APOSTROPHE": ("'", '"'),
    "KEY_GRAVE": ("`", "~"),
    "KEY_COMMA": (",", "<"),
    "KEY_DOT": (".", ">"),
    "KEY_SLASH": ("/", "?"),
    "KEY_102ND": ("\\", "|"),
}

_DIGIT_US_SHIFT = {
    "KEY_1": "!",
    "KEY_2": "@",
    "KEY_3": "#",
    "KEY_4": "$",
    "KEY_5": "%",
    "KEY_6": "^",
    "KEY_7": "&",
    "KEY_8": "*",
    "KEY_9": "(",
    "KEY_0": ")",
}

_DIGIT_DE_SHIFT = {
    "KEY_1": "!",
    "KEY_2": '"',
    "KEY_3": "§",
    "KEY_4": "$",
    "KEY_5": "%",
    "KEY_6": "&",
    "KEY_7": "/",
    "KEY_8": "(",
    "KEY_9": ")",
    "KEY_0": "=",
}


class UnsupportedLayoutError(ValueError):
    """Raised when an unknown keyboard layout is configured."""


def _base_layout() -> dict[str, tuple[str, str, str | None]]:
    mapping: dict[str, tuple[str, str, str | None]] = {}

    for number in range(10):
        key = f"KEY_{number}"
        mapping[key] = (str(number), str(number), None)

    for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        key = f"KEY_{char}"
        mapping[key] = (char.lower(), char, None)

    keypad_mapping = {
        "KEY_KP0": "0",
        "KEY_KP1": "1",
        "KEY_KP2": "2",
        "KEY_KP3": "3",
        "KEY_KP4": "4",
        "KEY_KP5": "5",
        "KEY_KP6": "6",
        "KEY_KP7": "7",
        "KEY_KP8": "8",
        "KEY_KP9": "9",
        "KEY_KPDOT": ".",
        "KEY_KPSLASH": "/",
        "KEY_KPASTERISK": "*",
        "KEY_KPMINUS": "-",
        "KEY_KPPLUS": "+",
        "KEY_KPCOMMA": ",",
    }
    for key, char in keypad_mapping.items():
        mapping[key] = (char, char, None)

    return mapping


def _build_layout(
    base: dict[str, tuple[str, str, str | None]],
    specific: dict[str, tuple[str, str]],
    shifted_digits: dict[str, str],
    altgr: dict[str, str] | None = None,
) -> dict[int, tuple[str, str, str | None]]:
    layout = dict(base)
    for key_name, (normal, shifted) in specific.items():
        _, _, existing_altgr = layout.get(key_name, ("", "", None))
        layout[key_name] = (normal, shifted, existing_altgr)

    for key_name, shifted in shifted_digits.items():
        normal, _, altgr_char = layout[key_name]
        layout[key_name] = (normal, shifted, altgr_char)

    if altgr:
        for key_name, altgr_char in altgr.items():
            normal, shifted, _ = layout[key_name]
            layout[key_name] = (normal, shifted, altgr_char)

    return {
        getattr(ecodes, name): pair
        for name, pair in layout.items()
        if hasattr(ecodes, name)
    }


def get_layout(layout_name: str) -> dict[int, tuple[str, str, str | None]]:
    base = _base_layout()

    if layout_name == "de":
        return _build_layout(base, _LAYOUT_DE, _DIGIT_DE_SHIFT, _ALTGR_DE)

    if layout_name == "us":
        return _build_layout(base, _LAYOUT_US, _DIGIT_US_SHIFT)

    raise UnsupportedLayoutError(f"Unsupported keyboard layout: {layout_name}")
