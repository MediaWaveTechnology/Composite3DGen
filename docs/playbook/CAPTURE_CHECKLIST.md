# Capture checklist

Multi-angle inputs drive both free local drafts (TripoSR) and paid multi-view reconstruct. Bad capture forces inventing unseen sides — promote to photogrammetry or cloud multiview instead of trusting a single silhouette.

## Before you shoot

- [ ] Subject cleaned; stickers/labels that should not appear in texture noted
- [ ] Neutral, diffuse lighting; avoid hard specular blowouts on metal/plastic
- [ ] Fixed focal length preferred; record approximate subject size for later CAD/register work
- [ ] Background simple enough for occupancy scoring (or plan masking)
- [ ] Domain profile chosen: **GLM industrial** vs **RC** (affects BOM depth and CAD lane)

## Angle coverage (minimum)

Canonical cardinals expected by pack builder (U2):

| View | Required | Notes |
|------|----------|-------|
| Front | **Yes** | Packs missing front are rejected |
| Left | Yes | 90° yaw |
| Back | Yes | 180° yaw |
| Right | Yes | 270° yaw |
| Top | Optional | Strongly preferred for machines / RC chassis |
| Iso | Optional | Presentation / Seedance source only after QA |

### Good orbit habits

- [ ] Level camera height through the orbit (or document intentional elevation changes)
- [ ] Overlap ≥ 60% between adjacent frames if photogrammetry (COLMAP/Meshroom) is a goal
- [ ] Include underside or wheel wells when RC leaf fitment matters
- [ ] Avoid motion blur; sharpness scoring will drop soft frames

## Video path

- [ ] Steady orbit or turntable; constant angular speed helps frame pick
- [ ] ffmpeg extract on MWT1 (happy path); keep source media next to the job dir
- [ ] Prefer extracting more frames than needed, then let quality scoring cull

## Still path

- [ ] Same white balance / exposure across the set
- [ ] Include a scale reference in at least one frame when CAD claims are intended (RC)

## Pack readiness (post-ingest)

- [ ] Contact sheets reviewed by a human for missing sides / reflections / crop cuts
- [ ] Cardinal composites written under `build_packs/<provider>/`
- [ ] Subject manifest filled (domain, units, known dims, reuse of prior GLM Tripo outs)

## Known failure modes

| Symptom | Likely cause | Next step |
|---------|--------------|-----------|
| Invented backside geometry | Single-view TripoSR overreach | Add back/left/right; or photogrammetry; or Tripo multiview + `--spend` |
| Soft / melted small parts | Low res or motion blur | Reshoot close orbits; promote Hi3D master after QA miss |
| Wrong BOM groups | AI parts ≠ engineering BOM | Blender Empty rename + QA mandatory |
| Texture seams | Inconsistent lighting | Reshoot or texture-on-parts two-pass |

## Related

- [WORKFLOW.md](WORKFLOW.md) — stage order and gates
- [COST_QUALITY_MATRIX.md](COST_QUALITY_MATRIX.md) — when to escalate
