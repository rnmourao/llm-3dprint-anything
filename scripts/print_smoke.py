"""End-to-end smoke print: stream scratch/smoke/assembly.gcode to the Ender-3 S1 Pro.

Run as: .venv/bin/python scripts/print_smoke.py
Progress lines are emitted to stdout, line-buffered, so an external Monitor
can pick them up.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skill"))

import serial

from transport import stream_gcode
from transport.streamer import Progress, SerialTransport

PORT = "/dev/cu.usbserial-110"
BAUD = 115200
GCODE = Path("scratch/smoke/assembly.gcode")


def _drain_banner(port: str, baud: int) -> None:
    s = serial.Serial(port=port, baudrate=baud, timeout=2.0)
    time.sleep(2.5)  # printer resets on DTR; let it boot
    while True:
        line = s.readline()
        if not line:
            break
        print(f"BANNER: {line.decode('ascii', errors='replace').rstrip()}", flush=True)
    s.close()


def main() -> int:
    print(f"START gcode={GCODE} port={PORT}", flush=True)
    _drain_banner(PORT, BAUD)

    transport = SerialTransport(PORT, baudrate=BAUD, timeout_s=2.0)
    # The constructor reopens the port; printer will reset again. Drain inline.
    time.sleep(2.5)
    while True:
        line = transport.read_line(timeout_s=0.5)
        if line is None:
            break
        print(f"BANNER2: {line}", flush=True)

    last_pct = -1
    last_emit = time.monotonic()

    def on_progress(p: Progress) -> None:
        nonlocal last_pct, last_emit
        pct = int(100 * p.lines_sent / p.total_lines) if p.total_lines else 0
        # Emit every 5% OR every 30 s, whichever first.
        now = time.monotonic()
        if pct != last_pct and (pct % 5 == 0 or now - last_emit > 30):
            print(
                f"PROGRESS {pct}% line={p.lines_sent}/{p.total_lines} gcode={p.current_gcode!r}",
                flush=True,
            )
            last_pct = pct
            last_emit = now

    result = stream_gcode(GCODE, transport, on_progress=on_progress)
    transport.close()

    if result.completed:
        print(
            f"DONE lines={result.lines_sent}/{result.total_lines} elapsed={result.elapsed_s:.1f}s",
            flush=True,
        )
        return 0
    print(
        f"FAILED lines={result.lines_sent}/{result.total_lines} "
        f"elapsed={result.elapsed_s:.1f}s error={result.error}",
        flush=True,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
