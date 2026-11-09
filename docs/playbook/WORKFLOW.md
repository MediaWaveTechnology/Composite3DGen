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
3. **`--spend` gate** — without `--spend`, adapters dry-run or refuse live paid HTTP. With `--spend`, U7 will additionally require recorded QA miss reasons before authorizing cloud.
4. **BOM depth gate** — ship L1/L2 explode first; leaf tier is schema-ready but quality-gated. See [BOM_SCHEMA.md](BOM_SCHEMA.md).
5. **Presentation gate** — Seedance only after QA pass; never a geometry source.

## Spend policy

- **Default:** dry-run + recorded fixtures/proofs; local MWT1 stages only.
- **Authorize spend:** pass `--spend` on the CLI (and later: provide QA miss rationale).
- **Secrets:** Bitwarden / env on controller only — never commit keys (see root `AGENTS.md`).
- **Ledger (U7):** local stages marked `$0`; cloud via API `consumed` fields.

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
| Ingest / ffmpeg | SSH, writable `/Volumes/AlanTBrain/composite3dgen/jobs/`, `ffmpeg` |
| Quality / composites / packs | SSH, writable AlanTBrain jobs dir, Python Pillow image stack |
| TripoSR | SSH, AlanTBrain jobs dir, CUDA/PyTorch (~6GB+ VRAM), pinned TripoSR + `run.py` (separate on M4 Metal) |
| Photogrammetry (U6) | SSH, AlanTBrain jobs dir, **and** `colmap` **or** Meshroom |
| Blender explode / QA stills (U4) | SSH, AlanTBrain jobs dir, `blender` (+ Pillow for silhouette scoring) |

Missing **required** capabilities fail closed with remediation text. Jobs/media prefer **AlanTBrain** (not home). Optional COLMAP/Meshroom absence does not block base packs. Blender on MWT1 is probe-verified (`/opt/homebrew/bin/blender`, 5.2.3 LTS; Apple M4 Metal — explode/QA OK). TripoSR CUDA / COLMAP stay separate. Cloud VMs cannot reach `192.168.50.212`.

## Job directory pattern (planned)

Prefer `/Volumes/AlanTBrain/composite3dgen/jobs/<subject-id>/` on MWT1:

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

## Related

- [COST_QUALITY_MATRIX.md](COST_QUALITY_MATRIX.md) — routing ladder
- [CAPTURE_CHECKLIST.md](CAPTURE_CHECKLIST.md) — input quality
- [BOM_SCHEMA.md](BOM_SCHEMA.md) — hierarchy depth
