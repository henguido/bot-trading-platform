"""04E-1: long Spot + short USD-M quarterly, 28 días hasta delivery.

Solo datos públicos Binance Vision. No credenciales, no órdenes, 2026 cerrado.
"""
from __future__ import annotations

import csv
import io
import json
import math
import statistics
import time
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

import requests

from backend.economia.protocolo_spot_quarterly_04e1 import (
    ANIOS_04E1,
    BINANCE_DATA_04E1,
    CAPITAL_REFERENCIA_MULTIPLO_04E1,
    COBERTURA_HORARIA_STRESS_MIN_04E1,
    DRAG_POR_TRADE_04E1,
    MAX_DRAWDOWN_ECONOMICO_04E1,
    MAX_DRAWDOWN_PROD_04E1,
    MAX_STRESS_INTRATRADE_ECONOMICO_04E1,
    MAX_STRESS_INTRATRADE_PROD_04E1,
    MEDIA_ANUAL_PROD_MIN_04E1,
    MIN_TRADES_ECONOMICOS_04E1,
    MIN_TRADES_PROD_04E1,
    PEOR_ANIO_PROD_MIN_04E1,
    REINTENTOS_04E1,
    SHARPE_TRIMESTRAL_ECONOMICO_MIN_04E1,
    SHARPE_TRIMESTRAL_PROD_MIN_04E1,
    SIMBOLOS_04E1,
    TIMEOUT_04E1_SEGUNDOS,
    UMBRAL_BASIS_NET_04E1,
    WIN_RATE_PROD_MIN_04E1,
    contract_code_04e1,
    entry_04e1,
    expiries_04e1,
)

getcontext().prec = 34
_HORA_MS = 3_600_000
DELIVERY_FIXTURE_04E1 = Path(__file__).resolve().parent / "data" / "spot_quarterly_04e1_delivery_prices.json"


@dataclass(frozen=True)
class Punto04E1:
    open: Decimal


@dataclass(frozen=True)
class InputOportunidad04E1:
    symbol: str
    contract: str
    year: int
    entry_ms: int
    expiry_ms: int
    spot_entry: Decimal
    spot_exit: Decimal
    quarter_entry: Decimal
    delivery_price: Decimal
    stress_hours_expected: int
    stress_hours_observed: int
    worst_stress_return: Decimal


@dataclass(frozen=True)
class ResultadoOportunidad04E1:
    symbol: str
    contract: str
    year: int
    entry_basis: Decimal
    predicted_net: Decimal
    eligible: bool
    spot_return: Decimal
    futures_short_return: Decimal
    gross_return: Decimal
    net_return: Decimal
    stress_coverage: Decimal
    worst_stress_return: Decimal


@dataclass(frozen=True)
class ResultadoSpotQuarterly04E1:
    data_apt: bool
    data_reasons: Tuple[str, ...]
    opportunities_total: int
    eligible_trades: int
    win_rate: Decimal
    annual_btc: Tuple[Tuple[int, Decimal], ...]
    annual_eth: Tuple[Tuple[int, Decimal], ...]
    annual_portfolio: Tuple[Tuple[int, Decimal], ...]
    quarterly_portfolio: Tuple[Tuple[str, Decimal], ...]
    mean_annual_portfolio: Decimal
    worst_year_portfolio: Decimal
    quarterly_sharpe: Decimal
    max_drawdown: Decimal
    worst_stress_intratrade: Decimal
    economic_verdict: str
    production_verdict: str
    reject_economic: Tuple[str, ...]
    reject_production: Tuple[str, ...]
    opportunities: Tuple[ResultadoOportunidad04E1, ...]


def _d(raw, name: str = "valor") -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} invalido") from exc
    if not value.is_finite():
        raise ValueError(f"{name} no finito")
    return value


def _ms(raw: str) -> int:
    value = int(raw)
    return value // 1000 if value >= 100_000_000_000_000 else value


def _month_starts(start: datetime, end: datetime) -> Tuple[datetime, ...]:
    cur = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    last = datetime(end.year, end.month, 1, tzinfo=timezone.utc)
    out = []
    while cur <= last:
        out.append(cur)
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            cur = datetime(cur.year, cur.month + 1, 1, tzinfo=timezone.utc)
    return tuple(out)


def _ym(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def _url_spot(symbol: str, dt: datetime) -> str:
    ym = _ym(dt)
    return f"{BINANCE_DATA_04E1}/spot/monthly/klines/{symbol}/1h/{symbol}-1h-{ym}.zip"


def _url_quarter(contract: str, dt: datetime) -> str:
    ym = _ym(dt)
    return f"{BINANCE_DATA_04E1}/futures/um/monthly/klines/{contract}/1h/{contract}-1h-{ym}.zip"


class Cache04E1:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.cache: Dict[str, bytes] = {}

    def bytes(self, url: str) -> bytes:
        if url in self.cache:
            return self.cache[url]
        last_exc: Exception | None = None
        for attempt in range(REINTENTOS_04E1 + 1):
            try:
                response = self.session.get(url, timeout=TIMEOUT_04E1_SEGUNDOS)
                response.raise_for_status()
                if not response.content:
                    raise ValueError("respuesta vacia")
                self.cache[url] = response.content
                return response.content
            except Exception as exc:
                last_exc = exc
                if attempt < REINTENTOS_04E1:
                    time.sleep(0.4 * (attempt + 1))
        assert last_exc is not None
        raise last_exc


def _single_csv(payload: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = [name for name in zf.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"ZIP debe contener un archivo, tiene {len(names)}")
        return zf.read(names[0])


def parse_klines_04e1(payload: bytes) -> Dict[int, Punto04E1]:
    out: Dict[int, Punto04E1] = {}
    text = _single_csv(payload).decode("utf-8-sig")
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        try:
            ts = _ms(row[0])
        except (ValueError, TypeError):
            continue
        if len(row) < 2:
            raise ValueError("kline incompleta")
        op = _d(row[1], "open")
        if op <= 0:
            raise ValueError("open no positivo")
        if ts in out:
            raise ValueError("timestamp duplicado")
        out[ts] = Punto04E1(op)
    if not out:
        raise ValueError("kline vacia")
    return out


def _merge(target: Dict[int, Punto04E1], source: Mapping[int, Punto04E1]) -> None:
    overlap = set(target).intersection(source)
    if overlap:
        raise ValueError(f"klines solapadas: {len(overlap)}")
    target.update(source)


def _load(cache: Cache04E1, urls: Iterable[str]) -> Dict[int, Punto04E1]:
    out: Dict[int, Punto04E1] = {}
    for url in urls:
        _merge(out, parse_klines_04e1(cache.bytes(url)))
    return out


def cargar_delivery_prices_04e1() -> Dict[str, Decimal]:
    payload = json.loads(DELIVERY_FIXTURE_04E1.read_text(encoding="utf-8"))
    prices = payload.get("prices")
    expected = {
        contract_code_04e1(symbol, expiry)
        for symbol in SIMBOLOS_04E1
        for expiry in expiries_04e1()
    }
    if not isinstance(prices, dict) or set(prices) != expected:
        raise ValueError("fixture delivery no cubre exactamente 32 contratos")
    out = {key: _d(value, "delivery_price") for key, value in prices.items()}
    if any(value <= 0 for value in out.values()):
        raise ValueError("delivery price no positivo")
    return out


def cargar_input_oportunidad_04e1(
    symbol: str,
    expiry: datetime,
    *,
    cache: Cache04E1,
    deliveries: Mapping[str, Decimal],
) -> InputOportunidad04E1:
    contract = contract_code_04e1(symbol, expiry)
    entry = entry_04e1(expiry)
    entry_ms = int(entry.timestamp() * 1000)
    expiry_ms = int(expiry.timestamp() * 1000)
    months = _month_starts(entry, expiry)

    spot = _load(cache, (_url_spot(symbol, month) for month in months))
    quarter = _load(cache, (_url_quarter(contract, month) for month in months))
    if entry_ms not in spot or expiry_ms not in spot:
        raise ValueError(f"spot entry/expiry faltante {contract}")
    if entry_ms not in quarter:
        raise ValueError(f"quarter entry faltante {contract}")
    if contract not in deliveries:
        raise ValueError(f"delivery faltante {contract}")

    s0 = spot[entry_ms].open
    s1 = spot[expiry_ms].open
    f0 = quarter[entry_ms].open
    delivery = deliveries[contract]

    expected_hours = int((expiry_ms - entry_ms) // _HORA_MS)
    common = sorted(
        ts for ts in set(spot).intersection(quarter)
        if entry_ms <= ts < expiry_ms and ts % _HORA_MS == 0
    )
    observed_hours = len(common)
    if expected_hours <= 0:
        raise ValueError("hold no positivo")
    coverage = Decimal(observed_hours) / Decimal(expected_hours)
    if coverage < COBERTURA_HORARIA_STRESS_MIN_04E1:
        raise ValueError(f"stress coverage insuficiente {contract}: {coverage}")

    worst = Decimal("0")
    for ts in common:
        # Una unidad del activo Spot y una unidad base short del futuro lineal.
        mtm = (spot[ts].open - s0 + f0 - quarter[ts].open) / s0
        worst = min(worst, mtm)

    return InputOportunidad04E1(
        symbol=symbol,
        contract=contract,
        year=expiry.year,
        entry_ms=entry_ms,
        expiry_ms=expiry_ms,
        spot_entry=s0,
        spot_exit=s1,
        quarter_entry=f0,
        delivery_price=delivery,
        stress_hours_expected=expected_hours,
        stress_hours_observed=observed_hours,
        worst_stress_return=worst,
    )


def evaluar_oportunidad_04e1(row: InputOportunidad04E1) -> ResultadoOportunidad04E1:
    basis = row.quarter_entry / row.spot_entry - Decimal("1")
    predicted_net = basis - DRAG_POR_TRADE_04E1
    eligible = predicted_net > UMBRAL_BASIS_NET_04E1
    spot_return = row.spot_exit / row.spot_entry - Decimal("1")
    futures_short = (row.quarter_entry - row.delivery_price) / row.spot_entry
    gross = spot_return + futures_short
    net = gross - DRAG_POR_TRADE_04E1 if eligible else Decimal("0")
    coverage = Decimal(row.stress_hours_observed) / Decimal(row.stress_hours_expected)
    return ResultadoOportunidad04E1(
        symbol=row.symbol,
        contract=row.contract,
        year=row.year,
        entry_basis=basis,
        predicted_net=predicted_net,
        eligible=eligible,
        spot_return=spot_return,
        futures_short_return=futures_short,
        gross_return=gross,
        net_return=net,
        stress_coverage=coverage,
        worst_stress_return=row.worst_stress_return if eligible else Decimal("0"),
    )


def _annual(rows: Sequence[ResultadoOportunidad04E1], symbol: str) -> Tuple[Tuple[int, Decimal], ...]:
    return tuple(
        (year, sum((r.net_return for r in rows if r.symbol == symbol and r.year == year), Decimal("0")))
        for year in ANIOS_04E1
    )


def _quarter_key(contract: str) -> str:
    return contract.rsplit("_", 1)[1]


def _quarterly_portfolio(rows: Sequence[ResultadoOportunidad04E1]) -> Tuple[Tuple[str, Decimal], ...]:
    by_q: Dict[str, list[Decimal]] = defaultdict(list)
    for row in rows:
        by_q[_quarter_key(row.contract)].append(row.net_return)
    return tuple((key, sum(vals, Decimal("0")) / Decimal(len(vals))) for key, vals in sorted(by_q.items()))


def _annual_portfolio(rows: Sequence[ResultadoOportunidad04E1]) -> Tuple[Tuple[int, Decimal], ...]:
    q = _quarterly_portfolio(rows)
    return tuple(
        (year, sum((value for key, value in q if int(key[:2]) == year % 100), Decimal("0")))
        for year in ANIOS_04E1
    )


def _sharpe_quarterly(q: Sequence[Tuple[str, Decimal]]) -> Decimal:
    vals = [float(value) for _, value in q]
    if len(vals) < 2:
        return Decimal("0")
    sd = statistics.stdev(vals)
    if sd == 0:
        return Decimal("0")
    return Decimal(str((statistics.mean(vals) / sd) * math.sqrt(4)))


def _max_drawdown(q: Sequence[Tuple[str, Decimal]]) -> Decimal:
    equity = Decimal("1")
    peak = Decimal("1")
    worst = Decimal("0")
    for _, value in q:
        equity *= Decimal("1") + value
        peak = max(peak, equity)
        dd = equity / peak - Decimal("1")
        worst = min(worst, dd)
    return -worst


def evaluar_04e1(inputs: Sequence[InputOportunidad04E1], data_reasons: Sequence[str] = ()) -> ResultadoSpotQuarterly04E1:
    rows = tuple(evaluar_oportunidad_04e1(row) for row in inputs)
    data_apt = not data_reasons and len(rows) == 32 and all(r.stress_coverage >= COBERTURA_HORARIA_STRESS_MIN_04E1 or not r.eligible for r in rows)
    eligible = [r for r in rows if r.eligible]
    wins = sum(1 for r in eligible if r.net_return > 0)
    win_rate = Decimal(wins) / Decimal(len(eligible)) if eligible else Decimal("0")
    annual_btc = _annual(rows, "BTCUSDT")
    annual_eth = _annual(rows, "ETHUSDT")
    annual_portfolio = _annual_portfolio(rows)
    quarterly = _quarterly_portfolio(rows)
    annual_values = [value for _, value in annual_portfolio]
    mean_annual = sum(annual_values, Decimal("0")) / Decimal(len(annual_values)) if annual_values else Decimal("0")
    worst_year = min(annual_values) if annual_values else Decimal("0")
    sharpe = _sharpe_quarterly(quarterly)
    max_dd = _max_drawdown(quarterly)
    worst_stress = min((r.worst_stress_return for r in eligible), default=Decimal("0"))

    reject_econ = []
    if not data_apt:
        reject_econ.append("DATOS_NO_APTOS")
    if len(eligible) < MIN_TRADES_ECONOMICOS_04E1:
        reject_econ.append("TRADES_ELEGIBLES_INSUFICIENTES")
    if not all(value > 0 for value in annual_values):
        reject_econ.append("NO_4_DE_4_ANIOS_POSITIVOS")
    if mean_annual <= 0:
        reject_econ.append("MEDIA_ANUAL_NO_POSITIVA")
    if sharpe < SHARPE_TRIMESTRAL_ECONOMICO_MIN_04E1:
        reject_econ.append("SHARPE_ECONOMICO_INSUFICIENTE")
    if max_dd > MAX_DRAWDOWN_ECONOMICO_04E1:
        reject_econ.append("DRAWDOWN_ECONOMICO_EXCESIVO")
    if -worst_stress > MAX_STRESS_INTRATRADE_ECONOMICO_04E1:
        reject_econ.append("STRESS_ECONOMICO_EXCESIVO")
    economic = "SPOT_QUARTERLY_ECONOMICAMENTE_APTO_04E1" if not reject_econ else "SPOT_QUARTERLY_ECONOMICAMENTE_FALSADO_04E1"

    reject_prod = []
    if reject_econ:
        reject_prod.append("GATE_ECONOMICO_NO_SUPERADO")
    if mean_annual < MEDIA_ANUAL_PROD_MIN_04E1:
        reject_prod.append("MEDIA_ANUAL_MENOR_5PCT")
    if worst_year < PEOR_ANIO_PROD_MIN_04E1:
        reject_prod.append("PEOR_ANIO_MENOR_2PCT")
    if sharpe < SHARPE_TRIMESTRAL_PROD_MIN_04E1:
        reject_prod.append("SHARPE_PRODUCCION_MENOR_1_5")
    if max_dd > MAX_DRAWDOWN_PROD_04E1:
        reject_prod.append("DRAWDOWN_PRODUCCION_EXCESIVO")
    if -worst_stress > MAX_STRESS_INTRATRADE_PROD_04E1:
        reject_prod.append("STRESS_PRODUCCION_EXCESIVO")
    if win_rate < WIN_RATE_PROD_MIN_04E1:
        reject_prod.append("WIN_RATE_MENOR_60PCT")
    if len(eligible) < MIN_TRADES_PROD_04E1:
        reject_prod.append("TRADES_PRODUCCION_INSUFICIENTES")
    production = "SPOT_QUARTERLY_CANDIDATO_PRODUCCION_04E1" if not reject_prod else "SPOT_QUARTERLY_NO_CANDIDATO_PRODUCCION_04E1"

    return ResultadoSpotQuarterly04E1(
        data_apt=data_apt,
        data_reasons=tuple(data_reasons),
        opportunities_total=len(rows),
        eligible_trades=len(eligible),
        win_rate=win_rate,
        annual_btc=annual_btc,
        annual_eth=annual_eth,
        annual_portfolio=annual_portfolio,
        quarterly_portfolio=quarterly,
        mean_annual_portfolio=mean_annual,
        worst_year_portfolio=worst_year,
        quarterly_sharpe=sharpe,
        max_drawdown=max_dd,
        worst_stress_intratrade=worst_stress,
        economic_verdict=economic,
        production_verdict=production,
        reject_economic=tuple(reject_econ),
        reject_production=tuple(reject_prod),
        opportunities=rows,
    )


def descargar_inputs_04e1(cache: Cache04E1 | None = None) -> Tuple[Tuple[InputOportunidad04E1, ...], Tuple[str, ...]]:
    cache = cache or Cache04E1()
    deliveries = cargar_delivery_prices_04e1()
    rows = []
    errors = []
    for expiry in expiries_04e1():
        for symbol in SIMBOLOS_04E1:
            try:
                rows.append(cargar_input_oportunidad_04e1(symbol, expiry, cache=cache, deliveries=deliveries))
            except Exception as exc:
                errors.append(f"{contract_code_04e1(symbol, expiry)}:{type(exc).__name__}:{exc}")
    return tuple(rows), tuple(errors)
