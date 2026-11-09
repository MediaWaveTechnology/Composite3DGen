"""Compute node contracts (MWT1) + executor selection."""

from composite3dgen.nodes.capabilities import (
    BASE_REQUIRED,
    STAGE_REQUIREMENTS,
    CapabilityError,
    CapabilityName,
    StageName,
)
from composite3dgen.nodes.executor import (
    Executor,
    ExecutorSelection,
    LocalExecutor,
    MWT1Executor,
    select_executor,
)
from composite3dgen.nodes.health import (
    HealthReport,
    capability_matrix_fixture,
    run_health_check,
)

__all__ = [
    "BASE_REQUIRED",
    "STAGE_REQUIREMENTS",
    "CapabilityError",
    "CapabilityName",
    "Executor",
    "ExecutorSelection",
    "HealthReport",
    "LocalExecutor",
    "MWT1Executor",
    "StageName",
    "capability_matrix_fixture",
    "run_health_check",
    "select_executor",
]
