# Study 03 — Mesh integrity and collision detection

**Disciplines:** Computer graphics / video games / geometry processing
**Why we care:** Two cheap, deterministic, 100%-solvable problems live here. (1) **Mesh integrity** (non-manifold edges, holes, normal flips) is a one-time check at import — slicers reject invalid meshes outright. (2) **Collision detection** is decades old, has well-known broad/narrow-phase architecture, and gives us off-the-shelf algorithms (GJK, SAT, BVH) for the geometry kernel. Neither belongs anywhere near the LLM.

## Sources distilled

- **Non-manifold meshes — MeshLib** ([article](https://meshlib.io/blog/non-manifold-meshes/))
- **3D collision detection — MDN** ([article](https://developer.mozilla.org/en-US/docs/Games/Techniques/3D_collision_detection))
- **Collision detection — Wikipedia** ([article](https://en.wikipedia.org/wiki/Collision_detection))

## Concepts to internalize

### Mesh defects (MeshLib)

The manifold rule: **each edge borders exactly two faces** (or one on an intentional opening), and **faces around a vertex form one continuous fan**. Defects:

| Defect | Definition | Why it breaks downstream |
|---|---|---|
| **Non-manifold edge** | Shared by more than two faces. | "Extra-shared edges break the half-edge data structure. A union/difference often returns an empty or self-intersecting body." Slicers (Cura, PrusaSlicer) **reject** with "Error. Non manifold edges." |
| **Non-manifold vertex** | Faces around it split into multiple disjoint fans. | "Difficult to define a clear surface direction" — breaks normal calculation. |
| **Self-intersection** | Faces cross instead of meeting at edges/vertices. | Slicer cannot decide inside vs. outside. |
| **Inconsistent normals** (winding) | Some faces wound CW, some CCW. | "Confuses rendering and mesh tools." Slicer guesses wrong, prints inverted shells. |
| **Surface discontinuity** | Unintended gaps. | Mesh is not watertight; slicer can't extract a closed volume. |

### MeshLib's auto-repair tactics (and the trade-off)

- **Non-manifold edge:** delete the offending triangles.
- **Non-manifold vertex:** duplicate the vertex so each face gets its own copy, restoring local manifoldness.

The library is explicit about the cost: **"this process can remove or alter parts of the geometry you expected to keep."** Auto-repair is not free — it can silently shrink walls or punch holes. **Repair is acceptable for noise but must be flagged loudly when it changes load-bearing geometry.**

### Why FEA cares too

"Non-manifold junctions create singularities that stall stiffness-matrix assembly, so the solver diverges or exits with a non-positive-definite error." If our `validators/structural.py` ever calls into a real FEA tool (CalculiX, Code_Aster), mesh integrity must be enforced before that call.

### Collision detection: broad-phase / narrow-phase

The defining architectural pattern in this field. **Always two stages:**

- **Broad phase** — "answers whether objects might collide, using a conservative but efficient approach to rule out pairs that clearly do not intersect." Uses bounding volumes only.
- **Narrow phase** — runs more precise (and more expensive) algorithms on the survivors.

#### Broad-phase tools

| Tool | Definition | Trade-off |
|---|---|---|
| **AABB** (axis-aligned bounding box) | Non-rotated box wrapping the geometry. Overlap is a logical comparison only. | Quickest. Must be rebuilt when entity rotates. |
| **OBB** (oriented bounding box) | Rotates with the entity. | More accurate fit; intersection test is more expensive. |
| **Bounding sphere** | Sphere wrapping the geometry. | Rotation-invariant. Wraps non-spherical objects loosely → false positives. |
| **BVH** (bounding volume hierarchy) | Tree of nested bounding volumes; recursive culling. | The standard structure for scenes with many objects. |
| **Sweep-and-prune** | Sort AABB intervals along axes, detect overlap; updates are small frame-to-frame. | Excellent when objects move incrementally. |
| **Spatial hashing** | Bin space into cells; only test pairs sharing a cell. | Cheap; good for uniform distributions. |

#### Narrow-phase tools

- **GJK** (Gilbert–Johnson–Keerthi) — closest points on convex polyhedra. "Approaches constant time when applied repeatedly to pairs of stationary or slow-moving objects."
- **SAT** (Separating Axis Theorem) — for convex objects: "there exists a plane so that one object lies completely on one side." If you find that plane, no collision. Standard for convex hulls and OBBs.

### Discrete vs. continuous

- **Discrete (a posteriori):** advance the simulation, check for intersection. **Risks missing fast-moving collisions** (tunnelling).
- **Continuous (a priori):** compute the *instant of collision* before advancing. "Is highly trajectory dependent" and typically requires numerical root-finding.

For our skill, time doesn't matter — parts are static. We always do discrete intersection. **But** for the *workflow / assembly* check ("can this part swing into place without passing through that part?"), the LLM's verbal walkthrough is implicitly continuous. We should not pretend to compute that geometrically in v1; flag it instead.

### The honest limits of the field

Wikipedia is candid: deformable / soft-body / cloth collision is hard because "the volume hierarchy has to be adjusted as the shape deforms." Game engines simplify with primitive colliders, *not* the visible mesh. **Game "physics" is an approximation built from primitives, not real-world physics.** This is the crucial caveat — borrowing collision algorithms doesn't mean borrowing *physical realism*.

## What to borrow

1. **Mesh integrity is a tool call, period.** The skill must never ask the LLM "is this mesh manifold?" — it must call Trimesh / MeshLib and read the answer. Failure-mode taxonomy from MeshLib is the validator's output schema.
2. **Auto-repair is allowed, but loud.** When the validator silently fixes a non-manifold edge, it must surface it in the report ("removed 3 degenerate triangles near feature X"). MeshLib's own warning — that repair "can remove or alter parts of the geometry you expected to keep" — is exactly the user-facing message.
3. **Use broad / narrow phase even at our scale.** A printed object with 3–10 distinct part volumes is not many, but the architectural pattern still pays off:
   - Broad phase = AABB intersection on each pair of part bounding boxes. Filters most pairs in nanoseconds.
   - Narrow phase = boolean mesh intersection (Trimesh `boolean.intersection`) only on the survivors.
   - This makes the validator scale to assemblies of 50+ parts without re-architecting.
4. **Adopt the GJK / SAT vocabulary.** Trimesh / FCL (Flexible Collision Library) expose these primitives directly. The skill's documentation should use the standard terms so future contributors can map onto the broader field.
5. **Punt on continuous / motion collision in v1.** Assembly-feasibility checking ("does this part fit through that gap when rotated into place?") is genuinely hard, and the field acknowledges it. The skill flags it as an open question for the user, doesn't try to compute it.

## Concrete implications for our code

- `validators/mesh.py`:
  - `check_mesh_integrity(mesh) -> MeshReport` returning the MeshLib-style defect taxonomy: `non_manifold_edges`, `non_manifold_vertices`, `self_intersections`, `inconsistent_normals`, `holes` (non-watertight), and counts for each.
  - `repair_mesh(mesh, *, allow_destructive=True) -> (repaired_mesh, repair_log)` — log every alteration so the user can see what changed.
  - Implementation: Trimesh has `is_watertight`, `is_winding_consistent`, `fill_holes`, `fix_normals`. MeshLib (Python bindings) for the harder repairs.
- `validators/clash.py`:
  - Two-pass design: AABB pre-filter → mesh boolean. The pre-filter is `trimesh.bounds.bounding_box_overlap`. The boolean is `trimesh.boolean.intersection` with a non-zero-volume threshold (e.g. `min_volume_mm3 = 0.01`) to suppress numerical noise.
  - For *clearance* checks (soft clash): inflate one mesh by the clearance gap (offset surface) and re-run intersection. Trimesh doesn't have offset surfaces directly; CadQuery's `Workplane.faces().shell()` or PyMesh's `inflate` can.
- Slicer-step prerequisite: every STL produced by stage 2 (OpenSCAD generation) must pass `validators/mesh.py` before stage 4 (slicer) is invoked. Slicer rejection should be impossible at runtime.
- **Explicit non-goal in v1**: continuous-time motion / assembly collision. Document it in `validators/__init__.py` so we don't drift.

## Gaps these sources don't fill

- No discussion of *which* boolean library is robust enough for our workload. Trimesh delegates to `manifold3d` or `blender`; CadQuery uses OpenCascade. We will likely need a comparison study before locking in.
- No coverage of *signed-distance-field* methods, which are increasingly the right tool for soft-clash / clearance checks at scale (and are how slicers themselves do support generation). Worth a follow-up read.
- No coverage of mesh simplification / decimation, which we will need before any structural FEA call (FEA solvers want millions of tets, not millions of triangles, and FDM-print-meshes are typically over-tessellated).
