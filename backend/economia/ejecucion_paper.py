"""Modelo economico puro de ejecucion PAPER.

Convierte un libro de ordenes y la fee taker conocida en un fill simulable.
No hace red, no toca DB, no ejecuta ordenes y no modifica el trading loop.

Objetivo: reemplazar progresivamente el fill optimista `quantity * price` del
Simulator por una ejecucion PAPER que refleje profundidad y comision.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from backend.economia.fuentes import (
    DISPONIBLE,
    estimar_slippage_compra,
    estimar_slippage_venta,
)

_BPS = Decimal("10000")


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


def calcular_fill_compra(*, order_book, quote_amount, fee_taker_bps_por_lado) -> FillPaper:
    """Simula una compra taker caminando asks por un presupuesto quote.

    `quote_neto` representa el efectivo total consumido: notional ejecutado +
    fee. Si no hay profundidad suficiente, falla cerrado.
    """
    fee_bps = _fee_bps(fee_taker_bps_por_lado)
    quote_objetivo = _decimal(quote_amount, nombre="quote_amount")
    if quote_objetivo <= 0:
        raise ValueError("quote_amount debe ser positivo")

    asks = order_book.get("asks", ()) if isinstance(order_book, dict) else ()
    est = estimar_slippage_compra(asks, quote_amount=quote_objetivo)
    if est.estado != DISPONIBLE:
        return FillPaper(
            lado="BUY", estado=est.estado, base_ejecutada=None,
            quote_bruto=None, fee_usd=None, quote_neto=None,
            mejor_precio=est.mejor_precio, precio_vwap=est.precio_vwap,
            slippage_bps=est.slippage_bps,
            fee_taker_bps_por_lado=fee_bps,
            motivo=est.motivo,
        )

    quote = est.quote_ejecutado
    fee = quote * fee_bps / _BPS
    return FillPaper(
        lado="BUY", estado=DISPONIBLE,
        base_ejecutada=est.base_ejecutada,
        quote_bruto=quote,
        fee_usd=fee,
        quote_neto=quote + fee,
        mejor_precio=est.mejor_precio,
        precio_vwap=est.precio_vwap,
        slippage_bps=est.slippage_bps,
        fee_taker_bps_por_lado=fee_bps,
    )


def calcular_fill_venta(*, order_book, base_quantity, fee_taker_bps_por_lado) -> FillPaper:
    """Simula una venta taker caminando bids por una cantidad base.

    `quote_neto` es el efectivo recibido despues de la fee.
    """
    fee_bps = _fee_bps(fee_taker_bps_por_lado)
    base_objetivo = _decimal(base_quantity, nombre="base_quantity")
    if base_objetivo <= 0:
        raise ValueError("base_quantity debe ser positivo")

    bids = order_book.get("bids", ()) if isinstance(order_book, dict) else ()
    est = estimar_slippage_venta(bids, base_quantity=base_objetivo)
    if est.estado != DISPONIBLE:
        return FillPaper(
            lado="SELL", estado=est.estado, base_ejecutada=None,
            quote_bruto=None, fee_usd=None, quote_neto=None,
            mejor_precio=est.mejor_precio, precio_vwap=est.precio_vwap,
            slippage_bps=est.slippage_bps,
            fee_taker_bps_por_lado=fee_bps,
            motivo=est.motivo,
        )

    quote = est.quote_ejecutado
    fee = quote * fee_bps / _BPS
    return FillPaper(
        lado="SELL", estado=DISPONIBLE,
        base_ejecutada=est.base_ejecutada,
        quote_bruto=quote,
        fee_usd=fee,
        quote_neto=quote - fee,
        mejor_precio=est.mejor_precio,
        precio_vwap=est.precio_vwap,
        slippage_bps=est.slippage_bps,
        fee_taker_bps_por_lado=fee_bps,
    )
