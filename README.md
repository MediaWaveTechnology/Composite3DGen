# Composite3DGen

Playbook + pipeline for **multi-angle composite 3D generation** with **multi-level exploded hierarchies** (L1/L2 first; leaf BOM schema-ready). Optimized for **cost and quality**, not speed.

Primary local compute: **MWT1** (`ssh mwt1`) — TripoSR drafts, Blender explode/hierarchy/QA, ingest/packs, optional photogrammetry. Paid cloud (Tripo / Hi3D / Rodin / Seedance) only behind an explicit `--spend` gate after local QA fails.

## Status

**U2** — subject manifest + ingest/quality/cardinal packs (MWT1-capable selection). Provider adapters / Blender / QA land in U3–U7.

## Quick start

```bash
# Editable install (Python ≥ 3.10)
pip install -e ".[dev]"

# Or run without installing via PYTHONPATH / src layout:
PYTHONPATH=src python -m composite3dgen --help
```

Smoke:

```bash
python -m composite3dgen --help
python -m composite3dgen build-packs path/to/job --executor local
```

## CLI

| Flag / command | Meaning |
|----------------|---------|
| `--spend` | Authorize paid cloud provider calls. Default: dry-run / local-only. |
| `--prefer-local` / `--no-prefer-local` | Prefer MWT1/local free stages (default: on). |
| `build-packs <job_dir>` | U2: ingest → quality → identical `build_packs/{triposr,tripo,hi3d,rodin}/`. |
| `run [job_dir]` | With a job dir, runs U2 local ingest→packs; later units add reconstruct. |
| `doctor` | Executor selection + stub probe (full MWT1 capabilities in U3b). |

MWT1 is preferred for ffmpeg ingest / quality / packs when healthy; controller local is the degraded fallback. Full SSH capability probes are a **U3b** follow-up.

## Playbook

| Doc | Purpose |
|-----|---------|
| [docs/playbook/WORKFLOW.md](docs/playbook/WORKFLOW.md) | Stages, gates, spend policy, MWT1 local-first |
| [docs/playbook/CAPTURE_CHECKLIST.md](docs/playbook/CAPTURE_CHECKLIST.md) | Multi-angle capture requirements |
| [docs/playbook/COST_QUALITY_MATRIX.md](docs/playbook/COST_QUALITY_MATRIX.md) | Routing: local → TripoSR → cloud promote |
| [docs/playbook/BOM_SCHEMA.md](docs/playbook/BOM_SCHEMA.md) | Hierarchy / explode depth (L1/L2/leaf) |

## Layout

```
src/composite3dgen/   # Package (ingest, packs, providers, nodes, blender, qa)
docs/playbook/        # Operator playbook
schema/               # JSON schemas (stubs → U2/U4)
deploy/mwt1/          # MWT1 install notes (U3b)
fixtures/             # GLM QM1 + RC DEX410 curated proofs (U5/U6)
tests/                # Unit / integration tests
examples/             # Minimal usage examples
```

## Secrets

**Never commit API keys or credentials.** Load Tripo / Hi3D / Rodin / Seedance secrets from Bitwarden or environment variables on the controller. See [AGENTS.md](AGENTS.md).

## License

Proprietary — MediaWave Technology.
