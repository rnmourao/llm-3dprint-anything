"""Pure-function tests for the Marlin protocol primitives."""

import pytest

from transport import (
    ErrorResponse,
    OkResponse,
    ResendResponse,
    UnknownResponse,
    compute_checksum,
    encode_line,
    parse_response,
    strip_gcode_line,
)


# ----- compute_checksum -----


def test_checksum_xor_of_ascii_bytes():
    # Manually computed: XOR of 'AB' = 0x41 ^ 0x42 = 0x03
    assert compute_checksum("AB") == 0x03


def test_checksum_empty_message_is_zero():
    assert compute_checksum("") == 0


def test_checksum_single_byte():
    assert compute_checksum("A") == 0x41


def test_checksum_known_marlin_example():
    # Marlin docs: "N3 T0*57" — checksum of "N3 T0" must be 57.
    assert compute_checksum("N3 T0") == 57


# ----- encode_line -----


def test_encode_line_includes_number_gcode_and_checksum():
    line = encode_line(3, "T0")
    assert line == "N3 T0*57"


def test_encode_line_strips_trailing_whitespace_from_gcode():
    line = encode_line(5, "G1 X10  \r\n")
    assert line.startswith("N5 G1 X10*")
    assert "  " not in line


def test_encode_line_zero_line_number():
    line = encode_line(0, "M110 N0")
    assert line.startswith("N0 M110 N0*")


# ----- strip_gcode_line -----


def test_strip_drops_comments():
    assert strip_gcode_line("G1 X10 ; move") == "G1 X10"


def test_strip_returns_none_for_blank_line():
    assert strip_gcode_line("") is None
    assert strip_gcode_line("   ") is None


def test_strip_returns_none_for_pure_comment():
    assert strip_gcode_line("; comment only") is None


def test_strip_preserves_executable_part():
    assert strip_gcode_line("  G1 X10 Y20  ") == "G1 X10 Y20"


# ----- parse_response -----


def test_parse_ok_simple():
    assert isinstance(parse_response("ok"), OkResponse)


def test_parse_ok_with_extras():
    """Marlin sometimes appends 'ok N5 P15 B3' (line number, planner buffer, etc)."""
    assert isinstance(parse_response("ok N5 P15 B3"), OkResponse)


def test_parse_resend_colon_form():
    r = parse_response("Resend: 5")
    assert isinstance(r, ResendResponse) and r.line == 5


def test_parse_resend_no_colon_form():
    r = parse_response("rs 7")
    assert isinstance(r, ResendResponse) and r.line == 7


def test_parse_resend_klipper_form():
    """Klipper sometimes uses lowercase 'resend:' too."""
    r = parse_response("resend:12")
    assert isinstance(r, ResendResponse) and r.line == 12


def test_parse_error_double_bang():
    r = parse_response("!! out of range: X300")
    assert isinstance(r, ErrorResponse)
    assert "out of range" in r.message


def test_parse_error_word():
    r = parse_response("Error: thermal runaway")
    assert isinstance(r, ErrorResponse)


def test_parse_unknown_for_echo():
    r = parse_response("echo:Marlin 2.1.0")
    assert isinstance(r, UnknownResponse)


def test_parse_unknown_for_blank():
    r = parse_response("")
    assert isinstance(r, UnknownResponse)


def test_parse_unparseable_resend_becomes_error():
    r = parse_response("Resend: notanumber")
    assert isinstance(r, ErrorResponse)
