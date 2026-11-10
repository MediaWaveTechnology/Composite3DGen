# Agent guide — Composite3DGen

Guidance for humans and coding agents working in this repository.

## Product intent

Composite3DGen is the **playbook + pipeline** home for multi-angle → reconstruct → multi-level explode workflows (GLM industrial machines, RC cars, and reusable subjects). Optimize for **cost and quality**, not wall-clock speed.

## Non-negotiables

1. **No secrets in git.** API keys, tokens, SSH passwords, Bitwarden session material, and `.env` files with live credentials must never be committed. Use Bitwarden CLI / agent secrets / environment variables on the **controller** only.
2. **`--spend` gate.** Paid cloud calls (Tripo API, Hi3D, Rodin/BANG, Seedance) require an explicit `--spend` flag. Default path is dry-run + local/MWT1 stages.
3. **`prefer_local` default.** Prefer MWT1 for ingest, packs, TripoSR, photogrammetry, Blender explode/QA. Escalate to cloud only when QA says local draft is insufficient.
4. **Do not port** GLM marketing/DAM site content or scorpion assets into this repo. Port **patterns** (manifests, pack layout, Tripo client shapes) only.
5. **TripoSR ≠ Tripo cloud.** TripoSR is local single-image draft reconstruct on MWT1. Tripo H3.1 multiview + `generate_parts` is the paid multi-view parts path.

## Secrets loading (controller)

```bash
# Example patterns — adapt to local Bitwarden item names
# bw get notes 'Composite3DGen/Tripo'   → export TRIPO_API_KEY=...
# bw get notes 'Composite3DGen/Hi3D'    → export HI3D_API_KEY=...
# bw get notes 'Composite3DGen/Rodin'   → export RODIN_API_KEY=...

# Never write keys into deploy/mwt1 docs, fixtures, or job manifests committed to git.
```

Orchestration and secret resolution stay on the controller (laptop). MWT1 runs GPU/DCC jobs over SSH/rsync; do not embed cloud API keys in MWT1 service units or shared node README facts beyond capability probes.

## MWT1

- Host alias: `mwt1` → `192.168.50.212`, user `davethompson` (see `deploy/mwt1/README.md`).
- Jobs/media: `/Volumes/AlanTBrain/composite3dgen/jobs/` + `…/media/` (**prefer AlanTBrain, not home**)
- Capabilities: SSH, writable AlanTBrain jobs dir, ffmpeg, Python image stack, CUDA/PyTorch (~6GB+ for TripoSR — separate on M4), Blender, optional COLMAP/Meshroom — probed by `composite3dgen doctor` (injectable transport; `--live` for SSH).
- Blender on MWT1 is **verified** (`/opt/homebrew/bin/blender`, App bundle fallback; 5.2.3 LTS). Host is Apple M4 Metal — Blender explode/QA OK; TripoSR CUDA / COLMAP remain separate (see `internal/mwt1-capability-probe.md`). Cloud agents cannot SSH the private LAN.

If MWT1 is unreachable, controller may run lightweight stages in **degraded mode** — fallback, not the happy path.

## Implementation units (do not jump ahead casually)

| Unit | Scope |
|------|--------|
| U1 | Repo bootstrap + playbook + CLI stub |
| U2 | Subject manifest + composite pack builder |
| U3 | Provider adapters + cost router |
| U3b | MWT1 node contract + health checks |
| U4 | BOM schema + Blender explode/QA on MWT1 |
| U5 | GLM fixture intake + dry-run E2E |
| U6 | RC CAD + photogrammetry on MWT1 (this milestone) |
| U7 | QA gates + cost ledger |

U6 ships `fixtures/rc-dex410/` (dimension register + mate-chain), CadQuery
adapter (prefer MWT1; missing-binary dry-run with structured `next_steps`),
Fusion handoff docs (**not** 3ds Max — later phase), and photogrammetry
adapter (COLMAP/Meshroom on MWT1; dry-run until installed — see
`deploy/mwt1/photogrammetry.md`). Do not invent COLMAP paths; probe found
neither tool. No secrets / live paid cloud. U7 is hooks only beyond this unit.

## Testing

```bash
pip install -e ".[dev]"
pytest
python -m composite3dgen --help
python -m composite3dgen build-packs fixtures/u2-sample --executor local
python -m composite3dgen route --stage triposr --stage tripo
python -m composite3dgen run fixtures/u2-sample --executor local --json
python -m composite3dgen explode fixtures/u2-sample --executor local --json
python -m composite3dgen dry-run fixtures/glm-qm1 --executor local --json
python -m composite3dgen cad fixtures/rc-dex410 --executor local --json
python -m composite3dgen photogrammetry fixtures/rc-dex410 --executor local --json
python -m composite3dgen doctor
# LAN / mwt1 worker only:
# python -m composite3dgen doctor --live
# python -m composite3dgen explode path/to/job --mesh draft.glb
```

## Playbook pointers

- Stages / gates / spend: `docs/playbook/WORKFLOW.md`
- Capture: `docs/playbook/CAPTURE_CHECKLIST.md`
- Routing: `docs/playbook/COST_QUALITY_MATRIX.md`
- Fusion handoff: `docs/playbook/FUSION_HANDOFF.md`
- BOM depth: `docs/playbook/BOM_SCHEMA.md`
