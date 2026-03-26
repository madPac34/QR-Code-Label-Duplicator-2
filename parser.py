"""Parser for QR payload interpretation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedPayload:
    raw: str
    fields: list[str]
    labornummer: str
    matrix: str
    date: str

    @property
    def text_payload(self) -> str:
        if self.labornummer and self.matrix and self.date:
            return f"{self.labornummer}\n{self.matrix}\nT:{self.date}"

        return self.raw


def parse_payload(payload: str) -> ParsedPayload:
    """Parse payload in format ``<labornummer>_<matrix>_<date>``.

    Underscore is the field separator.  Additional underscores are treated as
    part of the matrix field to keep labornummer and date mapping stable.

    Field contents are kept byte-for-byte as scanned (decoded as UTF-8 text).
    Trimming here can silently remove meaningful characters (including
    scanner-delivered control/spacing chars) and cause printed/logged payloads
    to differ from what was scanned.
    """

    parts = payload.split("_")

    if len(parts) >= 3:
        labornummer = parts[0]
        date = parts[-1]
        matrix = "_".join(parts[1:-1])
    else:
        labornummer = ""
        matrix = ""
        date = ""

    return ParsedPayload(
        raw=payload,
        fields=parts,
        labornummer=labornummer,
        matrix=matrix,
        date=date,
    )
