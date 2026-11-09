#!/usr/bin/env python3
"""Blender headless hub: Empty hierarchy, explode, GLB + parts.json, QA stills.

Designed for MWT1 (Apple M4 Metal; Blender explode/QA — not TripoSR CUDA).

Preferred binaries (probe-verified Blender 5.2.3 LTS)::

    /opt/homebrew/bin/blender --background --python explode_hub.py -- <args>
    # fallback:
    /Applications/Blender.app/Contents/MacOS/Blender --background --python ...

Remesh / UV / bake stay local Blender ops (never cloud) — optional flags only.
This script does not call any cloud APIs.

When imported outside Blender (unit tests), ``bpy`` is absent and helpers that
do not touch bpy remain usable; ``main()`` requires Blender.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

# bpy is only available inside Blender's Python.
try:
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore

    IN_BLENDER = True
except ImportError:  # pragma: no cover — normal outside Blender
    bpy = None  # type: ignore
    Vector = None  # type: ignore
    IN_BLENDER = False

SCHEMA_VERSION = "1.0.0"


def _argv_after_double_dash(argv: list[str] | None = None) -> list[str]:
    argv = list(argv if argv is not None else sys.argv)
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    # When run as ``blender --python script.py -- args``, Blender may leave
    # the script path in argv; strip known prefixes.
    if argv and argv[0].endswith("explode_hub.py"):
        return argv[1:]
    return argv


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Composite3DGen Blender explode / hierarchy / QA hub (MWT1).",
    )
    p.add_argument(
        "--input",
        required=True,
        help="Input mesh path (.glb / .gltf / .obj). Use '-' to keep current scene.",
    )
    p.add_argument(
        "--hierarchy",
        required=True,
        help="Input parts hierarchy JSON (schema parts.hierarchy).",
    )
    p.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for GLB, parts.json, and verification stills.",
    )
    p.add_argument(
        "--subject-id",
        default=None,
        help="Override subject_id written into parts.json.",
    )
    p.add_argument(
        "--explode-factor",
        type=float,
        default=None,
        help="Override explode.factor from hierarchy JSON.",
    )
    p.add_argument(
        "--tier-stills",
        default="L1,L2",
        help="Comma tiers for explode stills (default L1,L2).",
    )
    p.add_argument(
        "--skip-stills",
        action="store_true",
        help="Skip orthographic / silhouette renders.",
    )
    p.add_argument(
        "--resolution",
        type=int,
        default=1024,
        help="Still pixel size (square orthographic).",
    )
    p.add_argument(
        "--prefix",
        default="local",
        help="Verification filename prefix (local-* / live-*).",
    )
    return p


def load_hierarchy(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Hierarchy root must be an object: {path}")
    if "parts" not in data:
        raise SystemExit(f"Hierarchy missing 'parts': {path}")
    return data


def clear_scene() -> None:
    assert bpy is not None
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        bpy.data.materials.remove(block)


def import_mesh(path: Path) -> list[Any]:
    assert bpy is not None
    suffix = path.suffix.lower()
    before = set(bpy.data.objects)
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".obj":
        # Blender 3.x/4.x: wm.obj_import preferred when present.
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(path))
        else:
            bpy.ops.import_scene.obj(filepath=str(path))
    else:
        raise SystemExit(f"Unsupported input format: {path}")
    after = [obj for obj in bpy.data.objects if obj not in before]
    return after


def mesh_objects() -> list[Any]:
    assert bpy is not None
    return [o for o in bpy.data.objects if o.type == "MESH"]


def ensure_empty(name: str) -> Any:
    assert bpy is not None
    existing = bpy.data.objects.get(name)
    if existing is not None:
        return existing
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    bpy.context.scene.collection.objects.link(empty)
    return empty


def apply_hierarchy(hierarchy: dict[str, Any]) -> dict[str, Any]:
    """Create Empty parents and parent meshes by mesh_names / meshes map."""
    assert bpy is not None
    parts = hierarchy["parts"]
    empties: dict[str, Any] = {}

    # Create empties first (sorted so parents exist before children).
    level_order = {"L1": 0, "L2": 1, "leaf": 2}
    ordered = sorted(parts, key=lambda p: level_order.get(p.get("level", "L1"), 9))
    for part in ordered:
        pid = part["part_id"]
        empty = ensure_empty(pid)
        empties[pid] = empty

    for part in ordered:
        pid = part["part_id"]
        parent_id = part.get("parent_id")
        empty = empties[pid]
        if parent_id and parent_id in empties:
            empty.parent = empties[parent_id]
            empty.matrix_parent_inverse = empties[parent_id].matrix_world.inverted()

    # Mesh → part map
    binding: dict[str, str] = {}
    for part in parts:
        for name in part.get("mesh_names") or []:
            binding[name] = part["part_id"]
    for item in hierarchy.get("meshes") or []:
        binding[item["mesh_name"]] = item["part_id"]

    meshes = mesh_objects()
    used: set[str] = set()
    for obj in meshes:
        part_id = binding.get(obj.name)
        if part_id is None:
            # Fallback: prefix match part_id_
            for pid in empties:
                if obj.name == pid or obj.name.startswith(f"{pid}_"):
                    part_id = pid
                    break
        if part_id is None:
            continue
        empty = empties[part_id]
        obj.parent = empty
        obj.matrix_parent_inverse = empty.matrix_world.inverted()
        used.add(obj.name)
        # Keep mesh_names in sync for export
        for part in parts:
            if part["part_id"] == part_id:
                names = list(part.get("mesh_names") or [])
                if obj.name not in names:
                    names.append(obj.name)
                part["mesh_names"] = names

    # Record anonymous meshes under a synthetic dump note (not auto-L1).
    anonymous = [o.name for o in meshes if o.name not in used]
    if anonymous:
        hierarchy.setdefault("notes", "")
        note = f"Unassigned meshes (need BOM map): {', '.join(anonymous)}"
        existing = hierarchy.get("notes") or ""
        hierarchy["notes"] = f"{existing}; {note}" if existing else note

    hierarchy["meshes"] = [
        {"mesh_name": name, "part_id": pid} for name, pid in sorted(binding.items())
    ]
    return empties


def apply_explode(hierarchy: dict[str, Any], factor: float) -> None:
    assert bpy is not None
    mode = (hierarchy.get("explode") or {}).get("mode", "offset")
    if mode == "none" or factor == 0:
        return
    for part in hierarchy["parts"]:
        empty = bpy.data.objects.get(part["part_id"])
        if empty is None:
            continue
        offset = part.get("explode_offset") or [0.0, 0.0, 0.0]
        if mode == "radial":
            # Push along XY from origin using offset magnitude as radius hint.
            loc = empty.location
            direction = Vector((loc.x, loc.y, loc.z))
            if direction.length < 1e-6:
                direction = Vector((float(offset[0]), float(offset[1]), float(offset[2])))
            if direction.length < 1e-6:
                direction = Vector((1.0, 0.0, 0.0))
            direction.normalize()
            mag = math.sqrt(sum(float(c) ** 2 for c in offset)) or 1.0
            empty.location = empty.location + direction * (mag * factor)
        else:
            empty.location = empty.location + Vector(
                (float(offset[0]) * factor, float(offset[1]) * factor, float(offset[2]) * factor)
            )


def export_glb(path: Path) -> None:
    assert bpy is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=False,
        export_apply=False,
    )


def setup_ortho_camera(axis: str = "front", size: float = 2.5) -> Any:
    assert bpy is not None
    cam_data = bpy.data.cameras.new("QA_Ortho")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = size
    cam = bpy.data.objects.new("QA_Ortho", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    # Position for orthographic views (Y-up Blender: -Y forward often used for front).
    distance = size * 2.0
    if axis == "front":
        cam.location = (0.0, -distance, 0.0)
        cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    elif axis == "side":
        cam.location = (distance, 0.0, 0.0)
        cam.rotation_euler = (math.radians(90), 0.0, math.radians(90))
    elif axis == "top":
        cam.location = (0.0, 0.0, distance)
        cam.rotation_euler = (0.0, 0.0, 0.0)
    else:
        cam.location = (distance, -distance, distance * 0.6)
        cam.rotation_euler = (math.radians(60), 0.0, math.radians(45))
    return cam


def scene_bounds_scale() -> float:
    assert bpy is not None
    meshes = mesh_objects()
    if not meshes:
        return 2.5
    coords = []
    for obj in meshes:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            coords.append(world)
    if not coords:
        return 2.5
    xs = [v.x for v in coords]
    ys = [v.y for v in coords]
    zs = [v.z for v in coords]
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 0.1)
    return float(span * 1.4)


def render_still(path: Path, *, resolution: int, silhouette: bool = False) -> None:
    assert bpy is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"

    if silhouette:
        # Flat black silhouette on white — useful for U7 overlay scoring.
        scene.display.shading.light = "FLAT"
        scene.display.shading.color_type = "SINGLE"
        scene.display.shading.single_color = (0.0, 0.0, 0.0)
        scene.render.film_transparent = False
        # Workbench world / color management kept simple.
    else:
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"

    bpy.ops.render.render(write_still=True)


def render_qa_stills(
    out_dir: Path,
    *,
    tiers: list[str],
    prefix: str,
    resolution: int,
) -> list[str]:
    assert bpy is not None
    verification = out_dir / "verification"
    verification.mkdir(parents=True, exist_ok=True)
    scale = scene_bounds_scale()
    rels: list[str] = []

    # Clear prior QA cameras
    for obj in list(bpy.data.objects):
        if obj.type == "CAMERA" and obj.name.startswith("QA_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    for axis in ("front", "side", "top"):
        setup_ortho_camera(axis=axis, size=scale)
        for tier in tiers:
            name = f"{prefix}-exploded-{tier.lower()}-{axis}.png"
            path = verification / name
            render_still(path, resolution=resolution, silhouette=False)
            rels.append(f"verification/{name}")

        sil_name = f"{prefix}-silhouette-{axis}.png"
        sil_path = verification / sil_name
        render_still(sil_path, resolution=resolution, silhouette=True)
        rels.append(f"verification/{sil_name}")

    return rels


def write_parts_json(path: Path, hierarchy: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hierarchy, indent=2) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    if not IN_BLENDER:
        print("explode_hub: must run inside Blender (bpy missing)", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hierarchy = load_hierarchy(Path(args.hierarchy))
    if args.subject_id:
        hierarchy["subject_id"] = args.subject_id
    hierarchy["schema_version"] = hierarchy.get("schema_version") or SCHEMA_VERSION
    hierarchy["source"] = "blender"

    if args.input != "-":
        clear_scene()
        import_mesh(Path(args.input))

    apply_hierarchy(hierarchy)

    factor = args.explode_factor
    if factor is None:
        factor = float((hierarchy.get("explode") or {}).get("factor", 1.0))
    hierarchy.setdefault("explode", {})["factor"] = factor
    apply_explode(hierarchy, factor)

    glb_path = out_dir / "exploded.glb"
    export_glb(glb_path)

    stills: list[str] = []
    if not args.skip_stills:
        tiers = [t.strip() for t in args.tier_stills.split(",") if t.strip()]
        stills = render_qa_stills(
            out_dir,
            tiers=tiers,
            prefix=args.prefix,
            resolution=args.resolution,
        )

    hierarchy["artifacts"] = {
        "glb": "exploded.glb",
        "parts_json": "parts.json",
        "verification": stills,
    }
    parts_path = out_dir / "parts.json"
    write_parts_json(parts_path, hierarchy)

    print(json.dumps({"ok": True, "glb": str(glb_path), "parts": str(parts_path), "stills": stills}))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(_argv_after_double_dash(argv))
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
