"""Parse intent annotations out of an OpenSCAD source file.

The grammar is defined in SKILL.md. Each annotation is a comment line of the
form `// <key>: <body>`. Parsing is line-oriented and tolerant of whitespace
and ordering — but rejects unknown sub-keys so typos surface early.

Annotations:
    // part: <name>
    // fit: <a>~<b> class=<RC|LC|LT|LN|FN>
    // clash_whitelist: <a>~<b>
    // gravity: <axis>                       (axis ∈ {-x, +x, -y, +y, -z, +z})
    // bed_z: <value>
    // operating: temp_c=<N>                 (declares the operating temperature; fires check_operating_temperature on every part)
    // load: part=<name> force=<N> axis=<axis> length_mm=<L> section=<spec> [material=<mat>]
        spec ∈ rect:<W>x<H> | round:<D>
    // buckling: part=<name> axial_n=<F> length_mm=<L> section=<spec> [material=<mat>] [end_condition=<fixed-free|pinned-pinned|fixed-pinned|fixed-fixed>]
    // pressure: part=<name> internal_pa=<P> wall_thickness_mm=<t> radius_mm=<r> [material=<mat>]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from validators import CrossSection, RectSection, RoundSection

_LINE_RE = re.compile(
    r"^\s*//\s*(part|fit|clash_whitelist|gravity|bed_z|operating|load|buckling|pressure):\s*(.+?)\s*$"
)


@dataclass(frozen=True)
class Load:
    part: str
    force_n: float
    axis: str
    length_mm: float
    section: CrossSection
    material: str = "PLA"


@dataclass(frozen=True)
class Buckling:
    part: str
    axial_n: float
    length_mm: float
    section: CrossSection
    material: str = "PLA"
    end_condition: str = "fixed-free"


@dataclass(frozen=True)
class Pressure:
    part: str
    internal_pa: float
    wall_thickness_mm: float
    radius_mm: float
    material: str = "PLA"


@dataclass(frozen=True)
class Intent:
    parts: list[str] = field(default_factory=list)
    fits: list[tuple[str, str, str]] = field(default_factory=list)  # (a, b, fit_class)
    clash_whitelist: set[tuple[str, str]] = field(default_factory=set)
    gravity_axis: str = "-z"
    bed_z: Optional[float] = None
    operating_temp_c: Optional[float] = None
    loads: list[Load] = field(default_factory=list)
    bucklings: list[Buckling] = field(default_factory=list)
    pressures: list[Pressure] = field(default_factory=list)


def _parse_kv(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in s.split():
        if "=" not in token:
            raise ValueError(f"Expected key=value, got {token!r}")
        k, v = token.split("=", 1)
        out[k] = v
    return out


def _parse_section(spec: str) -> CrossSection:
    if ":" not in spec:
        raise ValueError(f"Bad section spec {spec!r}; expected 'rect:WxH' or 'round:D'")
    kind, dims = spec.split(":", 1)
    if kind == "rect":
        if "x" not in dims:
            raise ValueError(f"rect section needs WxH, got {spec!r}")
        w, h = dims.split("x", 1)
        return RectSection(width_mm=float(w), height_mm=float(h))
    if kind == "round":
        return RoundSection(diameter_mm=float(dims))
    raise ValueError(f"Unknown section kind {kind!r}; expected rect or round")


def _parse_pair(s: str) -> tuple[str, str]:
    if "~" not in s:
        raise ValueError(f"Expected a~b, got {s!r}")
    a, b = s.split("~", 1)
    return a, b


def parse_annotations(scad_text: str) -> Intent:
    parts: list[str] = []
    fits: list[tuple[str, str, str]] = []
    whitelist: set[tuple[str, str]] = set()
    gravity_axis = "-z"
    bed_z: Optional[float] = None
    operating_temp_c: Optional[float] = None
    loads: list[Load] = []
    bucklings: list[Buckling] = []
    pressures: list[Pressure] = []

    for lineno, line in enumerate(scad_text.splitlines(), start=1):
        m = _LINE_RE.match(line)
        if not m:
            continue
        key, body = m.group(1), m.group(2)

        try:
            if key == "part":
                name = body.strip()
                if not name or " " in name:
                    raise ValueError(f"part name must be a single token, got {body!r}")
                parts.append(name)

            elif key == "fit":
                head, *rest = body.split(maxsplit=1)
                a, b = _parse_pair(head)
                kv = _parse_kv(rest[0]) if rest else {}
                if "class" not in kv:
                    raise ValueError("fit annotation missing 'class='")
                fits.append((a, b, kv["class"]))

            elif key == "clash_whitelist":
                a, b = _parse_pair(body.strip())
                whitelist.add(tuple(sorted((a, b))))

            elif key == "gravity":
                gravity_axis = body.strip()

            elif key == "bed_z":
                bed_z = float(body.strip())

            elif key == "load":
                kv = _parse_kv(body)
                missing = {"part", "force", "axis", "length_mm", "section"} - kv.keys()
                if missing:
                    raise ValueError(f"load annotation missing keys: {sorted(missing)}")
                loads.append(Load(
                    part=kv["part"],
                    force_n=float(kv["force"]),
                    axis=kv["axis"],
                    length_mm=float(kv["length_mm"]),
                    section=_parse_section(kv["section"]),
                    material=kv.get("material", "PLA"),
                ))

            elif key == "operating":
                kv = _parse_kv(body)
                if "temp_c" not in kv:
                    raise ValueError("operating annotation missing 'temp_c='")
                operating_temp_c = float(kv["temp_c"])

            elif key == "buckling":
                kv = _parse_kv(body)
                missing = {"part", "axial_n", "length_mm", "section"} - kv.keys()
                if missing:
                    raise ValueError(f"buckling annotation missing keys: {sorted(missing)}")
                bucklings.append(Buckling(
                    part=kv["part"],
                    axial_n=float(kv["axial_n"]),
                    length_mm=float(kv["length_mm"]),
                    section=_parse_section(kv["section"]),
                    material=kv.get("material", "PLA"),
                    end_condition=kv.get("end_condition", "fixed-free"),
                ))

            elif key == "pressure":
                kv = _parse_kv(body)
                missing = {"part", "internal_pa", "wall_thickness_mm", "radius_mm"} - kv.keys()
                if missing:
                    raise ValueError(f"pressure annotation missing keys: {sorted(missing)}")
                pressures.append(Pressure(
                    part=kv["part"],
                    internal_pa=float(kv["internal_pa"]),
                    wall_thickness_mm=float(kv["wall_thickness_mm"]),
                    radius_mm=float(kv["radius_mm"]),
                    material=kv.get("material", "PLA"),
                ))

        except (ValueError, KeyError) as e:
            raise ValueError(f"line {lineno}: {key} annotation malformed: {e}") from e

    return Intent(
        parts=parts,
        fits=fits,
        clash_whitelist=whitelist,
        gravity_axis=gravity_axis,
        bed_z=bed_z,
        operating_temp_c=operating_temp_c,
        loads=loads,
        bucklings=bucklings,
        pressures=pressures,
    )
