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

## GLM QM1 dry-run E2E (U5)

```bash
python -m composite3dgen dry-run fixtures/glm-qm1 --executor local --json
```

Runs packs → virtual TripoSR/Tripo jobs → Blender L1/L2 from
`staging/qm1-assembly.json` → `manifests/dry_run_checklist.json`.
Reuses `recorded/tripo/*` proofs; large GLBs stay as external/LFS refs.
Refuses `--spend` (zero new cloud spend).

## QA gates + cost ledger (U7)

```bash
# BOM gate on QM1 staging hierarchy (skip silhouette if no stills)
python -m composite3dgen qa fixtures/glm-qm1 --skip-silhouette --json

# Promote-to-hero policy (Seedance post-QA only)
python -m composite3dgen qa /dev/null --policy

# --spend hard-blocked without QA miss under prefer_local:
# python -m composite3dgen --spend run ./job --qa-miss silhouette --stage tripo
```

## Global flags

```bash
python -m composite3dgen --help
python -m composite3dgen doctor          # capability matrix (no live SSH)
# python -m composite3dgen doctor --live  # LAN / mwt1 worker only
# --spend requires QA miss reasons when prefer_local (U7); ignored for build-packs / refused by dry-run
```
