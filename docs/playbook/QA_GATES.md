# QA gates + cost ledger + promote-to-hero (U7)

Silhouette overlay and BOM completeness run on **MWT1 renders when available**, and are **fully mockable offline** (Pillow masks / fixture stills). Cost ledger marks every local stage **$0**; cloud rows use API `consumed`. Seedance is **post-QA presentation only**.

## CLI

```bash
# Score silhouette + BOM; write manifests/qa_gate_report.json + cost_ledger.json + qa_misses.json
python -m composite3dgen qa path/to/job --bom-tier L2

# Offline / CI: skip stills discovery; BOM-only
python -m composite3dgen qa path/to/job --skip-silhouette

# Print promote-to-hero policy
python -m composite3dgen qa /dev/null --policy

# Authorize cloud only after QA miss reasons exist
python -m composite3dgen --spend run path/to/job --qa-miss silhouette --stage tripo
# Or: run `qa` first, then `run --spend` loads manifests/qa_misses.json automatically
```

## Silhouette overlay

| Input | Location |
|-------|----------|
| Reference | `verification/reference-silhouette-<axis>.png` (or `frames/silhouette-<axis>.png`) |
| Candidate | `out/blender/verification/*-silhouette-<axis>.png` (Blender/MWT1 QA stills) |

Scores **IoU** and **coverage** (intersection / reference foreground). Defaults: IoU ≥ 0.55, coverage ≥ 0.70. Failing coverage **fails the gate** and emits `QAMiss(kind="silhouette")`.

## BOM completeness (L1 / L2 / leaf)

| Tier | Gate |
|------|------|
| L1 | ≥1 L1 assembly; meshes assigned |
| L2 | L1 + L2 present; L1 without children fails; no unassigned scene meshes |
| Leaf | Claimed `tier=leaf` + leaf nodes; RC requires CAD/register (`--require-cad-for-leaf`) |

Anonymous / unassigned meshes fail. AI parts ≠ engineering BOM — leaf fitment still needs the CAD lane.

## Cost ledger

Written to `manifests/cost_ledger.json`:

- Local pipeline stages (`ingest`, `quality`, `composites`, `build_packs`, `triposr`, `photogrammetry`, `blender_explode`, `qa_silhouette`, `qa_bom`) always **`consumed=0.0`**.
- Cloud / presentation rows use adapter API `consumed` (dry-run stays 0).
- Provider runner also refreshes the ledger after `run`.

## `--spend` hard-block

Under default `prefer_local`:

1. **No `--spend`** → dry-run / local only.
2. **`--spend` without QA miss** → **hard error** (exit 2). Pass `--qa-miss KIND` or load `manifests/qa_misses.json` from a prior `qa` run.
3. **`--spend --no-prefer-local`** → operator override (still no secrets in git).

Router keeps a belt-and-suspenders demotion to dry-run + `block_reason` if live somehow slips through.

## Promote-to-hero policy

| QA miss | Promote path |
|---------|----------------|
| `angle_coverage` | Photogrammetry (local) → Tripo multiview → Hi3D |
| `part_fidelity` | Tripo `generate_parts` / Rodin BANG |
| `hard_surface` | Rodin Gen-2.5 Extreme-High / Hi3D master |
| `texture` | Hi3D hero / Tripo texture-on-parts |
| `silhouette` | Tripo / Hi3D / Rodin Gen-2.5 |
| `bom_completeness` | Tripo / Rodin BANG / CAD leaf fitment |
| QA **pass** | Stop climbing; optional Seedance presentation |

### Seedance (presentation only)

- **Never** a geometry source.
- Allowed only after **QA pass**.
- Live still needs `--spend`; in-repo client records authorization only (no surprise paid HTTP in tests).

## Related

- [WORKFLOW.md](WORKFLOW.md) — stage table + gates
- [COST_QUALITY_MATRIX.md](COST_QUALITY_MATRIX.md) — routing ladder
- [BOM_SCHEMA.md](BOM_SCHEMA.md) — L1/L2/leaf schema
