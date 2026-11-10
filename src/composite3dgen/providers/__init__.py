"""Provider adapters + cost router (U3).

Adapters: TripoSR (MWT1 remote), Tripo API, Hi3D, Rodin Gen-2.5 + Custom BANG.
Router prefers local; cloud live only after QA miss or ``--spend`` rules.
"""

from composite3dgen.providers.base import (
    PAID_PROVIDERS,
    JobStatus,
    ProviderJobRequest,
    ProviderJobResult,
)
from composite3dgen.providers.router import RouteDecision, plan_routes, route_stage

__all__ = [
    "PAID_PROVIDERS",
    "JobStatus",
    "ProviderJobRequest",
    "ProviderJobResult",
    "RouteDecision",
    "plan_routes",
    "route_stage",
]
