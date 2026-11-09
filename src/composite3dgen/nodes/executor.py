"""Select MWT1 vs controller-local executor for MWT1-capable stages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from composite3dgen.nodes import mwt1
from composite3dgen.nodes.capabilities import StageName

ExecutorName = Literal["mwt1", "local"]
HealthProbe = Callable[[], bool]


class Executor(Protocol):
    """Minimal executor surface for local / MWT1 stages."""

    @property
    def name(self) -> ExecutorName: ...

    def is_healthy(self) -> bool: ...


@dataclass(frozen=True)
class LocalExecutor:
    """Controller-local executor (degraded fallback when MWT1 is down)."""

    @property
    def name(self) -> ExecutorName:
        return "local"

    def is_healthy(self) -> bool:
        return True


@dataclass(frozen=True)
class MWT1Executor:
    """MWT1 executor. Health uses injectable probe / default capability check."""

    probe: HealthProbe | None = None

    @property
    def name(self) -> ExecutorName:
        return "mwt1"

    def is_healthy(self) -> bool:
        return mwt1.is_healthy(self.probe)

    def ensure_stage(self, stage: StageName) -> None:
        """Fail closed if the stage's required capabilities are missing."""
        mwt1.ensure_stage(stage, transport=mwt1.get_default_transport())


@dataclass(frozen=True)
class ExecutorSelection:
    """Result of choosing where to run MWT1-capable stages."""

    executor: Executor
    reason: str
    prefer_mwt1: bool
    forced: ExecutorName | None = None

    @property
    def name(self) -> ExecutorName:
        return self.executor.name


def select_executor(
    *,
    prefer_mwt1: bool = True,
    force: ExecutorName | None = None,
    mwt1_probe: HealthProbe | None = None,
) -> ExecutorSelection:
    """Choose MWT1 or local based on preference and health.

    Policy (from playbook):
    - Happy path: MWT1 when healthy (ingest / quality / packs).
    - Degraded: controller local when MWT1 unreachable / missing base caps.
    - ``force`` overrides selection for dry-run / debugging.

    Health is fail-closed via capability probes (U3b), not a bare ping.
    """
    if force == "local":
        return ExecutorSelection(
            executor=LocalExecutor(),
            reason="Forced local executor",
            prefer_mwt1=prefer_mwt1,
            forced=force,
        )
    if force == "mwt1":
        return ExecutorSelection(
            executor=MWT1Executor(probe=mwt1_probe),
            reason="Forced MWT1 executor (capability probes still apply to stages)",
            prefer_mwt1=prefer_mwt1,
            forced=force,
        )

    mwt1_exec = MWT1Executor(probe=mwt1_probe)
    if prefer_mwt1 and mwt1_exec.is_healthy():
        return ExecutorSelection(
            executor=mwt1_exec,
            reason="MWT1 healthy — preferred for ingest/quality/packs",
            prefer_mwt1=prefer_mwt1,
        )

    reason = (
        "MWT1 unhealthy or unreachable — controller local degraded mode"
        if prefer_mwt1
        else "prefer_mwt1 disabled — using controller local"
    )
    return ExecutorSelection(
        executor=LocalExecutor(),
        reason=reason,
        prefer_mwt1=prefer_mwt1,
    )
