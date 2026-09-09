"""Build the Ember Pact demo dioramas as glTF binaries.

Voxel art, generated rather than modelled: a grid of coloured cubes turned into
one mesh per palette colour, with the faces nobody can see left out. Hidden-face
culling is what makes this practical — a solid 40x40x40 block is 64,000 cubes
and 384,000 faces, of which about 9,600 are on the outside.

Run from the repo root:

    conda run -n visualizer python docker/make_voxel_dioramas.py

Writes into ``docker/voxel/ember-pact/``. Nothing here is imported by the app;
Akasha only ever *reads* a .glb, and this is the tool that makes the demo ones.
"""

from __future__ import annotations

import json
import math
import random
import struct
from dataclasses import dataclass, field
from pathlib import Path

OUT = Path(__file__).resolve().parent / "voxel" / "ember-pact"

# The crag's flat top, and its radius: everything in the detailed scene is
# built from these, which is what stops the castle floating above the rock.
PLATEAU = 20
PLATEAU_R = 9

# Face definitions: normal, the four corners in winding order, and the
# neighbour offset that decides whether the face is hidden.
_FACES = (
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)), (0, 0, 1)),
    ((0, 0, -1), ((1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)), (0, 0, -1)),
    ((1, 0, 0), ((1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)), (1, 0, 0)),
    ((-1, 0, 0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)), (-1, 0, 0)),
    ((0, 1, 0), ((0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)), (0, 1, 0)),
    ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)), (0, -1, 0)),
)


@dataclass
class Material:
    name: str
    colour: tuple[float, float, float]
    metallic: float = 0.0
    roughness: float = 0.85
    emissive: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class Grid:
    """A sparse voxel grid: (x, y, z) -> material name."""

    cells: dict[tuple[int, int, int], str] = field(default_factory=dict)

    def set(self, x, y, z, material):
        self.cells[(int(x), int(y), int(z))] = material

    def box(self, x0, y0, z0, x1, y1, z1, material):
        for x in range(int(x0), int(x1) + 1):
            for y in range(int(y0), int(y1) + 1):
                for z in range(int(z0), int(z1) + 1):
                    self.set(x, y, z, material)

    def shell(self, x0, y0, z0, x1, y1, z1, material):
        """A hollow box -- walls, not a solid block."""
        for x in range(int(x0), int(x1) + 1):
            for y in range(int(y0), int(y1) + 1):
                for z in range(int(z0), int(z1) + 1):
                    on_edge = x in (x0, x1) or z in (z0, z1) or y in (y0, y1)
                    if on_edge:
                        self.set(x, y, z, material)

    def carve(self, x0, y0, z0, x1, y1, z1):
        for x in range(int(x0), int(x1) + 1):
            for y in range(int(y0), int(y1) + 1):
                for z in range(int(z0), int(z1) + 1):
                    self.cells.pop((x, y, z), None)


def _surface(grid: Grid):
    """Group visible faces by material. This is the whole optimisation."""
    by_material: dict[str, list] = {}
    considered = culled = 0
    for (x, y, z), material in grid.cells.items():
        for normal, corners, offset in _FACES:
            considered += 1
            neighbour = (x + offset[0], y + offset[1], z + offset[2])
            if neighbour in grid.cells:
                culled += 1
                continue
            quad = [(x + cx, y + cy, z + cz) for cx, cy, cz in corners]
            by_material.setdefault(material, []).append((quad, normal))
    return by_material, considered, culled


def _pack_mesh(quads):
    positions, normals, indices = bytearray(), bytearray(), bytearray()
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    count = 0
    for quad, normal in quads:
        base = count
        for corner in quad:
            positions += struct.pack("<3f", *corner)
            normals += struct.pack("<3f", *normal)
            for axis in range(3):
                lo[axis] = min(lo[axis], corner[axis])
                hi[axis] = max(hi[axis], corner[axis])
            count += 1
        for offset in (0, 1, 2, 0, 2, 3):
            indices += struct.pack("<I", base + offset)
    return bytes(positions), bytes(normals), bytes(indices), lo, hi, count


def write_glb(path: Path, grid: Grid, materials: dict[str, Material]) -> dict:
    surface, considered, culled = _surface(grid)

    binary = bytearray()
    accessors, views, primitives, used = [], [], [], []

    def add_view(payload: bytes, target: int | None = None) -> int:
        while len(binary) % 4:
            binary.append(0)
        view = {"buffer": 0, "byteOffset": len(binary), "byteLength": len(payload)}
        if target is not None:
            view["target"] = target
        binary.extend(payload)
        views.append(view)
        return len(views) - 1

    for name in sorted(surface):
        positions, normals, indices, lo, hi, count = _pack_mesh(surface[name])
        pos_view = add_view(positions, 34962)
        nrm_view = add_view(normals, 34962)
        idx_view = add_view(indices, 34963)
        accessors.append({"bufferView": pos_view, "componentType": 5126,
                          "count": count, "type": "VEC3", "min": lo, "max": hi})
        accessors.append({"bufferView": nrm_view, "componentType": 5126,
                          "count": count, "type": "VEC3"})
        accessors.append({"bufferView": idx_view, "componentType": 5125,
                          "count": len(indices) // 4, "type": "SCALAR"})
        primitives.append({
            "attributes": {"POSITION": len(accessors) - 3, "NORMAL": len(accessors) - 2},
            "indices": len(accessors) - 1,
            "material": len(used),
        })
        used.append(materials[name])

    while len(binary) % 4:
        binary.append(0)

    document = {
        "asset": {"version": "2.0", "generator": "akasha voxel demo builder"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": path.stem}],
        "meshes": [{"name": path.stem, "primitives": primitives}],
        "materials": [
            {
                "name": material.name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [*material.colour, 1.0],
                    "metallicFactor": material.metallic,
                    "roughnessFactor": material.roughness,
                },
                "emissiveFactor": list(material.emissive),
            }
            for material in used
        ],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }

    raw = json.dumps(document, separators=(",", ":")).encode()
    raw += b" " * (-len(raw) % 4)
    body = struct.pack("<II", len(raw), 0x4E4F534A) + raw
    body += struct.pack("<II", len(binary), 0x004E4942) + bytes(binary)
    glb = struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(glb)

    return {
        "path": path,
        "bytes": len(glb),
        "voxels": len(grid.cells),
        "faces": considered - culled,
        "culled": f"{100 * culled / considered:.1f}%",
        "primitives": len(primitives),
        "vertices": sum(a["count"] for a in accessors[::3]),
    }


# -- the two dioramas --------------------------------------------------------


def basic_highkeep() -> tuple[Grid, dict[str, Material]]:
    """The plain one: a square tower on a plinth. Four colours, no tricks."""
    materials = {
        "rock": Material("rock", (0.36, 0.36, 0.40)),
        "stone": Material("stone", (0.55, 0.54, 0.52)),
        "roof": Material("roof", (0.42, 0.16, 0.15), roughness=0.7),
        "window": Material("window", (1.0, 0.78, 0.36),
                           emissive=(0.9, 0.6, 0.18), roughness=0.4),
    }
    grid = Grid()
    grid.box(-7, 0, -7, 7, 1, 7, "rock")          # plinth
    grid.shell(-4, 2, -4, 4, 14, 4, "stone")      # tower walls
    grid.box(-5, 15, -5, 5, 16, 5, "stone")       # parapet
    for x in range(-5, 6, 2):                      # crenellations
        grid.set(x, 17, -5, "stone")
        grid.set(x, 17, 5, "stone")
    for z in range(-5, 6, 2):
        grid.set(-5, 17, z, "stone")
        grid.set(5, 17, z, "stone")
    for y in (5, 9, 13):                           # lit windows
        grid.set(0, y, -4, "window")
        grid.set(0, y, 4, "window")
        grid.set(-4, y, 0, "window")
        grid.set(4, y, 0, "window")
    grid.box(-1, 2, -5, 1, 5, -5, "roof")          # door
    return grid, materials


def detailed_highkeep() -> tuple[Grid, dict[str, Material]]:
    """The good one: a keep on a crag, inside a curtain wall, with a
    switchback road, a snow cap and a lit beacon."""
    rng = random.Random(1387)
    materials = {
        "crag": Material("crag", (0.27, 0.28, 0.32)),
        "crag-lit": Material("crag-lit", (0.37, 0.38, 0.42)),
        "snow": Material("snow", (0.88, 0.91, 0.96), roughness=0.55),
        "stone": Material("stone", (0.58, 0.57, 0.54)),
        "stone-dark": Material("stone-dark", (0.45, 0.44, 0.43)),
        "roof": Material("roof", (0.38, 0.14, 0.13), roughness=0.65),
        "roof-dark": Material("roof-dark", (0.28, 0.10, 0.10), roughness=0.65),
        "timber": Material("timber", (0.33, 0.22, 0.15)),
        "road": Material("road", (0.52, 0.47, 0.39)),
        "window": Material("window", (1.0, 0.80, 0.40),
                           emissive=(1.0, 0.62, 0.2), roughness=0.35),
        "beacon": Material("beacon", (1.0, 0.58, 0.16),
                           emissive=(1.0, 0.48, 0.10), roughness=0.3),
        "banner": Material("banner", (0.62, 0.14, 0.16), roughness=0.75),
    }
    grid = Grid()

    # -- the crag: steep, solid, and flat where the keep goes ----------------
    #
    # Ridges come from a couple of low-frequency terms in the angle rather than
    # per-cell noise. Random jitter at voxel scale reads as scattered rubble --
    # every cell decides for itself and nothing lines up. Modulating the radius
    # by cos(3θ) and cos(5θ) instead gives buttresses and gullies that run all
    # the way down the face, which is what a rock mass actually looks like.
    base_r = 14.0
    for y in range(PLATEAU + 1):
        t = y / PLATEAU
        radius = base_r + (PLATEAU_R - base_r) * (t ** 0.85)
        for x in range(-18, 19):
            for z in range(-18, 19):
                edge = math.hypot(x, z)
                if edge > radius + 3:
                    continue
                angle = math.atan2(z, x)
                ridge = (math.cos(angle * 3) * 1.5
                         + math.cos(angle * 5 + 1.2) * 0.9
                         + math.cos(angle * 2 - 0.6) * 0.7)
                # The ridges fade out near the top so the plateau stays a
                # dependable place to build on.
                if edge <= radius + ridge * (1 - t) ** 0.6:
                    grid.set(x, y, z, "crag")

    # Snow on the exposed upper flanks; the sunward face a shade lighter.
    snowline = PLATEAU * 0.62
    for (x, y, z) in list(grid.cells):
        if (x, y + 1, z) in grid.cells:
            continue
        # A soft edge rather than a speckle: snow thickens with height
        # instead of each cell tossing a coin, which reads as drifts.
        depth = (y - snowline) / max(PLATEAU - snowline, 1)
        if depth > 0 and depth + rng.uniform(-0.18, 0.18) > 0.08:
            grid.set(x, y, z, "snow")
        elif x + z > 3:
            grid.set(x, y, z, "crag-lit")

    # -- the road: a switchback cut into the flank, ending at the gate -------
    for step in range(110):
        t = step / 109
        y = round(1 + t * (PLATEAU - 1))
        angle = math.pi * (0.5 + t * 3.2)
        radius = base_r - 0.5 + (PLATEAU_R - base_r) * (t ** 0.85)
        x = round(math.cos(angle) * radius)
        z = round(math.sin(angle) * radius)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if (x + dx, y, z + dz) in grid.cells:
                    grid.set(x + dx, y, z + dz, "road")

    top = PLATEAU + 1

    # -- curtain wall: an actual wall, one thick, with a walk on top ---------
    wall = 7
    for x in range(-wall, wall + 1):
        for z in range(-wall, wall + 1):
            if abs(x) != wall and abs(z) != wall:
                continue
            for y in range(top, top + 4):
                grid.set(x, y, z, "stone-dark")
    for x in range(-wall, wall + 1, 2):
        grid.set(x, top + 4, -wall, "stone-dark")
        grid.set(x, top + 4, wall, "stone-dark")
    for z in range(-wall, wall + 1, 2):
        grid.set(-wall, top + 4, z, "stone-dark")
        grid.set(wall, top + 4, z, "stone-dark")

    # Corner towers: taller than the wall, with small caps rather than the
    # oversized roofs that swallowed the first version's silhouette.
    for cx in (-wall, wall):
        for cz in (-wall, wall):
            grid.box(cx - 1, top, cz - 1, cx + 1, top + 6, cz + 1, "stone")
            grid.box(cx - 1, top + 7, cz - 1, cx + 1, top + 7, cz + 1, "roof-dark")
            grid.set(cx, top + 8, cz, "roof-dark")

    # -- gatehouse, where the road arrives -----------------------------------
    grid.box(-2, top, wall - 1, 2, top + 5, wall + 1, "stone")
    grid.carve(-1, top, wall - 1, 1, top + 2, wall + 1)
    grid.box(-3, top + 6, wall - 1, 3, top + 6, wall + 1, "roof")
    grid.set(0, top + 4, wall + 1, "window")
    for x in (-2, 2):
        grid.set(x, top + 3, wall + 1, "timber")

    # -- the bailey: a hall, a store and a well, so the yard is not hollow ----
    grid.box(-6, top, -6, -3, top + 3, -2, "stone-dark")     # long hall
    grid.box(-7, top + 4, -7, -2, top + 4, -1, "roof")
    grid.box(-6, top + 5, -6, -3, top + 5, -2, "roof")
    grid.set(-4, top + 2, -2, "window")
    grid.set(-5, top + 2, -2, "window")

    grid.box(4, top, -6, 6, top + 2, -3, "timber")           # store shed
    grid.box(3, top + 3, -7, 7, top + 3, -2, "roof-dark")

    for x in (-1, 0):                                         # well
        for z in (5, 6):
            grid.set(x, top, z, "stone-dark")
    grid.set(-1, top + 1, 5, "timber")
    grid.set(0, top + 1, 6, "timber")
    grid.box(-1, top + 2, 5, 0, top + 2, 6, "roof-dark")

    # -- the keep ------------------------------------------------------------
    keep_lo, keep_hi = -4, 3
    keep_top = top + 17
    for x in range(keep_lo, keep_hi + 1):
        for z in range(keep_lo, keep_hi + 1):
            edge = x in (keep_lo, keep_hi) or z in (keep_lo, keep_hi)
            for y in range(top, keep_top):
                if edge:
                    grid.set(x, y, z, "stone")
    grid.box(keep_lo - 1, keep_top, keep_lo - 1, keep_hi + 1, keep_top + 1,
             keep_hi + 1, "stone")
    for x in range(keep_lo - 1, keep_hi + 2, 2):
        grid.set(x, keep_top + 2, keep_lo - 1, "stone")
        grid.set(x, keep_top + 2, keep_hi + 1, "stone")
    for z in range(keep_lo - 1, keep_hi + 2, 2):
        grid.set(keep_lo - 1, keep_top + 2, z, "stone")
        grid.set(keep_hi + 1, keep_top + 2, z, "stone")

    # Stair turret, carried higher than the keep so the outline has a step.
    grid.box(keep_hi, top, keep_hi + 1, keep_hi + 2, keep_top + 6,
             keep_hi + 3, "stone-dark")
    grid.box(keep_hi - 1, keep_top + 7, keep_hi, keep_hi + 3, keep_top + 7,
             keep_hi + 4, "roof")
    grid.box(keep_hi, keep_top + 8, keep_hi + 1, keep_hi + 2, keep_top + 8,
             keep_hi + 3, "roof")
    grid.set(keep_hi + 1, keep_top + 9, keep_hi + 2, "roof-dark")

    # Windows: a column up each face, and the great hall picked out wider.
    for y in range(top + 3, keep_top - 1, 3):
        grid.set(keep_lo, y, 0, "window")
        grid.set(keep_hi, y, -1, "window")
        grid.set(0, y, keep_lo, "window")
        grid.set(-1, y, keep_hi, "window")
    for x in range(-2, 2):
        grid.set(x, top + 3, keep_lo, "window")

    # -- beacon and banner ---------------------------------------------------
    grid.box(-1, keep_top + 2, -1, 0, keep_top + 2, 0, "stone")
    grid.box(-1, keep_top + 3, -1, 0, keep_top + 4, 0, "beacon")
    for y in range(keep_top + 4, keep_top + 8):
        grid.set(keep_hi + 4, y, keep_hi + 2, "timber")
    grid.box(keep_hi + 5, keep_top + 5, keep_hi + 2,
             keep_hi + 6, keep_top + 7, keep_hi + 2, "banner")

    # A few lit windows in the corner towers, so the bailey reads as occupied.
    for cx in (-wall, wall):
        for cz in (-wall, wall):
            grid.set(cx, top + 4, cz + (1 if cz < 0 else -1), "window")

    return grid, materials


def main() -> None:
    for name, build, note in (
        ("highkeep-basic", basic_highkeep, "a square tower on a plinth"),
        ("highkeep", detailed_highkeep, "the keep, its wall and the road up"),
    ):
        grid, materials = build()
        stats = write_glb(OUT / f"{name}.glb", grid, materials)
        print(
            f"{name + '.glb':<22} {stats['bytes']:>9,} B  "
            f"{stats['voxels']:>6,} voxels  {stats['faces']:>7,} faces "
            f"({stats['culled']} culled)  {stats['primitives']} materials  "
            f"{stats['vertices']:,} vertices  -- {note}"
        )


if __name__ == "__main__":
    main()
