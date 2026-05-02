"""G-code streamer: drive a Transport through a .gcode file.

Pluggable Transport (mirror of orchestrator.Renderer / slicer.Slicer): the
production impl is `SerialTransport` (pyserial); tests inject fakes.

Sequence:
    1. Send `M110 N0` (line 0) to reset the printer's line counter.
    2. For each non-empty, non-comment line in the G-code:
       - Encode with the next line number + checksum.
       - Send.
       - Read responses until one parses as Ok / Resend / Error.
       - On Resend, replay from the small recent-line ring buffer.
       - On Error, abort with a populated StreamResult.error.
       - On Ok, advance.

v1 limitations (documented; not silently broken):
    * No M105 keepalive thread. Long blocking moves rely on response_timeout_s.
      The README's "M105 heartbeat" requirement is future work.
    * No flow control beyond the per-line ack. Marlin/Klipper's own buffer
      is the only smoothing; for high-throughput streaming, this matters.
    * No pause/resume. Streaming is a single blocking call.
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol

from .protocol import (
    ErrorResponse,
    OkResponse,
    ResendResponse,
    UnknownResponse,
    encode_line,
    parse_response,
    strip_gcode_line,
)


class Transport(Protocol):
    def write_line(self, line: str) -> None: ...
    def read_line(self, *, timeout_s: Optional[float] = None) -> Optional[str]: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class Progress:
    lines_sent: int
    total_lines: int
    current_gcode: str


@dataclass(frozen=True)
class StreamResult:
    lines_sent: int
    total_lines: int
    completed: bool
    error: Optional[str] = None
    elapsed_s: float = 0.0


def stream_gcode(
    gcode_path: Path,
    transport: Transport,
    *,
    response_timeout_s: float = 30.0,
    max_resends: int = 3,
    history_size: int = 32,
    on_progress: Optional[Callable[[Progress], None]] = None,
) -> StreamResult:
    gcode_path = Path(gcode_path)
    raw_lines = gcode_path.read_text().splitlines()
    executable = [s for s in (strip_gcode_line(line) for line in raw_lines) if s]
    total = len(executable)

    history: dict[int, str] = {}
    history_order: collections.deque[int] = collections.deque()
    resend_counts: dict[int, int] = collections.defaultdict(int)

    def _send_numbered(n: int, gcode: str) -> str:
        wire = encode_line(n, gcode)
        history[n] = wire
        history_order.append(n)
        while len(history_order) > history_size:
            evicted = history_order.popleft()
            history.pop(evicted, None)
        transport.write_line(wire)
        return wire

    def _await_response() -> tuple[str, object]:
        """Read until we get a definitive Ok / Resend / Error response."""
        deadline = time.monotonic() + response_timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "", None
            line = transport.read_line(timeout_s=remaining)
            if line is None:
                return "", None
            parsed = parse_response(line)
            if isinstance(parsed, UnknownResponse):
                continue  # echo / temperature / banner — keep reading
            return line, parsed

    start = time.monotonic()

    # 1. Line-counter reset
    _send_numbered(0, "M110 N0")
    raw, parsed = _await_response()
    if parsed is None:
        return StreamResult(0, total, False, "timeout waiting for ack of M110 reset",
                            time.monotonic() - start)
    if isinstance(parsed, ErrorResponse):
        return StreamResult(0, total, False, f"printer error during M110: {parsed.message}",
                            time.monotonic() - start)

    # 2. Stream
    line_number = 1
    lines_sent = 0
    for gcode in executable:
        _send_numbered(line_number, gcode)
        if on_progress is not None:
            on_progress(Progress(lines_sent=lines_sent, total_lines=total, current_gcode=gcode))

        while True:
            raw, parsed = _await_response()
            if parsed is None:
                return StreamResult(
                    lines_sent, total, False,
                    f"timeout after line {line_number}: {gcode!r}",
                    time.monotonic() - start,
                )
            if isinstance(parsed, OkResponse):
                lines_sent += 1
                line_number += 1
                break
            if isinstance(parsed, ResendResponse):
                resend_counts[parsed.line] += 1
                if resend_counts[parsed.line] > max_resends:
                    return StreamResult(
                        lines_sent, total, False,
                        f"line {parsed.line} exceeded max_resends={max_resends}",
                        time.monotonic() - start,
                    )
                if parsed.line not in history:
                    return StreamResult(
                        lines_sent, total, False,
                        f"printer requested resend of line {parsed.line} but it has fallen out of history",
                        time.monotonic() - start,
                    )
                transport.write_line(history[parsed.line])
                continue  # await another response
            if isinstance(parsed, ErrorResponse):
                return StreamResult(
                    lines_sent, total, False,
                    f"printer error after line {line_number}: {parsed.message}",
                    time.monotonic() - start,
                )

    return StreamResult(lines_sent, total, True, None, time.monotonic() - start)


# ----- production transport -----


class SerialTransport:
    """pyserial-backed Transport. Imported lazily so tests don't need a serial port.

    The printer typically sends a banner ("start" / "echo:Marlin ...") on
    open; consumers may want to drain that before streaming. v1 leaves
    drainage as the caller's responsibility.
    """

    def __init__(self, port: str, *, baudrate: int = 115200, timeout_s: float = 1.0) -> None:
        import serial  # imported here so missing pyserial doesn't break protocol-only consumers

        self._ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout_s)

    def write_line(self, line: str) -> None:
        self._ser.write((line + "\n").encode("ascii"))
        self._ser.flush()

    def read_line(self, *, timeout_s: Optional[float] = None) -> Optional[str]:
        if timeout_s is not None:
            self._ser.timeout = timeout_s
        raw = self._ser.readline()
        if not raw:
            return None
        return raw.decode("ascii", errors="replace").rstrip("\r\n")

    def close(self) -> None:
        self._ser.close()
