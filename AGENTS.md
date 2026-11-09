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

- Host alias: `mwt1` → `192.168.50.212` (user recorded in `deploy/mwt1/README.md` when verified).
- Job root (planned): `~/composite3dgen/jobs/`
- Expected capabilities (verified in U3b): SSH, ffmpeg, CUDA/PyTorch (~6GB+ for TripoSR), Blender, optional COLMAP/Meshroom.

If MWT1 is unreachable, controller may run lightweight stages in **degraded mode** — document that as fallback, not the happy path.

## Implementation units (do not jump ahead casually)

| Unit | Scope |
|------|--------|
| U1 | Repo bootstrap + playbook + CLI stub |
| U2 | Subject manifest + composite pack builder (this milestone) |
| U3 | Provider adapters + cost router |
| U3b | MWT1 node contract + health checks |
| U4 | BOM schema + Blender explode/QA on MWT1 |
| U5 | GLM fixture intake + dry-run E2E |
| U6 | RC CAD + photogrammetry on MWT1 |
| U7 | QA gates + cost ledger |

U2 implements `manifest/`, `ingest/`, `composites/`, `packs/`, and the nodes
executor selection interface. Do not invent fake cloud provider clients until U3.
Full MWT1 SSH capability probes remain U3b.

## Testing

```bash
pip install -e ".[dev]"
pytest
python -m composite3dgen --help
python -m composite3dgen build-packs fixtures/u2-sample --executor local
```

## Playbook pointers

- Stages / gates / spend: `docs/playbook/WORKFLOW.md`
- Capture: `docs/playbook/CAPTURE_CHECKLIST.md`
- Routing: `docs/playbook/COST_QUALITY_MATRIX.md`
- BOM depth: `docs/playbook/BOM_SCHEMA.md`
