"""U1 smoke: CLI help and version."""

from __future__ import annotations

import subprocess
import sys


def test_module_help_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "composite3dgen", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "composite3dgen" in proc.stdout.lower()
    assert "--spend" in proc.stdout


def test_build_parser_spend_default_off() -> None:
    from composite3dgen.cli import build_parser

    args = build_parser().parse_args([])
    assert args.spend is False
    assert args.prefer_local is True
