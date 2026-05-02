
// part: peg
// part: socket
// fit: peg~socket class=LC
// gravity: -z

peg_diameter = 6;
peg_height = 14;
hole_diameter = peg_diameter + 0.50;
plate_size = 30;
plate_thickness = 6;

module peg() {
    cylinder(h=peg_height, d=peg_diameter, $fn=64);
}
module socket() {
    z_floor = peg_height - plate_thickness;
    translate([0, 0, z_floor])
        difference() {
            translate([-plate_size / 2, -plate_size / 2, 0])
                cube([plate_size, plate_size, plate_thickness]);
            translate([0, 0, -0.1])
                cylinder(h=plate_thickness + 0.2, d=hole_diameter, $fn=64);
        }
}
module assembly() { peg(); socket(); }
assembly();
