"""Select MWT1 vs controller-local executor for MWT1-capable stages (U2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from composite3dgen.nodes import mwt1

ExecutorName = Literal["mwt1", "local"]
HealthProbe = Callable[[], bool]


class Executor(Protocol):
    """Minimal executor surface for U2 local stages."""

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
    """MWT1 executor. Health uses injectable probe until U3b SSH lands."""

    probe: HealthProbe | None = None

    @property
    def name(self) -> ExecutorName:
        return "mwt1"

    def is_healthy(self) -> bool:
        return mwt1.is_healthy(self.probe)


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
    - Degraded: controller local when MWT1 unreachable.
    - ``force`` overrides selection for dry-run / debugging.

    Full SSH capability probes remain a **U3b** follow-up; U2 wires the
    selection interface and healthy-check hook only.
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
            reason="Forced MWT1 executor (U3b will enforce capability probes)",
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
        "MWT1 unhealthy or probe unimplemented — controller local degraded mode"
        if prefer_mwt1
        else "prefer_mwt1 disabled — using controller local"
    )
    return ExecutorSelection(
        executor=LocalExecutor(),
        reason=reason,
        prefer_mwt1=prefer_mwt1,
    )
