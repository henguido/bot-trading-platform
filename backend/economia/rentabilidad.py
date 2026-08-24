"""Gate deterministico de rentabilidad pre-trade (BOT 2.0-05A).

Este modulo conecta una estimacion de edge producida por una estrategia con el
modelo de costes 04A. No inventa edge a partir del score del scanner y no toca
RiskEngine, PAPER, red ni base de datos.

Reglas:
- desconocido != 0;
- si el coste round-trip no esta completo, la oportunidad es NO_EVALUABLE;
- si la estrategia no aporta edge bruto cuantificable, es NO_EVALUABLE;
- el edge neto es edge bruto - coste total round-trip;
- el margen neto minimo es una politica explicita del llamador, no un numero
  optimizado aqui;
- el multiplo edge/coste se reporta como telemetria, no es un gate oculto.

Orden previsto del ciclo:
scanner -> estrategia/edge -> costes -> rentabilidad -> MotorRiesgo -> PAPER.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from backend.economia.costes import EstimacionCostes, estimar_roundtrip

APTA = "APTA"
NO_APTA = "NO_APTA"
NO_EVALUABLE = "NO_EVALUABLE"

COSTES_INCOMPLETOS = "COSTES_INCOMPLETOS"
EDGE_DESCONOCIDO = "EDGE_DESCONOCIDO"
EDGE_NO_POSITIVO = "EDGE_NO_POSITIVO"
MARGEN_NETO_INSUFICIENTE = "MARGEN_NETO_INSUFICIENTE"

_BPS = Decimal("10000")


def _decimal(valor, *, nombre: str, permitir_none: bool = False) -> Optional[Decimal]:
    if valor is None:
        if permitir_none:
            return None
        raise ValueError(f"{nombre} es obligatorio")
    if isinstance(valor, bool):
        raise ValueError(f"{nombre} no puede ser booleano")
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{nombre} no es numerico") from None
    if not d.is_finite():
        raise ValueError(f"{nombre} debe ser finito")
    return d


@dataclass(frozen=True)
class EvaluacionRentabilidad:
    estado: str
    apta: bool
    edge_bruto_bps: Optional[Decimal]
    coste_total_bps: Optional[Decimal]
    margen_neto_minimo_bps: Decimal
    edge_neto_bps: Optional[Decimal]
    edge_neto_usd: Optional[Decimal]
    multiplo_edge_sobre_coste: Optional[Decimal]
    costes: EstimacionCostes
    motivos: Tuple[str, ...]

    @property
    def evaluable(self) -> bool:
        return self.estado != NO_EVALUABLE

    def como_dict(self) -> dict:
        def f(v):
            return float(v) if v is not None else None
        return {
            "estado": self.estado,
            "apta": self.apta,
            "edge_bruto_bps": f(self.edge_bruto_bps),
            "coste_total_bps": f(self.coste_total_bps),
            "margen_neto_minimo_bps": f(self.margen_neto_minimo_bps),
            "edge_neto_bps": f(self.edge_neto_bps),
            "edge_neto_usd": f(self.edge_neto_usd),
            "multiplo_edge_sobre_coste": f(self.multiplo_edge_sobre_coste),
            "motivos": list(self.motivos),
            "costes": self.costes.como_dict(),
        }


def evaluar_rentabilidad(*, edge_bruto_bps, costes: EstimacionCostes,
                          margen_neto_minimo_bps) -> EvaluacionRentabilidad:
    """Evalua si una oportunidad conserva margen neto despues de costes.

    `margen_neto_minimo_bps` debe declararse fuera de este modulo. Esto evita
    convertir 05A en una optimizacion post-hoc de umbrales. Puede ser cero para
    una medicion exploratoria PAPER, pero debe pasarse de forma explicita.
    """
    if not isinstance(costes, EstimacionCostes):
        raise TypeError("costes debe ser EstimacionCostes")

    margen = _decimal(margen_neto_minimo_bps, nombre="margen_neto_minimo_bps")
    if margen < 0:
        raise ValueError("margen_neto_minimo_bps no puede ser negativo")

    edge = _decimal(edge_bruto_bps, nombre="edge_bruto_bps", permitir_none=True)

    motivos = []
    if not costes.completa:
        motivos.append(COSTES_INCOMPLETOS)
    if edge is None:
        motivos.append(EDGE_DESCONOCIDO)

    if motivos:
        return EvaluacionRentabilidad(
            estado=NO_EVALUABLE,
            apta=False,
            edge_bruto_bps=edge,
            coste_total_bps=costes.total_bps,
            margen_neto_minimo_bps=margen,
            edge_neto_bps=None,
            edge_neto_usd=None,
            multiplo_edge_sobre_coste=None,
            costes=costes,
            motivos=tuple(motivos),
        )

    assert edge is not None
    assert costes.total_bps is not None

    coste_bps = costes.total_bps
    neto_bps = edge - coste_bps
    neto_usd = costes.notional_usd * neto_bps / _BPS
    multiplo = edge / coste_bps if coste_bps > 0 else None

    if edge <= 0:
        motivos.append(EDGE_NO_POSITIVO)
    if neto_bps < margen:
        motivos.append(MARGEN_NETO_INSUFICIENTE)

    apta = not motivos
    return EvaluacionRentabilidad(
        estado=APTA if apta else NO_APTA,
        apta=apta,
        edge_bruto_bps=edge,
        coste_total_bps=coste_bps,
        margen_neto_minimo_bps=margen,
        edge_neto_bps=neto_bps,
        edge_neto_usd=neto_usd,
        multiplo_edge_sobre_coste=multiplo,
        costes=costes,
        motivos=tuple(motivos),
    )


def evaluar_desde_componentes(*, edge_bruto_bps, margen_neto_minimo_bps,
                               notional_usd, spread_bps=None, bid=None, ask=None,
                               fee_taker_bps_por_lado=None,
                               slippage_bps_por_lado=None,
                               costo_ia_asignado_usd=None,
                               exigir_costo_ia: bool = False) -> EvaluacionRentabilidad:
    """Atajo puro: calcula costes 04A y aplica el gate 05A.

    `exigir_costo_ia=False` representa el camino barato sin LLM. Si una
    estrategia usa IA, el llamador debe activarlo y aportar el coste asignado;
    de lo contrario el modelo de costes fallara cerrado.
    """
    costes = estimar_roundtrip(
        notional_usd=notional_usd,
        spread_bps=spread_bps,
        bid=bid,
        ask=ask,
        fee_taker_bps_por_lado=fee_taker_bps_por_lado,
        slippage_bps_por_lado=slippage_bps_por_lado,
        costo_ia_asignado_usd=costo_ia_asignado_usd,
        exigir_costo_ia=exigir_costo_ia,
    )
    return evaluar_rentabilidad(
        edge_bruto_bps=edge_bruto_bps,
        costes=costes,
        margen_neto_minimo_bps=margen_neto_minimo_bps,
    )
