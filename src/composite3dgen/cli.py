"""CLI entrypoint for Composite3DGen (U1 stub).

Paid cloud providers stay behind an explicit ``--spend`` gate.
Local/MWT1 stages are preferred by default (``prefer_local``).
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from composite3dgen import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="composite3dgen",
        description=(
            "Composite3DGen: multi-angle composite 3D generation with "
            "multi-level explode hierarchies. Cost/quality over speed; "
            "local MWT1 stages preferred before paid cloud spend."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--spend",
        action="store_true",
        default=False,
        help=(
            "Authorize paid cloud provider calls (Tripo / Hi3D / Rodin / "
            "Seedance). Without this flag, only dry-run and local/MWT1 "
            "stages run. Requires QA miss reasons once QA gates land (U7)."
        ),
    )
    parser.add_argument(
        "--prefer-local",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Prefer MWT1 / local free stages before cloud reconstruct "
            "(default: true). Use --no-prefer-local only when deliberately "
            "skipping the local draft lane."
        ),
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    run = sub.add_parser(
        "run",
        help="Run a job (stub — implemented in later units)",
    )
    run.add_argument(
        "job_dir",
        nargs="?",
        default=None,
        help="Path to a job directory (optional until U2+)",
    )

    sub.add_parser(
        "doctor",
        help="Probe local/MWT1 capabilities (stub — U3b)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "run":
        mode = "spend" if args.spend else "dry-run / local-only"
        prefer = "prefer_local" if args.prefer_local else "no-prefer-local"
        print(
            f"composite3dgen run: stub ({mode}, {prefer}). "
            "Pipeline stages land in U2–U7.",
            file=sys.stderr,
        )
        return 0

    if args.command == "doctor":
        print(
            "composite3dgen doctor: stub. MWT1 capability probes land in U3b.",
            file=sys.stderr,
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
