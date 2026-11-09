# Composite3DGen

Playbook + pipeline for **multi-angle composite 3D generation** with **multi-level exploded hierarchies** (L1/L2 first; leaf BOM schema-ready). Optimized for **cost and quality**, not speed.

Primary local compute: **MWT1** (`ssh mwt1`) — TripoSR drafts, Blender explode/hierarchy/QA, ingest/packs, optional photogrammetry. Paid cloud (Tripo / Hi3D / Rodin / Seedance) only behind an explicit `--spend` gate after local QA fails.

## Status

**U1 bootstrap** — package layout, CLI stub, playbook skeleton. Pipeline stages land in U2–U7.

## Quick start

```bash
# Editable install (Python ≥ 3.10)
pip install -e .

# Or run without installing via PYTHONPATH / src layout:
PYTHONPATH=src python -m composite3dgen --help
```

Smoke:

```bash
python -m composite3dgen --help
```

## CLI (stub)

| Flag / command | Meaning |
|----------------|---------|
| `--spend` | Authorize paid cloud provider calls. Default: dry-run / local-only. |
| `--prefer-local` / `--no-prefer-local` | Prefer MWT1/local free stages (default: on). |
| `run [job_dir]` | Run a job (stub until U2+). |
| `doctor` | Probe local/MWT1 capabilities (stub until U3b). |

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
