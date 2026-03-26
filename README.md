# QR-Code-Label-Duplicator

Headless Raspberry Pi service that listens to a USB QR scanner (keyboard/HID mode), rebuilds the scanned payload, and prints one duplicate sticky label to a raw ZPL printer.

## Features

- Reads scanner input directly from Linux event device (`/dev/input/event*`) using `evdev`.
- Uses stable udev symlinks for scanner/printer (`/dev/labelclone-scanner`, `/dev/labelclone-printer`).
- Auto-detects scanner from `/dev/input/by-id/*event-kbd` when scanner symlink is disabled.
- Auto-detects printer from `/dev/usb/lp*` when printer symlink/path is unavailable.
- Supports keyboard layout mapping for `de` and `us`.
- UTF-8 end-to-end (`^CI28` + `^FH\` in ZPL and UTF-8 bytes to printer) including umlauts (`ä ö ü Ä Ö Ü ß`).
- Duplicate scan suppression (same payload scanned again within configured window is ignored).
- Template-based label rendering with placeholders for easy migration to a production layout.
- `systemd` unit for auto-start at boot and restart on failure.
- One-command installer script for Raspberry Pi OS Lite.

## Repository layout

- `labelclone.py` – main service loop and device I/O.
- `config.example.py` – configurable defaults (copy to `config.py`).
- `keyboard_layouts.py` – HID keycode to character mappings.
- `parser.py` – underscore-delimited payload parsing and field mapping.
- `zpl.py` – template loading and placeholder rendering.
- `templates/label_template.zpl` – default production-style label template.
- `systemd/labelclone.service` – background service definition.
- `scripts/install.sh` – install/update helper for `/opt/labelclone`.

## Payload handling

The label payload format is:

`<labornummer>_<matrix>_<date>`

Example payload:

`FL26-031347_CitroSäurEste_24.03.26`

Rendering behaviour:

1. `labornummer` is printed on the top line (`{{TOP_LINE}}`).
2. `matrix` is printed in a wrapped middle text block (`{{PRODUCT_NAME}}`).
3. `date` is printed as `T:<date>` (`{{DATE_LINE}}`).
4. QR code contains the exact original payload (`{{QR_PAYLOAD}}`).

If the payload does not contain all three underscore-separated fields, the service falls back to printing the raw payload text in templates that still use `{{TEXT_PAYLOAD}}`.

## German character handling

German umlauts and `ß` flow through the stack in three stages:

1. **HID → text** (`keyboard_layouts.py`): The `de` layout maps key codes to the correct Unicode characters, including dead keys and AltGr combinations. For example `KEY_APOSTROPHE` → `ä`/`Ä`, `KEY_LEFTBRACE` → `ü`/`Ü`, `KEY_SEMICOLON` → `ö`/`Ö`, `KEY_MINUS` → `ß`.
2. **Text → ZPL field data** (`zpl.py`): `_encode_zpl_field_data` converts each UTF-8 byte that falls outside safe ASCII — or is a ZPL control character (`^`, `~`, `\`) — to the `\xx` hex-escape form that Zebra's `^FH\` field-hex prefix understands.
3. **ZPL → printer** (`labelclone.py`): The raw ZPL is written as UTF-8 bytes. The template contains `^CI28` (UTF-8 codepage) so the printer renders multi-byte sequences correctly.

## Installation (one command)

From cloned repo on Raspberry Pi OS Lite:

```bash
sudo ./scripts/install.sh
```

Installer actions:

1. Installs system packages (`python3`, `python3-venv`, `python3-pip`, `rsync`).
2. Syncs repo to `/opt/labelclone`.
3. Preserves existing `/opt/labelclone/config.py` on upgrades.
4. Creates virtual environment and installs Python dependencies.
5. Installs `systemd` service, enables it, and starts/restarts it.
6. Installs udev rules that create stable scanner/printer symlinks.

## Configuration

After first install edit:

`/opt/labelclone/config.py`

Key options:

| Key | Default | Description |
|---|---|---|
| `SCANNER_DEVICE` | `/dev/labelclone-scanner` | udev symlink for the scanner. Set `None` for by-id auto-detect. |
| `KEYBOARD_LAYOUT` | `"de"` | `"de"` or `"us"`. |
| `PRINTER_DEVICE` | `/dev/labelclone-printer` | udev symlink for the printer. Falls back to first `/dev/usb/lp*`. |
| `TEMPLATE_PATH` | `/opt/labelclone/templates/label_template.zpl` | Path to ZPL template. |
| `DUPLICATE_SUPPRESSION_SECONDS` | `0.5` | Ignore repeated identical scans within this window. |

Testing-only toggles:

| Key | Default | Description |
|---|---|---|
| `ENABLE_TEST_LOG_FILE` | `False` | Write logs to `TEST_LOG_FILE_PATH` in addition to stdout. |
| `TEST_LOG_FILE_PATH` | `/tmp/labelclone-testing/labelclone.log` | Log file location. |
| `ENABLE_TEST_ZPL_FALLBACK` | `False` | On printer failure, save generated ZPL as `latest.zpl`. |
| `TEST_ZPL_OUTPUT_DIR` | `/tmp/labelclone-testing` | Output folder for fallback `latest.zpl`. |

Then restart service:

```bash
sudo systemctl restart labelclone.service
```

### TSC TC300 over USB

1. Connect the TC300 by USB and run the installer:
   ```bash
   sudo ./scripts/install.sh
   ```
2. Verify the stable printer symlink exists:
   ```bash
   ls -l /dev/labelclone-printer
   ```
3. Keep `PRINTER_DEVICE` as `/dev/labelclone-printer` in `/opt/labelclone/config.py`.
4. Ensure the printer emulation is set to ZPL-compatible mode.

If the symlink is absent, point `PRINTER_DEVICE` to `/dev/usb/lp0` and restart the service.

## Service operations

```bash
sudo systemctl status labelclone.service
sudo journalctl -u labelclone.service -f
```

## Running tests

```bash
pip install evdev
python -m pytest tests/
```

## Notes for production template migration

If label requirements change, adapt:

- `parser.py` field mapping logic.
- `templates/label_template.zpl` placeholders/positions.
- Optionally `zpl.py` to render additional placeholders.
