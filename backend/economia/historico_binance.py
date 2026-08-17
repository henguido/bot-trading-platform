"""Adquisicion historica Spot para BOT 2.0-04B-0.

Es un adaptador OFFLINE: nadie en `main.py` lo importa. Descarga klines de UN
simbolo por paginas y devuelve una serie validada para `edge_historico`.

Regla de integridad: si falla cualquier pagina, NO devuelve el prefijo parcial.
Una serie truncada presentada como completa contaminaria la evaluacion mas que
un fallo explicito.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from backend.economia.edge_historico import Vela, velas_desde_klines
from backend.telemetria_http import OPERACION_NULA, anotar_elementos, describir_error

INTERVALOS_MS = {
    "1h": 60 * 60 * 1000,
    "2h": 2 * 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "8h": 8 * 60 * 60 * 1000,
    "12h": 12 * 60 * 60 * 1000,
}


@dataclass(frozen=True)
class DescargaHistorica:
    symbol: str
    interval: str
    start_ms: int
    end_ms: int
    velas: Tuple[Vela, ...]
    n_requests: int
    completa: bool
    error: Optional[str] = None


def descargar_klines_rango(
    binance,
    symbol: str,
    *,
    interval: str = "1h",
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
    medicion=None,
) -> DescargaHistorica:
    """Descarga [start_ms, end_ms] por paginas, sin cache ni datos parciales.

    `binance` es el BinanceConnector ya existente. Construir este modulo o
    importarlo no inicializa cliente ni hace red; la red ocurre solo al invocar
    esta funcion deliberadamente desde una tarea offline.
    """
    if not isinstance(symbol, str) or not symbol.strip() or not symbol.isalnum():
        raise ValueError("symbol invalido")
    if interval not in INTERVALOS_MS:
        raise ValueError(f"interval no soportado: {interval!r}")
    if isinstance(start_ms, bool) or not isinstance(start_ms, int) or start_ms < 0:
        raise ValueError("start_ms invalido")
    if isinstance(end_ms, bool) or not isinstance(end_ms, int) or end_ms <= start_ms:
        raise ValueError("end_ms debe ser mayor que start_ms")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit debe estar entre 1 y 1000")

    op = medicion if medicion is not None else OPERACION_NULA
    paso_ms = INTERVALOS_MS[interval]
    cursor = start_ms
    paginas = []
    n_requests = 0

    try:
        binance.init_client()
        while cursor <= end_ms:
            with op.peticion(observador=binance.observador_http()):
                filas = binance.client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    startTime=cursor,
                    endTime=end_ms,
                    limit=limit,
                )
            n_requests += 1

            if not filas:
                break
            if not isinstance(filas, list):
                raise ValueError("payload de klines no es lista")

            # Se valida cada pagina antes de acumularla. El parser tambien
            # rechaza OHLC/timestamps ilegibles.
            pagina = velas_desde_klines(filas)
            if not pagina:
                break
            paginas.extend(pagina)

            ultimo_open = pagina[-1].open_time_ms
            siguiente = ultimo_open + paso_ms
            if siguiente <= cursor:
                raise ValueError("paginacion de klines no avanzo")
            cursor = siguiente

            # Binance devolvio menos del limite: ya no hay otra pagina en el
            # rango solicitado. No se hace una peticion vacia adicional.
            if len(filas) < limit:
                break

        # Duplicados entre paginas tambien son error: no se silencian.
        tiempos = [v.open_time_ms for v in paginas]
        if len(tiempos) != len(set(tiempos)):
            raise ValueError("klines duplicados entre paginas")

        velas = tuple(sorted(paginas, key=lambda v: v.open_time_ms))
        anotar_elementos(op, len(velas))
        return DescargaHistorica(
            symbol=symbol,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
            velas=velas,
            n_requests=n_requests,
            completa=True,
            error=None,
        )
    except Exception as e:
        # No se devuelve `paginas`: un prefijo parcial NO es una descarga valida.
        return DescargaHistorica(
            symbol=symbol,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
            velas=(),
            n_requests=n_requests,
            completa=False,
            error=describir_error(e),
        )
