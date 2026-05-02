// Wall-mount bracket. Vertical plate fixes to a wall (modeled as the bed
// for printing); horizontal arm extends forward to support a tip load.
//
// Demonstrates: cantilever_stress (point load) + static_stability (COM
// outside support polygon when the arm is loaded). Also illustrates how
// `// load:` works with a real cross-section.
//
// part: bracket
// gravity: -z
// load: part=bracket force=30 axis=-z length_mm=60 section=rect:4x4 material=PLA

plate_w = 30;
plate_d = 4;
plate_h = 30;
arm_w  = 4;
arm_l  = 60;
arm_h  = 4;

module bracket() {
    // Vertical plate (the "wall" is the y=0 plane, here the bed).
    translate([-plate_w / 2, 0, 0])
        cube([plate_w, plate_d, plate_h]);
    // Horizontal arm extending in +y, attached at the top of the plate.
    translate([-arm_w / 2, plate_d, plate_h - arm_h])
        cube([arm_w, arm_l, arm_h]);
}

module assembly() {
    bracket();
}

assembly();
