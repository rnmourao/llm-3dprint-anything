"""Stage 5: stream G-code to a Marlin/Klipper printer over USB serial.

The line-numbered protocol with checksum is implemented in
[`transport.protocol`](protocol.py) (pure functions). Streaming, response
handling, and resends live in [`transport.streamer`](streamer.py). The
production `SerialTransport` wraps pyserial; tests inject fakes.
"""

from .protocol import (
    ErrorResponse,
    OkResponse,
    Response,
    ResendResponse,
    UnknownResponse,
    compute_checksum,
    encode_line,
    parse_response,
    strip_gcode_line,
)
from .streamer import (
    Progress,
    SerialTransport,
    StreamResult,
    Transport,
    stream_gcode,
)

__all__ = [
    "ErrorResponse",
    "OkResponse",
    "Progress",
    "Response",
    "ResendResponse",
    "SerialTransport",
    "StreamResult",
    "Transport",
    "UnknownResponse",
    "compute_checksum",
    "encode_line",
    "parse_response",
    "stream_gcode",
    "strip_gcode_line",
]
