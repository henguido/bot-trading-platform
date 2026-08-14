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
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EstadoOrden(str, Enum):
    """
    Estados de una orden. La distincion critica (P0-10) es:

        ERROR_PRE_ENVIO      el fallo ocurrio ANTES de que el POST pudiera
                             abandonar nuestro proceso. Es TERMINAL y seguro:
                             no existe ninguna orden en el broker.

        ESTADO_DESCONOCIDO   el POST pudo llegar al broker. NO es terminal y
                             NO significa "no ejecutada": significa que todavia
                             no lo sabemos. Solo la reconciliacion por
                             client_order_id puede resolverlo.

    El resultado del transporte NO es el estado de la orden.
    """

    CREADA = "CREADA"                        # intencion persistida, sin enviar
    ENVIANDO = "ENVIANDO"                    # POST en vuelo
    ESTADO_DESCONOCIDO = "ESTADO_DESCONOCIDO"  # pudo ejecutarse; hay que preguntar
    PARCIAL = "PARCIAL"                      # fill parcial confirmado

    EJECUTADA = "EJECUTADA"                  # fill confirmado y completo
    NO_EJECUTADA = "NO_EJECUTADA"            # el broker acepto y no lleno nada
    RECHAZADA = "RECHAZADA"                  # rechazada por el broker
    CANCELADA = "CANCELADA"
    EXPIRADA = "EXPIRADA"
    ERROR_PRE_ENVIO = "ERROR_PRE_ENVIO"      # fallo antes del POST; no hay orden
    BLOQUEADA_PAPER = "BLOQUEADA_PAPER"      # LIVE no habilitado; no se intento


# Estados en los que ya sabemos con certeza que fue de la orden.
ESTADOS_TERMINALES = frozenset({
    EstadoOrden.EJECUTADA, EstadoOrden.NO_EJECUTADA, EstadoOrden.RECHAZADA,
    EstadoOrden.CANCELADA, EstadoOrden.EXPIRADA, EstadoOrden.ERROR_PRE_ENVIO,
    EstadoOrden.BLOQUEADA_PAPER,
})

# Estados que exigen reconciliacion antes de abrir nueva exposicion.
ESTADOS_NO_TERMINALES = frozenset({
    EstadoOrden.CREADA, EstadoOrden.ENVIANDO,
    EstadoOrden.ESTADO_DESCONOCIDO, EstadoOrden.PARCIAL,
})


def es_terminal(estado) -> bool:
    return EstadoOrden(estado) in ESTADOS_TERMINALES


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

    order_id: Optional[str] = None            # id del broker
    client_order_id: Optional[str] = None     # id nuestro, generado antes del POST
    error: Optional[str] = None
    respuesta_cruda: Optional[Any] = field(default=None, repr=False, compare=False)
    # Fills individuales tal y como los devuelve el broker, con su comision.
    fills: tuple = field(default_factory=tuple, compare=False)

    @property
    def success(self) -> bool:
        return self.estado is EstadoOrden.EJECUTADA and self.executed_base_quantity > 0

    @property
    def requiere_reconciliacion(self) -> bool:
        return self.estado in ESTADOS_NO_TERMINALES

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
def rechazada(symbol, side, motivo, *, base_quantity=None, quote_amount=None,
              client_order_id=None) -> ResultadoOrden:
    return ResultadoOrden(
        symbol=symbol, side=side, estado=EstadoOrden.RECHAZADA,
        requested_base_quantity=base_quantity, requested_quote_amount=quote_amount,
        client_order_id=client_order_id, error=motivo,
    )


def nuevo_client_order_id() -> str:
    """
    Identidad de la orden, generada ANTES de cualquier envio (P0-11).

    Binance admite hasta 36 caracteres del conjunto [.A-Za-z0-9:/_-]; 'b-' mas
    32 hex son 34. Es la unica forma de preguntar despues 'que paso con ESTA
    orden' cuando se pierde la respuesta.
    """
    return f"b-{uuid.uuid4().hex}"


def error_pre_envio(symbol, side, motivo, *, base_quantity=None, quote_amount=None,
                    client_order_id=None) -> ResultadoOrden:
    """
    Fallo ANTES de que el POST pudiera salir: validacion, precio del ticker,
    step size. Terminal y seguro: no existe ninguna orden en el broker.
    """
    return ResultadoOrden(
        symbol=symbol, side=side, estado=EstadoOrden.ERROR_PRE_ENVIO,
        requested_base_quantity=base_quantity, requested_quote_amount=quote_amount,
        client_order_id=client_order_id, error=motivo,
    )


def estado_desconocido(symbol, side, motivo, *, base_quantity=None, quote_amount=None,
                       client_order_id=None) -> ResultadoOrden:
    """
    El POST pudo llegar al broker. NO afirmamos que no se ejecuto: solo la
    reconciliacion por client_order_id puede decirlo.
    """
    return ResultadoOrden(
        symbol=symbol, side=side, estado=EstadoOrden.ESTADO_DESCONOCIDO,
        requested_base_quantity=base_quantity, requested_quote_amount=quote_amount,
        client_order_id=client_order_id, error=motivo,
    )


def bloqueada_paper(symbol, side, *, base_quantity=None, quote_amount=None,
                    client_order_id=None) -> ResultadoOrden:
    return ResultadoOrden(
        symbol=symbol, side=side, estado=EstadoOrden.BLOQUEADA_PAPER,
        requested_base_quantity=base_quantity, requested_quote_amount=quote_amount,
        client_order_id=client_order_id,
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
ESTADO_BROKER_A_ORDEN = {
    "REJECTED": EstadoOrden.RECHAZADA,
    "EXPIRED": EstadoOrden.EXPIRADA,
    "EXPIRED_IN_MATCH": EstadoOrden.EXPIRADA,
    "CANCELED": EstadoOrden.CANCELADA,
    "PENDING_CANCEL": EstadoOrden.CANCELADA,
}


def extraer_fills(respuesta) -> tuple:
    """
    Normaliza `fills[]` de una respuesta MARKET de Binance.

    Cada fill trae price, qty, commission, commissionAsset y tradeId. La tasa
    NUNCA se deduce ni se hardcodea: se guarda lo que informa el broker.
    """
    if not isinstance(respuesta, dict):
        return ()
    normalizados = []
    for f in respuesta.get("fills") or []:
        if not isinstance(f, dict):
            continue
        try:
            normalizados.append({
                "trade_id": str(f.get("tradeId")) if f.get("tradeId") is not None else None,
                "price": float(f.get("price", 0) or 0),
                "qty": float(f.get("qty", 0) or 0),
                "commission": float(f.get("commission", 0) or 0),
                "commission_asset": f.get("commissionAsset"),
            })
        except (TypeError, ValueError):
            continue
    return tuple(normalizados)


def interpretar_respuesta_binance(respuesta, symbol, side, *, base_quantity=None,
                                  quote_amount=None, client_order_id=None) -> ResultadoOrden:
    """
    Traduce la respuesta de python-binance a un ResultadoOrden.

    No inventa fills: si la respuesta no trae executedQty numerico y mayor que
    cero, el resultado NO es una ejecucion. Y si la respuesta es ilegible, el
    estado es ESTADO_DESCONOCIDO, no NO_EJECUTADA: la orden pudo ejecutarse
    aunque no podamos leer la confirmacion.
    """
    comun = dict(symbol=symbol, side=side,
                 requested_base_quantity=base_quantity,
                 requested_quote_amount=quote_amount,
                 client_order_id=client_order_id,
                 respuesta_cruda=respuesta)

    if respuesta is None:
        return ResultadoOrden(**comun, estado=EstadoOrden.ESTADO_DESCONOCIDO,
                              error="el broker no devolvio respuesta")
    if not isinstance(respuesta, dict):
        return ResultadoOrden(**comun, estado=EstadoOrden.ESTADO_DESCONOCIDO,
                              error=f"respuesta ilegible: {type(respuesta).__name__}")

    estado_broker = str(respuesta.get("status", "")).upper()
    order_id = respuesta.get("orderId")
    order_id = str(order_id) if order_id is not None else None
    cid = respuesta.get("clientOrderId") or client_order_id
    comun["client_order_id"] = cid
    fills = extraer_fills(respuesta)

    try:
        ejecutado_base = float(respuesta.get("executedQty", 0) or 0)
        ejecutado_quote = float(respuesta.get("cummulativeQuoteQty", 0) or 0)
    except (TypeError, ValueError):
        return ResultadoOrden(**comun, estado=EstadoOrden.ESTADO_DESCONOCIDO,
                              order_id=order_id, fills=fills,
                              error="cantidades no numericas en la respuesta del broker")

    if ejecutado_base <= 0 and estado_broker in ESTADO_BROKER_A_ORDEN:
        return ResultadoOrden(**comun, estado=ESTADO_BROKER_A_ORDEN[estado_broker],
                              order_id=order_id, fills=fills,
                              error=f"el broker devolvio status={estado_broker}")

    if ejecutado_base <= 0:
        return ResultadoOrden(**comun, estado=EstadoOrden.NO_EJECUTADA, order_id=order_id,
                              fills=fills,
                              error=f"sin fill (status={estado_broker or 'desconocido'})")

    precio_medio = (ejecutado_quote / ejecutado_base) if ejecutado_quote > 0 else None
    solicitada = respuesta.get("origQty")
    parcial = False
    try:
        if solicitada is not None:
            parcial = float(solicitada) - ejecutado_base > 1e-12
    except (TypeError, ValueError):
        parcial = False

    return ResultadoOrden(
        **comun,
        estado=EstadoOrden.PARCIAL if parcial else EstadoOrden.EJECUTADA,
        order_id=order_id, fills=fills,
        executed_base_quantity=ejecutado_base,
        executed_quote_amount=ejecutado_quote,
        average_fill_price=precio_medio)
