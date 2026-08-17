"""Adquisicion historica Spot para BOT 2.0-04B-0.

Es un adaptador OFFLINE: nadie en `main.py` lo importa. Puede descargar klines
por el conector Binance existente o por el host publico market-data-only
`data-api.binance.vision`, que no requiere autenticacion.

Regla de integridad: si falla cualquier pagina, NO devuelve el prefijo parcial.
Una serie truncada presentada como completa contaminaria la evaluacion mas que
un fallo explicito.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import requests

from backend.economia.edge_historico import Vela, velas_desde_klines
from backend.telemetria_http import OPERACION_NULA, anotar_elementos, describir_error

DATA_API_BINANCE_VISION = "https://data-api.binance.vision/api/v3/klines"
TIMEOUT_HISTORICO_SEGUNDOS = 20

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
    fuente: str = "api.binance.com"


def _validar_parametros(symbol: str, interval: str, start_ms: int,
                        end_ms: int, limit: int) -> None:
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


def _finalizar_paginas(symbol: str, interval: str, start_ms: int, end_ms: int,
                       paginas, n_requests: int, *, fuente: str,
                       op=OPERACION_NULA) -> DescargaHistorica:
    tiempos = [v.open_time_ms for v in paginas]
    if len(tiempos) != len(set(tiempos)):
        raise ValueError("klines duplicados entre paginas")
    velas = tuple(sorted(paginas, key=lambda v: v.open_time_ms))
    anotar_elementos(op, len(velas))
    return DescargaHistorica(
        symbol=symbol, interval=interval, start_ms=start_ms, end_ms=end_ms,
        velas=velas, n_requests=n_requests, completa=True, error=None,
        fuente=fuente)


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
    """Descarga [start_ms, end_ms] por el conector existente de Binance."""
    _validar_parametros(symbol, interval, start_ms, end_ms, limit)

    op = medicion if medicion is not None else OPERACION_NULA
    paso_ms = INTERVALOS_MS[interval]
    cursor = start_ms
    paginas = []
    n_requests = 0

    try:
        binance.init_client()
        while cursor <= end_ms:
            n_requests += 1
            with op.peticion(observador=binance.observador_http()):
                filas = binance.client.get_klines(
                    symbol=symbol, interval=interval, startTime=cursor,
                    endTime=end_ms, limit=limit)

            if not filas:
                break
            if not isinstance(filas, list):
                raise ValueError("payload de klines no es lista")
            pagina = velas_desde_klines(filas)
            if not pagina:
                break
            paginas.extend(pagina)

            ultimo_open = pagina[-1].open_time_ms
            siguiente = ultimo_open + paso_ms
            if siguiente <= cursor:
                raise ValueError("paginacion de klines no avanzo")
            cursor = siguiente
            if len(filas) < limit:
                break

        return _finalizar_paginas(
            symbol, interval, start_ms, end_ms, paginas, n_requests,
            fuente="api.binance.com", op=op)
    except Exception as e:
        return DescargaHistorica(
            symbol=symbol, interval=interval, start_ms=start_ms, end_ms=end_ms,
            velas=(), n_requests=n_requests, completa=False,
            error=describir_error(e), fuente="api.binance.com")


def descargar_klines_data_api(
    symbol: str,
    *,
    interval: str = "1h",
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
    http_get=None,
    timeout_segundos: int = TIMEOUT_HISTORICO_SEGUNDOS,
) -> DescargaHistorica:
    """Descarga del host publico market-data-only de Binance Vision.

    No usa API key, firma, cuenta ni endpoints privados. `http_get` es
    inyectable para tests. Cada pagina fallida invalida la descarga completa.
    """
    _validar_parametros(symbol, interval, start_ms, end_ms, limit)
    if isinstance(timeout_segundos, bool) or not isinstance(timeout_segundos, int) \
            or timeout_segundos <= 0:
        raise ValueError("timeout_segundos debe ser entero positivo")

    get = requests.get if http_get is None else http_get
    paso_ms = INTERVALOS_MS[interval]
    cursor = start_ms
    paginas = []
    n_requests = 0

    try:
        while cursor <= end_ms:
            n_requests += 1
            respuesta = get(
                DATA_API_BINANCE_VISION,
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": limit,
                },
                timeout=timeout_segundos,
            )
            respuesta.raise_for_status()
            filas = respuesta.json()
            if not filas:
                break
            if not isinstance(filas, list):
                raise ValueError("payload de klines no es lista")
            pagina = velas_desde_klines(filas)
            if not pagina:
                break
            paginas.extend(pagina)

            ultimo_open = pagina[-1].open_time_ms
            siguiente = ultimo_open + paso_ms
            if siguiente <= cursor:
                raise ValueError("paginacion de klines no avanzo")
            cursor = siguiente
            if len(filas) < limit:
                break

        return _finalizar_paginas(
            symbol, interval, start_ms, end_ms, paginas, n_requests,
            fuente="data-api.binance.vision")
    except Exception as e:
        return DescargaHistorica(
            symbol=symbol, interval=interval, start_ms=start_ms, end_ms=end_ms,
            velas=(), n_requests=n_requests, completa=False,
            error=describir_error(e), fuente="data-api.binance.vision")
