"""Shared async provider job interface (U3)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

ProviderName = Literal[
    "triposr",
    "tripo",
    "hi3d",
    "rodin",
    "colmap",
    "meshroom",
    "blender",
    "seedance",
]
JobMode = Literal["dry-run", "local", "live"]
SCHEMA_VERSION = "1.0.0"


class JobStatus(str, Enum):
    """Lifecycle status for a provider job."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DRY_RUN = "dry_run"
    BLOCKED = "blocked"


# Paid cloud providers that require ``--spend`` for live HTTP.
PAID_PROVIDERS: frozenset[str] = frozenset({"tripo", "hi3d", "rodin", "seedance"})

# Local / MWT1 free reconstruct+split stages (Rodin BANG is paid — on rodin).
LOCAL_PROVIDERS: frozenset[str] = frozenset({"triposr", "colmap", "meshroom", "blender"})


@dataclass(frozen=True)
class ProviderJobRequest:
    """Inputs for submitting a provider job."""

    provider: ProviderName
    job_dir: Path
    inputs: dict[str, Any] = field(default_factory=dict)
    mode: JobMode = "dry-run"
    options: dict[str, Any] = field(default_factory=dict)
    subject_id: str | None = None

    def ensure_out_dir(self) -> Path:
        out = Path(self.job_dir) / "out" / self.provider
        out.mkdir(parents=True, exist_ok=True)
        return out


@dataclass
class ProviderJobResult:
    """Normalized result from a provider adapter."""

    provider: ProviderName
    job_id: str
    status: JobStatus
    mode: JobMode
    artifacts: dict[str, Any] = field(default_factory=dict)
    consumed: float | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    remote_task_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Serialize to ``job.provider.schema.json`` shape."""
        return {
            "schema_version": SCHEMA_VERSION,
            "provider": self.provider,
            "mode": self.mode,
            "job_id": self.job_id,
            "status": self.status.value,
            "consumed": self.consumed if self.consumed is not None else (0.0 if self.mode in ("dry-run", "local") else None),
            "artifacts": {k: str(v) if isinstance(v, Path) else v for k, v in self.artifacts.items()},
            "remote_task_id": self.remote_task_id,
            "error": self.error,
            "notes": list(self.notes),
            "meta": dict(self.meta),
        }


def new_job_id(provider: str) -> str:
    return f"{provider}-{uuid.uuid4().hex[:12]}"


@runtime_checkable
class ProviderAdapter(Protocol):
    """Async adapter contract shared by TripoSR / Tripo / Hi3D / Rodin."""

    name: ProviderName
    is_paid: bool

    async def submit(self, request: ProviderJobRequest) -> ProviderJobResult:
        """Start a job (or record a dry-run virtual job)."""

    async def poll(self, job_id: str, *, job_dir: Path | None = None) -> ProviderJobResult:
        """Poll an existing job by local job_id."""

    async def run(self, request: ProviderJobRequest) -> ProviderJobResult:
        """Submit then poll until terminal status."""
