"""Diagnostico puro de edge bruto contra costes 04A (BOT 2.0-04B-v2b).

Este modulo NO es EconomicGate y NO decide trading. Sirve para responder si una
familia de Expected Edge bruto tiene siquiera espacio economico antes de abrir
otra fase. Desconocido sigue siendo desconocido: si el modelo 04A no tiene coste
total, el diagnostico no inventa cero.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from backend.economia.costes import DISPONIBLE, EstimacionCostes

CUBRE_COSTES = "CUBRE_COSTES"
NO_CUBRE_COSTES = "NO_CUBRE_COSTES"
COSTE_NO_DISPONIBLE = "COSTE_NO_DISPONIBLE"

_DOS = Decimal("2")


def _decimal(valor, *, nombre: str) -> Decimal:
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"{nombre} es obligatorio")
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{nombre} no es numerico") from None
    if not d.is_finite():
        raise ValueError(f"{nombre} debe ser finito")
    return d


def _no_negativo(valor, *, nombre: str) -> Decimal:
    d = _decimal(valor, nombre=nombre)
    if d < 0:
        raise ValueError(f"{nombre} no puede ser negativo")
    return d


@dataclass(frozen=True)
class DiagnosticoEdgeCostes:
    edge_bruto_bps: Decimal
    coste_total_bps: Optional[Decimal]
    margen_seguridad_bps: Decimal
    edge_neto_antes_margen_bps: Optional[Decimal]
    edge_neto_despues_margen_bps: Optional[Decimal]
    estado: str
    motivos: Tuple[str, ...]

    @property
    def cubre(self) -> bool:
        return self.estado == CUBRE_COSTES


def diagnosticar_edge_vs_costes(
    edge_bruto_bps,
    costes: EstimacionCostes,
    *,
    margen_seguridad_bps=0,
) -> DiagnosticoEdgeCostes:
    """Compara retorno bruto esperado contra coste round-trip y margen.

    `edge_bruto_bps` puede ser negativo: un edge bruto adverso tambien debe
    quedar diagnosticado. El margen de seguridad, en cambio, no puede ser
    negativo porque reduciria artificialmente la friccion exigida.
    """
    edge = _decimal(edge_bruto_bps, nombre="edge_bruto_bps")
    margen = _no_negativo(margen_seguridad_bps, nombre="margen_seguridad_bps")

    if costes.estado != DISPONIBLE or costes.total_bps is None:
        motivos = tuple(f"coste_{m}_no_disponible" for m in costes.faltantes)
        if not motivos:
            motivos = ("coste_total_no_disponible",)
        return DiagnosticoEdgeCostes(
            edge_bruto_bps=edge,
            coste_total_bps=None,
            margen_seguridad_bps=margen,
            edge_neto_antes_margen_bps=None,
            edge_neto_despues_margen_bps=None,
            estado=COSTE_NO_DISPONIBLE,
            motivos=motivos,
        )

    coste_total = _no_negativo(costes.total_bps, nombre="costes.total_bps")
    neto_antes_margen = edge - coste_total
    neto_despues_margen = neto_antes_margen - margen
    if neto_despues_margen >= 0:
        estado = CUBRE_COSTES
        motivos: Tuple[str, ...] = ()
    elif neto_antes_margen < 0:
        estado = NO_CUBRE_COSTES
        motivos = ("coste_total_mayor_que_edge_bruto",)
    else:
        estado = NO_CUBRE_COSTES
        motivos = ("margen_seguridad_no_cubierto",)

    return DiagnosticoEdgeCostes(
        edge_bruto_bps=edge,
        coste_total_bps=coste_total,
        margen_seguridad_bps=margen,
        edge_neto_antes_margen_bps=neto_antes_margen,
        edge_neto_despues_margen_bps=neto_despues_margen,
        estado=estado,
        motivos=motivos,
    )


def fee_taker_break_even_por_lado_bps(
    edge_bruto_bps,
    *,
    spread_bps=0,
    slippage_bps_por_lado=0,
    costo_ia_bps=0,
    margen_seguridad_bps=0,
) -> Decimal:
    """Fee taker maxima por lado que dejaria neto cero bajo supuestos dados."""
    edge = _decimal(edge_bruto_bps, nombre="edge_bruto_bps")
    spread = _no_negativo(spread_bps, nombre="spread_bps")
    slip = _no_negativo(slippage_bps_por_lado, nombre="slippage_bps_por_lado")
    ia = _no_negativo(costo_ia_bps, nombre="costo_ia_bps")
    margen = _no_negativo(margen_seguridad_bps, nombre="margen_seguridad_bps")
    return (edge - spread - (slip * _DOS) - ia - margen) / _DOS
