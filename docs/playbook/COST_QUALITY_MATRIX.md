# Cost × quality routing matrix

Default: climb the ladder from free local stages; stop when QA passes. Paid cloud is a promote step, not the default reconstruct.

## Ladder

| Priority | Path | When | Cost |
|----------|------|------|------|
| 1 | Local prep on MWT1 (ingest → quality → composites/packs) | Always | $0 |
| 2 | TripoSR draft on MWT1 → Blender hierarchy/explode/QA | Default first reconstruct | $0 |
| 3 | COLMAP / Meshroom on MWT1 | Real orbit coverage; need metric multi-view | $0 |
| 4 | Tripo H3.1 multiview + `generate_parts` | Local QA fails on angle coverage / part fidelity | ~$0.40–$0.70 |
| 5 | Hi3D quality/master **or** Tripo texture-on-parts | Need textured hero after draft/parts | ~$0.90 / ~$2.90 |
| 6 | Rodin Custom BANG (or Hi3D Split) → Blender re-parent | Need cross-provider part split on any GLB | ~0.5 cr |
| 7 | Rodin Gen-2.5 Extreme-High | Hard-surface hero when drafts fail QA | Higher |
| 8 | CadQuery + Fusion + dimension register | RC leaf fitment claims | Local / license |
| 9 | Seedance | Presentation only after QA pass | Paid |

## Router rules (U3 / U7)

1. **`prefer_local=true` (default)** — attempt MWT1-capable stages before cloud.
2. **No `--spend`** — refuse live Tripo / Hi3D / Rodin / Seedance HTTP; dry-run + fixtures OK.
3. **With `--spend`** — **hard-blocked** under `prefer_local` unless QA miss reasons are recorded (`--qa-miss` or `manifests/qa_misses.json`). `--no-prefer-local --spend` is the explicit override.
4. **TripoSR role boundary** — single-image (or per-view independent) draft. **Not** true multi-view fusion. Do not treat TripoSR success as proof of unseen sides.
5. **Reuse before re-spend** — ingest existing GLM Tripo generations / staging assembly fixtures when available (U5).
6. **Seedance** — presentation only after QA **pass**; never geometry.

CLI: `composite3dgen qa` runs silhouette + BOM gates and writes the cost ledger; `route` / `run` consume miss reasons. Router still demotes unjustified live cloud to dry-run + `block_reason` as belt-and-suspenders. Full policy: [QA_GATES.md](QA_GATES.md).

## Quality tiers

| Tier | Deliverable | Gate |
|------|-------------|------|
| Draft | TripoSR / early Tripo mesh | Silhouette sanity; not for leaf BOM claims |
| L1/L2 explode | Blender Empty hierarchy + GLB + `parts.json` | BOM completeness L1/L2; orthographic QA |
| Text | Full leaf BOM | Schema ready; quality-gated; RC needs CAD lane |
| Hero | Textured presentation mesh | Hi3D/Rodin after QA; Seedance optional |

## Decision cheat sheet

```
capture OK?
  no  → reshoot / fix packs (CAPTURE_CHECKLIST)
  yes → TripoSR on MWT1 → Blender QA
          pass → stop (or Seedance post-QA)
          fail angle coverage → photogrammetry if orbit dense, else Tripo multiview (--spend)
          fail part fidelity → Tripo generate_parts or Rodin BANG (--spend)
          fail hard-surface → Rodin Extreme-High / Hi3D master (--spend)
          RC leaf fitment → CadQuery + Fusion (not AI alone)
```

## MWT1 capability gate (before climbing the ladder)

`composite3dgen doctor` probes SSH, job root, ffmpeg, Python image stack, CUDA/PyTorch, Blender, TripoSR pin, optional COLMAP/Meshroom. Executor selection prefers MWT1 only when **base** capabilities pass; TripoSR/Blender/photogrammetry stages additionally require their own caps (see WORKFLOW.md). Fail closed.

**Verified host reality:** MWT1 is Apple M4 / Metal. TripoSR = **experimental MPS**; CUDA optional for Linux GPU only. Prefer `/Volumes/AlanTBrain/Composite3DGen` for jobs/media/tools (agent-worker needs FDA/Terminal). Blender 5.2.3 LTS + ffmpeg verified; install Pillow before quality/composites. Details: `deploy/mwt1/README.md`.

## U6 local CAD / SfM notes

- Photogrammetry adapter executes on MWT1 when `colmap` **or** Meshroom probes pass; otherwise dry-run + install next steps (`deploy/mwt1/photogrammetry.md`). Probe 2026-11-09: both missing.
- CadQuery prefer MWT1; Fusion interactive edit on licensed workstation ([FUSION_HANDOFF.md](FUSION_HANDOFF.md)). 3ds Max = later phase.

## Related

- [WORKFLOW.md](WORKFLOW.md) — stages and `--spend` policy
- [QA_GATES.md](QA_GATES.md) — silhouette / BOM / ledger / promote-to-hero / Seedance
- [BOM_SCHEMA.md](BOM_SCHEMA.md) — L1/L2 vs leaf
- [FUSION_HANDOFF.md](FUSION_HANDOFF.md) — Fusion handoff
- [`deploy/mwt1/README.md`](../../deploy/mwt1/README.md) — install / verify-on-LAN facts
- [`deploy/mwt1/photogrammetry.md`](../../deploy/mwt1/photogrammetry.md) — COLMAP / Meshroom
