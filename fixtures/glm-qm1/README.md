# Fixture: GLM QM1

Curated dry-run proofs for **U5** end-to-end: packs → virtual providers → Blender L1/L2 explode → verification checklist — **without new cloud spend**.

## Layout

```
fixtures/glm-qm1/
  frames/                     # Cardinal stills (pack intake)
  manifests/subject.manifest.json
  staging/qm1-assembly.json   # L1/L2 hierarchy (source=staging)
  recorded/
    tripo/parts-task.json     # Recorded generate_parts proof
    tripo/texture-task.json   # Recorded texture-on-parts proof
    media-refs.json           # External / future LFS refs for large GLBs
```

## Truth policy

- **Use** staging assembly + recorded Tripo task records.
- **Do not** treat live dump-truck `qm1-assembly` stubs as QM1 truth.
- Large parts (~41MB) / textured (~101MB) GLBs are **external media refs** (AlanTBrain or Git LFS) — not invented binaries in git.

## Dry-run

```bash
python -m composite3dgen dry-run fixtures/glm-qm1 --executor local --json
```

Expects `$0` this-run consumed, schema-valid `out/blender/parts.json` at tier L2, and a verification checklist under `manifests/dry_run_checklist.json`.
