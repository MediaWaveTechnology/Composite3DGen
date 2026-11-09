# MWT1 deploy notes

MWT1 is the primary local compute node for Composite3DGen.

Live facts marked **verified** come from
`/cursor/stores/bc-324ff812-5250-4e5d-8668-d1094cebdfc5/internal/mwt1-capability-probe.md`
(self-hosted worker `f75a6644-73f7-4bb5-814f-ace1fafc0279`).

## Storage policy (user decision)

**Prefer `/Volumes/AlanTBrain` for jobs, media, and heavy installs** — not the home volume.

| Path | Role |
|------|------|
| `/Volumes/AlanTBrain/composite3dgen/` | Remote root (default) |
| `/Volumes/AlanTBrain/composite3dgen/jobs/` | Job staging (default `DEFAULT_JOB_ROOT`) |
| `/Volumes/AlanTBrain/composite3dgen/media/` | Large source media |
| `/Volumes/AlanTBrain/composite3dgen/vendor/TripoSR/` | TripoSR pin + weights |
| `/Volumes/AlanTBrain/composite3dgen/.venv/` | Node Python venv (Pillow, torch MPS, …) |

**Why:** home (`/System/Volumes/Data`) had only **~13 GiB free** at probe (**verified**, tight). AlanTBrain showed ~**1.4 TiB free** via `df` (**verified**).

**Access caveat (verified):** probe worker got **Operation not permitted** listing `/Volumes/AlanTBrain` even though `df` saw the mount. Preferred layout is still the contract — on the node, confirm the volume is mounted for `davethompson` and fix ACLs/Full Disk Access / ownership so `mkdir`/`ls` work:

```bash
ls -la /Volumes/AlanTBrain
mkdir -p /Volumes/AlanTBrain/composite3dgen/{jobs,media,vendor}
touch /Volumes/AlanTBrain/composite3dgen/jobs/.write_test && rm $_
```

**Home bootstrap only:** probe created `/Users/davethompson/composite3dgen/jobs/` (writable). Keep it as a tiny fallback if AlanTBrain is unmounted — **do not** store TripoSR weights or job media there.

Optional convenience symlink once AlanTBrain is writable:

```bash
mkdir -p /Volumes/AlanTBrain/composite3dgen
ln -sfn /Volumes/AlanTBrain/composite3dgen ~/composite3dgen-data
```

## Verified host facts

| Fact | Value | Status |
|------|-------|--------|
| Hostname | `MWT1.local` | **verified** |
| SSH Host alias | `mwt1` | expected (docs) |
| LAN address | `192.168.50.212` (`en0`; also `192.168.50.37`) | **verified** |
| SSH user | `davethompson` | **verified** |
| Home | `/Users/davethompson` | **verified** |
| OS | macOS 27.0.1 / Darwin 27.0.0 **arm64** | **verified** |
| CPU / GPU | Apple **M4** (`Mac16,10`), 10 CPU + 10 GPU cores, **Metal 4** | **verified** |
| RAM | 24 GiB | **verified** |
| CUDA / `nvidia-smi` | **none** (Apple Silicon) | **verified** |
| Job root (contract) | `/Volumes/AlanTBrain/composite3dgen/jobs/` | **preferred** (ACL TBD) |
| Job root (probe bootstrap) | `/Users/davethompson/composite3dgen/jobs/` | **verified** writable |
| ffmpeg | `/opt/homebrew/bin/ffmpeg` — **9.0.2** | **verified** |
| Blender (PATH) | `/opt/homebrew/bin/blender` | **verified** |
| Blender (app) | `/Applications/Blender.app/Contents/MacOS/Blender` | **verified** |
| Blender version | **5.2.3 LTS** (build 2026-10-22, Darwin, `e13b728c6880`) | **verified** |
| `python3` | `/opt/homebrew/bin/python3` — **3.15.2** | **verified** |
| Pillow / numpy / torch | **not installed** | **verified** |
| TripoSR checkout | **none** | **verified** |
| COLMAP / Meshroom | **not found** | **verified** |
| Home disk free | **~13 GiB** | **verified** (tight) |
| AlanTBrain `df` | ~1.8 Ti total, **~1.4 Ti free** | **verified** |
| AlanTBrain `ls` | **Operation not permitted** from probe worker | **verified** |

TripoSR pin (not yet checked out):

| Fact | Value | Status |
|------|-------|--------|
| Vendor dir | `/Volumes/AlanTBrain/composite3dgen/vendor/TripoSR` | planned |
| Pin commit | `107cefdc244c39106fa830359024f6a2f1c78871` | documented |
| Weights | `stabilityai/TripoSR` (Hugging Face) | documented |
| Device policy | **PyTorch MPS / Metal (experimental)** on mwt1 | user decision |
| CUDA | **optional** — Linux GPU hosts only | documented |

## TripoSR: Metal/MPS on mwt1 (experimental)

**User decision:** try **Metal/MPS**, not CUDA, for TripoSR on this Apple M4.

| Backend | Role on mwt1 | Role elsewhere |
|---------|--------------|----------------|
| **PyTorch MPS** | **Preferred** path (experimental) | — |
| CUDA + ~6GB VRAM | **Not available** here (no NVIDIA) | Optional on Linux GPU nodes |
| CPU-only torch | Not acceptable for TripoSR happy path | Fail closed |

Capability id `cuda_pytorch` (legacy name) means “GPU PyTorch ready”: **MPS available** *or* **CUDA with enough VRAM**. Probes **fail closed** with remediation if neither works.

Caveats:

- Upstream TripoSR / `torchmcubes` are CUDA-oriented; **MPS is experimental** — first successful `run.py` on M4 must be recorded here before calling the stage production-ready.
- Adapter/default invoke should use device `mps` when MPS probes pass (not `cuda:0`).
- Install torch **macOS/MPS** wheels — never a CUDA index URL on this host.
- Put checkout + weights on **AlanTBrain**, not home.

### Install sketch (after AlanTBrain is writable)

```bash
ROOT=/Volumes/AlanTBrain/composite3dgen
mkdir -p "$ROOT"/{jobs,media,vendor}
python3 -m venv "$ROOT/.venv"
source "$ROOT/.venv/bin/activate"
# Install current macOS arm64 PyTorch (MPS) — pin versions when proven:
pip install torch torchvision
python -c "import torch; assert torch.backends.mps.is_available(); print(torch.__version__, 'mps_ok')"
pip install 'Pillow>=10' numpy
git clone https://github.com/VAST-AI-Research/TripoSR.git "$ROOT/vendor/TripoSR"
cd "$ROOT/vendor/TripoSR" && git checkout 107cefdc244c39106fa830359024f6a2f1c78871
pip install -r requirements.txt
# Smoke (device mps — adjust if run.py needs --device mps):
python run.py --help
```

`run.py` flags used by the adapter: input image(s), `--output-dir`, `--model-save-format glb` (and `--device mps` when wiring live runs). Outputs: `{output_dir}/0/mesh.glb`.

If MPS install or inference fails → leave `triposr` stage blocked; use cloud Tripo/Hi3D after QA miss + `--spend`, or a Linux CUDA node.

## Capability checklist (post-probe)

| Capability | Purpose | MWT1 status |
|------------|---------|-------------|
| SSH (LAN) | Reach node | **verified** from mwt1 worker (cloud VM cannot) |
| Writable job root | Stage media / pull GLB | AlanTBrain **preferred** (ACL TBD); home bootstrap ready |
| `ffmpeg` | Frame extract | **ready** |
| Python image stack (Pillow) | Quality / composites | **missing** |
| GPU PyTorch (`cuda_pytorch`) | TripoSR | **missing** torch; target = **MPS** (experimental) |
| Pinned TripoSR + `run.py` | Local draft | **missing** |
| `blender` | Explode / QA stills | **ready** (5.2.3 LTS) |
| `colmap` / Meshroom | Photogrammetry (U6) | **missing** |

## Stage → capability map

| Stage | Required | On this MWT1 |
|-------|----------|--------------|
| ingest (ffmpeg) | ssh, job_root_writable, ffmpeg | ready once job root is AlanTBrain-writable (or bootstrap) |
| quality / composites | ssh, job_root_writable, python_image | **blocked** until Pillow |
| TripoSR draft | ssh, job_root_writable, cuda_pytorch (MPS\|CUDA), triposr | **blocked** until MPS torch + checkout proven |
| Photogrammetry | ssh, job_root_writable, colmap\|meshroom | **blocked** |
| Blender explode | ssh, job_root_writable, blender | **ready** (paths verified) |
| QA renders | ssh, job_root_writable, blender, python_image | **blocked** on Pillow |

## ffmpeg / COLMAP

- `ffmpeg` **verified** at `/opt/homebrew/bin/ffmpeg` 9.0.2.
- COLMAP / Meshroom **verified missing** — see `photogrammetry.md`.

## Files in this directory

- `triposr.service.example` — oneshot shape; enable only after AlanTBrain checkout + MPS smoke.
- `photogrammetry.md` — COLMAP/Meshroom (both missing).

## Policy

- Prefer MWT1 for stages whose capabilities are ready; AlanTBrain for all heavy I/O.
- Controller degraded mode when MWT1 unreachable from the controller.
- **Never** embed cloud API keys on MWT1.
- Executor selection uses capability health; TripoSR SSH wiring only when stage probes pass (MPS or CUDA).

## Re-probe

```bash
df -h /Volumes/AlanTBrain /System/Volumes/Data
ls -la /Volumes/AlanTBrain/composite3dgen 2>&1
mkdir -p /Volumes/AlanTBrain/composite3dgen/jobs && touch /Volumes/AlanTBrain/composite3dgen/jobs/.w && rm $_
command -v ffmpeg; ffmpeg -version | head -n 1
command -v blender; blender --version 2>&1 | head -n 1
python3 -c "from PIL import Image; print('pillow_ok')"
python3 -c "import torch; print(torch.__version__, torch.backends.mps.is_available(), torch.cuda.is_available())"
test -f /Volumes/AlanTBrain/composite3dgen/vendor/TripoSR/run.py && \
  git -C /Volumes/AlanTBrain/composite3dgen/vendor/TripoSR rev-parse HEAD
PYTHONPATH=src python3 -m composite3dgen doctor --live
```
