# Examples

## Build packs from a job directory (U2)

Job layout:

```
job/
  manifests/subject.manifest.json
  frames/   # or photos/ / video/ via capture.media_paths
```

```bash
# Prefer MWT1 when healthy; force local for controller degraded mode / CI
python -m composite3dgen build-packs ./path/to/job --executor local

# Equivalent dry-run/local run stage
python -m composite3dgen run ./path/to/job --executor local
```

Sample fixture:

```bash
python -m composite3dgen build-packs fixtures/u2-sample --executor local
```

Expects identical `build_packs/{triposr,tripo,hi3d,rodin}/` with `README.md` and
cardinal JPEGs. Packs missing `front.jpg` are rejected.

## Global flags

```bash
python -m composite3dgen --help
python -m composite3dgen doctor          # capability matrix (no live SSH)
# python -m composite3dgen doctor --live  # LAN / mwt1 worker only
# --spend authorizes paid cloud later (U3+); ignored for build-packs
```
