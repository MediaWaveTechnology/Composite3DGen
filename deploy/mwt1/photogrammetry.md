# Photogrammetry on MWT1 (U6)

Local **metric multi-view** when orbit coverage is real. Adapter: `composite3dgen photogrammetry` / router stage `photogrammetry` (COLMAP preferred, Meshroom alternative).

## Tools (live probe)

| Tool | Role | Status |
|------|------|--------|
| COLMAP | SfM/MVS CLI | **verified missing** (`command -v colmap` not found) |
| Meshroom | GUI / `meshroom_batch` | **verified missing** (no PATH hit, no `/Applications/Meshroom*`) |

Source: `/cursor/stores/bc-324ff812-5250-4e5d-8668-d1094cebdfc5/internal/mwt1-capability-probe.md`.

Until installed, the adapter **dry-runs** and returns structured `next_steps` / `meta.next_steps`. Doctor stage `photogrammetry` stays **blocked**. Mark paths **verified** only after `composite3dgen doctor --live` on LAN / mwt1 worker.

## Policy

- Run on MWT1 next to job `frames/` under `/Volumes/AlanTBrain/Composite3DGen/jobs/` when installed (Terminal/FDA if agent lacks volume access).
- Tools installs: `/Volumes/AlanTBrain/Composite3DGen/tools/` (home disk is tight).
- Prefer this **$0** lane before Tripo multiview when angle density supports SfM.
- Doctor stage `photogrammetry` is **ready** only if SSH + writable jobs dir **and** at least one of COLMAP/Meshroom is present — **currently blocked**.
- Missing binaries → structured remediation (fail closed for that stage), not a silent skip of the cloud gate.
- No secrets in install notes; no live paid cloud from this path.

## Install COLMAP (Homebrew, Apple Silicon)

On MWT1 as `davethompson`:

```bash
brew install colmap
command -v colmap && colmap -h 2>&1 | head -n 1
```

If brew formula pulls are heavy, prefer staging caches on AlanTBrain and keep workspace outputs under:

```bash
mkdir -p /Volumes/AlanTBrain/Composite3DGen/jobs
mkdir -p /Volumes/AlanTBrain/Composite3DGen/tools
```

Adapter invoke shape (automatic reconstructor):

```bash
colmap automatic_reconstructor \
  --workspace_path /Volumes/AlanTBrain/Composite3DGen/jobs/<subject>/<job>/ \
  --image_path    /Volumes/AlanTBrain/Composite3DGen/jobs/<subject>/<job>/images
```

## Install Meshroom (alternative)

1. Download AliceVision Meshroom release for macOS (operator workstation browser; do not commit binaries).
2. Place under AlanTBrain tools, e.g. `/Volumes/AlanTBrain/Composite3DGen/tools/Meshroom/`.
3. Ensure `meshroom_batch` (or `Meshroom`) is on PATH for the SSH user:

```bash
# example — adjust to the extracted layout
export PATH="/Volumes/AlanTBrain/Composite3DGen/tools/Meshroom:$PATH"
command -v meshroom_batch || command -v Meshroom
```

## Probe / doctor

```bash
command -v colmap && colmap -h 2>&1 | head -n 1
command -v meshroom_batch || command -v Meshroom
ls /Applications/Meshroom* 2>/dev/null

# From LAN controller or mwt1 worker:
python -m composite3dgen doctor --live
python -m composite3dgen photogrammetry path/to/job --json
```

Capability contract: `nodes.capabilities.PHOTOGRAMMETRY_ANY_OF = (colmap, meshroom)`.

## Executor selection

| Condition | Behavior |
|-----------|----------|
| MWT1 healthy + colmap or meshroom | Execute on MWT1 (`mode=mwt1`) |
| Tools missing | `mode=dry-run`, `status=dry_run`, `meta.next_steps` populated |
| MWT1 down / no SSH | Controller local if tools present; else dry-run |

Cloud agents cannot reach `192.168.50.212` — expect dry-run from CI.

## Related

- `deploy/mwt1/README.md` — node facts / AlanTBrain roots
- `docs/playbook/COST_QUALITY_MATRIX.md` — ladder rung 3
- `docs/playbook/FUSION_HANDOFF.md` — CAD lane (separate from SfM)
