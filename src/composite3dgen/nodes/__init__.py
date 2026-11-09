"""Compute node contracts.

U2 wires the MWT1-vs-local **selection interface** (healthy-check hook).
Full SSH capability probes land in U3b.
"""

from composite3dgen.nodes.executor import (
    Executor,
    ExecutorSelection,
    LocalExecutor,
    MWT1Executor,
    select_executor,
)

__all__ = [
    "Executor",
    "ExecutorSelection",
    "LocalExecutor",
    "MWT1Executor",
    "select_executor",
]
