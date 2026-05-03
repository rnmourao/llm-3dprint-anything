"""Marlin / Klipper line-numbering protocol — pure functions only.

Wire format for a numbered line:
    N<line> <gcode>*<checksum>

Checksum is XOR of every byte of the message before the `*`, including the
leading `N<line>` and the space. Printer responds with one of:
    ok                  — accepted; advance
    Resend: <N>         — re-send line N (some firmwares emit `rs <N>`)
    !! error: <text>    — fatal; abort
    echo: ... / others  — informational; ignore and keep reading

This module is pure — no IO, no globals. The streamer composes these.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def compute_checksum(message: str) -> int:
    """XOR of all bytes in the ASCII-encoded message."""
    cs = 0
    for byte in message.encode("ascii"):
        cs ^= byte
    return cs


def encode_line(line_number: int, gcode: str) -> str:
    """Compose the wire-format line. Strip any trailing whitespace from gcode."""
    msg = f"N{line_number} {gcode.rstrip()}"
    return f"{msg}*{compute_checksum(msg)}"


def strip_gcode_line(line: str) -> Optional[str]:
    """Return the executable part of a line, or None if there's nothing to send.

    Drops:
      - inline `;` comments (everything after the first `;`)
      - leading/trailing whitespace
      - blank lines
    """
    s = line.split(";", 1)[0].strip()
    return s or None


# ----- response types -----


@dataclass(frozen=True)
class OkResponse:
    pass


@dataclass(frozen=True)
class ResendResponse:
    line: int


@dataclass(frozen=True)
class ErrorResponse:
    message: str


@dataclass(frozen=True)
class UnknownResponse:
    raw: str


Response = OkResponse | ResendResponse | ErrorResponse | UnknownResponse


def parse_response(line: str) -> Response:
    """Classify a single line of printer output."""
    s = line.strip()
    if not s:
        return UnknownResponse(s)
    low = s.lower()

    if low.startswith("ok"):
        return OkResponse()

    # Resend forms: "Resend: 5", "Resend:5", "rs 5", "rs:5"
    if low.startswith("resend") or low.startswith("rs"):
        for token in s.replace(":", " ").split()[1:]:
            try:
                return ResendResponse(line=int(token))
            except ValueError:
                continue
        return ErrorResponse(f"unparseable resend: {s!r}")

    if s.startswith("!!") or low.startswith("error"):
        return ErrorResponse(s)

    return UnknownResponse(s)
