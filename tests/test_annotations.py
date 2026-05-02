import pytest

from orchestrator import parse_annotations
from validators import RectSection, RoundSection


# ----- happy paths -----


def test_parse_part_annotations():
    intent = parse_annotations("""
        // part: shaft
        // part: hole
        module shaft() {}
    """)
    assert intent.parts == ["shaft", "hole"]


def test_parse_fit_annotation():
    intent = parse_annotations("// fit: shaft~hole class=RC")
    assert intent.fits == [("shaft", "hole", "RC")]


def test_parse_clash_whitelist_normalises_order():
    intent = parse_annotations("""
        // clash_whitelist: bolt~boss
        // clash_whitelist: nut~bolt
    """)
    assert intent.clash_whitelist == {("bolt", "boss"), ("bolt", "nut")}


def test_parse_gravity_and_bed_z():
    intent = parse_annotations("""
        // gravity: +y
        // bed_z: -1.5
    """)
    assert intent.gravity_axis == "+y"
    assert intent.bed_z == -1.5


def test_parse_load_with_rect_section():
    intent = parse_annotations(
        "// load: part=arm force=10 axis=-z length_mm=50 section=rect:5x3 material=PETG"
    )
    [load] = intent.loads
    assert load.part == "arm"
    assert load.force_n == 10.0
    assert load.axis == "-z"
    assert load.length_mm == 50.0
    assert load.section == RectSection(5.0, 3.0)
    assert load.material == "PETG"


def test_parse_load_with_round_section_default_material():
    intent = parse_annotations(
        "// load: part=rod force=2.5 axis=-z length_mm=20 section=round:8"
    )
    [load] = intent.loads
    assert load.section == RoundSection(8.0)
    assert load.material == "PLA"


def test_defaults_when_nothing_specified():
    intent = parse_annotations("module foo() {}")
    assert intent.parts == []
    assert intent.fits == []
    assert intent.clash_whitelist == set()
    assert intent.gravity_axis == "-z"
    assert intent.bed_z is None
    assert intent.loads == []


def test_non_annotation_comments_are_ignored():
    intent = parse_annotations("""
        // this is a regular comment
        // TODO: something
        // part: shaft
        /* block comments don't count either */
    """)
    assert intent.parts == ["shaft"]


def test_annotation_inside_indented_code():
    """Annotations may appear with leading whitespace."""
    intent = parse_annotations("    // part: shaft\n        // fit: a~b class=LC")
    assert intent.parts == ["shaft"]
    assert intent.fits == [("a", "b", "LC")]


# ----- error paths -----


def test_fit_without_class_raises():
    with pytest.raises(ValueError, match="missing 'class='"):
        parse_annotations("// fit: shaft~hole")


def test_pair_without_tilde_raises():
    with pytest.raises(ValueError, match="Expected a~b"):
        parse_annotations("// fit: shafthole class=RC")


def test_load_missing_required_keys_raises():
    with pytest.raises(ValueError, match="missing keys"):
        parse_annotations("// load: part=arm force=10")


def test_bad_section_kind_raises():
    with pytest.raises(ValueError, match="Unknown section kind"):
        parse_annotations(
            "// load: part=arm force=10 axis=-z length_mm=50 section=triangle:1x2"
        )


def test_rect_section_without_x_raises():
    with pytest.raises(ValueError, match="rect section needs WxH"):
        parse_annotations(
            "// load: part=arm force=10 axis=-z length_mm=50 section=rect:5"
        )


def test_part_with_space_raises():
    with pytest.raises(ValueError, match="single token"):
        parse_annotations("// part: my shaft")


def test_kv_token_without_equals_raises():
    with pytest.raises(ValueError, match="key=value"):
        parse_annotations(
            "// load: part=arm force=10 axis=-z length_mm=50 section=round:5 bogus_token"
        )


def test_error_includes_line_number():
    src = "// part: ok\n// fit: a~b\n// part: also_ok\n"
    with pytest.raises(ValueError, match="line 2"):
        parse_annotations(src)


# ----- new heat-and-pressure annotations -----


def test_parse_operating_temperature():
    intent = parse_annotations("// operating: temp_c=65")
    assert intent.operating_temp_c == 65.0


def test_operating_without_temp_raises():
    with pytest.raises(ValueError, match="missing 'temp_c='"):
        parse_annotations("// operating: ambient=hot")


def test_parse_buckling_with_defaults():
    intent = parse_annotations(
        "// buckling: part=column axial_n=50 length_mm=80 section=round:4"
    )
    [b] = intent.bucklings
    assert b.part == "column"
    assert b.axial_n == 50.0
    assert b.length_mm == 80.0
    assert b.section == RoundSection(4.0)
    assert b.material == "PLA"
    assert b.end_condition == "fixed-free"


def test_parse_buckling_with_overrides():
    intent = parse_annotations(
        "// buckling: part=strut axial_n=100 length_mm=50 section=rect:5x5 "
        "material=PETG end_condition=fixed-fixed"
    )
    [b] = intent.bucklings
    assert b.material == "PETG"
    assert b.end_condition == "fixed-fixed"
    assert b.section == RectSection(5.0, 5.0)


def test_buckling_missing_keys_raises():
    with pytest.raises(ValueError, match="missing keys"):
        parse_annotations("// buckling: part=arm axial_n=10")


def test_parse_pressure_vessel():
    intent = parse_annotations(
        "// pressure: part=tank internal_pa=100000 wall_thickness_mm=2 radius_mm=50"
    )
    [p] = intent.pressures
    assert p.part == "tank"
    assert p.internal_pa == 100_000.0
    assert p.wall_thickness_mm == 2.0
    assert p.radius_mm == 50.0
    assert p.material == "PLA"


def test_pressure_with_material_override():
    intent = parse_annotations(
        "// pressure: part=tank internal_pa=200000 wall_thickness_mm=3 "
        "radius_mm=40 material=ABS"
    )
    [p] = intent.pressures
    assert p.material == "ABS"


def test_pressure_missing_keys_raises():
    with pytest.raises(ValueError, match="missing keys"):
        parse_annotations("// pressure: part=tank internal_pa=100")
