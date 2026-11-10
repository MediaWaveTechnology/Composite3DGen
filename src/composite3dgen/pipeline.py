"""U2 pipeline: ingest → quality → cardinal selection → identical build packs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from composite3dgen.composites.quality import score_frames
from composite3dgen.composites.select import AngleSelection, select_canonical_angles
from composite3dgen.ingest.frames import IngestResult, ingest_media
from composite3dgen.manifest import SubjectManifest, load_manifest
from composite3dgen.nodes.executor import ExecutorName, ExecutorSelection, select_executor
from composite3dgen.packs.builder import PackBuildResult, build_provider_packs


@dataclass
class BuildPacksPipelineResult:
    """Aggregate result for the U2 local pack-building stages."""

    job_dir: Path
    manifest: SubjectManifest
    executor: ExecutorSelection
    ingest: IngestResult
    selection: AngleSelection
    packs: PackBuildResult
    frame_quality_path: Path | None = None
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "job_dir": str(self.job_dir),
            "subject_id": self.manifest.subject_id,
            "domain": self.manifest.domain,
            "executor": self.executor.name,
            "executor_reason": self.executor.reason,
            "frame_count": len(self.ingest.frames),
            "angles": {k: str(v) for k, v in self.selection.angles.items()},
            "providers": list(self.packs.providers),
            "packs_root": str(self.packs.packs_root),
            "notes": [*self.ingest.notes, *self.selection.notes, *self.packs.notes, *self.notes],
        }


def resolve_manifest(job_dir: Path, manifest_path: Path | None = None) -> SubjectManifest:
    """Load manifest from explicit path or ``job_dir/manifests/subject.manifest.json``."""
    job_dir = Path(job_dir)
    if manifest_path is not None:
        return load_manifest(manifest_path)
    default = job_dir / "manifests" / "subject.manifest.json"
    if default.is_file():
        return load_manifest(default)
    alt = job_dir / "subject.manifest.json"
    if alt.is_file():
        return load_manifest(alt)
    raise FileNotFoundError(
        f"No subject manifest found. Expected {default} or pass --manifest."
    )


def run_build_packs(
    job_dir: Path,
    *,
    manifest_path: Path | None = None,
    prefer_mwt1: bool = True,
    force_executor: ExecutorName | None = None,
    mwt1_probe: Any | None = None,
) -> BuildPacksPipelineResult:
    """Run U2 dry-run/local stages: ingest → score → select → packs.

    No paid cloud calls. Node selection prefers MWT1 when healthy.
    """
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "manifests").mkdir(parents=True, exist_ok=True)

    manifest = resolve_manifest(job_dir, manifest_path)
    selection_exec = select_executor(
        prefer_mwt1=prefer_mwt1,
        force=force_executor,
        mwt1_probe=mwt1_probe,
    )

    ingest = ingest_media(
        job_dir,
        manifest,
        executor_name=selection_exec.name,
    )
    scores = score_frames(ingest.frames)
    quality_doc = {
        "subject_id": manifest.subject_id,
        "executor": selection_exec.name,
        "frames": [s.as_dict() for s in scores],
    }
    frame_quality_path = job_dir / "manifests" / "frame_quality.json"
    frame_quality_path.write_text(json.dumps(quality_doc, indent=2) + "\n", encoding="utf-8")

    angle_selection = select_canonical_angles(ingest.frames, manifest, scores=scores)
    packs = build_provider_packs(
        job_dir,
        angle_selection,
        manifest,
        executor_name=selection_exec.name,
    )

    return BuildPacksPipelineResult(
        job_dir=job_dir,
        manifest=manifest,
        executor=selection_exec,
        ingest=ingest,
        selection=angle_selection,
        packs=packs,
        frame_quality_path=frame_quality_path,
        notes=[
            "U2 local stages only — no paid cloud providers invoked.",
            f"Executor selection: {selection_exec.reason}",
        ],
    )
