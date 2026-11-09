# Photogrammetry on MWT1

Local metric multi-view when orbit coverage is real. Full adapter execution is **U6**; capability probes are **U3b** (`colmap` / `meshroom`, optional).

## Tools (live probe)

| Tool | Role | Status |
|------|------|--------|
| COLMAP | SfM/MVS CLI | **verified missing** (`command -v colmap` not found) |
| Meshroom | GUI / `meshroom_batch` | **verified missing** (no PATH hit, no `/Applications/Meshroom*`) |

Source: `/cursor/stores/bc-324ff812-5250-4e5d-8668-d1094cebdfc5/internal/mwt1-capability-probe.md`.

## Policy

- Run on MWT1 next to job `frames/` under `/Volumes/AlanTBrain/composite3dgen/jobs/` when installed.
- Prefer this free local lane before Tripo multiview when angle density supports it.
- Doctor stage `photogrammetry` is **ready** only if SSH + writable jobs dir **and** at least one of COLMAP/Meshroom is present — **currently blocked**.
- Missing binaries → structured remediation (fail closed for that stage), not a silent skip of the cloud gate.

## Probe commands

```bash
command -v colmap && colmap -h 2>&1 | head -n 1
command -v meshroom_batch || command -v Meshroom
ls /Applications/Meshroom* 2>/dev/null
```
