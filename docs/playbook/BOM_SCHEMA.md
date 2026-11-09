# BOM / hierarchy schema

Multi-level exploded hierarchies are a first-class output. AI “parts” are **not** an engineering BOM until Blender naming + QA (and for RC leaf fitment, the CAD lane) say so.

## Depth tiers

| Tier | Meaning | v1 ship target |
|------|---------|----------------|
| **L1** | Major assemblies (e.g. chassis, cabin, boom) | Yes |
| **L2** | Sub-assemblies under L1 | Yes |
| **Leaf** | Individual replaceable parts | Schema-ready; quality-gated |

GLM staging assembly JSON historically held L1/L2 mesh groups only. Leaf BOM is not claimed from AI alone.

## Planned artifacts

| Artifact | Role |
|----------|------|
| `schema/parts.hierarchy.schema.json` | Canonical hierarchy + explode metadata (U4) |
| `schema/subject.manifest.schema.json` | Subject / domain / units / capture refs (U2) |
| `schema/job.provider.schema.json` | Provider job records + cost fields (U3/U7) |
| Job `parts.json` | Instance export from Blender Empty parents |
| Job GLB | Mesh + hierarchy for DCC / web viewers |

Stub schema files may be empty or minimal until U2/U4 land. Do not invent fake production JSON that pretends leaf completeness.

## Blender convention (U4)

- Prefer **Empty parents** (or Full Collection Hierarchy export) so GLB round-trips parent links.
- Collections alone do **not** reliably round-trip in GLB — do not rely on them as the sole hierarchy carrier.
- Explode offsets recorded per node for L1/L2 stills (`*-exploded-l1.png` naming from prior art).
- Orthographic / silhouette stills generated on MWT1 next to the job dir for QA scoring.

## Naming

- Stable IDs in schema (`part_id`); human labels separate.
- Domain profiles (GLM vs RC) may add mate-chain / dimension-register fields without forking the core pipeline.
- Verification naming: `local-*` / `live-*` / `*-exploded-l1.png` (and L2 equivalents).

## QA expectations (U7)

- L1/L2 completeness: every mesh assigned under the hierarchy; no anonymous dump roots.
- Leaf claims require explicit tier flag + (for RC) dimension-register evidence.
- Cost ledger marks Blender/local stages `$0`.

## Related

- [WORKFLOW.md](WORKFLOW.md) — BOM depth gate
- [COST_QUALITY_MATRIX.md](COST_QUALITY_MATRIX.md) — when to promote providers vs CAD
