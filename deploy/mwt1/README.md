# MWT1 deploy notes

MWT1 is the primary local compute node for Composite3DGen.

| Fact | Value | Status |
|------|-------|--------|
| SSH Host alias | `mwt1` | expected |
| LAN address | `192.168.50.212` | expected |
| SSH user | `davethompson` | expected |
| Job root | `~/composite3dgen/jobs/` | expected |
| TripoSR vendor dir | `~/composite3dgen/vendor/TripoSR` | expected |
| TripoSR pin commit | `107cefdc244c39106fa830359024f6a2f1c78871` | documented pin (checkout **verify on LAN**) |
| TripoSR weights | `stabilityai/TripoSR` (Hugging Face) | documented |
| Blender path | `<verify on LAN>` | **not verified from cloud** |
| ffmpeg path | `<verify on LAN>` | **not verified from cloud** |
| CUDA device / VRAM | `<verify on LAN>` (need ≥ ~6GB for TripoSR) | **not verified from cloud** |
| COLMAP path | `<verify on LAN>` (optional) | **not verified from cloud** |
| Meshroom path | `<verify on LAN>` (optional) | **not verified from cloud** |

**Do not invent verified Blender/CUDA/COLMAP paths.** Cloud agents cannot SSH to `192.168.50.212` (private LAN). Live facts come from:

1. `composite3dgen doctor --live` on a LAN controller, or
2. A follow-up agent on the **mwt1 self-hosted worker** (`f75a6644-73f7-4bb5-814f-ace1fafc0279`), writing `/cursor/stores/bc-324ff812-5250-4e5d-8668-d1094cebdfc5/internal/mwt1-capability-probe.md` — fold verified values from that file into this table only when present.

## Capability checklist

| Capability | Purpose | Required for |
|------------|---------|--------------|
| SSH | Reach node | all MWT1 stages |
| Writable job root | Stage media / pull GLB | all MWT1 stages |
| `ffmpeg` | Frame extract | ingest |
| Python image stack (Pillow; numpy optional) | Quality / composites | quality_composites |
| CUDA / PyTorch (~6GB+ VRAM) | TripoSR | triposr |
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
# Without verified Blender / without transport → dry-run parts.json only
# (`<verify on LAN>` — do not invent paths)
```

## Install TripoSR (on MWT1 — run on LAN)

```bash
mkdir -p ~/composite3dgen/vendor ~/composite3dgen/jobs
git clone https://github.com/VAST-AI-Research/TripoSR.git ~/composite3dgen/vendor/TripoSR
cd ~/composite3dgen/vendor/TripoSR
git checkout 107cefdc244c39106fa830359024f6a2f1c78871
python3 -m venv .venv && source .venv/bin/activate
# Install CUDA-matched torch first, then:
pip install -r requirements.txt
# Weights pull from Hugging Face on first run: stabilityai/TripoSR
python run.py --help
```

`run.py` flags used by the adapter: input image(s), `--output-dir`, `--model-save-format glb`. Outputs land at `{output_dir}/0/mesh.glb` (or `.obj`).

## CUDA notes

- TripoSR feedforward needs roughly **6GB+ VRAM**.
- Match locally installed CUDA major with the PyTorch wheel CUDA major.
- `torchmcubes` CUDA build issues usually mean CUDA/toolchain mismatch — see upstream TripoSR README.

## ffmpeg / COLMAP

- `ffmpeg` is required for video ingest on the happy path.
- COLMAP / Meshroom are optional until U6 photogrammetry execution; probe them now so doctor reports readiness.

## Files in this directory

- `triposr.service.example` — example oneshot unit shape (no secrets; jobs are SSH-driven)
- `photogrammetry.md` — COLMAP/Meshroom notes (U6)

## Policy

- Prefer MWT1 for every stage that does not require a paid cloud API.
- Controller degraded mode (`--executor local`) is fallback only.
- **Never** embed Tripo / Hi3D / Rodin / Seedance API keys on MWT1 or in this README.
- Executor selection: `nodes.executor.select_executor` uses capability health (not bare ping).
- TripoSR adapter uses injectable `RemoteFSTransport`; CLI wires `SubprocessSSHTransport` only when the `triposr` stage probes pass.

## Follow-up commands (mwt1 worker / LAN)

Exact commands for a live probe agent:

```bash
hostname; whoami
command -v ffmpeg; ffmpeg -version | head -n 1
command -v blender || ls /usr/bin/blender /usr/local/bin/blender 2>/dev/null
blender --version 2>&1 | head -n 1
python3 -c "from PIL import Image; print('pillow_ok')"
python3 -c "import torch; print(torch.__version__, torch.cuda.is_available()); print(torch.cuda.get_device_properties(0).total_memory/(1024**3) if torch.cuda.is_available() else 'no_cuda')"
command -v colmap; command -v meshroom_batch; command -v Meshroom
mkdir -p ~/composite3dgen/jobs && touch ~/composite3dgen/jobs/.write_test && rm ~/composite3dgen/jobs/.write_test && echo job_root_ok
test -f ~/composite3dgen/vendor/TripoSR/run.py && git -C ~/composite3dgen/vendor/TripoSR rev-parse HEAD
# From repo checkout on controller/worker:
PYTHONPATH=src python3 -m composite3dgen doctor --live
```

Record results into `internal/mwt1-capability-probe.md` (project store), then update the status table above — mark **verified** only for values present in that probe file.
