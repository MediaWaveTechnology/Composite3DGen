# Fusion handoff (licensed workstation)

RC leaf fitment uses **CadQuery (prefer MWT1)** for parametric solids, then **Autodesk Fusion** on a workstation that already has a Fusion license for interactive mates / drawings.

**v1 Autodesk GUI is Fusion-only.** Optional **3ds Max** export/edit is a **later phase** after this Fusion path exists — not part of U6. Blender on MWT1 remains the explode / hierarchy hub.

## What leaves MWT1 / the job dir

| Artifact | Typical path | Fusion use |
|----------|--------------|------------|
| Dimension register | `cad/dimension-register.json` or fixture `fixtures/rc-dex410/dimension-register.json` | Human checklist for confirmed vs inferred; drive parameters |
| CadQuery STEP | `out/cadquery/fitment_envelope.step` (or scripted part STEP) | **File → Open / Insert** into Fusion design |
| CadQuery STL | `out/cadquery/*.stl` | Mesh reference only — prefer STEP for mates |
| Parts hierarchy | `out/blender/parts.json` / staging BOM | Name alignment with `part_ids` / mate_chain |
| Photogrammetry mesh | `out/colmap/` or `out/meshroom/` (when installed) | Optional underlay; not a substitute for confirmed dims |

No API keys, Fusion auth tokens, or license files belong in git or job manifests committed to the repo.

## Operator sequence

1. **Confirm dimensions** — edit the dimension register; mark caliper / datasheet rows `confidence: confirmed`. Inferred-only registers refuse leaf-fitment claims.
2. **CadQuery on MWT1** (preferred):
   ```bash
   composite3dgen cad path/to/job --executor mwt1 --script path/to/parametrics.py
   ```
   Missing CadQuery → dry-run JSON with structured `next_steps` (install into AlanTBrain tools venv). Controller `--executor local` is degraded fallback.
3. **Copy STEP** (LAN rsync / shared AlanTBrain path) to the Fusion workstation.
4. **Fusion** — import STEP; apply mates matching `mate_chain[]` (`coincident`, `offset`, `axis`, …). Prefer confirmed `dim_ids` only.
5. **Export** refined STEP/STL back into the job `out/fusion/` (operator-managed; no cloud spend).
6. **Blender on MWT1** — re-parent / explode using BOM ids; QA stills as usual. Do not treat Fusion as the explode hub.

## Out of scope (U6)

- Autodesk **3ds Max** max/FBX round-trip (later phase).
- Paid cloud CAD or generative design APIs.
- Claiming leaf BOM completeness from TripoSR / Tripo / Hi3D alone.

## Related

- [BOM_SCHEMA.md](BOM_SCHEMA.md) — L1/L2 vs leaf
- [COST_QUALITY_MATRIX.md](COST_QUALITY_MATRIX.md) — CadQuery + Fusion rung
- [WORKFLOW.md](WORKFLOW.md) — stage 11 RC leaf fitment
- `schema/dimension.register.schema.json`
- `deploy/mwt1/photogrammetry.md` — local metric multi-view when orbit exists
- Preferences: Fusion-only v1 GUI; AlanTBrain jobs/media; TripoSR MPS (separate from CAD)
