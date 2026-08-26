"""Modelo economico puro de ejecucion PAPER.

Convierte un libro de ordenes y la fee taker conocida en un fill simulable.
No hace red, no toca DB, no ejecuta ordenes y no modifica el trading loop.

Además puede aplicar los filtros ejecutables de Binance (LOT_SIZE y notional)
antes de declarar un fill completo. Sin esos filtros conserva el contrato legacy
para consumidores puramente analíticos; el camino PAPER productivo los aporta.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Optional

from backend.economia.fuentes import (
    DISPONIBLE,
    NO_DISPONIBLE,
    estimar_slippage_compra,
    estimar_slippage_compra_base,
    estimar_slippage_venta,
)

_BPS = Decimal("10000")
_DECIMALES_EJECUCION = Decimal("0.000001")


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


def _decimal_opcional(valor, *, nombre: str) -> Optional[Decimal]:
    return None if valor is None else _decimal(valor, nombre=nombre)


@dataclass(frozen=True)
class FillPaper:
    lado: str
    estado: str
    base_ejecutada: Optional[Decimal]
    quote_bruto: Optional[Decimal]
    fee_usd: Optional[Decimal]
    quote_neto: Optional[Decimal]
    mejor_precio: Optional[Decimal]
    precio_vwap: Optional[Decimal]
    slippage_bps: Optional[Decimal]
    fee_taker_bps_por_lado: Optional[Decimal]
    motivo: Optional[str] = None

    @property
    def completo(self) -> bool:
        return self.estado == DISPONIBLE

    def como_dict(self) -> dict:
        def f(v):
            return float(v) if v is not None else None
        return {
            "lado": self.lado,
            "estado": self.estado,
            "base_ejecutada": f(self.base_ejecutada),
            "quote_bruto": f(self.quote_bruto),
            "fee_usd": f(self.fee_usd),
            "quote_neto": f(self.quote_neto),
            "mejor_precio": f(self.mejor_precio),
            "precio_vwap": f(self.precio_vwap),
            "slippage_bps": f(self.slippage_bps),
            "fee_taker_bps_por_lado": f(self.fee_taker_bps_por_lado),
            "motivo": self.motivo,
        }


def _fee_bps(valor) -> Decimal:
    fee = _decimal(valor, nombre="fee_taker_bps_por_lado")
    if fee < 0:
        raise ValueError("fee_taker_bps_por_lado no puede ser negativa")
    return fee


def _cuantizar_base(base: Decimal, *, step_size=None) -> Decimal:
    """Replica el piso a step + seis decimales del conector LIVE."""
    if step_size is None:
        return base
    step = _decimal(step_size, nombre="step_size")
    if step <= 0:
        raise ValueError("step_size debe ser positivo")
    piso = (base / step).to_integral_value(rounding=ROUND_FLOOR) * step
    return piso.quantize(_DECIMALES_EJECUCION, rounding=ROUND_FLOOR)


def _validar_filtros(base: Decimal, quote: Decimal, *, min_qty=None,
                     max_qty=None, min_notional=None) -> Optional[str]:
    minimo = _decimal_opcional(min_qty, nombre="min_qty")
    maximo = _decimal_opcional(max_qty, nombre="max_qty")
    notional = _decimal_opcional(min_notional, nombre="min_notional")
    for nombre, valor in (("min_qty", minimo), ("max_qty", maximo),
                          ("min_notional", notional)):
        if valor is not None and valor < 0:
            raise ValueError(f"{nombre} no puede ser negativo")
    if maximo is not None and maximo <= 0:
        raise ValueError("max_qty debe ser positivo")
    if base <= 0:
        return "LOT_SIZE_CANTIDAD_CERO"
    if minimo is not None and base < minimo:
        return "MIN_QTY_INALCANZABLE"
    if maximo is not None and base > maximo:
        return "MAX_QTY_INCOMPATIBLE"
    if notional is not None and quote < notional:
        return "MIN_NOTIONAL_INALCANZABLE"
    return None


def _sin_fill(lado: str, fee_bps: Decimal, motivo: str, *, est=None) -> FillPaper:
    return FillPaper(
        lado=lado,
        estado=NO_DISPONIBLE,
        base_ejecutada=None,
        quote_bruto=None,
        fee_usd=None,
        quote_neto=None,
        mejor_precio=getattr(est, "best_price", None),
        precio_vwap=getattr(est, "vwap", None),
        slippage_bps=getattr(est, "slippage_bps", None),
        fee_taker_bps_por_lado=fee_bps,
        motivo=motivo,
    )


def calcular_fill_compra(
    *,
    order_book,
    quote_amount,
    fee_taker_bps_por_lado,
    step_size=None,
    min_qty=None,
    max_qty=None,
    min_notional=None,
) -> FillPaper:
    """Simula una compra taker caminando asks por un presupuesto quote.

    `quote_neto` representa el efectivo total consumido: notional ejecutado +
    fee. Si se aportan filtros de Binance, la cantidad base se pisa a stepSize
    ANTES de calcular el VWAP definitivo. Así PAPER no registra una cantidad
    que el camino LIVE redondearía o que el exchange rechazaría.
    """
    fee_bps = _fee_bps(fee_taker_bps_por_lado)
    quote_objetivo = _decimal(quote_amount, nombre="quote_amount")
    if quote_objetivo <= 0:
        raise ValueError("quote_amount debe ser positivo")

    asks = order_book.get("asks", ()) if isinstance(order_book, dict) else ()
    est = estimar_slippage_compra(asks, quote_amount=quote_objetivo)
    if est.estado != DISPONIBLE:
        return _sin_fill("BUY", fee_bps, est.faltante, est=est)

    usa_filtros = any(v is not None for v in
                      (step_size, min_qty, max_qty, min_notional))
    if usa_filtros:
        base_objetivo = _cuantizar_base(est.base_ejecutada, step_size=step_size)
        if base_objetivo <= 0:
            return _sin_fill("BUY", fee_bps, "LOT_SIZE_CANTIDAD_CERO", est=est)
        est = estimar_slippage_compra_base(asks, base_quantity=base_objetivo)
        if est.estado != DISPONIBLE:
            return _sin_fill("BUY", fee_bps, est.faltante, est=est)

    quote = est.quote_ejecutado
    motivo_filtro = _validar_filtros(
        est.base_ejecutada,
        quote,
        min_qty=min_qty,
        max_qty=max_qty,
        min_notional=min_notional,
    )
    if motivo_filtro:
        return _sin_fill("BUY", fee_bps, motivo_filtro, est=est)

    fee = quote * fee_bps / _BPS
    return FillPaper(
        lado="BUY", estado=DISPONIBLE,
        base_ejecutada=est.base_ejecutada,
        quote_bruto=quote,
        fee_usd=fee,
        quote_neto=quote + fee,
        mejor_precio=est.best_price,
        precio_vwap=est.vwap,
        slippage_bps=est.slippage_bps,
        fee_taker_bps_por_lado=fee_bps,
    )


def calcular_fill_venta(
    *,
    order_book,
    base_quantity,
    fee_taker_bps_por_lado,
    step_size=None,
    min_qty=None,
    max_qty=None,
    min_notional=None,
) -> FillPaper:
    """Simula una venta taker caminando bids por una cantidad base.

    `quote_neto` es el efectivo recibido despues de la fee. Con filtros, la
    cantidad se pisa a stepSize antes de caminar el libro, igual que en LIVE.
    """
    fee_bps = _fee_bps(fee_taker_bps_por_lado)
    base_objetivo = _decimal(base_quantity, nombre="base_quantity")
    if base_objetivo <= 0:
        raise ValueError("base_quantity debe ser positivo")
    base_objetivo = _cuantizar_base(base_objetivo, step_size=step_size)
    if base_objetivo <= 0:
        return _sin_fill("SELL", fee_bps, "LOT_SIZE_CANTIDAD_CERO")

    bids = order_book.get("bids", ()) if isinstance(order_book, dict) else ()
    est = estimar_slippage_venta(bids, base_quantity=base_objetivo)
    if est.estado != DISPONIBLE:
        return _sin_fill("SELL", fee_bps, est.faltante, est=est)

    quote = est.quote_ejecutado
    motivo_filtro = _validar_filtros(
        est.base_ejecutada,
        quote,
        min_qty=min_qty,
        max_qty=max_qty,
        min_notional=min_notional,
    )
    if motivo_filtro:
        return _sin_fill("SELL", fee_bps, motivo_filtro, est=est)

    fee = quote * fee_bps / _BPS
    return FillPaper(
        lado="SELL", estado=DISPONIBLE,
        base_ejecutada=est.base_ejecutada,
        quote_bruto=quote,
        fee_usd=fee,
        quote_neto=quote - fee,
        mejor_precio=est.best_price,
        precio_vwap=est.vwap,
        slippage_bps=est.slippage_bps,
        fee_taker_bps_por_lado=fee_bps,
    )