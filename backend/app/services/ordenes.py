"""
Contrato de ejecucion de ordenes.

Regla fundamental: UNA INTENCION DE OPERAR NO ES UNA TRANSACCION.

    senal -> validacion -> intento de orden -> respuesta del broker
          -> validacion de la respuesta/fill -> persistencia -> estado

Si falla cualquier etapa anterior a la confirmacion, NO se registra ninguna
transaccion ejecutada. Este modulo define el resultado explicito que devuelven
los conectores para que el llamador pueda distinguir sin ambiguedad entre
ejecutada, rechazada, error y no ejecutada.

UNIDADES — nunca usar una variable generica "cantidad":

    base_quantity  cantidad del ACTIVO BASE   (BTC en BTCUSDT)
    quote_amount   importe del ACTIVO COTIZADO (USDT en BTCUSDT)

    precio = quote_amount / base_quantity
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EstadoOrden(str, Enum):
    """Desenlace de un intento de orden. Mutuamente excluyentes."""

    EJECUTADA = "EJECUTADA"          # el broker confirmo un fill > 0
    NO_EJECUTADA = "NO_EJECUTADA"    # el broker acepto pero no lleno nada
    RECHAZADA = "RECHAZADA"          # rechazada por validacion propia o por el broker
    ERROR = "ERROR"                  # fallo tecnico: red, excepcion, respuesta ilegible
    BLOQUEADA_PAPER = "BLOQUEADA_PAPER"  # LIVE no habilitado; no se intento nada


class Lado(str, Enum):
    COMPRA = "BUY"
    VENTA = "SELL"


@dataclass(frozen=True)
class ResultadoOrden:
    """
    Resultado inequivoco de un intento de orden.

    `success` es True SOLO si el broker confirmo una ejecucion con cantidad
    mayor que cero. Nunca se infieren fills: si la respuesta no los confirma,
    executed_base_quantity queda en 0.0 y success en False.
    """

    symbol: str
    side: Lado
    estado: EstadoOrden

    # Lo que se pidio. Solo uno de los dos aplica segun el lado.
    requested_base_quantity: Optional[float] = None   # ventas
    requested_quote_amount: Optional[float] = None    # compras

    # Lo que el broker confirmo. 0.0 mientras no haya confirmacion.
    executed_base_quantity: float = 0.0
    executed_quote_amount: float = 0.0
    average_fill_price: Optional[float] = None

    order_id: Optional[str] = None
    error: Optional[str] = None
    respuesta_cruda: Optional[Any] = field(default=None, repr=False, compare=False)

    @property
    def success(self) -> bool:
        return self.estado is EstadoOrden.EJECUTADA and self.executed_base_quantity > 0

    def __str__(self) -> str:
        if self.success:
            return (f"{self.side.value} {self.symbol} EJECUTADA: "
                    f"{self.executed_base_quantity} base @ {self.average_fill_price} "
                    f"(order_id={self.order_id})")
        return (f"{self.side.value} {self.symbol} {self.estado.value}"
                + (f": {self.error}" if self.error else ""))


# ─────────────────────────────────────────────────────────────────────────────
# Constructores de conveniencia
# ─────────────────────────────────────────────────────────────────────────────
def rechazada(symbol, side, motivo, *, base_quantity=None, quote_amount=None) -> ResultadoOrden:
    return ResultadoOrden(
        symbol=symbol, side=side, estado=EstadoOrden.RECHAZADA,
        requested_base_quantity=base_quantity, requested_quote_amount=quote_amount,
        error=motivo,
    )


def error_tecnico(symbol, side, motivo, *, base_quantity=None, quote_amount=None) -> ResultadoOrden:
    return ResultadoOrden(
        symbol=symbol, side=side, estado=EstadoOrden.ERROR,
        requested_base_quantity=base_quantity, requested_quote_amount=quote_amount,
        error=motivo,
    )


def bloqueada_paper(symbol, side, *, base_quantity=None, quote_amount=None) -> ResultadoOrden:
    return ResultadoOrden(
        symbol=symbol, side=side, estado=EstadoOrden.BLOQUEADA_PAPER,
        requested_base_quantity=base_quantity, requested_quote_amount=quote_amount,
        error="LIVE no habilitado: no se intento ninguna orden real.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Validaciones previas al broker
# ─────────────────────────────────────────────────────────────────────────────
def es_cantidad_valida(valor) -> bool:
    """Numero real, finito y estrictamente positivo. Rechaza NaN e infinitos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return False
    return math.isfinite(valor) and valor > 0


def validar_simbolo(symbol) -> Optional[str]:
    """Devuelve el motivo del rechazo, o None si es valido."""
    if not isinstance(symbol, str) or not symbol.strip():
        return "simbolo vacio o no textual"
    if not symbol.isalnum():
        return f"simbolo con caracteres no alfanumericos: {symbol!r}"
    return None


def validar_peticion_compra(symbol, quote_amount) -> Optional[str]:
    motivo = validar_simbolo(symbol)
    if motivo:
        return motivo
    if not es_cantidad_valida(quote_amount):
        return f"quote_amount invalido: {quote_amount!r} (debe ser finito y > 0)"
    return None


def validar_peticion_venta(symbol, base_quantity, disponible=None) -> Optional[str]:
    motivo = validar_simbolo(symbol)
    if motivo:
        return motivo
    if not es_cantidad_valida(base_quantity):
        return f"base_quantity invalido: {base_quantity!r} (debe ser finito y > 0)"
    if disponible is not None and base_quantity > disponible:
        return (f"posicion insuficiente: se pidio vender {base_quantity} "
                f"y solo hay {disponible}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Lectura de la respuesta del broker
# ─────────────────────────────────────────────────────────────────────────────
ESTADOS_BINANCE_SIN_FILL = {"REJECTED", "EXPIRED", "CANCELED", "PENDING_CANCEL"}


def interpretar_respuesta_binance(respuesta, symbol, side, *,
                                  base_quantity=None, quote_amount=None) -> ResultadoOrden:
    """
    Traduce la respuesta de python-binance a un ResultadoOrden.

    No inventa fills bajo ninguna circunstancia: si la respuesta no trae
    executedQty numerico y mayor que cero, el resultado NO es una ejecucion.
    """
    comun = dict(symbol=symbol, side=side,
                 requested_base_quantity=base_quantity,
                 requested_quote_amount=quote_amount,
                 respuesta_cruda=respuesta)

    if respuesta is None:
        return ResultadoOrden(**comun, estado=EstadoOrden.ERROR,
                              error="el broker no devolvio respuesta")
    if not isinstance(respuesta, dict):
        return ResultadoOrden(**comun, estado=EstadoOrden.ERROR,
                              error=f"respuesta ilegible del broker: {type(respuesta).__name__}")

    estado_broker = str(respuesta.get("status", "")).upper()
    order_id = respuesta.get("orderId")
    order_id = str(order_id) if order_id is not None else None

    try:
        ejecutado_base = float(respuesta.get("executedQty", 0) or 0)
        ejecutado_quote = float(respuesta.get("cummulativeQuoteQty", 0) or 0)
    except (TypeError, ValueError):
        return ResultadoOrden(**comun, estado=EstadoOrden.ERROR, order_id=order_id,
                              error="cantidades no numericas en la respuesta del broker")

    if estado_broker in ESTADOS_BINANCE_SIN_FILL:
        return ResultadoOrden(**comun, estado=EstadoOrden.RECHAZADA, order_id=order_id,
                              error=f"el broker devolvio status={estado_broker}")

    if ejecutado_base <= 0:
        return ResultadoOrden(**comun, estado=EstadoOrden.NO_EJECUTADA, order_id=order_id,
                              error=f"sin fill (status={estado_broker or 'desconocido'})")

    precio_medio = (ejecutado_quote / ejecutado_base) if ejecutado_quote > 0 else None

    return ResultadoOrden(**comun, estado=EstadoOrden.EJECUTADA, order_id=order_id,
                          executed_base_quantity=ejecutado_base,
                          executed_quote_amount=ejecutado_quote,
                          average_fill_price=precio_medio)
