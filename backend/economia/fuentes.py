"""Fuentes y transformaciones de costes para BOT 2.0-04A-1.

Este modulo NO decide trading. Convierte datos observables en magnitudes que el
modelo de costes de 04A puede consumir:

- fee taker de la cuenta Binance -> bps por lado;
- profundidad bid/ask -> slippage por lado, SIN volver a cobrar el spread;
- coste real de una llamada LLM -> asignacion unica entre decisiones accionables.

Invariante: desconocido != cero. Datos ausentes o profundidad insuficiente se
reportan como NO_DISPONIBLE; nunca se inventa una friccion favorable.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional, Sequence, Tuple

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"
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
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{nombre} no es numerico") from None
    if not d.is_finite():
        raise ValueError(f"{nombre} debe ser finito")
    return d


def extraer_taker_bps(account_info) -> Optional[Decimal]:
    """Extrae `commissionRates.taker` de GET /api/v3/account y lo pasa a bps.

    Binance expresa `commissionRates.taker` como fraccion (p.ej. 0.001 = 0.1%).
    Se usa exclusivamente ese campo explicito. Si no viene, devolvemos None en
    vez de adivinar a partir de defaults o de campos legacy ambiguos.
    """
    if not isinstance(account_info, dict):
        return None
    rates = account_info.get("commissionRates")
    if not isinstance(rates, dict):
        return None
    raw = rates.get("taker")
    if raw is None:
        return None
    try:
        tasa = _decimal(raw, nombre="commissionRates.taker")
    except ValueError:
        return None
    if tasa < 0:
        return None
    return tasa * _BPS


@dataclass(frozen=True)
class EstimacionSlippage:
    lado: str
    estado: str
    best_price: Optional[Decimal]
    vwap: Optional[Decimal]
    slippage_bps: Optional[Decimal]
    base_ejecutada: Decimal
    quote_ejecutado: Decimal
    faltante: Optional[str] = None

    @property
    def completa(self) -> bool:
        return self.estado == DISPONIBLE


def _niveles_validos(niveles: Iterable, *, asks: bool) -> list[Tuple[Decimal, Decimal]]:
    validos = []
    for fila in niveles or ():
        try:
            precio = _decimal(fila[0], nombre="precio")
            cantidad = _decimal(fila[1], nombre="cantidad")
        except (ValueError, TypeError, IndexError, KeyError):
            continue
        if precio <= 0 or cantidad <= 0:
            continue
        validos.append((precio, cantidad))
    validos.sort(key=lambda x: x[0], reverse=not asks)
    return validos


def estimar_slippage_compra(asks: Sequence, *, quote_amount) -> EstimacionSlippage:
    """Camina asks para comprar gastando `quote_amount`.

    Slippage se mide contra el MEJOR ASK. El spread se contabiliza aparte en
    `costes.estimar_roundtrip`; medir contra el mid lo cobraria dos veces.
    """
    objetivo = _decimal(quote_amount, nombre="quote_amount")
    if objetivo <= 0:
        raise ValueError("quote_amount debe ser positivo")
    niveles = _niveles_validos(asks, asks=True)
    if not niveles:
        return EstimacionSlippage("BUY", NO_DISPONIBLE, None, None, None,
                                  Decimal("0"), Decimal("0"), "sin_asks")

    best = niveles[0][0]
    restante = objetivo
    base = Decimal("0")
    quote = Decimal("0")
    for precio, cantidad in niveles:
        capacidad_quote = precio * cantidad
        gastar = min(restante, capacidad_quote)
        base += gastar / precio
        quote += gastar
        restante -= gastar
        if restante <= 0:
            break

    if restante > 0 or base <= 0:
        return EstimacionSlippage("BUY", NO_DISPONIBLE, best, None, None,
                                  base, quote, "profundidad_insuficiente")
    vwap = quote / base
    slippage = (vwap / best - Decimal("1")) * _BPS
    return EstimacionSlippage("BUY", DISPONIBLE, best, vwap, max(slippage, Decimal("0")),
                              base, quote)


def estimar_slippage_venta(bids: Sequence, *, base_quantity) -> EstimacionSlippage:
    """Camina bids para vender `base_quantity`; slippage contra mejor BID."""
    objetivo = _decimal(base_quantity, nombre="base_quantity")
    if objetivo <= 0:
        raise ValueError("base_quantity debe ser positivo")
    niveles = _niveles_validos(bids, asks=False)
    if not niveles:
        return EstimacionSlippage("SELL", NO_DISPONIBLE, None, None, None,
                                  Decimal("0"), Decimal("0"), "sin_bids")

    best = niveles[0][0]
    restante = objetivo
    base = Decimal("0")
    quote = Decimal("0")
    for precio, cantidad in niveles:
        vender = min(restante, cantidad)
        base += vender
        quote += vender * precio
        restante -= vender
        if restante <= 0:
            break

    if restante > 0 or base <= 0:
        return EstimacionSlippage("SELL", NO_DISPONIBLE, best, None, None,
                                  base, quote, "profundidad_insuficiente")
    vwap = quote / base
    slippage = (Decimal("1") - vwap / best) * _BPS
    return EstimacionSlippage("SELL", DISPONIBLE, best, vwap, max(slippage, Decimal("0")),
                              base, quote)


@dataclass(frozen=True)
class SlippageRoundTrip:
    entrada: EstimacionSlippage
    salida: EstimacionSlippage
    slippage_bps_por_lado_promedio: Optional[Decimal]
    estado: str


def estimar_slippage_roundtrip(order_book, *, quote_amount) -> SlippageRoundTrip:
    """Estima BUY y salida SELL sobre el mismo libro para un notional objetivo.

    Es una foto pre-trade, no una prediccion del libro futuro. Su utilidad es
    detectar si el propio tamano de la orden ya barre niveles del book.
    """
    if not isinstance(order_book, dict):
        vacio = EstimacionSlippage("BUY", NO_DISPONIBLE, None, None, None,
                                   Decimal("0"), Decimal("0"), "libro_invalido")
        salida = EstimacionSlippage("SELL", NO_DISPONIBLE, None, None, None,
                                    Decimal("0"), Decimal("0"), "libro_invalido")
        return SlippageRoundTrip(vacio, salida, None, NO_DISPONIBLE)

    entrada = estimar_slippage_compra(order_book.get("asks", ()), quote_amount=quote_amount)
    if not entrada.completa:
        salida = EstimacionSlippage("SELL", NO_DISPONIBLE, None, None, None,
                                    Decimal("0"), Decimal("0"), "entrada_incompleta")
        return SlippageRoundTrip(entrada, salida, None, NO_DISPONIBLE)

    salida = estimar_slippage_venta(order_book.get("bids", ()),
                                    base_quantity=entrada.base_ejecutada)
    if not salida.completa:
        return SlippageRoundTrip(entrada, salida, None, NO_DISPONIBLE)
    promedio = (entrada.slippage_bps + salida.slippage_bps) / Decimal("2")
    return SlippageRoundTrip(entrada, salida, promedio, DISPONIBLE)


@dataclass(frozen=True)
class AsignacionCostoIA:
    estado: str
    costo_llamada_usd: Optional[Decimal]
    decisiones_accionables: int
    costo_por_operacion_usd: Optional[Decimal]
    costo_screening_sin_asignar_usd: Optional[Decimal]


def asignar_costo_ia(costo_llamada_usd, *, decisiones_accionables: int) -> AsignacionCostoIA:
    """Asigna el coste de UNA llamada exactamente una vez.

    Politica 04A-1:
    - N>0 decisiones accionables: coste / N para cada operacion propuesta.
    - N=0: todo el coste queda como screening del ciclo, sin inventar un trade.
    - coste desconocido: NO_DISPONIBLE, nunca cero.

    `decisiones_accionables` debe contar solo propuestas que podrian llegar al
    RiskEngine (COMPRAR/VENDER), no candidatos meramente analizados ni ESPERAR.
    """
    if isinstance(decisiones_accionables, bool) or not isinstance(decisiones_accionables, int):
        raise ValueError("decisiones_accionables debe ser entero")
    if decisiones_accionables < 0:
        raise ValueError("decisiones_accionables no puede ser negativo")
    if costo_llamada_usd is None:
        return AsignacionCostoIA(NO_DISPONIBLE, None, decisiones_accionables, None, None)
    costo = _decimal(costo_llamada_usd, nombre="costo_llamada_usd")
    if costo < 0:
        raise ValueError("costo_llamada_usd no puede ser negativo")
    if decisiones_accionables == 0:
        return AsignacionCostoIA(DISPONIBLE, costo, 0, None, costo)
    por_op = costo / Decimal(decisiones_accionables)
    return AsignacionCostoIA(DISPONIBLE, costo, decisiones_accionables, por_op,
                              Decimal("0"))
