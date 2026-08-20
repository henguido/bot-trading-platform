"""Evaluación de perpetual basis reutilizando el motor estadístico v15.

Se transforma score=-basis para que el bottom-5 del motor v15 sea exactamente
el top-5 de basis predeclarado en v17. No se prueba la dirección contraria.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

from backend.economia.basis_spot_v17 import ObservacionBasisV17
from backend.economia.evaluacion_premium_v15 import ResultadoAnualPremiumV15, evaluar_premium_v15
from backend.economia.premium_spot_v15 import ObservacionPremiumSpotV15
from backend.economia.protocolo_basis_v17 import (
    CLASE_BASIS_PROMETEDOR_V17, CLASE_BASIS_SIN_SENAL_V17, MIN_ANIOS_APTOS_V17,
)


@dataclass(frozen=True)
class ResultadoBasisV17:
    anuales: Tuple[ResultadoAnualPremiumV15, ...]
    anios_aptos: int
    clase: str

    @property
    def prometedor(self) -> bool:
        return self.clase == CLASE_BASIS_PROMETEDOR_V17


def evaluar_basis_v17(observaciones: Sequence[ObservacionBasisV17]) -> ResultadoBasisV17:
    adaptadas = tuple(
        ObservacionPremiumSpotV15(
            symbol=o.symbol,
            timestamp_signal_ms=o.timestamp_signal_ms,
            premium_close=-o.basis_perp,
            timestamp_entrada_ms=o.timestamp_entrada_ms,
            retorno_spot_siguiente=o.retorno_spot_siguiente,
        )
        for o in observaciones
    )
    base = evaluar_premium_v15(adaptadas)
    n = base.anios_aptos
    clase = CLASE_BASIS_PROMETEDOR_V17 if n >= MIN_ANIOS_APTOS_V17 else CLASE_BASIS_SIN_SENAL_V17
    return ResultadoBasisV17(anuales=base.anuales, anios_aptos=n, clase=clase)
