// Thin-walled pressurised cylindrical bottle, operating above PLA's glass
// transition.
//
// Demonstrates: pressure_vessel_hoop WARN (stress between safety threshold
// and yield) and operating_temperature BLOCK (PLA at 70 °C is past Tg and
// loses structural strength entirely). A real water bottle made out of PLA
// at this size, this pressure, and this temperature would not survive —
// the warnings catch it before it ships.
//
// part: bottle
// gravity: -z
// operating: temp_c=70
// pressure: part=bottle internal_pa=600000 wall_thickness_mm=1 radius_mm=50 material=PLA

inner_radius   = 50;
wall_thickness = 1;
height         = 100;

module bottle() {
    difference() {
        cylinder(h=height, r=inner_radius + wall_thickness, $fn=128);
        // Inner cavity stops short of the top and bottom faces so the
        // bottle is actually sealed (the mesh is watertight).
        translate([0, 0, wall_thickness])
            cylinder(h=height - 2 * wall_thickness, r=inner_radius, $fn=128);
    }
}

module assembly() {
    bottle();
}

assembly();
