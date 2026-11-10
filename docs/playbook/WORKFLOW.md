# Workflow — stages, gates, spend policy

Composite3DGen happy path keeps **ingest → packs → TripoSR → Blender → QA** on **MWT1 at $0** before any cloud spend. Cost and quality beat speed.

## Stages (v1)

| # | Stage | Prefer | Cost |
|---|--------|--------|------|
| 1 | Video/photo ingest + ffmpeg frame extract | MWT1 | $0 |
| 2 | Frame quality / angle-coverage scoring | MWT1 | $0 |
| 3 | Contact sheets + cardinal composites + build packs | MWT1 | $0 |
| 4 | Free local draft mesh (TripoSR) | MWT1 | $0 |
| 5 | Optional local metric multi-view (COLMAP / Meshroom) | MWT1 | $0 |
| 6 | Blender: import, Empty hierarchy, explode, remesh/UV/bake, orthographic QA stills | MWT1 | $0 |
| 7 | Silhouette / BOM QA scoring | MWT1 | $0 |
| 8 | Paid multi-view parts (Tripo H3.1 + `generate_parts`) | Cloud | Paid |
| 9 | Promote textured hero (Hi3D quality/master or Tripo texture-on-parts) | Cloud | Paid |
| 10 | Split refine (Rodin Custom BANG or Hi3D Split) → re-parent in Blender | Cloud → MWT1 | Paid then $0 |
| 11 | RC leaf fitment (CadQuery + Fusion + dimension register) | MWT1 / workstation | $0 / license |
| 12 | Presentation (Seedance from clay/explode renders) | Cloud | Paid — **post-QA only** |

Orchestration, manifests, router decisions, and Bitwarden secrets stay on the **controller**. Human review / Fusion GUI stay on a licensed workstation.

## Gates

1. **Capture gate** — packs must include canonical front (and expected cardinals). See [CAPTURE_CHECKLIST.md](CAPTURE_CHECKLIST.md).
2. **Local-first gate** — `prefer_local` defaults on. Cloud reconstruct only after local TripoSR (and photogrammetry when applicable) miss QA, or operator overrides with `--no-prefer-local` **and** `--spend`.
3. **`--spend` gate (U7)** — without `--spend`, adapters dry-run or refuse live paid HTTP. With `--spend` under `prefer_local`, **hard-requires** recorded QA miss reasons (`--qa-miss` or `manifests/qa_misses.json` from `composite3dgen qa`).
4. **BOM depth gate** — ship L1/L2 explode first; leaf tier is schema-ready but quality-gated. See [BOM_SCHEMA.md](BOM_SCHEMA.md).
5. **Presentation gate** — Seedance only after QA pass; never a geometry source. See [QA_GATES.md](QA_GATES.md).

## Spend policy

- **Default:** dry-run + recorded fixtures/proofs; local MWT1 stages only.
- **Authorize spend:** pass `--spend` **and** QA miss rationale (`--qa-miss` / prior `qa` report), or `--no-prefer-local --spend`.
- **Secrets:** Bitwarden / env on controller only — never commit keys (see root `AGENTS.md`).
- **Ledger (U7):** `manifests/cost_ledger.json` — local stages `$0`; cloud via API `consumed`.

Approximate cloud reference (order-of-magnitude; verify live pricing):

| Path | Ballpark |
|------|----------|
| Tripo H3.1 multiview + `generate_parts` | ~$0.40–$0.70 |
| Hi3D `2048quality` / `2048master` | ~$0.90 / ~$2.90 |
| Rodin Custom BANG | ~0.5 credit |
| Rodin Gen-2.5 Extreme-High | higher — hero hard-surface when drafts fail |

## MWT1 local-first policy

- Treat MWT1 as the primary node for every stage that does not require a paid cloud API.
- Controller degraded mode (run lightweight stages locally if MWT1 is down) is a **fallback**, not the documented happy path.
- Capability probes + fail-closed remediations: `composite3dgen doctor` / `doctor --live` (LAN or mwt1 self-hosted worker). See `deploy/mwt1/README.md`.

### Stage capability requirements (U3b)

| Stage | Requires on MWT1 |
|-------|------------------|
| Ingest / ffmpeg | SSH, writable jobs dir (prefer AlanTBrain), `ffmpeg` |
| Quality / composites / packs | SSH, writable jobs dir, Python Pillow image stack |
| TripoSR | SSH, jobs dir, **MPS (mwt1)** or CUDA (optional Linux), pinned TripoSR + `run.py` |
| Photogrammetry (U6) | SSH, jobs dir, **and** `colmap` **or** Meshroom |
| Blender explode / QA stills (U4) | SSH, jobs dir, `blender` (+ Pillow for silhouette scoring) |

Missing **required** capabilities fail closed with remediation text. Optional COLMAP/Meshroom absence does not block base packs.

**Live MWT1 (verified):** Apple **M4 / Metal**. Jobs/media/tools → `/Volumes/AlanTBrain/Composite3DGen/` (capitalized; home too small; agent needs FDA/Terminal for volume I/O). TripoSR = **experimental MPS**. ffmpeg + Blender 5.2.3 LTS ready; Pillow/torch/TripoSR/COLMAP **missing**. See `deploy/mwt1/README.md`.

## Job directory pattern (planned)

Prefer `/Volumes/AlanTBrain/Composite3DGen/jobs/<subject-id>/` on MWT1:

```
jobs/<subject-id>/
  frames/
  contact_sheets/
  build_packs/{triposr,tripo,hi3d,rodin}/
  manifests/
  out/
  verification/   # local-* / live-* / *-exploded-l1.png
```

## Dry-run E2E (U5)

Zero-spend proof path for curated fixtures (GLM QM1 first):

```bash
python -m composite3dgen dry-run fixtures/glm-qm1 --executor local
```

Stages: packs → virtual local/cloud providers → Blender hierarchy (staging
L1/L2) → `manifests/dry_run_checklist.json`. Reuses recorded Tripo
parts/texture task records; large GLBs are external/LFS refs only. Do **not**
treat live dump-truck assembly stubs as QM1 truth. `dry-run` refuses `--spend`.

## RC CAD + photogrammetry (U6)

```bash
python -m composite3dgen cad fixtures/rc-dex410 --executor local
python -m composite3dgen photogrammetry path/to/job --executor local
```

CadQuery prefer MWT1; missing CadQuery/COLMAP/Meshroom → dry-run with structured
`next_steps` (see `deploy/mwt1/photogrammetry.md`, [FUSION_HANDOFF.md](FUSION_HANDOFF.md)).
3ds Max is later-phase — not invoked here.

## QA gates + cost ledger (U7)

```bash
python -m composite3dgen qa path/to/job --bom-tier L2
python -m composite3dgen --spend run path/to/job --qa-miss silhouette --stage tripo
```

Silhouette overlay + BOM completeness (L1/L2/leaf) from MWT1 renders when
present (mockable offline). Failing coverage fails the gate. Cost ledger
includes zero-cost local pipeline stages. Seedance is post-QA presentation
only — see [QA_GATES.md](QA_GATES.md).

## Related

- [COST_QUALITY_MATRIX.md](COST_QUALITY_MATRIX.md) — routing ladder
- [CAPTURE_CHECKLIST.md](CAPTURE_CHECKLIST.md) — input quality
- [BOM_SCHEMA.md](BOM_SCHEMA.md) — hierarchy depth
- [QA_GATES.md](QA_GATES.md) — silhouette / BOM / ledger / promote-to-hero
- [FUSION_HANDOFF.md](FUSION_HANDOFF.md) — Fusion handoff (v1 GUI)
