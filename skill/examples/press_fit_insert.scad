// A printed boss with a hole sized for an interference (press-fit) insert.
// The insert is sized 0.30 mm larger in diameter than the hole — 0.15 mm
// radial interference, mid-band of the FN spec range (-0.20 .. -0.10 mm).
//
// Demonstrates: FN fit class within spec, plus the `clash_whitelist`
// annotation suppressing the hard-clash BLOCK that would otherwise fire
// on this geometry. (Without the whitelist this example would BLOCK on
// hard_clash:boss~insert by ~16 mm³.)
//
// part: boss
// part: insert
// fit: boss~insert class=FN
// clash_whitelist: boss~insert
// gravity: -z

boss_outer    = 12;
boss_inner    = 5.7;
boss_height   = 8;
insert_outer  = 6.0;
insert_height = 6;

module boss() {
    difference() {
        cylinder(h=boss_height, d=boss_outer, $fn=64);
        translate([0, 0, -0.1])
            cylinder(h=boss_height + 0.2, d=boss_inner, $fn=64);
    }
}

module insert() {
    cylinder(h=insert_height, d=insert_outer, $fn=64);
}

module assembly() {
    boss();
    insert();
}

assembly();
