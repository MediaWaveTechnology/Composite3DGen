"""CLI entrypoint for Composite3DGen.

Paid cloud providers stay behind an explicit ``--spend`` gate.
Local/MWT1 stages are preferred by default (``prefer_local`` / MWT1).
U3b wires capability probes into executor selection + TripoSR transport.
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
            "stages run. Live cloud still needs QA miss reasons when "
            "prefer_local is on (full ledger in U7)."
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
        help="Run job stages: U2 packs + U3 routed provider jobs (dry-run default)",
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
    run.add_argument(
        "--skip-packs",
        action="store_true",
        help="Skip U2 ingest→packs (use existing build_packs/)",
    )
    run.add_argument(
        "--providers-only",
        action="store_true",
        help="Alias for --skip-packs: only run the U3 router + adapters",
    )
    run.add_argument(
        "--qa-miss",
        action="append",
        default=[],
        metavar="KIND",
        help=(
            "Record a QA miss kind justifying cloud promote "
            "(angle_coverage|part_fidelity|hard_surface|texture|"
            "silhouette|bom_completeness|operator_override). Repeatable."
        ),
    )
    run.add_argument(
        "--stage",
        action="append",
        default=[],
        metavar="STAGE",
        help=(
            "Explicit route stage(s): triposr|photogrammetry|tripo|hi3d|"
            "rodin_bang|rodin_gen25|seedance. Default: policy ladder."
        ),
    )
    run.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable summary JSON",
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

    route = sub.add_parser(
        "route",
        help="Print cost/quality route plan without executing adapters",
    )
    route.add_argument(
        "--qa-miss",
        action="append",
        default=[],
        metavar="KIND",
        help="QA miss kind(s); see `run --qa-miss`",
    )
    route.add_argument(
        "--stage",
        action="append",
        default=[],
        metavar="STAGE",
        help="Explicit stage(s); default policy ladder",
    )

    doctor = sub.add_parser(
        "doctor",
        help="Probe MWT1 capability matrix (injectable; --live attempts SSH)",
    )
    doctor.add_argument(
        "--live",
        action="store_true",
        default=False,
        help=(
            "Attempt live SSH to Host mwt1. Cloud VMs typically cannot reach "
            "the private LAN — run this from a LAN controller or mwt1 worker."
        ),
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Print JSON report (default)",
    )

    dry = sub.add_parser(
        "dry-run",
        help=(
            "U5: end-to-end dry-run — packs → virtual providers → Blender "
            "L1/L2 hierarchy → verification checklist (no cloud spend; "
            "reuses recorded GLM/Tripo proofs when present)"
        ),
    )
    dry.add_argument(
        "job_dir",
        type=Path,
        help="Job / fixture directory (e.g. fixtures/glm-qm1)",
    )
    dry.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional path to subject.manifest.json",
    )
    dry.add_argument(
        "--hierarchy",
        type=Path,
        default=None,
        help="Optional staging hierarchy JSON (default: staging/qm1-assembly.json)",
    )
    dry.add_argument(
        "--executor",
        choices=("auto", "mwt1", "local"),
        default="auto",
        help="Force executor selection (default: auto — MWT1 if healthy)",
    )
    dry.add_argument(
        "--skip-packs",
        action="store_true",
        help="Skip U2 ingest→packs (use existing build_packs/)",
    )
    dry.add_argument(
        "--stage",
        action="append",
        default=[],
        metavar="STAGE",
        help="Virtual provider stage(s); default: triposr + tripo",
    )
    dry.add_argument(
        "--prefix",
        default="local",
        help="Verification filename prefix (local-* / live-*)",
    )
    dry.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable summary JSON",
    )

    explode = sub.add_parser(
        "explode",
        help=(
            "U4: Blender Empty hierarchy + explode GLB/parts.json + QA stills "
            "(MWT1 when capable; dry-run without Blender)"
        ),
    )
    explode.add_argument(
        "job_dir",
        type=Path,
        help="Job directory (writes out/blender/parts.json + planned stills)",
    )
    explode.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional subject.manifest.json (for subject_id)",
    )
    explode.add_argument(
        "--mesh",
        type=Path,
        default=None,
        help="Input mesh (.glb/.obj) for Blender import; optional in dry-run",
    )
    explode.add_argument(
        "--hierarchy",
        type=Path,
        default=None,
        help="Input parts hierarchy JSON (default: synthetic L1/L2 example)",
    )
    explode.add_argument(
        "--executor",
        choices=("auto", "mwt1", "local"),
        default="auto",
        help="Force executor selection (default: auto — MWT1 if healthy)",
    )
    explode.add_argument(
        "--explode-factor",
        type=float,
        default=None,
        help="Override explode factor applied to per-node offsets",
    )
    explode.add_argument(
        "--skip-stills",
        action="store_true",
        help="Skip orthographic/silhouette QA stills when Blender runs",
    )
    explode.add_argument(
        "--allow-local-blender",
        action="store_true",
        help=(
            "If local executor and `blender` is on PATH, invoke it for smoke. "
            "Happy path remains MWT1; default without Blender is dry-run."
        ),
    )
    explode.add_argument(
        "--prefix",
        default="local",
        help="Verification filename prefix (local-* / live-*)",
    )
    explode.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable summary JSON",
    )

    return parser


def _force_from_args(executor: str) -> str | None:
    if executor == "auto":
        return None
    return executor


def _parse_qa_misses(kinds: Sequence[str]):
    from composite3dgen.qa.miss import QAMiss

    allowed = {
        "angle_coverage",
        "part_fidelity",
        "hard_surface",
        "texture",
        "silhouette",
        "bom_completeness",
        "operator_override",
    }
    misses = []
    for kind in kinds:
        if kind not in allowed:
            raise ValueError(
                f"Unknown QA miss kind '{kind}'. Expected one of: {sorted(allowed)}"
            )
        misses.append(QAMiss(kind=kind))  # type: ignore[arg-type]
    return misses


def _run_build_packs(args: argparse.Namespace) -> tuple[int, dict | None]:
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
        return 1, None

    summary = result.summary()
    is_build_cmd = getattr(args, "command", None) == "build-packs"
    if is_build_cmd and getattr(args, "json", False):
        print(json.dumps(summary, indent=2))
    elif is_build_cmd or not getattr(args, "json", False):
        print(
            f"build-packs ok: subject={result.manifest.subject_id} "
            f"executor={result.executor.name} "
            f"angles={sorted(result.selection.angles)} "
            f"providers={result.packs.providers}"
        )
        print(f"  packs: {result.packs.packs_root}")
        print(f"  quality: {result.frame_quality_path}")
        print(f"  reason: {result.executor.reason}")
    if args.spend and is_build_cmd:
        print(
            "note: --spend ignored for build-packs (local stage only; no cloud).",
            file=sys.stderr,
        )
    return 0, summary


def _resolve_mwt1_triposr_transport():
    """Return SSH transport when TripoSR stage capabilities pass; else None."""
    from composite3dgen.nodes import mwt1 as mwt1_mod
    from composite3dgen.nodes.health import run_health_check

    existing = mwt1_mod.get_default_transport()
    if existing is not None:
        report = run_health_check(transport=existing)  # type: ignore[arg-type]
        if report.stages.get("triposr") == "ready":
            return existing
        return None

    # Prefer prefer_mwt1 path: probe live only when explicitly selected healthy.
    # Avoid surprising cloud agents with long SSH timeouts — try briefly via
    # default probe installed by doctor / tests, else virtualize.
    if mwt1_mod.is_healthy():
        transport = mwt1_mod.make_ssh_transport()
        report = run_health_check(transport=transport)
        if report.stages.get("triposr") == "ready":
            mwt1_mod.set_default_transport(transport)
            return transport
    return None


def _run_providers(args: argparse.Namespace, *, subject_id: str | None = None) -> int:
    from composite3dgen.providers.router import plan_routes
    from composite3dgen.providers.runner import collect_pack_inputs, run_plan

    try:
        misses = _parse_qa_misses(args.qa_miss or [])
    except ValueError as exc:
        print(f"composite3dgen: error: {exc}", file=sys.stderr)
        return 1

    stages = list(args.stage) if args.stage else None
    # Without --spend, cloud stages are dry-run; with --spend but prefer_local
    # and no misses, router keeps dry-run + block_reason (no live HTTP).
    plan = plan_routes(
        prefer_local=bool(args.prefer_local),
        spend=bool(args.spend),
        qa_misses=misses,
        stages=stages,  # type: ignore[arg-type]
    )

    job_dir = Path(args.job_dir)
    inputs = collect_pack_inputs(job_dir, "triposr")

    # Wire TripoSR live transport only when MWT1 TripoSR stage is ready.
    # Otherwise virtualize as dry-run (controller/cloud safe).
    from composite3dgen.providers.router import RouteDecision

    triposr_transport = _resolve_mwt1_triposr_transport()
    safe_plan_decisions = []
    for d in plan.decisions:
        if d.stage == "triposr" and d.mode == "local" and triposr_transport is None:
            safe_plan_decisions.append(
                RouteDecision(
                    stage=d.stage,
                    provider=d.provider,
                    mode="dry-run",
                    allowed=d.allowed,
                    block_reason=(
                        "TripoSR MWT1 transport unavailable or stage capabilities "
                        "missing; recording virtual job. Run "
                        "`composite3dgen doctor --live` on LAN / mwt1 worker."
                    ),
                    estimated_cost=0.0,
                    prefer_local=d.prefer_local,
                    spend=d.spend,
                    qa_misses=d.qa_misses,
                    notes=tuple(
                        [
                            *d.notes,
                            "Controller dry-run: TripoSR virtualized "
                            "(inject RemoteFSTransport or pass doctor --live).",
                        ]
                    ),
                )
            )
        else:
            safe_plan_decisions.append(d)
    plan.decisions = safe_plan_decisions

    # Hard spend gate: live paid mode must never run without --spend.
    live_attempts = [
        d for d in plan.decisions if d.mode == "live" and d.provider in ("tripo", "hi3d", "rodin", "seedance")
    ]
    if live_attempts and not args.spend:
        print(
            "composite3dgen: error: live paid providers require --spend "
            "(secrets via env/Bitwarden only).",
            file=sys.stderr,
        )
        return 2

    bundle = None
    if triposr_transport is not None:
        from composite3dgen.providers.runner import default_bundle

        bundle = default_bundle(remote_fs=triposr_transport)

    result = run_plan(
        plan, job_dir, subject_id=subject_id, inputs=inputs, bundle=bundle
    )
    summary = result.summary()
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        mode = "spend" if args.spend else "dry-run"
        print(
            f"providers ok: mode={mode} prefer_local={args.prefer_local} "
            f"jobs={len(result.results)}"
        )
        for job in result.results:
            print(
                f"  - {job.provider} {job.job_id} status={job.status.value} "
                f"mode={job.mode} consumed={job.consumed}"
            )
        if result.ledger_path:
            print(f"  ledger: {result.ledger_path}")
        blocked = [d for d in plan.decisions if d.block_reason]
        for d in blocked:
            print(f"  router note ({d.stage}): {d.block_reason}", file=sys.stderr)
    return 0


def _cmd_route(args: argparse.Namespace) -> int:
    from composite3dgen.providers.router import plan_routes

    try:
        misses = _parse_qa_misses(args.qa_miss or [])
    except ValueError as exc:
        print(f"composite3dgen: error: {exc}", file=sys.stderr)
        return 1
    stages = list(args.stage) if args.stage else None
    plan = plan_routes(
        prefer_local=bool(args.prefer_local),
        spend=bool(args.spend),
        qa_misses=misses,
        stages=stages,  # type: ignore[arg-type]
    )
    print(json.dumps(plan.as_dict(), indent=2))
    return 0


def _cmd_dry_run(args: argparse.Namespace) -> int:
    from composite3dgen.dryrun import run_dry_run_e2e

    if args.spend:
        print(
            "composite3dgen: error: dry-run refuses --spend "
            "(U5 success is zero new cloud spend; use `run --spend` for live).",
            file=sys.stderr,
        )
        return 2

    prefer_mwt1 = bool(args.prefer_local)
    force = _force_from_args(args.executor)
    stages = list(args.stage) if args.stage else None
    result = run_dry_run_e2e(
        Path(args.job_dir),
        manifest_path=args.manifest,
        hierarchy_path=args.hierarchy,
        prefer_mwt1=prefer_mwt1,
        force_executor=force,  # type: ignore[arg-type]
        skip_packs=bool(args.skip_packs),
        stages=stages,
        prefix=str(args.prefix),
        spend_requested=False,
    )
    summary = result.summary()
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"dry-run ok={result.ok}: subject={result.subject_id} "
            f"consumed={result.this_run_consumed} "
            f"reused={len(result.reused_records)}"
        )
        if result.explode:
            print(
                f"  explode: mode={result.explode.mode} "
                f"tier={summary.get('explode', {}).get('tier')} "
                f"parts={result.explode.parts_path}"
            )
        if result.checklist_path:
            print(f"  checklist: {result.checklist_path}")
        for item in result.checklist:
            print(f"  [{item.status}] {item.id}: {item.label}")
        for note in result.notes[:8]:
            print(f"  note: {note}")
        if result.error:
            print(f"composite3dgen: error: {result.error}", file=sys.stderr)
    return 0 if result.ok else 1


def _cmd_explode(args: argparse.Namespace) -> int:
    from composite3dgen.blender.jobs import run_blender_explode

    prefer_mwt1 = bool(args.prefer_local)
    force = _force_from_args(args.executor)
    subject_id = None
    try:
        from composite3dgen.pipeline import resolve_manifest

        subject_id = resolve_manifest(Path(args.job_dir), args.manifest).subject_id
    except Exception:  # noqa: BLE001 — hierarchy may supply subject_id
        subject_id = None

    result = run_blender_explode(
        Path(args.job_dir),
        subject_id=subject_id,
        input_mesh=args.mesh,
        hierarchy_path=args.hierarchy,
        prefer_mwt1=prefer_mwt1,
        force_executor=force,  # type: ignore[arg-type]
        explode_factor=args.explode_factor,
        skip_stills=bool(args.skip_stills),
        prefix=str(args.prefix),
        allow_local_blender=bool(args.allow_local_blender),
    )
    summary = result.summary()
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"explode ok={result.ok}: mode={result.mode} "
            f"executor={result.executor.name} "
            f"blender={summary['blender']['display']} "
            f"tier={summary.get('tier')}"
        )
        if result.parts_path:
            print(f"  parts: {result.parts_path}")
        if result.glb_path:
            print(f"  glb: {result.glb_path}")
        if result.verification:
            print(f"  verification: {len(result.verification)} still(s)")
        for note in result.notes[:6]:
            print(f"  note: {note}")
        if result.error:
            print(f"composite3dgen: error: {result.error}", file=sys.stderr)
            return 1
    if args.spend:
        print(
            "note: --spend ignored for explode (local Blender/MWT1 stage; $0).",
            file=sys.stderr,
        )
    return 0 if result.ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "build-packs":
        code, _ = _run_build_packs(args)
        return code

    if args.command == "route":
        return _cmd_route(args)

    if args.command == "dry-run":
        return _cmd_dry_run(args)

    if args.command == "explode":
        return _cmd_explode(args)

    if args.command == "run":
        if not args.job_dir:
            mode = "spend" if args.spend else "dry-run / local-only"
            prefer = "prefer_local" if args.prefer_local else "no-prefer-local"
            print(
                f"composite3dgen run: no job_dir ({mode}, {prefer}). "
                "Pass a job directory to run packs + routed providers.",
                file=sys.stderr,
            )
            return 0

        skip_packs = bool(args.skip_packs or args.providers_only)
        subject_id = None
        if not skip_packs:
            code, summary = _run_build_packs(args)
            if code != 0:
                return code
            if summary:
                subject_id = summary.get("subject_id")
                if not args.json:
                    print(
                        f"run: packs ready (subject={subject_id}). "
                        "Routing providers…",
                        file=sys.stderr,
                    )
        else:
            # Best-effort subject id from manifest
            try:
                from composite3dgen.pipeline import resolve_manifest

                subject_id = resolve_manifest(
                    Path(args.job_dir), args.manifest
                ).subject_id
            except Exception:  # noqa: BLE001
                subject_id = None

        return _run_providers(args, subject_id=subject_id)

    if args.command == "doctor":
        from composite3dgen.nodes import mwt1 as mwt1_mod
        from composite3dgen.nodes.executor import select_executor
        from composite3dgen.nodes.health import run_health_check

        live = bool(getattr(args, "live", False))
        if live:
            transport = mwt1_mod.make_ssh_transport()
            health = run_health_check(transport=transport)
            if health.ok:
                mwt1_mod.set_default_transport(transport)
                mwt1_mod.set_health_probe(lambda: True)
            else:
                mwt1_mod.set_health_probe(lambda: False)
        else:
            health = run_health_check()

        # Wire executor selection to the just-probed result when live.
        selection = select_executor(
            prefer_mwt1=bool(args.prefer_local),
            mwt1_probe=(lambda: health.ok) if live else None,
        )
        payload = {
            "contract": mwt1_mod.node_contract().as_dict(),
            "probe": health.as_dict(),
            "executor_selection": {
                "name": selection.name,
                "reason": selection.reason,
                "prefer_mwt1": selection.prefer_mwt1,
            },
        }
        print(json.dumps(payload, indent=2))
        if not health.ok:
            print(
                "composite3dgen doctor: MWT1 not ready — fail closed; "
                "see probe.notes / remediations. "
                "Cloud agents: use mwt1 self-hosted worker or LAN controller "
                "with --live.",
                file=sys.stderr,
            )
            # Non-live skipped probes are informational (exit 0). Live miss → 1.
            return 1 if live else 0
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
