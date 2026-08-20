"""Adquisición OFFLINE de funding USD-M para BOT 2.0-04B-v18."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Sequence, Tuple

import requests

from backend.economia.protocolo_funding_v18 import (
    FUNDING_URL_V18,
    LIMITE_PAGINA_V18,
    TIMEOUT_V18_SEGUNDOS,
)


@dataclass(frozen=True)
class EventoFundingV18:
    symbol: str
    funding_time_ms: int
    funding_rate: Decimal


@dataclass(frozen=True)
class DescargaFundingV18:
    symbol: str
    eventos: Tuple[EventoFundingV18, ...]
    completa: bool
    n_requests: int
    status_http: Optional[int]
    error: Optional[str]


def _decimal_finito(valor: Any, nombre: str) -> Decimal:
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{nombre} invalido") from exc
    if not d.is_finite():
        raise ValueError(f"{nombre} no finito")
    return d


def parsear_funding_v18(
    payload: Sequence[Mapping[str, Any]],
    *,
    symbol_esperado: str,
    desde_ms: int,
    hasta_exclusivo_ms: int,
) -> Tuple[EventoFundingV18, ...]:
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise ValueError("payload funding debe ser lista")
    eventos = []
    vistos = set()
    anterior = None
    for item in payload:
        if not isinstance(item, Mapping):
            raise ValueError("item funding invalido")
        symbol = str(item.get("symbol", ""))
        if symbol != symbol_esperado:
            raise ValueError("symbol funding inesperado")
        try:
            ts = int(item["fundingTime"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("fundingTime invalido") from exc
        if ts < desde_ms or ts >= hasta_exclusivo_ms:
            raise ValueError("fundingTime fuera de rango")
        if ts in vistos:
            raise ValueError("fundingTime duplicado")
        if anterior is not None and ts <= anterior:
            raise ValueError("funding no ascendente")
        vistos.add(ts)
        anterior = ts
        eventos.append(
            EventoFundingV18(
                symbol=symbol,
                funding_time_ms=ts,
                funding_rate=_decimal_finito(item.get("fundingRate"), "fundingRate"),
            )
        )
    return tuple(eventos)


def descargar_funding_rango_v18(
    symbol: str,
    desde_ms: int,
    hasta_exclusivo_ms: int,
    *,
    http_get=None,
    timeout_segundos: int = TIMEOUT_V18_SEGUNDOS,
    limite: int = LIMITE_PAGINA_V18,
) -> DescargaFundingV18:
    """Descarga rango completo con paginación ascendente y sin prefijo parcial."""
    if not isinstance(symbol, str) or not symbol.isalnum():
        raise ValueError("symbol invalido")
    if isinstance(desde_ms, bool) or not isinstance(desde_ms, int):
        raise ValueError("desde_ms invalido")
    if isinstance(hasta_exclusivo_ms, bool) or not isinstance(hasta_exclusivo_ms, int) or hasta_exclusivo_ms <= desde_ms:
        raise ValueError("hasta_exclusivo_ms invalido")
    if isinstance(timeout_segundos, bool) or not isinstance(timeout_segundos, int) or timeout_segundos <= 0:
        raise ValueError("timeout invalido")
    if isinstance(limite, bool) or not isinstance(limite, int) or not 1 <= limite <= 1000:
        raise ValueError("limite invalido")

    get = requests.get if http_get is None else http_get
    cursor = desde_ms
    acumulados = []
    vistos = set()
    n_requests = 0
    ultimo_status = None
    try:
        while cursor < hasta_exclusivo_ms:
            params = {
                "symbol": symbol,
                "startTime": cursor,
                "endTime": hasta_exclusivo_ms - 1,
                "limit": limite,
            }
            n_requests += 1
            r = get(FUNDING_URL_V18, params=params, timeout=timeout_segundos)
            ultimo_status = int(r.status_code)
            r.raise_for_status()
            payload = r.json()
            if not isinstance(payload, list):
                raise ValueError("respuesta funding no es lista")
            if not payload:
                break
            pagina = parsear_funding_v18(
                payload,
                symbol_esperado=symbol,
                desde_ms=cursor,
                hasta_exclusivo_ms=hasta_exclusivo_ms,
            )
            if not pagina:
                break
            for evento in pagina:
                if evento.funding_time_ms in vistos:
                    raise ValueError("funding duplicado entre paginas")
                vistos.add(evento.funding_time_ms)
                acumulados.append(evento)
            ultimo_ts = pagina[-1].funding_time_ms
            siguiente = ultimo_ts + 1
            if siguiente <= cursor:
                raise ValueError("paginacion funding no avanza")
            cursor = siguiente
            if len(payload) < limite:
                break
        return DescargaFundingV18(symbol, tuple(acumulados), True, n_requests, ultimo_status, None)
    except Exception as exc:
        return DescargaFundingV18(
            symbol=symbol,
            eventos=(),
            completa=False,
            n_requests=n_requests,
            status_http=ultimo_status,
            error=f"{type(exc).__name__}: {exc}",
        )
