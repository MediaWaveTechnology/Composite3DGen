"""QA gates, cost ledger, and promote-to-hero policy (U7).

Keep this module light: ``providers.router`` imports ``qa.miss`` at import
time, so heavy submodules (gates/promote/ledger) are imported lazily via
``__getattr__`` to avoid circular imports.
"""

from composite3dgen.qa.miss import QAMiss, summarize_misses

__all__ = [
    "BomCompletenessResult",
    "CostLedger",
    "LOCAL_PIPELINE_STAGES",
    "QAGateReport",
    "QAMiss",
    "SilhouetteGateResult",
    "assert_spend_authorized",
    "build_ledger_from_provider_jobs",
    "check_bom_completeness",
    "load_misses_file",
    "policy_summary",
    "promote_from_misses",
    "run_qa_gates",
    "run_silhouette_gate",
    "score_silhouette_pair",
    "seedance_allowed",
    "summarize_misses",
    "write_ledger",
]

_LAZY = {
    "BomCompletenessResult": ("composite3dgen.qa.bom", "BomCompletenessResult"),
    "check_bom_completeness": ("composite3dgen.qa.bom", "check_bom_completeness"),
    "QAGateReport": ("composite3dgen.qa.gates", "QAGateReport"),
    "load_misses_file": ("composite3dgen.qa.gates", "load_misses_file"),
    "run_qa_gates": ("composite3dgen.qa.gates", "run_qa_gates"),
    "CostLedger": ("composite3dgen.qa.ledger", "CostLedger"),
    "LOCAL_PIPELINE_STAGES": ("composite3dgen.qa.ledger", "LOCAL_PIPELINE_STAGES"),
    "build_ledger_from_provider_jobs": (
        "composite3dgen.qa.ledger",
        "build_ledger_from_provider_jobs",
    ),
    "write_ledger": ("composite3dgen.qa.ledger", "write_ledger"),
    "assert_spend_authorized": ("composite3dgen.qa.promote", "assert_spend_authorized"),
    "policy_summary": ("composite3dgen.qa.promote", "policy_summary"),
    "promote_from_misses": ("composite3dgen.qa.promote", "promote_from_misses"),
    "seedance_allowed": ("composite3dgen.qa.promote", "seedance_allowed"),
    "SilhouetteGateResult": ("composite3dgen.qa.silhouette", "SilhouetteGateResult"),
    "run_silhouette_gate": ("composite3dgen.qa.silhouette", "run_silhouette_gate"),
    "score_silhouette_pair": ("composite3dgen.qa.silhouette", "score_silhouette_pair"),
}


def __getattr__(name: str):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr = target
    import importlib

    mod = importlib.import_module(mod_name)
    value = getattr(mod, attr)
    globals()[name] = value
    return value
