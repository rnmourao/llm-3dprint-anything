// End-to-end smoke-test design: a vertical peg passes up through a flat
// socket plate, with a controlled clearance fit. Both parts are grounded
// (z=0); the peg sticks out the top of the socket.
//
// CONVENTION (skill orchestrator): each `// part:` module must be defined
// AT ITS FINAL ASSEMBLY POSITION. The `assembly()` module is the canonical
// what-we-print, formed by union of the part calls. Every part should
// touch the bed plane in the as-printed orientation, or `check_grounded`
// will flag it.
//
// part: peg
// part: socket
// fit: peg~socket class=LC
// gravity: -z

// LC (locational clearance) per study 02 ⇒ 0.20–0.30 mm radial gap.
// Use 0.25 mm radial → 0.50 mm diametral.
peg_diameter = 6;
peg_height = 14;
hole_diameter = peg_diameter + 0.50;
plate_size = 30;
plate_thickness = 6;

module peg() {
    // Peg stands on the bed at the origin, axis +z.
    cylinder(h=peg_height, d=peg_diameter, $fn=64);
}

module socket() {
    // Plate sits flat on the bed. Hole concentric with the peg; the peg
    // passes up through the hole and projects (peg_height - plate_thickness)
    // mm above the plate.
    difference() {
        translate([-plate_size / 2, -plate_size / 2, 0])
            cube([plate_size, plate_size, plate_thickness]);
        translate([0, 0, -0.1])
            cylinder(h=plate_thickness + 0.2, d=hole_diameter, $fn=64);
    }
}

module assembly() {
    peg();
    socket();
}

assembly();
