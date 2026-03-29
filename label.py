"""
labelclone – ZPL label renderer.

Renders a ZPL II label from a template string by substituting named
placeholders.  Encoding is always UTF-8 (^CI28 + ^FH\\ escape in ZPL).

Template placeholders
---------------------
{{labornummer}}   – first segment of payload  (e.g. FL26-031347)
{{matrix}}        – second segment            (e.g. CitroSäurEste)
{{DATE_LINE}}     – "T:" + third segment      (e.g. T:24.03.26)
{{QR_PAYLOAD}}    – exact original payload    (used in QR data field)

ZPL hex-escaping for UTF-8
---------------------------
^FH\\ enables hex escaping in the following ^FD field.
Every non-ASCII byte is emitted as _XX (underscore + two upper-hex digits).
ASCII bytes are passed through verbatim.

Label geometry is driven by Config attributes so a different printer
(e.g. 300 dpi) only needs a config change.
"""

import logging

log = logging.getLogger("labelclone.label")

# ---------------------------------------------------------------------------
# Default ZPL template
# ---------------------------------------------------------------------------
# Coordinates assume 203 dpi (8 dpmm), 4 inch wide × 2 inch tall label.
# Adjust X/Y/font sizes in the config or by editing DEFAULT_TEMPLATE below.

DEFAULT_TEMPLATE = """\
^XA
^CI28
^PW{label_width_dots}
^LL{label_height_dots}
^PR{print_speed}
^MD{print_darkness}

^FO20,18^A0N,70,65^FH\\^FD{labornummer_hex}^FS

^FO20,110^A0N,58,52^FH\\^FD{matrix_hex}^FS

^FO20,192^A0N,48,44^FH\\^FD{DATE_LINE_hex}^FS

^FO390,14
^BQN,{qr_model},{qr_magnification}
^FH\\^FDQA,{QR_PAYLOAD_hex}^FS

^XZ"""


# ---------------------------------------------------------------------------
# Hex-escape helper (ZPL ^FH\\ notation)
# ---------------------------------------------------------------------------

def _zpl_hex_escape(text: str) -> str:
    """
    Encode *text* for use inside a ZPL ^FH\\ / ^FD…^FS block.

    ASCII printable chars (0x20-0x7E) are passed verbatim.
    Everything else (including multi-byte UTF-8 sequences) is emitted
    as _XX (ZPL hex-escape prefix underscore + two uppercase hex digits
    per byte in the UTF-8 encoding).

    Circumflex (^) and tilde (~) have special meaning in ZPL; they are
    also hex-escaped.
    """
    out: list[str] = []
    for byte in text.encode("utf-8"):
        if 0x20 <= byte <= 0x7E and byte not in (ord("^"), ord("~"), ord("_")):
            out.append(chr(byte))
        else:
            out.append(f"_{byte:02X}")
    return "".join(out)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_label(cfg, raw_payload: str, fields: dict) -> str:
    """
    Build and return a ZPL string ready to be sent to the printer.

    Parameters
    ----------
    cfg         : Config instance
    raw_payload : the exact string read from the scanner
    fields      : dict with keys labornummer, matrix, date
    """
    labornummer = fields["labornummer"]
    matrix = fields["matrix"]
    date = fields["date"]
    date_line = f"T:{date}"

    context = {
        # Geometry / print settings (plain integers, no hex-escaping needed)
        "label_width_dots": cfg.label_width_dots,
        "label_height_dots": cfg.label_height_dots,
        "print_speed": cfg.print_speed,
        "print_darkness": cfg.print_darkness,
        "qr_magnification": cfg.qr_magnification,
        "qr_model": cfg.qr_model,
        # Text fields – hex-escaped for ZPL ^FH\\ mode
        "labornummer_hex": _zpl_hex_escape(labornummer),
        "matrix_hex": _zpl_hex_escape(matrix),
        "DATE_LINE_hex": _zpl_hex_escape(date_line),
        "QR_PAYLOAD_hex": _zpl_hex_escape(raw_payload),
    }

    template = DEFAULT_TEMPLATE
    zpl = template.format(**context)

    log.debug(
        "render_label: labornummer=%r  matrix=%r  date_line=%r  qr=%r",
        labornummer, matrix, date_line, raw_payload,
    )
    return zpl
