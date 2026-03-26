"""ZPL rendering from template placeholders."""

from __future__ import annotations

from pathlib import Path

from parser import ParsedPayload


class TemplateError(RuntimeError):
    """Raised when required placeholders are missing."""


def _encode_zpl_field_data(value: str) -> str:
    """Encode field data for safe ZPL rendering with ``^FH\\`` enabled.

    Zebra interprets ``\\xx`` as a hexadecimal byte when ``^FH\\`` is active.
    We hex-encode non-ASCII bytes and ZPL control characters to preserve UTF-8
    payloads (including German umlauts ä ö ü Ä Ö Ü ß) and avoid accidental
    command parsing.
    """

    safe_ascii = set(range(ord(" "), ord("~") + 1))
    always_encode = {ord("^"), ord("~"), ord("\\")}

    chunks: list[str] = []
    for byte in value.encode("utf-8"):
        if byte in safe_ascii and byte not in always_encode:
            chunks.append(chr(byte))
        else:
            chunks.append(f"\\{byte:02X}")

    return "".join(chunks)


def _encode_zpl_hex_bytes(value: str) -> str:
    """Encode every UTF-8 byte as ``\\xx`` for binary-safe fields.

    QR payloads are particularly sensitive to mode/control parsing.
    Emitting pure hex escapes guarantees special characters — including German
    umlauts encoded as multi-byte UTF-8 sequences — are preserved exactly.
    """

    return "".join(f"\\{byte:02X}" for byte in value.encode("utf-8"))


def render_zpl(template_path: Path, parsed_payload: ParsedPayload) -> str:
    template = template_path.read_text(encoding="utf-8")

    if "{{QR_PAYLOAD}}" not in template:
        raise TemplateError("Template must include {{QR_PAYLOAD}} placeholder")

    replacements = {
        "{{TEXT_PAYLOAD}}": _encode_zpl_field_data(parsed_payload.text_payload),
        "{{TOP_LINE}}": _encode_zpl_field_data(
            parsed_payload.labornummer or parsed_payload.raw
        ),
        "{{PRODUCT_NAME}}": _encode_zpl_field_data(parsed_payload.matrix),
        "{{DATE_LINE}}": _encode_zpl_field_data(
            f"T:{parsed_payload.date}" if parsed_payload.date else ""
        ),
        "{{QR_PAYLOAD}}": _encode_zpl_hex_bytes(parsed_payload.raw),
    }

    rendered = template
    for marker, replacement in replacements.items():
        rendered = rendered.replace(marker, replacement)

    return rendered
