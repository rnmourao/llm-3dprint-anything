"""Streamer integration tests using a fake transport.

The fake transport plays back a programmed response queue and records
every line that was sent. This lets us cover the full protocol-state-
machine paths (clean run, resend, error, timeout) without real hardware.
"""

from pathlib import Path
from typing import Optional

import pytest

from transport import StreamResult, Transport, stream_gcode


class FakeTransport:
    """Transport stub: programmable responses, recorded sends."""

    def __init__(self, responses: list[Optional[str]]) -> None:
        self.responses = list(responses)
        self.sent: list[str] = []
        self.closed = False

    def write_line(self, line: str) -> None:
        self.sent.append(line)

    def read_line(self, *, timeout_s: Optional[float] = None) -> Optional[str]:
        if not self.responses:
            return None  # exhausted → simulate timeout
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


def _gcode_file(tmp_path: Path, lines: list[str]) -> Path:
    p = tmp_path / "job.gcode"
    p.write_text("\n".join(lines) + "\n")
    return p


# ----- happy path -----


def test_clean_stream_completes(tmp_path):
    gcode = _gcode_file(tmp_path, ["G28", "G1 X10", "G1 Y20"])
    transport = FakeTransport(["ok", "ok", "ok", "ok"])  # 1 for M110 + 3 for gcode

    result = stream_gcode(gcode, transport)
    assert result.completed is True
    assert result.lines_sent == 3
    assert result.total_lines == 3
    assert result.error is None
    # M110 reset is line 0; first user gcode is line 1
    assert transport.sent[0].startswith("N0 M110 N0*")
    assert transport.sent[1].startswith("N1 G28*")
    assert transport.sent[2].startswith("N2 G1 X10*")
    assert transport.sent[3].startswith("N3 G1 Y20*")


def test_strips_blank_and_comment_lines(tmp_path):
    gcode = _gcode_file(tmp_path, [
        "; header comment",
        "",
        "G28",
        "; mid comment",
        "G1 X10  ; inline comment",
    ])
    transport = FakeTransport(["ok", "ok", "ok"])  # M110 + G28 + G1
    result = stream_gcode(gcode, transport)
    assert result.completed is True
    assert result.lines_sent == 2
    # The G1 line should have its inline comment stripped before encoding
    assert any("G1 X10*" in s for s in transport.sent)


def test_progress_callback_is_invoked(tmp_path):
    gcode = _gcode_file(tmp_path, ["G28", "G1 X10"])
    transport = FakeTransport(["ok", "ok", "ok"])
    progress_log = []
    stream_gcode(gcode, transport, on_progress=progress_log.append)
    assert len(progress_log) == 2
    assert progress_log[0].current_gcode == "G28"
    assert progress_log[1].current_gcode == "G1 X10"
    assert progress_log[0].total_lines == 2


def test_unknown_responses_are_skipped(tmp_path):
    """Echo / temperature lines before 'ok' should not break the stream."""
    gcode = _gcode_file(tmp_path, ["G28"])
    transport = FakeTransport([
        "echo:Marlin 2.1.0",
        "ok",                  # M110 ack
        "echo:something",
        "T:200 /200 B:60 /60",
        "ok",                  # G28 ack
    ])
    result = stream_gcode(gcode, transport)
    assert result.completed is True


# ----- resend handling -----


def test_resend_replays_buffered_line(tmp_path):
    gcode = _gcode_file(tmp_path, ["G28", "G1 X10"])
    transport = FakeTransport([
        "ok",            # M110
        "ok",            # G28 (line 1)
        "Resend: 2",     # printer asks to resend line 2
        "ok",            # ack of resend
    ])
    result = stream_gcode(gcode, transport)
    assert result.completed is True
    # The G1 X10 line should appear twice in the sent buffer
    g1_sent = [s for s in transport.sent if "G1 X10*" in s]
    assert len(g1_sent) == 2


def test_resend_loop_aborts_after_max(tmp_path):
    gcode = _gcode_file(tmp_path, ["G28"])
    # M110 ok, then printer keeps asking for resend of line 1
    transport = FakeTransport(["ok"] + ["Resend: 1"] * 10)
    result = stream_gcode(gcode, transport, max_resends=3)
    assert result.completed is False
    assert "max_resends" in result.error


# ----- error handling -----


def test_error_response_aborts(tmp_path):
    gcode = _gcode_file(tmp_path, ["G28", "G1 X1000"])
    transport = FakeTransport([
        "ok",                       # M110
        "ok",                       # G28
        "!! out of range: X1000",   # G1 fails
    ])
    result = stream_gcode(gcode, transport)
    assert result.completed is False
    assert "out of range" in result.error
    assert result.lines_sent == 1  # only G28 succeeded


def test_timeout_at_first_response_aborts(tmp_path):
    gcode = _gcode_file(tmp_path, ["G28"])
    transport = FakeTransport([])  # nothing to read → immediate timeout
    result = stream_gcode(gcode, transport, response_timeout_s=0.01)
    assert result.completed is False
    assert "timeout" in result.error.lower()


def test_timeout_during_stream_aborts(tmp_path):
    gcode = _gcode_file(tmp_path, ["G28", "G1 X10"])
    transport = FakeTransport(["ok", "ok"])  # ack M110 and G28, then nothing
    result = stream_gcode(gcode, transport, response_timeout_s=0.01)
    assert result.completed is False
    assert result.lines_sent == 1


def test_error_during_m110_aborts(tmp_path):
    gcode = _gcode_file(tmp_path, ["G28"])
    transport = FakeTransport(["!! firmware mismatch"])
    result = stream_gcode(gcode, transport)
    assert result.completed is False
    assert "M110" in result.error or "firmware" in result.error
    assert result.lines_sent == 0


# ----- empty / pathological inputs -----


def test_empty_gcode_succeeds(tmp_path):
    gcode = _gcode_file(tmp_path, ["; just a comment", ""])
    transport = FakeTransport(["ok"])  # only M110 needs an ack
    result = stream_gcode(gcode, transport)
    assert result.completed is True
    assert result.lines_sent == 0
    assert result.total_lines == 0


# ----- long-block ack timeout -----


class SlowTransport:
    """Per-response delay queue. Each entry is (delay_s_before_response, response_string)."""

    def __init__(self, responses: list[tuple[float, Optional[str]]]) -> None:
        import time as _time
        self._time = _time
        self.responses = list(responses)
        self.sent: list[str] = []
        self._next_ready = _time.monotonic()

    def write_line(self, line: str) -> None:
        self.sent.append(line)
        # Arm the next response delay relative to this write.
        if self.responses:
            delay, _ = self.responses[0]
            self._next_ready = self._time.monotonic() + delay

    def read_line(self, *, timeout_s=None):
        if not self.responses:
            return None
        wait = self._next_ready - self._time.monotonic()
        if timeout_s is not None and wait > timeout_s:
            self._time.sleep(max(0.0, timeout_s))
            return None
        if wait > 0:
            self._time.sleep(wait)
        _, resp = self.responses.pop(0)
        return resp

    def close(self) -> None:
        pass


def test_long_block_opcode_uses_long_timeout(tmp_path):
    """M190's ack legitimately takes longer than response_timeout_s —
    long_block_timeout_s must cover it."""
    gcode = _gcode_file(tmp_path, ["M190 S60", "G1 X10"])
    # M110 acks fast (0 s); M190 holds for 0.15 s; G1 acks fast.
    transport = SlowTransport([(0.0, "ok"), (0.15, "ok"), (0.0, "ok")])
    result = stream_gcode(
        gcode, transport,
        response_timeout_s=0.05,
        long_block_timeout_s=2.0,
    )
    assert result.completed is True
    assert result.lines_sent == 2


def test_short_timeout_still_aborts_normal_moves(tmp_path):
    """A regular G1 that doesn't ack within response_timeout_s must time out
    even when long_block_timeout_s is generous."""
    gcode = _gcode_file(tmp_path, ["G1 X10"])
    transport = SlowTransport([(0.0, "ok"), (0.20, "ok")])
    result = stream_gcode(
        gcode, transport,
        response_timeout_s=0.05,
        long_block_timeout_s=10.0,
    )
    assert result.completed is False
    assert "timeout" in result.error.lower()
