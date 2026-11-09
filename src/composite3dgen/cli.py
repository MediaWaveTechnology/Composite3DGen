"""CLI entrypoint for Composite3DGen.

Paid cloud providers stay behind an explicit ``--spend`` gate.
Local/MWT1 stages are preferred by default (``prefer_local`` / MWT1).
U2 wires ``build-packs`` and dry-run ``run`` for ingest→packs only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
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
        help="Run job stages (U2: local ingest→packs when job_dir given)",
    )
    run.add_argument(
        "job_dir",
        nargs="?",
        default=None,
        help="Path to a job directory with subject manifest + media/frames",
    )
    run.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional path to subject.manifest.json (default: job_dir/manifests/)",
    )
    run.add_argument(
        "--executor",
        choices=("auto", "mwt1", "local"),
        default="auto",
        help="Force executor selection (default: auto — MWT1 if healthy)",
    )

    build_packs = sub.add_parser(
        "build-packs",
        help="Ingest → quality → canonical angles → identical provider packs (U2)",
    )
    build_packs.add_argument(
        "job_dir",
        type=Path,
        help="Job directory (writes frames/, manifests/, build_packs/)",
    )
    build_packs.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional path to subject.manifest.json",
    )
    build_packs.add_argument(
        "--executor",
        choices=("auto", "mwt1", "local"),
        default="auto",
        help="Force executor selection (default: auto — MWT1 if healthy)",
    )
    build_packs.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable summary JSON",
    )

    sub.add_parser(
        "doctor",
        help="Probe local/MWT1 capabilities (stub surface — full probes in U3b)",
    )

    return parser


def _force_from_args(executor: str) -> str | None:
    if executor == "auto":
        return None
    return executor


def _run_build_packs(args: argparse.Namespace) -> int:
    from composite3dgen.composites.select import MissingFrontError
    from composite3dgen.manifest import ManifestError
    from composite3dgen.packs.builder import MissingFrontPackError
    from composite3dgen.pipeline import run_build_packs

    prefer_mwt1 = bool(args.prefer_local)
    force = _force_from_args(args.executor)
    try:
        result = run_build_packs(
            Path(args.job_dir),
            manifest_path=args.manifest,
            prefer_mwt1=prefer_mwt1,
            force_executor=force,  # type: ignore[arg-type]
        )
    except (ManifestError, MissingFrontError, MissingFrontPackError, FileNotFoundError) as exc:
        print(f"composite3dgen: error: {exc}", file=sys.stderr)
        return 1

    summary = result.summary()
    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"build-packs ok: subject={result.manifest.subject_id} "
            f"executor={result.executor.name} "
            f"angles={sorted(result.selection.angles)} "
            f"providers={result.packs.providers}"
        )
        print(f"  packs: {result.packs.packs_root}")
        print(f"  quality: {result.frame_quality_path}")
        print(f"  reason: {result.executor.reason}")
    if args.spend:
        print(
            "note: --spend ignored for build-packs (local stage only; no cloud).",
            file=sys.stderr,
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "build-packs":
        return _run_build_packs(args)

    if args.command == "run":
        if args.job_dir:
            # U2: dry-run / local-only path runs ingest→packs.
            ns = argparse.Namespace(
                job_dir=args.job_dir,
                manifest=args.manifest,
                executor=args.executor,
                prefer_local=args.prefer_local,
                spend=args.spend,
                json=False,
            )
            code = _run_build_packs(ns)
            if code == 0 and not args.spend:
                print(
                    "run: U2 local stages complete (ingest→packs). "
                    "Provider reconstruct / Blender / QA land in U3–U7.",
                    file=sys.stderr,
                )
            elif code == 0 and args.spend:
                print(
                    "run: U2 local packs ready; paid providers not invoked yet "
                    "(U3 adapters + spend gate).",
                    file=sys.stderr,
                )
            return code

        mode = "spend" if args.spend else "dry-run / local-only"
        prefer = "prefer_local" if args.prefer_local else "no-prefer-local"
        print(
            f"composite3dgen run: no job_dir ({mode}, {prefer}). "
            "Pass a job directory to run U2 ingest→packs.",
            file=sys.stderr,
        )
        return 0

    if args.command == "doctor":
        from composite3dgen.nodes.capabilities import probe_stub
        from composite3dgen.nodes.executor import select_executor

        report = probe_stub()
        selection = select_executor(prefer_mwt1=bool(args.prefer_local))
        print(json.dumps({"probe": report, "executor_selection": {
            "name": selection.name,
            "reason": selection.reason,
            "prefer_mwt1": selection.prefer_mwt1,
        }}, indent=2))
        print(
            "composite3dgen doctor: U2 selection hook only; "
            "full MWT1 capability probes land in U3b.",
            file=sys.stderr,
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
