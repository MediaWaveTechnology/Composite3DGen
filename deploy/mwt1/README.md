# MWT1 deploy notes

MWT1 is the primary local compute node for Composite3DGen (`ssh mwt1` → `192.168.50.212`).

This directory will hold install/pin notes for TripoSR, photogrammetry, and Blender path facts once **U3b** verifies capabilities. Do not put API keys or secrets here.

## Planned job root

```
~/composite3dgen/jobs/
```

## Capability checklist (verify in U3b)

| Capability | Purpose | Status |
|------------|---------|--------|
| SSH + writable job root | Stage media / pull GLB | TBD |
| `ffmpeg` | Frame extract | TBD |
| Python image stack | Quality / composites | TBD |
| CUDA / PyTorch (~6GB+ VRAM) | TripoSR | TBD |
| `blender` on PATH or known path | Explode / hierarchy / QA stills | TBD |
| `colmap` / Meshroom (optional) | Local metric multi-view | TBD |

## Files (stubs)

- `triposr.service.example` — example systemd unit shape (no secrets)
- `photogrammetry.md` — COLMAP/Meshroom notes (U6)

## Policy

Prefer MWT1 for every stage that does not require a paid cloud API. Controller degraded mode is fallback only — see `docs/playbook/WORKFLOW.md`.

## U2 note (selection interface)

`composite3dgen` already selects MWT1 vs local via `nodes.executor.select_executor`
for ingest / quality / packs. Until **U3b** wires real SSH health + capability
probes (`ffmpeg`, writable job root, Python image stack, …), the default probe
reports unhealthy and the CLI falls back to controller local. Follow-ups for U3b:

- Injectable SSH transport + `~/composite3dgen/jobs/` writability check
- Probe `ffmpeg` (required for video frame extract on-node)
- Record Blender / CUDA / COLMAP facts in this README
- Fail closed with remediation when a required capability is missing
