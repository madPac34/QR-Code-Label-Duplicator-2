# labelclone

Headless Raspberry Pi service that listens to a USB QR/barcode scanner
(HID / keyboard mode), parses the payload, and prints one duplicate sticky
label to a raw ZPL label printer.

---

## Payload format

```
<labornummer>_<matrix>_<date>
```

**Example**

```
FL26-031347_CitroSäurEste_24.03.26
```

| Field | Example | Label position |
|-------|---------|----------------|
| `labornummer` | `FL26-031347` | Top line (large font) |
| `matrix` | `CitroSäurEste` | Middle block |
| `date` | `24.03.26` | Bottom-left as `T:24.03.26` |
| full payload | `FL26-031347_CitroSäurEste_24.03.26` | QR code (bottom-right) |

UTF-8 / umlauts (`ä ö ü Ä Ö Ü ß`) are supported end-to-end.

---

## Architecture

```
USB QR Scanner (HID keyboard mode)
        │  /dev/input/event*  (evdev)
        ▼
  scanner.py  ──  key-code → char mapping (de / us layout)
        │  raw payload string
        ▼
  labelclone.py ──  parse & duplicate guard
        │  fields dict
        ▼
  label.py  ──  ZPL template rendering (^CI28 + ^FH\ hex-escape)
        │  ZPL bytes (UTF-8)
        ▼
  printer.py  ──  write to /dev/usb/lp* or /dev/labelclone-printer
        │
        ▼
  USB Label Printer (raw ZPL)
```

---

## File layout

```
labelclone/
├── labelclone.py        # Main service / entry point
├── config.py            # Config loader with auto-detection fallback
├── scanner.py           # evdev reader + keyboard layout tables (de / us)
├── label.py             # ZPL template renderer (UTF-8 hex-escape)
├── printer.py           # Raw write to USB printer device
├── labelclone.conf      # Default config  → /etc/labelclone/
├── labelclone.service   # systemd unit   → /etc/systemd/system/
├── 99-labelclone.rules  # udev rules     → /etc/udev/rules.d/
└── install.sh           # One-command installer
```

---

## Quick start (Raspberry Pi OS Lite)

```bash
# 1. Copy the labelclone/ directory to your Pi, then:
sudo bash labelclone/install.sh

# 2. Find device IDs (plug in both USB devices first)
udevadm info -a -n /dev/input/event0 | grep -E 'idVendor|idProduct'
udevadm info -a -n /dev/usb/lp0       | grep -E 'idVendor|idProduct'

# 3. Edit udev rules with real Vendor:Product IDs
sudo nano /etc/udev/rules.d/99-labelclone.rules

# 4. Reload udev and restart service
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo systemctl restart labelclone

# 5. Watch logs
journalctl -u labelclone -f
```

---

## Device detection

The service uses a two-stage fallback for each device:

| Priority | Scanner | Printer |
|----------|---------|---------|
| 1st | `/dev/labelclone-scanner` (udev symlink) | `/dev/labelclone-printer` (udev symlink) |
| 2nd | First `*event-kbd` in `/dev/input/by-id/` | First `lp*` in `/dev/usb/` |

The scanner device is **grabbed** exclusively so keypresses are not echoed
to any console/TTY.

---

## Configuration reference

`/etc/labelclone/labelclone.conf`

| Key | Default | Description |
|-----|---------|-------------|
| `scanner_symlink` | `/dev/labelclone-scanner` | evdev path or udev symlink |
| `printer_symlink` | `/dev/labelclone-printer` | char-device path |
| `keyboard_layout` | `de` | `de` (QWERTZ) or `us` (QWERTY) |
| `duplicate_window_seconds` | `5.0` | Ignore re-scans within this window |
| `label_width_dots` | `812` | Label width in printer dots |
| `label_height_dots` | `406` | Label height in printer dots |
| `label_dpmm` | `8` | Dots-per-mm (8 = 203 dpi, 12 = 300 dpi) |
| `print_speed` | `4` | ZPL ^PR speed value |
| `print_darkness` | `28` | ZPL ^MD darkness 0–30 |
| `qr_magnification` | `4` | QR module size in dots (1–10) |
| `qr_model` | `2` | QR model (1 = original, 2 = enhanced) |

---

## Keyboard layout

The scanner sends HID key-codes as if it were a keyboard.
`scanner.py` maps those codes to characters using one of two layout tables:

- **`de`** – German QWERTZ; Y↔Z swapped; includes `ä ö ü Ä Ö Ü ß`
- **`us`** – US QWERTY

Set `keyboard_layout` in `labelclone.conf` to match the layout your
scanner reports (visible in the scanner's configuration sheet).

---

## ZPL label structure

```
┌────────────────────────────────────┐
│ FL26-031347          (60pt bold)   │
│                                    │
│ CitroSäurEste        (50pt)        │
│                                    │
│ T:24.03.26           (40pt)   [QR] │
└────────────────────────────────────┘
```

All text is sent with `^CI28` (Unicode) and `^FH\` (hex-escape mode).
Multi-byte UTF-8 characters are encoded as `_XX` sequences per ZPL spec.
The QR code encodes the exact original payload string.

---

## Customising the label

Edit `DEFAULT_TEMPLATE` in `label.py`.  Available format variables:

| Variable | Content |
|----------|---------|
| `{label_width_dots}` | from config |
| `{label_height_dots}` | from config |
| `{print_speed}` | from config |
| `{print_darkness}` | from config |
| `{qr_magnification}` | from config |
| `{qr_model}` | from config |
| `{labornummer_hex}` | ZPL-hex-escaped labornummer |
| `{matrix_hex}` | ZPL-hex-escaped matrix |
| `{DATE_LINE_hex}` | ZPL-hex-escaped `T:<date>` |
| `{QR_PAYLOAD_hex}` | ZPL-hex-escaped full payload |

---

## Service management

```bash
# Status
sudo systemctl status labelclone

# Logs (live)
journalctl -u labelclone -f

# Restart
sudo systemctl restart labelclone

# Stop / disable
sudo systemctl stop labelclone
sudo systemctl disable labelclone

# Run manually (for testing)
sudo /opt/labelclone/venv/bin/python /opt/labelclone/labelclone.py --debug
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `No scanner device found` | `ls /dev/input/by-id/` – are there `*event-kbd` entries? Check udev rules. |
| `No printer found` | `ls /dev/usb/` – is `lp0` present? Check udev rules. |
| Garbled characters | Confirm `keyboard_layout` matches your scanner's HID config sheet. |
| Umlauts missing | Ensure printer firmware supports ZPL ^CI28. Flash latest firmware. |
| Labels printing twice | Increase `duplicate_window_seconds`. |
| Service won't start | `journalctl -u labelclone -n 50` for details. |

---

## Dependencies

- Python ≥ 3.9
- [python-evdev](https://python-evdev.readthedocs.io/) (`pip install evdev`)
- Raspberry Pi OS Lite (Bookworm / Bullseye) or any Debian-based Linux
- systemd
- A ZPL-capable label printer (Zebra, Godex, Citizen, …)
- A USB barcode/QR scanner in HID keyboard emulation mode
