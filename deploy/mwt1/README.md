# MWT1 deploy notes

MWT1 is the primary local compute node for Composite3DGen.

**Jobs/media prefer `/Volumes/AlanTBrain/composite3dgen/`** (not the home volume). Home has limited free space; AlanTBrain is the staging disk for Blender explode jobs, packs, and large GLBs.

| Fact | Value | Status |
|------|-------|--------|
| SSH Host alias | `mwt1` | expected |
| LAN address | `192.168.50.212` | **verified** (probe) |
| SSH user | `davethompson` | **verified** (probe) |
| Job root | `/Volumes/AlanTBrain/composite3dgen/jobs/` | **preferred** (create/mount on AlanTBrain) |
| Media root | `/Volumes/AlanTBrain/composite3dgen/media/` | **preferred** |
| Remote root | `/Volumes/AlanTBrain/composite3dgen/` | **preferred** |
| Home fallback jobs | `~/composite3dgen/jobs/` | probe once created here — **do not** stage large media |
| TripoSR vendor dir | `/Volumes/AlanTBrain/composite3dgen/vendor/TripoSR` | preferred — **not present** on probe |
| TripoSR pin commit | `107cefdc244c39106fa830359024f6a2f1c78871` | documented pin (checkout missing on probe) |
| TripoSR weights | `stabilityai/TripoSR` (Hugging Face) | documented |
| Blender path | `/opt/homebrew/bin/blender` (also `/Applications/Blender.app/Contents/MacOS/Blender`) | **verified** — Blender 5.2.3 LTS |
| ffmpeg path | `/opt/homebrew/bin/ffmpeg` | **verified** — ffmpeg 9.0.2 |
| CUDA device / VRAM | Apple M4 Metal (no CUDA); torch not installed | **probed** — TripoSR CUDA path blocked until torch/MPS install |
| COLMAP path | not found | **probed** (optional) |
| Meshroom path | not found | **probed** (optional) |
| Pillow / numpy | not importable on system python3 | **probed** — blocks `qa_renders` silhouette scoring until image stack installed |

Live facts folded from project store `internal/mwt1-capability-probe.md` (mwt1 worker). **Do not invent** paths beyond that probe + the AlanTBrain preference above. Cloud agents still cannot SSH to the private LAN; re-run `doctor --live` on LAN / mwt1 worker if facts drift.

## Capability checklist

| Capability | Purpose | Required for |
|------------|---------|--------------|
| SSH | Reach node | all MWT1 stages |
| Writable job root | Stage media / pull GLB on AlanTBrain | all MWT1 stages |
| `ffmpeg` | Frame extract | ingest |
| Python image stack (Pillow; numpy optional) | Quality / composites | quality_composites |
| CUDA / PyTorch (~6GB+ VRAM) | TripoSR | triposr (separate from Blender; M4 has Metal, not CUDA) |
| Pinned TripoSR + `run.py` | Local draft mesh | triposr |
| `blender` | Explode / hierarchy / QA stills | blender_explode, qa_renders (U4) |
| `colmap` / Meshroom | Local metric multi-view | photogrammetry (U6, optional either) |

Probes fail **closed** with remediation text (`composite3dgen doctor`). Missing optional COLMAP/Meshroom does not block base packs.

## Stage → capability map

See also `docs/playbook/WORKFLOW.md`.

| Stage | Required capabilities |
|-------|----------------------|
| ingest (ffmpeg) | ssh, job_root_writable, ffmpeg |
| quality / composites / packs | ssh, job_root_writable, python_image |
| TripoSR draft | ssh, job_root_writable, cuda_pytorch, triposr |
| Photogrammetry | ssh, job_root_writable, **and** colmap **or** meshroom |
| Blender explode / hierarchy | ssh, job_root_writable, blender |
| QA renders / silhouette prep | ssh, job_root_writable, blender, python_image |

U4 CLI (from controller; scripts execute on MWT1 when stage ready):

```bash
python -m composite3dgen explode path/to/job --mesh draft.glb --hierarchy parts.in.json
# MWT1 prefers: /opt/homebrew/bin/blender  (fallback: Blender.app bundle)
# Job staging: /Volumes/AlanTBrain/composite3dgen/jobs/…
# Without SSH transport → dry-run parts.json only (schema-valid; no invented mesh)
# Blender explode/QA is Metal-OK on M4; TripoSR CUDA remains a separate install
```

Headless invoke shape on the node:

```bash
/opt/homebrew/bin/blender --background --python explode_hub.py -- \
  --input mesh.glb --hierarchy hierarchy.json --out-dir out
```

## Install TripoSR (on MWT1 — run on LAN)

Prefer AlanTBrain (home volume is tight):

```bash
mkdir -p /Volumes/AlanTBrain/composite3dgen/{vendor,jobs,media}
git clone https://github.com/VAST-AI-Research/TripoSR.git \
  /Volumes/AlanTBrain/composite3dgen/vendor/TripoSR
cd /Volumes/AlanTBrain/composite3dgen/vendor/TripoSR
git checkout 107cefdc244c39106fa830359024f6a2f1c78871
python3 -m venv .venv && source .venv/bin/activate
# MWT1 is Apple M4 Metal (no CUDA). TripoSR CUDA wheels are a separate issue —
# install a Metal/MPS-capable torch only if pursuing local TripoSR on this host.
pip install -r requirements.txt
# Weights pull from Hugging Face on first run: stabilityai/TripoSR
python run.py --help
```

`run.py` flags used by the adapter: input image(s), `--output-dir`, `--model-save-format glb`. Outputs land at `{output_dir}/0/mesh.glb` (or `.obj`).

## CUDA / Metal notes

- Blender explode/QA on M4 Metal is the U4 happy path — no CUDA required.
- TripoSR historically expects CUDA (~6GB+ VRAM). On this M4 host that is a **separate** install/decision (MPS/torch or offload) — do not block Blender staging on TripoSR readiness.
- `torchmcubes` CUDA build issues usually mean CUDA/toolchain mismatch — see upstream TripoSR README.

## ffmpeg / COLMAP

- `ffmpeg` is required for video ingest on the happy path (`/opt/homebrew/bin/ffmpeg`).
- COLMAP / Meshroom are optional until U6 photogrammetry execution; probe them now so doctor reports readiness.

## Files in this directory

- `triposr.service.example` — example oneshot unit shape (no secrets; jobs are SSH-driven)
- `photogrammetry.md` — COLMAP/Meshroom notes (U6)

## Policy

- Prefer MWT1 for every stage that does not require a paid cloud API.
- Stage jobs/media on **AlanTBrain**, not home.
- Controller degraded mode (`--executor local`) is fallback only.
- **Never** embed Tripo / Hi3D / Rodin / Seedance API keys on MWT1 or in this README.
- Executor selection: `nodes.executor.select_executor` uses capability health (not bare ping).
- TripoSR adapter uses injectable `RemoteFSTransport`; CLI wires `SubprocessSSHTransport` only when the `triposr` stage probes pass.

## Follow-up commands (mwt1 worker / LAN)

Exact commands for a live probe agent:

```bash
hostname; whoami
df -h /Volumes/AlanTBrain /System/Volumes/Data
ls /Volumes/AlanTBrain
command -v ffmpeg; ffmpeg -version | head -n 1
command -v blender; ls /opt/homebrew/bin/blender /Applications/Blender.app/Contents/MacOS/Blender 2>/dev/null
/opt/homebrew/bin/blender --version 2>&1 | head -n 1
python3 -c "from PIL import Image; print('pillow_ok')"
python3 -c "import torch; print(getattr(torch,'__version__',None), getattr(getattr(torch,'cuda',None),'is_available',lambda:None)())" 2>&1 || echo no_torch
command -v colmap; command -v meshroom_batch; command -v Meshroom
mkdir -p /Volumes/AlanTBrain/composite3dgen/{jobs,media} \
  && touch /Volumes/AlanTBrain/composite3dgen/jobs/.write_test \
  && rm /Volumes/AlanTBrain/composite3dgen/jobs/.write_test && echo alantbrain_job_root_ok
test -f /Volumes/AlanTBrain/composite3dgen/vendor/TripoSR/run.py \
  && git -C /Volumes/AlanTBrain/composite3dgen/vendor/TripoSR rev-parse HEAD
# From repo checkout on controller/worker:
PYTHONPATH=src python3 -m composite3dgen doctor --live
```

Record results into `internal/mwt1-capability-probe.md` (project store), then update the status table above — mark **verified** only for values present in that probe file.
