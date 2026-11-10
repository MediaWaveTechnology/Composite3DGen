# MWT1 deploy notes

MWT1 is the primary local compute node for Composite3DGen.

Live facts marked **verified** come from store probes:
- `/cursor/stores/bc-324ff812-5250-4e5d-8668-d1094cebdfc5/internal/mwt1-capability-probe.md`
- `/cursor/stores/bc-324ff812-5250-4e5d-8668-d1094cebdfc5/internal/mwt1-alantbrain-layout.md`

## Storage policy (live layout)

**Canonical root (capitalized):** `/Volumes/AlanTBrain/Composite3DGen/`

| Path | Role | Status |
|------|------|--------|
| `/Volumes/AlanTBrain/Composite3DGen/jobs/` | Job staging (`DEFAULT_JOB_ROOT`) | **verified** created + writable (via Terminal) |
| `/Volumes/AlanTBrain/Composite3DGen/media/` | Large source media | **verified** created |
| `/Volumes/AlanTBrain/Composite3DGen/tools/` | Heavy installs (TripoSR, venvs, …) | **verified** created |
| `/Volumes/AlanTBrain/Composite3DGen/README.txt` | Volume root marker | **verified** |
| `~/composite3dgen/jobs` | **Symlink** → preferred jobs root | **verified** |
| `/Volumes/AlanTBrain/composite3dgen/` (lowercase) | Legacy / do not prefer | accept if present; not canonical |

**Why AlanTBrain:** home had only **~13 GiB free** (**verified**, tight). Volume has **~1.4 TiB free** (`df`, **verified**).

### Full Disk Access / agent-worker caveat (**verified**)

| Actor | AlanTBrain list/write |
|-------|------------------------|
| Cursor **agent-worker** (`CURSOR_AGENT=1`) | **Denied** — Operation not permitted (even via `~/composite3dgen/jobs` symlink) |
| **Terminal.app** (Full Disk Access) | **OK** — layout + write proof |
| `stat`/`ls -lad` of **known** paths from agent | often OK after paths exist; `readdir` of volume root still denied |

**Pipeline implication:** job staging / heavy I/O on AlanTBrain must run under **Terminal.app**, a LaunchAgent with FDA, or after granting **Full Disk Access** to the Cursor agent-worker. Do not assume cloud or agent shells can write the preferred root until FDA is granted.

Write proof (Terminal): `/Volumes/AlanTBrain/Composite3DGen/jobs/.layout-ok` (`layout-verified 2026-11-09T23:51:47Z`).

## Verified host facts

| Fact | Value | Status |
|------|-------|--------|
| Hostname | `MWT1.local` | **verified** |
| LAN / user | `192.168.50.212`, `davethompson` | **verified** |
| OS / CPU | macOS arm64, Apple **M4**, **Metal 4** | **verified** |
| CUDA / `nvidia-smi` | **none** | **verified** |
| ffmpeg | `/opt/homebrew/bin/ffmpeg` **9.0.2** | **verified** |
| Blender | `/opt/homebrew/bin/blender` + app bundle — **5.2.3 LTS** | **verified** |
| Pillow / torch / TripoSR / COLMAP / Meshroom | **missing** | **verified** |
| AlanTBrain free | **~1.4 TiB** | **verified** |
| Home free | **~13 GiB** | **verified** (tight) |

TripoSR pin (not checked out yet):

| Fact | Value |
|------|-------|
| Planned dir | `/Volumes/AlanTBrain/Composite3DGen/tools/TripoSR` |
| Pin | `107cefdc244c39106fa830359024f6a2f1c78871` |
| Device | **PyTorch MPS** (experimental); CUDA optional on Linux GPU only |

## TripoSR: Metal/MPS on mwt1 (experimental)

**User decision:** try **MPS/Metal**, not CUDA, on this Apple M4.

Capability id `cuda_pytorch` (legacy name) = GPU PyTorch ready: **MPS** *or* **CUDA+≥~6GB VRAM**. **Fail closed** if neither works.

Install under AlanTBrain **via Terminal/FDA**:

```bash
ROOT=/Volumes/AlanTBrain/Composite3DGen
python3 -m venv "$ROOT/tools/.venv"
source "$ROOT/tools/.venv/bin/activate"
pip install torch torchvision   # macOS arm64 MPS — not a CUDA index
python -c "import torch; assert torch.backends.mps.is_available(); print('mps_ok')"
pip install 'Pillow>=10' numpy
git clone https://github.com/VAST-AI-Research/TripoSR.git "$ROOT/tools/TripoSR"
cd "$ROOT/tools/TripoSR" && git checkout 107cefdc244c39106fa830359024f6a2f1c78871
pip install -r requirements.txt
python run.py --help
# Live: --device mps --output-dir … --model-save-format glb
```

## Capability / stage readiness (summary)

| Stage | Status on mwt1 |
|-------|----------------|
| ingest (ffmpeg) | ready when job root writable (Terminal/FDA or granted agent FDA) |
| quality / composites | **blocked** — Pillow missing |
| TripoSR | **blocked** — no torch/MPS proof, no checkout |
| Photogrammetry | **blocked** — no COLMAP/Meshroom |
| Blender explode | paths **ready** (5.2.3 LTS) |

## Files

- `triposr.service.example` — AlanTBrain `tools/` paths; MPS; enable after smoke
- `photogrammetry.md` — COLMAP/Meshroom missing

## Policy

- Prefer MWT1 for ready stages; AlanTBrain `Composite3DGen` for all heavy I/O.
- Never embed cloud API keys on MWT1.
- Accept legacy lowercase `/Volumes/AlanTBrain/composite3dgen` if found; **canonical is capitalized**.

## Re-probe

```bash
ls -la /Volumes/AlanTBrain/Composite3DGen
readlink ~/composite3dgen/jobs
touch /Volumes/AlanTBrain/Composite3DGen/jobs/.w && rm $_
command -v ffmpeg; blender --version 2>&1 | head -n 1
python3 -c "import torch; print(getattr(torch.backends,'mps',None) and torch.backends.mps.is_available())"
test -f /Volumes/AlanTBrain/Composite3DGen/tools/TripoSR/run.py
PYTHONPATH=src python3 -m composite3dgen doctor --live
```

## Stage → capability map

See also `docs/playbook/WORKFLOW.md`.

| Stage | Required capabilities |
|-------|----------------------|
| ingest (ffmpeg) | ssh, job_root_writable, ffmpeg |
| quality / composites / packs | ssh, job_root_writable, python_image |
| TripoSR draft | ssh, job_root_writable, cuda_pytorch (MPS or CUDA), triposr |
| Photogrammetry | ssh, job_root_writable, **and** colmap **or** meshroom |
| Blender explode / hierarchy | ssh, job_root_writable, blender |
| QA renders / silhouette prep | ssh, job_root_writable, blender, python_image |

U4 CLI (from controller; scripts execute on MWT1 when stage ready):

```bash
python -m composite3dgen explode path/to/job --mesh draft.glb --hierarchy parts.in.json
# MWT1 prefers: /opt/homebrew/bin/blender  (fallback: Blender.app bundle)
# Job staging: /Volumes/AlanTBrain/Composite3DGen/jobs/…
# Without SSH transport → dry-run parts.json only (schema-valid; no invented mesh)
```

Headless invoke shape on the node:

```bash
/opt/homebrew/bin/blender --background --python explode_hub.py -- \
  --input mesh.glb --hierarchy hierarchy.json --out-dir out
```
