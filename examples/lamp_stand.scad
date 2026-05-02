// Top-heavy lamp stand: small base, tall thin column, heavy lamp head
// offset to one side so the assembly's COM sits outside the base footprint.
//
// Demonstrates: stability_com_over_support WARN + physics_settles WARN. The
// COM-vs-support-polygon check fires deterministically; the MuJoCo sim
// confirms the design tips in motion as well.
//
// part: stand
// gravity: -z

base_w   = 20;
base_h   = 3;
column_w = 4;
column_h = 80;
head_w   = 30;
head_h   = 30;

module stand() {
    // Base
    translate([-base_w / 2, -base_w / 2, 0])
        cube([base_w, base_w, base_h]);
    // Column on the centre of the base
    translate([-column_w / 2, -column_w / 2, base_h])
        cube([column_w, column_w, column_h]);
    // Heavy head — offset in +x so the COM hangs outside the 20×20 base.
    translate([0, -head_w / 2, base_h + column_h])
        cube([head_w, head_w, head_h]);
}

module assembly() {
    stand();
}

assembly();
