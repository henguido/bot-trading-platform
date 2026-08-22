"""Auditoría pública de datos/mecánica ETH staking para BOT 2.0-04E-2.

Solo usa endpoints públicos de market data. No calcula retornos ni PnL y nunca
llama endpoints USER_DATA de staking.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, Optional, Sequence, Tuple

import requests

from backend.economia.protocolo_staking_eth_04e2 import (
    ANIOS_04E2,
    BETH_BARRAS_2022_MIN_04E2,
    BINANCE_MARKET_BASE_04E2,
    CREDENCIALES_PERMITIDAS_04E2,
    DESARROLLO_2026_ABIERTO_04E2,
    ENDPOINT_BETH_REWARDS_04E2,
    ENDPOINT_WBETH_RATE_04E2,
    ENDPOINT_WBETH_REWARDS_04E2,
    HASTA_EXCLUSIVO_04E2,
    PNL_PERMITIDO_04E2,
    REINTENTOS_04E2,
    SECURITY_REWARD_ENDPOINTS_04E2,
    SIMBOLOS_MARKET_DATA_04E2,
    STATUS_APTO_MARKET_BLOQUEADO_REWARD_04E2,
    STATUS_MARKET_INCOMPLETO_04E2,
    TIMEOUT_04E2_SEGUNDOS,
    USAR_PRECIO_SECUNDARIO_COMO_REWARD_PERMITIDO_04E2,
    WBETH_PRIMERA_BARRA_MAX_04E2,
    DESDE_04E2,
    IMPUTACION_REWARD_PERMITIDA_04E2,
)

_DIA_MS = 86_400_000
_MAX_KLINES = 1000


@dataclass(frozen=True)
class BarraDiaria04E2:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class CoberturaSimbolo04E2:
    symbol: str
    current_status: str
    first_bar_utc: str | None
    last_bar_utc: str | None
    total_bars: int
    bars_by_year: Tuple[Tuple[int, int], ...]
    missing_calendar_days: int
    max_gap_days: int


@dataclass(frozen=True)
class ResultadoAuditoriaStaking04E2:
    status: str
    market_data_apt: bool
    reward_series_public: bool
    economic_backtest_allowed: bool
    reward_security_type: str
    required_reward_endpoints: Tuple[str, ...]
    coverage: Tuple[CoberturaSimbolo04E2, ...]
    reasons: Tuple[str, ...]
    pnl_calculated: bool
    credentials_used: bool
    development_2026_opened: bool


class ClientePublico04E2:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

    def _get_json(self, path: str, params: Dict[str, object]) -> object:
        last_exc: Exception | None = None
        url = f"{BINANCE_MARKET_BASE_04E2}{path}"
        for attempt in range(REINTENTOS_04E2 + 1):
            try:
                response = self.session.get(url, params=params, timeout=TIMEOUT_04E2_SEGUNDOS)
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # pragma: no cover - retries validated via synthetic client
                last_exc = exc
                if attempt < REINTENTOS_04E2:
                    time.sleep(0.25 * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    def exchange_status(self, symbol: str) -> str:
        payload = self._get_json("/api/v3/exchangeInfo", {"symbol": symbol})
        if not isinstance(payload, dict):
            raise ValueError("exchangeInfo no es objeto")
        symbols = payload.get("symbols")
        if not isinstance(symbols, list) or len(symbols) != 1 or not isinstance(symbols[0], dict):
            raise ValueError(f"exchangeInfo inválido para {symbol}")
        if symbols[0].get("symbol") != symbol:
            raise ValueError(f"exchangeInfo devolvió símbolo distinto para {symbol}")
        status = symbols[0].get("status")
        if not isinstance(status, str) or not status:
            raise ValueError(f"status inválido para {symbol}")
        return status

    def daily_klines(self, symbol: str) -> Tuple[BarraDiaria04E2, ...]:
        start_ms = int(DESDE_04E2.timestamp() * 1000)
        end_exclusive_ms = int(HASTA_EXCLUSIVO_04E2.timestamp() * 1000)
        out: list[BarraDiaria04E2] = []
        seen: set[int] = set()
        cursor = start_ms

        while cursor < end_exclusive_ms:
            payload = self._get_json(
                "/api/v3/klines",
                {
                    "symbol": symbol,
                    "interval": "1d",
                    "startTime": cursor,
                    "endTime": end_exclusive_ms - 1,
                    "limit": _MAX_KLINES,
                },
            )
            if not isinstance(payload, list):
                raise ValueError(f"klines no es lista para {symbol}")
            if not payload:
                break

            parsed = parse_klines_04e2(payload, symbol=symbol)
            for row in parsed:
                if row.open_time_ms in seen:
                    raise ValueError(f"timestamp duplicado entre páginas {symbol}: {row.open_time_ms}")
                if not (start_ms <= row.open_time_ms < end_exclusive_ms):
                    raise ValueError(f"timestamp fuera de rango {symbol}: {row.open_time_ms}")
                seen.add(row.open_time_ms)
                out.append(row)

            next_cursor = parsed[-1].open_time_ms + _DIA_MS
            if next_cursor <= cursor:
                raise ValueError(f"paginación sin avance para {symbol}")
            cursor = next_cursor
            if len(payload) < _MAX_KLINES:
                break

        out.sort(key=lambda row: row.open_time_ms)
        return tuple(out)


def _decimal(raw: object, field: str) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} inválido") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{field} no positivo/finito")
    return value


def parse_klines_04e2(rows: Sequence[object], *, symbol: str) -> Tuple[BarraDiaria04E2, ...]:
    out: list[BarraDiaria04E2] = []
    seen: set[int] = set()
    previous: int | None = None
    for raw in rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 5:
            raise ValueError(f"kline incompleta {symbol}")
        try:
            ts = int(raw[0])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"timestamp inválido {symbol}") from exc
        if ts in seen:
            raise ValueError(f"timestamp duplicado {symbol}: {ts}")
        if previous is not None and ts <= previous:
            raise ValueError(f"timestamps no ascendentes {symbol}")
        op = _decimal(raw[1], "open")
        high = _decimal(raw[2], "high")
        low = _decimal(raw[3], "low")
        close = _decimal(raw[4], "close")
        if high < max(op, close, low) or low > min(op, close, high):
            raise ValueError(f"OHLC inconsistente {symbol} {ts}")
        seen.add(ts)
        previous = ts
        out.append(BarraDiaria04E2(ts, op, high, low, close))
    return tuple(out)


def _iso_day(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()


def resumir_cobertura_04e2(
    symbol: str, bars: Sequence[BarraDiaria04E2], current_status: str
) -> CoberturaSimbolo04E2:
    counts = {year: 0 for year in ANIOS_04E2}
    missing_days = 0
    max_gap = 0
    previous: int | None = None
    for row in bars:
        dt = datetime.fromtimestamp(row.open_time_ms / 1000, tz=timezone.utc)
        if dt.year in counts:
            counts[dt.year] += 1
        if previous is not None:
            delta_days = (row.open_time_ms - previous) // _DIA_MS
            if delta_days > 1:
                missing_days += int(delta_days - 1)
                max_gap = max(max_gap, int(delta_days - 1))
        previous = row.open_time_ms

    return CoberturaSimbolo04E2(
        symbol=symbol,
        current_status=current_status,
        first_bar_utc=_iso_day(bars[0].open_time_ms) if bars else None,
        last_bar_utc=_iso_day(bars[-1].open_time_ms) if bars else None,
        total_bars=len(bars),
        bars_by_year=tuple((year, counts[year]) for year in ANIOS_04E2),
        missing_calendar_days=missing_days,
        max_gap_days=max_gap,
    )


def evaluar_coberturas_04e2(coverage: Sequence[CoberturaSimbolo04E2]) -> Tuple[bool, Tuple[str, ...]]:
    by_symbol = {row.symbol: row for row in coverage}
    reasons: list[str] = []

    if set(by_symbol) != set(SIMBOLOS_MARKET_DATA_04E2):
        reasons.append("COBERTURA_SIMBOLOS_INCOMPLETA")
        return False, tuple(reasons)

    beth = by_symbol["BETHETH"]
    beth_by_year = dict(beth.bars_by_year)
    if beth_by_year.get(2022, 0) < BETH_BARRAS_2022_MIN_04E2:
        reasons.append("BETH_2022_INSUFICIENTE")

    wbeth = by_symbol["WBETHETH"]
    if wbeth.first_bar_utc is None:
        reasons.append("WBETH_SIN_MARKET_DATA")
    else:
        first = datetime.fromisoformat(wbeth.first_bar_utc).replace(tzinfo=timezone.utc)
        if first > WBETH_PRIMERA_BARRA_MAX_04E2:
            reasons.append("WBETH_APARECE_DEMASIADO_TARDE")

    return not reasons, tuple(reasons)


def construir_resultado_04e2(coverage: Sequence[CoberturaSimbolo04E2]) -> ResultadoAuditoriaStaking04E2:
    market_apt, market_reasons = evaluar_coberturas_04e2(coverage)

    required_endpoints = (
        ENDPOINT_BETH_REWARDS_04E2,
        ENDPOINT_WBETH_RATE_04E2,
        ENDPOINT_WBETH_REWARDS_04E2,
    )
    reward_series_public = False
    economic_backtest_allowed = False
    reasons = list(market_reasons)
    reasons.extend(
        (
            "BETH_REWARDS_REQUIERE_USER_DATA",
            "WBETH_RATE_HISTORY_REQUIERE_USER_DATA",
            "PRECIO_SECUNDARIO_NO_SUSTITUYE_REWARD_RATE",
        )
    )

    status = (
        STATUS_APTO_MARKET_BLOQUEADO_REWARD_04E2
        if market_apt
        else STATUS_MARKET_INCOMPLETO_04E2
    )
    return ResultadoAuditoriaStaking04E2(
        status=status,
        market_data_apt=market_apt,
        reward_series_public=reward_series_public,
        economic_backtest_allowed=economic_backtest_allowed,
        reward_security_type=SECURITY_REWARD_ENDPOINTS_04E2,
        required_reward_endpoints=required_endpoints,
        coverage=tuple(coverage),
        reasons=tuple(reasons),
        pnl_calculated=PNL_PERMITIDO_04E2,
        credentials_used=CREDENCIALES_PERMITIDAS_04E2,
        development_2026_opened=DESARROLLO_2026_ABIERTO_04E2,
    )


def ejecutar_auditoria_staking_04e2(
    client: Optional[ClientePublico04E2] = None,
) -> ResultadoAuditoriaStaking04E2:
    if IMPUTACION_REWARD_PERMITIDA_04E2 or USAR_PRECIO_SECUNDARIO_COMO_REWARD_PERMITIDO_04E2:
        raise RuntimeError("locks 04E-2 violados")
    client = client or ClientePublico04E2()
    coverage: list[CoberturaSimbolo04E2] = []
    for symbol in SIMBOLOS_MARKET_DATA_04E2:
        status = client.exchange_status(symbol)
        bars = client.daily_klines(symbol)
        coverage.append(resumir_cobertura_04e2(symbol, bars, status))
    return construir_resultado_04e2(coverage)
