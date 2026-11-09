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
