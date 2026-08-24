"""Comparacion conservadora de costes de ejecucion para BOT 2.0-05A.

Este modulo NO modela fills maker ni autoriza ordenes limit. Solo cuantifica
cuanto de la friccion observada podria, como maximo teorico, evitarse si una
orden pasiva lograra ejecutarse sin pagar spread/slippage taker.

El techo maker es deliberadamente optimista y se etiqueta como tal. No debe
usarse como coste ejecutable hasta medir tasa de fill y adverse selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

_BPS = Decimal("10000")


def _decimal(valor) -> Optional[Decimal]:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not d.is_finite():
        return None
    return d


def extraer_maker_bps(account_info) -> Optional[Decimal]:
    """Lee `commissionRates.maker` de GET /api/v3/account, sin defaults."""
    if not isinstance(account_info, dict):
        return None
    rates = account_info.get("commissionRates")
    if not isinstance(rates, dict):
        return None
    tasa = _decimal(rates.get("maker"))
    if tasa is None or tasa < 0:
        return None
    return tasa * _BPS


@dataclass(frozen=True)
class ComparacionEjecucion:
    estado: str
    fee_taker_bps_por_lado: Optional[float]
    fee_maker_bps_por_lado: Optional[float]
    spread_bps: Optional[float]
    slippage_bps_por_lado: Optional[float]
    coste_taker_roundtrip_bps: Optional[float]
    coste_maker_fee_only_roundtrip_bps: Optional[float]
    ahorro_fee_roundtrip_bps: Optional[float]
    microfriccion_taker_bps: Optional[float]
    ahorro_maximo_teorico_bps: Optional[float]
    maker_es_estimacion_ejecutable: bool = False

    def como_dict(self) -> dict:
        return self.__dict__.copy()


def comparar_ejecucion(*, fee_taker_bps_por_lado, fee_maker_bps_por_lado,
                       spread_bps, slippage_bps_por_lado) -> ComparacionEjecucion:
    """Compara taker observado contra un piso maker fee-only.

    Taker round-trip usa la misma descomposicion economica de 05A:
      spread + 2*fee_taker + 2*slippage.

    El escenario maker fee-only NO es una prediccion: asume de forma optimista
    que entrada y salida pasivas llenan sin adverse selection y sin coste de
    oportunidad. Por eso solo sirve como techo del ahorro potencial.
    """
    valores = [fee_taker_bps_por_lado, fee_maker_bps_por_lado,
               spread_bps, slippage_bps_por_lado]
    ds = [_decimal(v) for v in valores]
    if any(d is None or d < 0 for d in ds):
        return ComparacionEjecucion(
            estado="NO_EVALUABLE",
            fee_taker_bps_por_lado=None if ds[0] is None else float(ds[0]),
            fee_maker_bps_por_lado=None if ds[1] is None else float(ds[1]),
            spread_bps=None if ds[2] is None else float(ds[2]),
            slippage_bps_por_lado=None if ds[3] is None else float(ds[3]),
            coste_taker_roundtrip_bps=None,
            coste_maker_fee_only_roundtrip_bps=None,
            ahorro_fee_roundtrip_bps=None,
            microfriccion_taker_bps=None,
            ahorro_maximo_teorico_bps=None,
        )

    taker, maker, spread, slip = ds
    coste_taker = spread + (Decimal("2") * taker) + (Decimal("2") * slip)
    maker_fee_only = Decimal("2") * maker
    ahorro_fee = Decimal("2") * (taker - maker)
    micro = spread + Decimal("2") * slip
    ahorro_max = coste_taker - maker_fee_only

    return ComparacionEjecucion(
        estado="DISPONIBLE",
        fee_taker_bps_por_lado=float(taker),
        fee_maker_bps_por_lado=float(maker),
        spread_bps=float(spread),
        slippage_bps_por_lado=float(slip),
        coste_taker_roundtrip_bps=float(coste_taker),
        coste_maker_fee_only_roundtrip_bps=float(maker_fee_only),
        ahorro_fee_roundtrip_bps=float(ahorro_fee),
        microfriccion_taker_bps=float(micro),
        ahorro_maximo_teorico_bps=float(ahorro_max),
    )
