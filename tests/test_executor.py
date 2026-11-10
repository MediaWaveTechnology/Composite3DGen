"""Node executor selection (MWT1 vs local)."""

from __future__ import annotations

from composite3dgen.nodes import LocalExecutor, MWT1Executor, select_executor
from composite3dgen.nodes import mwt1 as mwt1_mod


def test_select_local_when_mwt1_unhealthy() -> None:
    mwt1_mod.set_health_probe(lambda: False)
    try:
        sel = select_executor(prefer_mwt1=True)
        assert sel.name == "local"
        assert isinstance(sel.executor, LocalExecutor)
        assert "degraded" in sel.reason.lower() or "unhealthy" in sel.reason.lower()
    finally:
        mwt1_mod.set_health_probe(None)


def test_select_mwt1_when_healthy() -> None:
    mwt1_mod.set_health_probe(lambda: True)
    try:
        sel = select_executor(prefer_mwt1=True)
        assert sel.name == "mwt1"
        assert isinstance(sel.executor, MWT1Executor)
    finally:
        mwt1_mod.set_health_probe(None)


def test_force_local() -> None:
    sel = select_executor(prefer_mwt1=True, force="local", mwt1_probe=lambda: True)
    assert sel.name == "local"
    assert sel.forced == "local"


def test_default_probe_unhealthy() -> None:
    mwt1_mod.set_health_probe(None)
    assert mwt1_mod.is_healthy() is False
