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

## U2/U3 note (selection + TripoSR transport)

`composite3dgen` selects MWT1 vs local via `nodes.executor.select_executor` for
ingest / quality / packs. The TripoSR adapter stages images over an injectable
`RemoteFSTransport` (`providers/transport.py`) and invokes a pinned `run.py`.

Until **U3b** wires real SSH health + capability probes, the default health probe
reports unhealthy (controller local degraded mode) and the CLI virtualizes
TripoSR as dry-run when no transport is injected.

### U3b must fill

- Wire `SubprocessSSHTransport(host="mwt1")` after probes pass; keep injection for tests
- Capability matrix: SSH, writable `~/composite3dgen/jobs/`, `ffmpeg`, Python image stack, CUDA/PyTorch (~6GB+ VRAM), `blender` path, optional `colmap`/`meshroom`
- Install/pin TripoSR under `~/composite3dgen/vendor/TripoSR` — replace placeholder pin in `providers/triposr.py` (`TRIPOSR_PIN_COMMIT`) with the real git SHA + weights path
- Confirm `run.py` CLI flags (`--output-dir`, mesh.glb/obj layout) match the adapter pull paths
- Fail closed with remediation text in this README when a required capability is missing
- Record verified Blender / CUDA / COLMAP facts here (user `davethompson` on `192.168.50.212`)
