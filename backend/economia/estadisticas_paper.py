"""Atribución económica por estrategia sobre el journal PAPER.

La atribución sigue lotes FIFO de COMPRA. Cada lote conserva la estrategia que
originó la entrada y su coste neto (incluida la fee de entrada). Una VENTA
consume esos lotes y reparte su `quote_net` proporcionalmente por cantidad;
como `quote_net` ya descuenta la fee de salida, el P&L atribuido es neto de las
fees registradas en ambos lados.

No hace red, no modifica el journal y no convierte datos desconocidos en cero.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Iterable, Optional


SIN_ESTRATEGIA = "SIN_ESTRATEGIA"


def _campo(op, nombre, defecto=None):
    if isinstance(op, dict):
        return op.get(nombre, defecto)
    return getattr(op, nombre, defecto)


def _numero(valor, nombre: str) -> float:
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"{nombre} es obligatorio")
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre} no es numerico") from None
    if not math.isfinite(numero):
        raise ValueError(f"{nombre} debe ser finito")
    return numero


def _numero_opcional(valor, nombre: str) -> Optional[float]:
    if valor is None:
        return None
    return _numero(valor, nombre)


def _estrategia(op) -> str:
    valor = _campo(op, "strategy")
    if valor is None:
        return SIN_ESTRATEGIA
    texto = str(valor).strip()
    return texto or SIN_ESTRATEGIA


@dataclass
class _Lote:
    cantidad: float
    coste_unitario_neto: float
    estrategia: str
    expected_net_bps: Optional[float]


@dataclass
class _Acumulado:
    coste_cerrado_usd: float = 0.0
    pnl_realizado_usd: float = 0.0
    cantidad_cerrada: float = 0.0
    cantidad_abierta: float = 0.0
    coste_abierto_usd: float = 0.0
    expected_net_bps_x_coste: float = 0.0
    coste_con_expected_usd: float = 0.0
    cierres: int = 0
    cierres_positivos: int = 0


def resumen_por_estrategia(operaciones: Iterable) -> dict:
    """Reconstruye lotes y devuelve P&L realizado neto por estrategia de entrada."""
    lotes = defaultdict(list)
    acumulados = defaultdict(_Acumulado)

    for op in operaciones or ():
        symbol = str(_campo(op, "symbol") or "").strip().upper()
        side = str(_campo(op, "side") or "").strip().upper()
        if not symbol or side not in ("BUY", "SELL"):
            raise ValueError("operacion PAPER invalida para atribucion")

        qty = _numero(_campo(op, "base_quantity"), "base_quantity")
        quote_net = _numero(_campo(op, "quote_net"), "quote_net")
        if qty <= 0 or quote_net <= 0:
            raise ValueError("magnitudes PAPER invalidas para atribucion")

        if side == "BUY":
            estrategia = _estrategia(op)
            expected = _numero_opcional(
                _campo(op, "expected_net_bps"), "expected_net_bps")
            lotes[symbol].append(_Lote(
                cantidad=qty,
                coste_unitario_neto=quote_net / qty,
                estrategia=estrategia,
                expected_net_bps=expected,
            ))
            continue

        disponibles = sum(lote.cantidad for lote in lotes[symbol])
        if qty > disponibles + 1e-12:
            raise ValueError("venta PAPER excede lotes disponibles")

        neto_salida_unitario = quote_net / qty
        restante = qty
        pnl_evento = defaultdict(float)
        coste_evento = defaultdict(float)

        while restante > 1e-12:
            lote = lotes[symbol][0]
            tomado = min(restante, lote.cantidad)
            coste = tomado * lote.coste_unitario_neto
            pnl = tomado * neto_salida_unitario - coste
            a = acumulados[lote.estrategia]
            a.coste_cerrado_usd += coste
            a.pnl_realizado_usd += pnl
            a.cantidad_cerrada += tomado
            if lote.expected_net_bps is not None:
                a.expected_net_bps_x_coste += lote.expected_net_bps * coste
                a.coste_con_expected_usd += coste
            pnl_evento[lote.estrategia] += pnl
            coste_evento[lote.estrategia] += coste

            lote.cantidad -= tomado
            restante -= tomado
            if lote.cantidad <= 1e-12:
                lotes[symbol].pop(0)

        for estrategia, pnl in pnl_evento.items():
            a = acumulados[estrategia]
            a.cierres += 1
            if pnl > 0:
                a.cierres_positivos += 1

    # Posiciones todavía abiertas también se atribuyen a su estrategia de entrada.
    for lista in lotes.values():
        for lote in lista:
            a = acumulados[lote.estrategia]
            a.cantidad_abierta += lote.cantidad
            a.coste_abierto_usd += lote.cantidad * lote.coste_unitario_neto

    estrategias = {}
    for nombre in sorted(acumulados):
        a = acumulados[nombre]
        realizado_bps = (
            a.pnl_realizado_usd / a.coste_cerrado_usd * 10_000.0
            if a.coste_cerrado_usd > 0 else None
        )
        expected = (
            a.expected_net_bps_x_coste / a.coste_con_expected_usd
            if a.coste_con_expected_usd > 0 else None
        )
        estrategias[nombre] = {
            "cierres": a.cierres,
            "cierres_positivos": a.cierres_positivos,
            "positive_rate": (
                a.cierres_positivos / a.cierres if a.cierres else None
            ),
            "cantidad_cerrada": a.cantidad_cerrada,
            "coste_cerrado_usd": a.coste_cerrado_usd,
            "pnl_realizado_neto_usd": a.pnl_realizado_usd,
            "retorno_realizado_neto_bps": realizado_bps,
            "expected_net_bps_ponderado": expected,
            "error_expected_vs_realizado_bps": (
                realizado_bps - expected
                if realizado_bps is not None and expected is not None else None
            ),
            "cantidad_abierta": a.cantidad_abierta,
            "coste_abierto_usd": a.coste_abierto_usd,
        }

    return {
        "metodologia": "FIFO_POR_ESTRATEGIA_DE_ENTRADA",
        "pnl_incluye_fees_ejecutadas": True,
        "unknown_is_zero": False,
        "estrategias": estrategias,
    }
