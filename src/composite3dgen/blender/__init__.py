"""Blender explode / hierarchy / QA hub (U4) — scripts execute on MWT1.

Public surface:
- :mod:`composite3dgen.blender.schema` — ``parts.hierarchy`` load/validate
- :mod:`composite3dgen.blender.jobs` — MWT1 / dry-run job runner
- :mod:`composite3dgen.blender.paths` — Blender path resolution (no invented paths)
- ``scripts/explode_hub.py`` — headless bpy entry for Empty parents, explode
  GLB + ``parts.json``, orthographic / silhouette QA stills

Remesh / UV / bake stay local Blender ops (never cloud) and are not invoked
by the default explode job.
"""

from composite3dgen.blender.jobs import BlenderExplodeResult, run_blender_explode
from composite3dgen.blender.schema import (
    PartsHierarchy,
    PartsHierarchyError,
    build_l1_l2_example,
    load_parts_hierarchy,
    parse_parts_hierarchy,
    schema_path,
    validate_parts_hierarchy,
    write_parts_hierarchy,
)

__all__ = [
    "BlenderExplodeResult",
    "PartsHierarchy",
    "PartsHierarchyError",
    "build_l1_l2_example",
    "load_parts_hierarchy",
    "parse_parts_hierarchy",
    "run_blender_explode",
    "schema_path",
    "validate_parts_hierarchy",
    "write_parts_hierarchy",
]
