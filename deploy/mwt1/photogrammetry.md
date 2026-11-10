# Photogrammetry on MWT1 (U6)

Local **metric multi-view** when orbit coverage is real. Adapter: `composite3dgen photogrammetry` / router stage `photogrammetry` (COLMAP preferred, Meshroom alternative).

## Live probe status (2026-11-09)

| Tool | Status |
|------|--------|
| COLMAP | **not found** (`command -v colmap` empty) |
| Meshroom | **not found** (no `/Applications/Meshroom*`, no `meshroom_batch`) |

Until installed, the adapter **dry-runs** and returns structured `next_steps` / `meta.next_steps`. Doctor stage `photogrammetry` stays **blocked**. Mark paths **verified** only after `composite3dgen doctor --live` on LAN / mwt1 worker (or an update to store `internal/mwt1-capability-probe.md`).

## Policy

- Run on **MWT1** next to job `frames/` under AlanTBrain:
  - Preferred: `/Volumes/AlanTBrain/composite3dgen/jobs/<subject>/frames/`
  - Tools installs: `/Volumes/AlanTBrain/composite3dgen/tools/` (home disk is tight)
- Prefer this **$0** lane before Tripo multiview when angle density supports SfM.
- Stage ready only if SSH + writable job root **and** at least one of COLMAP / Meshroom.
- Missing binaries → fail closed for the stage (structured remediation), not a silent skip of the cloud gate.
- No secrets in install notes; no live paid cloud from this path.

## Install COLMAP (Homebrew, Apple Silicon)

On MWT1 as `davethompson`:

```bash
brew install colmap
command -v colmap && colmap -h 2>&1 | head -n 1
```

If brew formula pulls are heavy, prefer staging caches on AlanTBrain and keep workspace outputs under:

```bash
mkdir -p /Volumes/AlanTBrain/composite3dgen/jobs
mkdir -p /Volumes/AlanTBrain/composite3dgen/tools
```

Adapter invoke shape (automatic reconstructor):

```bash
colmap automatic_reconstructor \
  --workspace_path /Volumes/AlanTBrain/composite3dgen/jobs/<subject>/<job>/ \
  --image_path    /Volumes/AlanTBrain/composite3dgen/jobs/<subject>/<job>/images
```

## Install Meshroom (alternative)

1. Download AliceVision Meshroom release for macOS (operator workstation browser; do not commit binaries).
2. Place under AlanTBrain tools, e.g. `/Volumes/AlanTBrain/composite3dgen/tools/Meshroom/`.
3. Ensure `meshroom_batch` (or `Meshroom`) is on PATH for the SSH user:

```bash
# example — adjust to the extracted layout
export PATH="/Volumes/AlanTBrain/composite3dgen/tools/Meshroom:$PATH"
command -v meshroom_batch || command -v Meshroom
```

## Probe / doctor

```bash
command -v colmap && colmap -h 2>&1 | head -n 1
command -v meshroom_batch || command -v Meshroom

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
