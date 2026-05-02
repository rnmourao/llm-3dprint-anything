// Slender vertical post under axial compression. A long thin cylinder will
// buckle long before it yields in pure compression — this is the failure
// mode that the yield-stress check (`check_cantilever`) cannot see.
//
// Demonstrates: column_buckling BLOCK with margin << 1. The same geometry
// at the same load passes a back-of-envelope yield check (compressive
// stress = F/A ≈ 4 MPa, well below PLA yield 50 MPa); only Euler's
// formula catches the actual failure mode.
//
// part: post
// gravity: -z
// buckling: part=post axial_n=50 length_mm=200 section=round:4 material=PLA end_condition=fixed-free

post_diameter = 4;
post_height   = 200;

module post() {
    cylinder(h=post_height, d=post_diameter, $fn=64);
}

module assembly() {
    post();
}

assembly();
