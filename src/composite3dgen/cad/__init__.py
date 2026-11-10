"""RC CAD lane: dimension register + CadQuery adapter (U6).

Fusion GUI handoff is documented under ``docs/playbook/FUSION_HANDOFF.md``.
3ds Max is a later-phase workstation path — not part of U6.
"""

from composite3dgen.cad.cadquery_adapter import (
    CadQueryResult,
    run_cadquery,
)
from composite3dgen.cad.register import (
    DimensionRegister,
    DimensionRegisterError,
    load_dimension_register,
    validate_dimension_register,
)

__all__ = [
    "CadQueryResult",
    "DimensionRegister",
    "DimensionRegisterError",
    "load_dimension_register",
    "run_cadquery",
    "validate_dimension_register",
]
