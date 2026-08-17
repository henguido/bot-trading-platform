"""Modelo deterministico de costes pre-trade (BOT 2.0-04A).

OBJETIVO
    Expresar en una sola unidad (USD y bps sobre notional) la friccion que una
    operacion tendria que recuperar ANTES de ser economicamente rentable.

COMPONENTES
    - fee de entrada y salida (ordenes de mercado/taker en el flujo actual),
    - spread bid/ask round-trip,
    - slippage estimado por lado,
    - coste de IA que el llamador decida asignar a esta oportunidad.

INVARIANTE
    desconocido != 0. Si falta fee, slippage, spread o coste IA requerido, el
    TOTAL queda NO_DISPONIBLE. Se conserva un subtotal de componentes conocidos
    solo para observabilidad; nunca debe interpretarse como coste total.

Esta fase NO estima beneficio, NO aplica EconomicGate, NO decide y NO toca el
RiskEngine. Es aritmetica pura y no hace red ni BD.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional, Tuple

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"

_BPS = Decimal("10000")
_DOS = Decimal("2")


def _decimal(valor, *, nombre: str, permitir_none: bool = True) -> Optional[Decimal]:
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


def _no_negativo(valor, *, nombre: str) -> Optional[Decimal]:
    d = _decimal(valor, nombre=nombre)
    if d is not None and d < 0:
        raise ValueError(f"{nombre} no puede ser negativo")
    return d


def spread_bps_desde_bid_ask(bid, ask) -> Optional[Decimal]:
    """Spread completo `(ask-bid)/mid` en bps, o None si faltan precios.

    Para un round-trip que compra cruzando al ask y vende cruzando al bid, con
    el mid sin cambiar, la perdida aproximada atribuible al spread es UN spread
    completo, no dos: medio spread al entrar + medio spread al salir.
    """
    if bid is None or ask is None:
        return None
    b = _decimal(bid, nombre="bid", permitir_none=False)
    a = _decimal(ask, nombre="ask", permitir_none=False)
    if b <= 0 or a <= 0 or a < b:
        raise ValueError("bid/ask invalidos")
    mid = (a + b) / _DOS
    return ((a - b) / mid) * _BPS


@dataclass(frozen=True)
class EstimacionCostes:
    notional_usd: Decimal
    spread_bps: Optional[Decimal]
    fee_taker_bps_por_lado: Optional[Decimal]
    slippage_bps_por_lado: Optional[Decimal]
    costo_ia_asignado_usd: Optional[Decimal]

    spread_usd: Optional[Decimal]
    fees_usd: Optional[Decimal]
    slippage_usd: Optional[Decimal]

    subtotal_conocido_usd: Decimal
    total_usd: Optional[Decimal]
    total_bps: Optional[Decimal]
    estado: str
    faltantes: Tuple[str, ...]

    @property
    def completa(self) -> bool:
        return self.estado == DISPONIBLE

    def como_dict(self) -> dict:
        def f(v):
            return float(v) if v is not None else None
        return {
            "notional_usd": f(self.notional_usd),
            "spread_bps": f(self.spread_bps),
            "fee_taker_bps_por_lado": f(self.fee_taker_bps_por_lado),
            "slippage_bps_por_lado": f(self.slippage_bps_por_lado),
            "costo_ia_asignado_usd": f(self.costo_ia_asignado_usd),
            "spread_usd": f(self.spread_usd),
            "fees_usd": f(self.fees_usd),
            "slippage_usd": f(self.slippage_usd),
            "subtotal_conocido_usd": f(self.subtotal_conocido_usd),
            "total_usd": f(self.total_usd),
            "total_bps": f(self.total_bps),
            "estado": self.estado,
            "faltantes": list(self.faltantes),
        }


def estimar_roundtrip(*, notional_usd, spread_bps=None, bid=None, ask=None,
                       fee_taker_bps_por_lado=None,
                       slippage_bps_por_lado=None,
                       costo_ia_asignado_usd=None,
                       exigir_costo_ia: bool = True) -> EstimacionCostes:
    """Estima la friccion round-trip para un notional dado.

    `fee_taker_bps_por_lado` y `slippage_bps_por_lado` se duplican porque el
    flujo economico completo tiene entrada y salida. El spread se aplica una
    sola vez como spread COMPLETO (medio al entrar + medio al salir).

    `costo_ia_asignado_usd` no se inventa aqui. La fase 04C decidira si asigna
    el coste completo de una llamada, una fraccion o una estimacion historica.
    En 04A el llamador lo aporta. Por defecto se considera componente requerido.
    """
    n = _decimal(notional_usd, nombre="notional_usd", permitir_none=False)
    if n <= 0:
        raise ValueError("notional_usd debe ser positivo")

    if spread_bps is not None and (bid is not None or ask is not None):
        raise ValueError("usa spread_bps o bid/ask, no ambos")

    if spread_bps is None:
        s = spread_bps_desde_bid_ask(bid, ask)
    else:
        s = _no_negativo(spread_bps, nombre="spread_bps")

    fee = _no_negativo(fee_taker_bps_por_lado, nombre="fee_taker_bps_por_lado")
    slip = _no_negativo(slippage_bps_por_lado, nombre="slippage_bps_por_lado")
    ia = _no_negativo(costo_ia_asignado_usd, nombre="costo_ia_asignado_usd")

    spread_usd = n * s / _BPS if s is not None else None
    fees_usd = n * (fee * _DOS) / _BPS if fee is not None else None
    slippage_usd = n * (slip * _DOS) / _BPS if slip is not None else None

    faltantes = []
    if s is None:
        faltantes.append("spread")
    if fee is None:
        faltantes.append("fee_taker")
    if slip is None:
        faltantes.append("slippage")
    if exigir_costo_ia and ia is None:
        faltantes.append("costo_ia")

    conocidos: Iterable[Optional[Decimal]] = (spread_usd, fees_usd, slippage_usd, ia)
    subtotal = sum((v for v in conocidos if v is not None), Decimal("0"))

    if faltantes:
        total = None
        total_bps = None
        estado = NO_DISPONIBLE
    else:
        # Si IA no se exige y no fue aportada, economicamente aporta 0 SOLO
        # porque el llamador declaro expresamente que no corresponde incluirla.
        total = (spread_usd or Decimal("0")) + (fees_usd or Decimal("0")) \
            + (slippage_usd or Decimal("0")) + (ia or Decimal("0"))
        total_bps = total / n * _BPS
        estado = DISPONIBLE

    return EstimacionCostes(
        notional_usd=n,
        spread_bps=s,
        fee_taker_bps_por_lado=fee,
        slippage_bps_por_lado=slip,
        costo_ia_asignado_usd=ia,
        spread_usd=spread_usd,
        fees_usd=fees_usd,
        slippage_usd=slippage_usd,
        subtotal_conocido_usd=subtotal,
        total_usd=total,
        total_bps=total_bps,
        estado=estado,
        faltantes=tuple(faltantes),
    )


@dataclass
class ResumenCostes:
    """Telemetria en memoria; no participa en decisiones."""
    evaluados: int = 0
    completos: int = 0
    incompletos: int = 0
    faltantes: dict = None
    totales_bps: list = None

    def __post_init__(self):
        if self.faltantes is None:
            self.faltantes = {}
        if self.totales_bps is None:
            self.totales_bps = []

    def anotar(self, estimacion: EstimacionCostes) -> None:
        try:
            self.evaluados += 1
            if estimacion.completa:
                self.completos += 1
                self.totales_bps.append(float(estimacion.total_bps))
            else:
                self.incompletos += 1
                for motivo in estimacion.faltantes:
                    self.faltantes[motivo] = self.faltantes.get(motivo, 0) + 1
        except Exception:
            # Observabilidad fail-open: jamas puede cambiar trading.
            pass

    def linea(self, duracion_ms=None) -> str:
        try:
            extra = ""
            if self.totales_bps:
                v = sorted(self.totales_bps)
                extra += (f" total_bps[min={v[0]:.2f} p50={v[len(v)//2]:.2f} "
                          f"max={v[-1]:.2f}]")
            if self.faltantes:
                detalle = ",".join(f"{k}={v}" for k, v in sorted(self.faltantes.items()))
                extra += f" faltantes[{detalle}]"
            if duracion_ms is not None:
                extra += f" | {duracion_ms} ms"
            return (f"[COSTES-04A] evaluados={self.evaluados} completos={self.completos} "
                    f"incompletos={self.incompletos}{extra}")
        except Exception:
            return "[COSTES-04A] resumen no disponible"
