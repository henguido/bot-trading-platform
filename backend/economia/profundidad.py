"""Fuente on-demand de profundidad para BOT 2.0-04A-1.

No se usa en el scanner ni se llama por cada candidato. La intención es que el
EconomicGate final la consulte sólo para propuestas concretas, evitando otro
N+1. La aritmética del slippage vive en `backend.economia.fuentes` y permanece
pura; este módulo sólo adquiere el libro.
"""
from __future__ import annotations

from backend.telemetria_http import (OPERACION_NULA, anotar_elementos,
                                     describir_error)


def obtener_order_book(binance, symbol: str, *, limit: int = 20, medicion=None):
    """Obtiene un book de UN símbolo con UNA petición REST.

    Devuelve None ante fallo o payload ilegible. No reutiliza un libro anterior
    ni inventa profundidad. `limit=20` mantiene la consulta pequeña; 04A-1 no
    hace ninguna llamada de este tipo por sí sola desde el trading loop.
    """
    if not isinstance(symbol, str) or not symbol.strip() or not symbol.isalnum():
        raise ValueError("symbol inválido")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0 or limit > 100:
        raise ValueError("limit debe ser entero entre 1 y 100")

    op = medicion if medicion is not None else OPERACION_NULA
    try:
        binance.init_client()
        with op.peticion(observador=binance.observador_http()):
            book = binance.client.get_order_book(symbol=symbol, limit=limit)
    except Exception as e:
        print(f"⚠️ No se pudo obtener profundidad de {symbol}: {describir_error(e)}")
        return None

    if not isinstance(book, dict):
        return None
    asks = book.get("asks")
    bids = book.get("bids")
    if not isinstance(asks, list) or not isinstance(bids, list):
        return None
    anotar_elementos(op, len(asks) + len(bids))
    return {"asks": asks, "bids": bids}
