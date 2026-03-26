import unittest

from evdev import ecodes

from keyboard_layouts import get_layout


class KeyboardLayoutSpecialCharsTests(unittest.TestCase):
    def test_de_layout_maps_iso_extra_key_and_altgr(self) -> None:
        layout = get_layout("de")

        self.assertIn(ecodes.KEY_102ND, layout)
        self.assertEqual(layout[ecodes.KEY_102ND], ("<", ">", "|"))

    def test_us_layout_maps_iso_extra_key(self) -> None:
        layout = get_layout("us")

        self.assertIn(ecodes.KEY_102ND, layout)
        self.assertEqual(layout[ecodes.KEY_102ND], ("\\", "|", None))

    def test_keypad_chars_are_available_in_layout(self) -> None:
        layout = get_layout("de")

        self.assertEqual(layout[ecodes.KEY_KPSLASH], ("/", "/", None))
        self.assertEqual(layout[ecodes.KEY_KPASTERISK], ("*", "*", None))
        self.assertEqual(layout[ecodes.KEY_KPMINUS], ("-", "-", None))
        self.assertEqual(layout[ecodes.KEY_KPPLUS], ("+", "+", None))
        self.assertEqual(layout[ecodes.KEY_KPDOT], (".", ".", None))


if __name__ == "__main__":
    unittest.main()
