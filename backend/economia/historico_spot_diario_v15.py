"""Adquisición OFFLINE de Spot 1d para BOT 2.0-04B-v15.

Usa exclusivamente el host público market-data-only de Binance Vision. No usa
API key, cuenta ni endpoints privados. Si cualquier página falla, la serie se
rechaza completa; no se presenta un prefijo parcial como histórico válido.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

import requests

from backend.economia.edge_historico import velas_desde_klines

DATA_API_V15 = "https://data-api.binance.vision/api/v3/klines"
DIA_MS = 86_400_000
TIMEOUT_V15_SEGUNDOS = 20


@dataclass(frozen=True)
class SpotDiarioV15:
    open_time_ms: int
    open: Decimal
    close: Decimal


@dataclass(frozen=True)
class DescargaSpotV15:
    symbol: str
    start_ms: int
    end_ms: int
    barras: Tuple[SpotDiarioV15, ...]
    n_requests: int
    completa: bool
    error: Optional[str] = None


def _validar(symbol: str, start_ms: int, end_ms: int, limit: int, timeout_segundos: int) -> None:
    if not isinstance(symbol, str) or not symbol.isalnum():
        raise ValueError("symbol invalido")
    if isinstance(start_ms, bool) or not isinstance(start_ms, int) or start_ms < 0:
        raise ValueError("start_ms invalido")
    if isinstance(end_ms, bool) or not isinstance(end_ms, int) or end_ms <= start_ms:
        raise ValueError("end_ms invalido")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit invalido")
    if isinstance(timeout_segundos, bool) or not isinstance(timeout_segundos, int) or timeout_segundos <= 0:
        raise ValueError("timeout invalido")


def descargar_spot_diario_v15(
    symbol: str,
    *,
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
    http_get=None,
    timeout_segundos: int = TIMEOUT_V15_SEGUNDOS,
) -> DescargaSpotV15:
    """Descarga klines Spot 1d en [start_ms, end_ms), fail-closed."""
    _validar(symbol, start_ms, end_ms, limit, timeout_segundos)
    get = requests.get if http_get is None else http_get
    cursor = start_ms
    n_requests = 0
    barras = []
    try:
        while cursor < end_ms:
            n_requests += 1
            r = get(
                DATA_API_V15,
                params={
                    "symbol": symbol,
                    "interval": "1d",
                    "startTime": cursor,
                    "endTime": end_ms - 1,
                    "limit": limit,
                },
                timeout=timeout_segundos,
            )
            r.raise_for_status()
            filas = r.json()
            if not isinstance(filas, list):
                raise ValueError("payload Spot no es lista")
            if not filas:
                break
            velas = velas_desde_klines(filas)
            if not velas:
                break
            for v in velas:
                if v.open_time_ms % DIA_MS:
                    raise ValueError("Spot 1d no alineado a medianoche UTC")
                if v.open <= 0 or v.close <= 0:
                    raise ValueError("Spot 1d con precio no positivo")
                if start_ms <= v.open_time_ms < end_ms:
                    barras.append(SpotDiarioV15(v.open_time_ms, v.open, v.close))
            siguiente = velas[-1].open_time_ms + DIA_MS
            if siguiente <= cursor:
                raise ValueError("paginacion Spot no avanzo")
            cursor = siguiente
            if len(filas) < limit:
                break

        tiempos = [b.open_time_ms for b in barras]
        if len(tiempos) != len(set(tiempos)):
            raise ValueError("timestamps Spot duplicados")
        return DescargaSpotV15(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            barras=tuple(sorted(barras, key=lambda b: b.open_time_ms)),
            n_requests=n_requests,
            completa=True,
            error=None,
        )
    except Exception as exc:
        return DescargaSpotV15(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            barras=(),
            n_requests=n_requests,
            completa=False,
            error=f"{type(exc).__name__}: {exc}",
        )
