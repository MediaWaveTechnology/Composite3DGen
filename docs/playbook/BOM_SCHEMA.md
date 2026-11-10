# BOM / hierarchy schema

Multi-level exploded hierarchies are a first-class output. AI “parts” are **not** an engineering BOM until Blender naming + QA (and for RC leaf fitment, the CAD lane) say so.

## Depth tiers

| Tier | Meaning | v1 ship target |
|------|---------|----------------|
| **L1** | Major assemblies (e.g. chassis, cabin, boom) | Yes |
| **L2** | Sub-assemblies under L1 | Yes |
| **Leaf** | Individual replaceable parts | Schema-ready; quality-gated |

GLM staging assembly JSON historically held L1/L2 mesh groups only. Leaf BOM is not claimed from AI alone.

## Canonical schema (U4)

| Artifact | Role |
|----------|------|
| `schema/parts.hierarchy.schema.json` | Canonical hierarchy + explode metadata (`schema_version` **1.0.0**) |
| `schema/subject.manifest.schema.json` | Subject / domain / units / capture refs (U2) |
| `schema/job.provider.schema.json` | Provider job records + cost fields (U3/U7) |
| `schema/dimension.register.schema.json` | RC dimension register + mate-chain (U6; confirmed vs inferred) |
| Job `out/blender/parts.json` | Instance export from Blender Empty parents |
| Job `out/blender/exploded.glb` | Mesh + Empty hierarchy for DCC / web viewers |
| Job `out/blender/verification/` | Orthographic + silhouette stills for QA |

### Document shape

Required top-level fields: `schema_version`, `subject_id`, `tier`, `parts`.

Each `parts[]` node:

| Field | Notes |
|-------|--------|
| `part_id` | Stable id (Empty object name stem in Blender) |
| `label` | Human name (separate from id) |
| `level` | `L1` \| `L2` \| `leaf` |
| `parent_id` | `null` for L1 roots; required for L2/leaf |
| `mesh_names` | Blender mesh object names owned by the Empty |
| `explode_offset` | XYZ local explode translation (scaled by `explode.factor`) |

Optional `meshes[]` repeats the mesh→BOM map explicitly. `tier` must match the deepest `level` present (claim leaf only when leaf nodes exist **and** QA/CAD allow it).

Semantic checks (beyond JSON Schema) live in `composite3dgen.blender.schema`: unique `part_id`, parent existence, L1/L2/leaf parent rules, mesh `part_id` references.

Do not invent fake production JSON that pretends leaf completeness.

## Blender convention (U4)

- Prefer **Empty parents** (or Full Collection Hierarchy export) so GLB round-trips parent links.
- Collections alone do **not** reliably round-trip in GLB — do not rely on them as the sole hierarchy carrier.
- Hub script: `src/composite3dgen/blender/scripts/explode_hub.py` — headless on MWT1 via `composite3dgen explode`.
- Explode offsets recorded per node for L1/L2 stills (`*-exploded-l1-*.png` / `*-exploded-l2-*.png`).
- Orthographic / silhouette stills written under `out/blender/verification/` next to the job for later U7 scoring.
- **Remesh / UV / bake** stay local Blender ops on MWT1 — never cloud; not part of the default explode CLI path.

## CLI

```bash
# Dry-run (no Blender): schema-valid parts.json + planned verification markers
python -m composite3dgen explode path/to/job --executor local

# Happy path when MWT1 Blender stage probes pass (LAN / mwt1 worker):
python -m composite3dgen explode path/to/job --mesh draft.glb --hierarchy parts.in.json
```

MWT1 prefers probe-verified `/opt/homebrew/bin/blender` (then App bundle). Without SSH transport the runner dry-runs schema-valid `parts.json` — it does not invent mesh bytes. Apple M4 Metal is fine for explode/QA; TripoSR CUDA is unrelated.

## Naming

- Stable IDs in schema (`part_id`); human labels separate.
- Domain profiles (GLM vs RC) may add mate-chain / dimension-register fields without forking the core pipeline.
- Verification naming: `local-*` / `live-*` / `*-exploded-l1-*.png` (and L2 equivalents); silhouettes `*-silhouette-*.png`.

## QA expectations (U7)

- L1/L2 completeness: every mesh assigned under the hierarchy; no anonymous dump roots.
- Leaf claims require explicit tier flag + (for RC) dimension-register evidence (`--require-cad-for-leaf`).
- Cost ledger marks Blender/local stages `$0` (`manifests/cost_ledger.json`).
- CLI: `composite3dgen qa` — see [QA_GATES.md](QA_GATES.md).

## RC dimension register (U6)

- Template + fixture: `fixtures/rc-dex410/dimension-register.json`
- CadQuery: `composite3dgen cad` (prefer MWT1; missing binary → structured `next_steps`)
- Fusion GUI handoff: [FUSION_HANDOFF.md](FUSION_HANDOFF.md) — **not** 3ds Max (later phase)
- Leaf fitment requires ≥1 **confirmed** dimension; inferred-only registers fail validation

## Related

- [WORKFLOW.md](WORKFLOW.md) — BOM depth gate
- [QA_GATES.md](QA_GATES.md) — silhouette + BOM gates + ledger
- [COST_QUALITY_MATRIX.md](COST_QUALITY_MATRIX.md) — when to promote providers vs CAD
- [FUSION_HANDOFF.md](FUSION_HANDOFF.md) — Fusion workstation path
- `deploy/mwt1/README.md` — verified Blender Homebrew / App paths
- `deploy/mwt1/photogrammetry.md` — COLMAP / Meshroom install
