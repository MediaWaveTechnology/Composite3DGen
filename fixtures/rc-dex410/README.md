# Fixture: RC DEX410 (U6 domain profile)

DEX410-style **dimension register** + CAD / photogrammetry hooks for RC leaf fitment.

| Artifact | Role |
|----------|------|
| `dimension-register.json` | Confirmed vs inferred dimensions + mate-chain (schema `dimension.register`) |
| `manifests/subject.manifest.json` | Subject domain=`rc` |
| `staging/parts-hierarchy.l1l2.json` | BOM ids referenced by mate-chain (leaf nodes schema-valid; fitment still CAD-gated) |

## Commands

```bash
# Validate register + CadQuery dry-run (missing binary → structured next_steps)
python -m composite3dgen cad fixtures/rc-dex410 --executor local --json

# Photogrammetry dry-run when COLMAP/Meshroom missing (expected on MWT1 until install)
python -m composite3dgen photogrammetry fixtures/rc-dex410 --executor local --json
```

## Policy

- No Fusion license secrets or private CAD binaries in git.
- Autodesk GUI for v1 handoff is **Fusion-only** — see `docs/playbook/FUSION_HANDOFF.md`.
- **3ds Max is later-phase** (not U6).
- Prefer CadQuery + photogrammetry on **MWT1** / AlanTBrain when installed.
- Leaf fitment claims need at least one **confirmed** dimension — inferred-only registers fail validation.
