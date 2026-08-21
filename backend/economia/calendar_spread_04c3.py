"""Réplica predeclarada 04C-3: long USD-M perpetual + short USD-M quarterly.

Solo datos públicos Binance. No usa credenciales, no ejecuta órdenes y no abre 2026.
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
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

import requests

from backend.economia.protocolo_calendar_04c3 import (
    ANIOS_04C3,
    BINANCE_DATA_04C3,
    CAPITAL_REFERENCIA_MULTIPLO_04C3,
    COBERTURA_HORARIA_STRESS_MIN_04C3,
    DAILY_MARK_FALLBACK_04C3,
    DIAS_LOOKBACK_FUNDING_04C3,
    DRAG_POR_TRADE_04C3,
    FUNDING_ALIGNMENT_MAX_OFFSET_MS_04C3,
    MAX_DRAWDOWN_ECONOMICO_04C3,
    MAX_DRAWDOWN_PROD_04C3,
    MAX_STRESS_INTRATRADE_ECONOMICO_04C3,
    MAX_STRESS_INTRATRADE_PROD_04C3,
    MEDIA_ANUAL_PROD_MIN_04C3,
    MIN_TRADES_ECONOMICOS_04C3,
    MIN_TRADES_PROD_04C3,
    PEOR_ANIO_PROD_MIN_04C3,
    REINTENTOS_04C3,
    SHARPE_TRIMESTRAL_ECONOMICO_MIN_04C3,
    SHARPE_TRIMESTRAL_PROD_MIN_04C3,
    SIMBOLOS_04C3,
    TIMEOUT_04C3_SEGUNDOS,
    UMBRAL_PREDICTED_NET_04C3,
    WIN_RATE_PROD_MIN_04C3,
    contract_code_04c3,
    entry_04c3,
    expiries_04c3,
)

getcontext().prec = 34
_HORA_MS = 3_600_000
_DIA_MS = 86_400_000
DELIVERY_FIXTURE_04C3 = Path(__file__).resolve().parent / "data" / "calendar_04c3_delivery_prices.json"


@dataclass(frozen=True)
class Punto04C3:
    open: Decimal
    high: Decimal


@dataclass(frozen=True)
class Funding04C3:
    ts_ms: int
    interval_hours: int
    rate: Decimal


@dataclass(frozen=True)
class InputOportunidad04C3:
    symbol: str
    contract: str
    expiry_ms: int
    entry_ms: int
    perp_entry: Decimal
    perp_exit: Decimal
    quarter_entry: Decimal
    delivery_price: Decimal
    trailing_funding_pnl: Decimal
    holding_funding_pnl: Decimal
    stress_hours_expected: int
    stress_hours_observed: int
    worst_stress_return: Decimal


@dataclass(frozen=True)
class ResultadoOportunidad04C3:
    symbol: str
    contract: str
    year: int
    entry_ms: int
    expiry_ms: int
    entry_spread: Decimal
    trailing_funding_cost: Decimal
    predicted_net: Decimal
    eligible: bool
    perp_pnl: Decimal
    quarter_pnl: Decimal
    holding_funding_pnl: Decimal
    gross_return: Decimal
    net_return: Decimal
    stress_hours_expected: int
    stress_hours_observed: int
    stress_coverage: Decimal
    worst_stress_return: Decimal


@dataclass(frozen=True)
class ResultadoCalendar04C3:
    data_apt: bool
    data_reasons: Tuple[str, ...]
    opportunities_total: int
    eligible_trades: int
    win_rate: Decimal
    annual_btc: Tuple[Tuple[int, Decimal], ...]
    annual_eth: Tuple[Tuple[int, Decimal], ...]
    annual_portfolio: Tuple[Tuple[int, Decimal], ...]
    quarterly_portfolio: Tuple[Tuple[int, Decimal], ...]
    mean_annual_portfolio: Decimal
    worst_year_portfolio: Decimal
    quarterly_sharpe: Decimal
    max_drawdown: Decimal
    worst_stress_intratrade: Decimal
    economic_verdict: str
    production_verdict: str
    reject_economic: Tuple[str, ...]
    reject_production: Tuple[str, ...]
    opportunities: Tuple[ResultadoOportunidad04C3, ...]


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


def _url_perp(symbol: str, dt: datetime) -> str:
    ym = _ym(dt)
    return f"{BINANCE_DATA_04C3}/futures/um/monthly/klines/{symbol}/1h/{symbol}-1h-{ym}.zip"


def _url_quarter(contract: str, dt: datetime) -> str:
    ym = _ym(dt)
    return f"{BINANCE_DATA_04C3}/futures/um/monthly/klines/{contract}/1h/{contract}-1h-{ym}.zip"


def _url_mark(symbol: str, dt: datetime) -> str:
    ym = _ym(dt)
    return f"{BINANCE_DATA_04C3}/futures/um/monthly/markPriceKlines/{symbol}/1h/{symbol}-1h-{ym}.zip"


def _url_mark_daily(symbol: str, dt: datetime) -> str:
    day = f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
    return f"{BINANCE_DATA_04C3}/futures/um/daily/markPriceKlines/{symbol}/1h/{symbol}-1h-{day}.zip"


def _url_funding(symbol: str, dt: datetime) -> str:
    ym = _ym(dt)
    return f"{BINANCE_DATA_04C3}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{ym}.zip"


class Cache04C3:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.cache: Dict[str, bytes] = {}

    def bytes(self, url: str) -> bytes:
        if url in self.cache:
            return self.cache[url]
        last_exc: Exception | None = None
        for attempt in range(REINTENTOS_04C3 + 1):
            try:
                r = self.session.get(url, timeout=TIMEOUT_04C3_SEGUNDOS)
                r.raise_for_status()
                if not r.content:
                    raise ValueError("respuesta vacia")
                self.cache[url] = r.content
                return r.content
            except Exception as exc:
                last_exc = exc
                if attempt < REINTENTOS_04C3:
                    time.sleep(0.4 * (attempt + 1))
        assert last_exc is not None
        raise last_exc


def _single_csv(payload: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"ZIP debe contener exactamente un archivo, tiene {len(names)}")
        return zf.read(names[0])


def parse_klines_04c3(payload: bytes) -> Dict[int, Punto04C3]:
    out: Dict[int, Punto04C3] = {}
    text = _single_csv(payload).decode("utf-8-sig")
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        try:
            ts = _ms(row[0])
        except (ValueError, TypeError):
            continue
        if len(row) < 3:
            raise ValueError("kline incompleta")
        op = _d(row[1], "open")
        high = _d(row[2], "high")
        if op <= 0 or high <= 0 or high < op:
            raise ValueError("kline invalida")
        if ts in out:
            raise ValueError("timestamp kline duplicado")
        out[ts] = Punto04C3(op, high)
    if not out:
        raise ValueError("kline vacia")
    return out


def _normalize_funding_ts(ts_ms: int) -> int:
    offset = ts_ms % _HORA_MS
    if offset > FUNDING_ALIGNMENT_MAX_OFFSET_MS_04C3:
        raise ValueError(f"funding offset>{FUNDING_ALIGNMENT_MAX_OFFSET_MS_04C3}ms: {offset}")
    return ts_ms - offset


def parse_funding_04c3(payload: bytes) -> Tuple[Funding04C3, ...]:
    out = []
    seen = set()
    text = _single_csv(payload).decode("utf-8-sig")
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        try:
            raw_ts = int(row[0])
            interval = int(row[1])
        except (ValueError, TypeError):
            continue
        if len(row) < 3 or interval <= 0:
            raise ValueError("funding incompleto")
        ts = _normalize_funding_ts(raw_ts)
        if ts in seen:
            raise ValueError("funding normalizado duplicado")
        seen.add(ts)
        out.append(Funding04C3(ts, interval, _d(row[2], "funding_rate")))
    out.sort(key=lambda x: x.ts_ms)
    if not out:
        raise ValueError("funding vacio")
    return tuple(out)


def _merge_klines(target: Dict[int, Punto04C3], rows: Mapping[int, Punto04C3]) -> None:
    overlap = set(target).intersection(rows)
    if overlap:
        raise ValueError(f"klines solapadas: {len(overlap)}")
    target.update(rows)


def _load_klines_months(cache: Cache04C3, urls: Iterable[str]) -> Dict[int, Punto04C3]:
    out: Dict[int, Punto04C3] = {}
    for url in urls:
        _merge_klines(out, parse_klines_04c3(cache.bytes(url)))
    return out


def _load_funding_months(cache: Cache04C3, symbol: str, months: Sequence[datetime]) -> Tuple[Funding04C3, ...]:
    all_events = []
    seen = set()
    for month in months:
        for event in parse_funding_04c3(cache.bytes(_url_funding(symbol, month))):
            if event.ts_ms in seen:
                raise ValueError("funding duplicado entre meses")
            seen.add(event.ts_ms)
            all_events.append(event)
    all_events.sort(key=lambda x: x.ts_ms)
    return tuple(all_events)


def cargar_delivery_prices_04c3() -> Dict[str, Decimal]:
    payload = json.loads(DELIVERY_FIXTURE_04C3.read_text(encoding="utf-8"))
    prices = payload.get("prices")
    expected = {
        contract_code_04c3(symbol, expiry)
        for symbol in SIMBOLOS_04C3
        for expiry in expiries_04c3()
    }
    if not isinstance(prices, dict) or set(prices) != expected:
        raise ValueError("fixture delivery no cubre exactamente 32 contratos")
    out = {k: _d(v, "delivery_price") for k, v in prices.items()}
    if any(v <= 0 for v in out.values()):
        raise ValueError("delivery price no positivo")
    return out


def _mark_at(
    *, cache: Cache04C3, symbol: str, ts_ms: int, monthly: Dict[int, Punto04C3]
) -> Decimal:
    if ts_ms in monthly:
        return monthly[ts_ms].open
    if not DAILY_MARK_FALLBACK_04C3:
        raise ValueError(f"mark faltante {symbol} {ts_ms}")
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    daily = parse_klines_04c3(cache.bytes(_url_mark_daily(symbol, dt)))
    if ts_ms not in daily:
        raise ValueError(f"mark faltante también en daily {symbol} {ts_ms}")
    monthly[ts_ms] = daily[ts_ms]
    return daily[ts_ms].open


def cargar_input_oportunidad_04c3(
    symbol: str,
    expiry: datetime,
    *,
    cache: Cache04C3,
    deliveries: Mapping[str, Decimal],
) -> InputOportunidad04C3:
    contract = contract_code_04c3(symbol, expiry)
    entry = entry_04c3(expiry)
    lookback_start = entry - timedelta(days=DIAS_LOOKBACK_FUNDING_04C3)
    entry_ms = int(entry.timestamp() * 1000)
    expiry_ms = int(expiry.timestamp() * 1000)
    lookback_ms = int(lookback_start.timestamp() * 1000)

    hold_months = _month_starts(entry, expiry)
    funding_months = _month_starts(lookback_start, expiry)

    perp = _load_klines_months(cache, (_url_perp(symbol, m) for m in hold_months))
    quarter = _load_klines_months(cache, (_url_quarter(contract, m) for m in hold_months))
    mark = _load_klines_months(cache, (_url_mark(symbol, m) for m in funding_months))
    funding = _load_funding_months(cache, symbol, funding_months)

    if entry_ms not in perp or expiry_ms not in perp:
        raise ValueError(f"perp entry/expiry faltante {contract}")
    if entry_ms not in quarter:
        raise ValueError(f"quarter entry faltante {contract}")
    if contract not in deliveries:
        raise ValueError(f"delivery faltante {contract}")

    p0 = perp[entry_ms].open
    p1 = perp[expiry_ms].open
    q0 = quarter[entry_ms].open
    delivery = deliveries[contract]

    relevant = [e for e in funding if lookback_ms <= e.ts_ms < expiry_ms]
    if not relevant:
        raise ValueError(f"funding window vacia {contract}")
    trailing_pnl = Decimal("0")
    holding_pnl = Decimal("0")
    holding_cashflows: Dict[int, Decimal] = {}
    for event in relevant:
        mark_price = _mark_at(cache=cache, symbol=symbol, ts_ms=event.ts_ms, monthly=mark)
        long_pnl = -(event.rate * mark_price)
        if lookback_ms <= event.ts_ms < entry_ms:
            trailing_pnl += -long_pnl  # coste positivo cuando long paga funding positivo
        elif entry_ms < event.ts_ms < expiry_ms:
            holding_pnl += long_pnl
            holding_cashflows[event.ts_ms] = long_pnl

    expected_hours = int((expiry_ms - entry_ms) // _HORA_MS)
    common = sorted(
        ts for ts in set(perp).intersection(quarter)
        if entry_ms <= ts < expiry_ms and ts % _HORA_MS == 0
    )
    observed_hours = len(common)
    if expected_hours <= 0:
        raise ValueError("hold no positivo")
    coverage = Decimal(observed_hours) / Decimal(expected_hours)
    if coverage < COBERTURA_HORARIA_STRESS_MIN_04C3:
        raise ValueError(f"stress coverage insuficiente {contract}: {coverage}")

    cumulative_funding = Decimal("0")
    worst = Decimal("0")
    for ts in common:
        cumulative_funding += holding_cashflows.get(ts, Decimal("0"))
        mtm = (perp[ts].open - p0) + (q0 - quarter[ts].open) + cumulative_funding
        r = mtm / p0
        if r < worst:
            worst = r

    realized_gross = ((p1 - p0) + (q0 - delivery) + holding_pnl) / p0
    if realized_gross < worst:
        worst = realized_gross

    return InputOportunidad04C3(
        symbol=symbol,
        contract=contract,
        expiry_ms=expiry_ms,
        entry_ms=entry_ms,
        perp_entry=p0,
        perp_exit=p1,
        quarter_entry=q0,
        delivery_price=delivery,
        trailing_funding_pnl=trailing_pnl,
        holding_funding_pnl=holding_pnl,
        stress_hours_expected=expected_hours,
        stress_hours_observed=observed_hours,
        worst_stress_return=worst,
    )


def evaluar_oportunidad_04c3(inp: InputOportunidad04C3) -> ResultadoOportunidad04C3:
    if inp.perp_entry <= 0:
        raise ValueError("perp entry no positivo")
    entry_spread = (inp.quarter_entry - inp.perp_entry) / inp.perp_entry
    trailing_cost = inp.trailing_funding_pnl / inp.perp_entry
    predicted_net = entry_spread - trailing_cost - DRAG_POR_TRADE_04C3
    eligible = predicted_net > UMBRAL_PREDICTED_NET_04C3
    perp_pnl = inp.perp_exit - inp.perp_entry
    quarter_pnl = inp.quarter_entry - inp.delivery_price
    gross = (perp_pnl + quarter_pnl + inp.holding_funding_pnl) / inp.perp_entry
    net = gross - DRAG_POR_TRADE_04C3 if eligible else Decimal("0")
    coverage = Decimal(inp.stress_hours_observed) / Decimal(inp.stress_hours_expected)
    year = datetime.fromtimestamp(inp.expiry_ms / 1000, tz=timezone.utc).year
    return ResultadoOportunidad04C3(
        symbol=inp.symbol,
        contract=inp.contract,
        year=year,
        entry_ms=inp.entry_ms,
        expiry_ms=inp.expiry_ms,
        entry_spread=entry_spread,
        trailing_funding_cost=trailing_cost,
        predicted_net=predicted_net,
        eligible=eligible,
        perp_pnl=perp_pnl,
        quarter_pnl=quarter_pnl,
        holding_funding_pnl=inp.holding_funding_pnl,
        gross_return=gross,
        net_return=net,
        stress_hours_expected=inp.stress_hours_expected,
        stress_hours_observed=inp.stress_hours_observed,
        stress_coverage=coverage,
        worst_stress_return=inp.worst_stress_return,
    )


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def _sharpe_quarterly(values: Sequence[Decimal]) -> Decimal:
    if len(values) < 2:
        return Decimal("0")
    xs = [float(v) for v in values]
    sd = statistics.stdev(xs)
    if sd == 0:
        return Decimal("999") if statistics.mean(xs) > 0 else Decimal("0")
    return Decimal(str(statistics.mean(xs) / sd * math.sqrt(4)))


def _max_drawdown(values: Sequence[Decimal]) -> Decimal:
    wealth = Decimal("1")
    peak = Decimal("1")
    worst = Decimal("0")
    for r in values:
        wealth *= Decimal("1") + r
        peak = max(peak, wealth)
        if peak > 0:
            worst = max(worst, (peak - wealth) / peak)
    return worst


def resultado_datos_insuficientes_04c3(reasons: Sequence[str]) -> ResultadoCalendar04C3:
    return ResultadoCalendar04C3(
        data_apt=False,
        data_reasons=tuple(reasons),
        opportunities_total=32,
        eligible_trades=0,
        win_rate=Decimal("0"),
        annual_btc=(), annual_eth=(), annual_portfolio=(), quarterly_portfolio=(),
        mean_annual_portfolio=Decimal("0"), worst_year_portfolio=Decimal("0"),
        quarterly_sharpe=Decimal("0"), max_drawdown=Decimal("0"),
        worst_stress_intratrade=Decimal("0"),
        economic_verdict="DATOS_INSUFICIENTES_04C3",
        production_verdict="NO_EVALUABLE_PRODUCCION_04C3",
        reject_economic=tuple(reasons),
        reject_production=("DATOS_INSUFICIENTES_04C3",),
        opportunities=(),
    )


def evaluar_calendar_04c3(inputs: Sequence[InputOportunidad04C3]) -> ResultadoCalendar04C3:
    expected_keys = {
        (symbol, contract_code_04c3(symbol, expiry))
        for symbol in SIMBOLOS_04C3 for expiry in expiries_04c3()
    }
    got_keys = {(i.symbol, i.contract) for i in inputs}
    if got_keys != expected_keys or len(inputs) != 32:
        return resultado_datos_insuficientes_04c3(("OPORTUNIDADES_NO_32",))

    rows = tuple(sorted((evaluar_oportunidad_04c3(i) for i in inputs), key=lambda r: (r.expiry_ms, r.symbol)))
    if any(r.stress_coverage < COBERTURA_HORARIA_STRESS_MIN_04C3 for r in rows):
        return resultado_datos_insuficientes_04c3(("COBERTURA_STRESS_INSUFICIENTE",))

    eligible = [r for r in rows if r.eligible]
    wins = sum(r.net_return > 0 for r in eligible)
    win_rate = Decimal(wins) / Decimal(len(eligible)) if eligible else Decimal("0")

    annual_by_symbol: Dict[Tuple[str, int], Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        annual_by_symbol[(row.symbol, row.year)] += row.net_return
    annual_btc = tuple((year, annual_by_symbol[("BTCUSDT", year)]) for year in ANIOS_04C3)
    annual_eth = tuple((year, annual_by_symbol[("ETHUSDT", year)]) for year in ANIOS_04C3)
    annual_portfolio = tuple(
        (year, _mean([annual_by_symbol[(s, year)] for s in SIMBOLOS_04C3]))
        for year in ANIOS_04C3
    )

    quarter_values = []
    quarterly_portfolio = []
    by_contract_expiry = defaultdict(dict)
    for row in rows:
        by_contract_expiry[row.expiry_ms][row.symbol] = row.net_return
    for expiry in expiries_04c3():
        ts = int(expiry.timestamp() * 1000)
        value = _mean([by_contract_expiry[ts].get(s, Decimal("0")) for s in SIMBOLOS_04C3])
        quarterly_portfolio.append((ts, value))
        quarter_values.append(value)

    annual_values = [v for _, v in annual_portfolio]
    mean_annual = _mean(annual_values)
    worst_year = min(annual_values, default=Decimal("0"))
    sharpe = _sharpe_quarterly(quarter_values)
    max_dd = _max_drawdown(quarter_values)
    worst_stress = min((r.worst_stress_return for r in eligible), default=Decimal("0"))

    reject_econ = []
    if len(eligible) < MIN_TRADES_ECONOMICOS_04C3:
        reject_econ.append("TRADES_ELEGIBLES_INSUFICIENTES")
    if any(v <= 0 for v in annual_values):
        reject_econ.append("NO_4_DE_4_ANIOS_POSITIVOS")
    if mean_annual <= 0:
        reject_econ.append("MEDIA_ANUAL_NO_POSITIVA")
    if sharpe < SHARPE_TRIMESTRAL_ECONOMICO_MIN_04C3:
        reject_econ.append("SHARPE_ECONOMICO_INSUFICIENTE")
    if max_dd > MAX_DRAWDOWN_ECONOMICO_04C3:
        reject_econ.append("DRAWDOWN_ECONOMICO_EXCESIVO")
    if worst_stress < -MAX_STRESS_INTRATRADE_ECONOMICO_04C3:
        reject_econ.append("STRESS_INTRATRADE_ECONOMICO_EXCESIVO")
    econ_ok = not reject_econ

    reject_prod = []
    if not econ_ok:
        reject_prod.append("GATE_ECONOMICO_NO_SUPERADO")
    if mean_annual < MEDIA_ANUAL_PROD_MIN_04C3:
        reject_prod.append("MEDIA_ANUAL_MENOR_5PCT")
    if worst_year < PEOR_ANIO_PROD_MIN_04C3:
        reject_prod.append("PEOR_ANIO_MENOR_2PCT")
    if sharpe < SHARPE_TRIMESTRAL_PROD_MIN_04C3:
        reject_prod.append("SHARPE_PRODUCCION_MENOR_1_5")
    if max_dd > MAX_DRAWDOWN_PROD_04C3:
        reject_prod.append("DRAWDOWN_PRODUCCION_MAYOR_7_5PCT")
    if worst_stress < -MAX_STRESS_INTRATRADE_PROD_04C3:
        reject_prod.append("STRESS_INTRATRADE_MENOR_NEG_7_5PCT")
    if win_rate < WIN_RATE_PROD_MIN_04C3:
        reject_prod.append("WIN_RATE_MENOR_60PCT")
    if len(eligible) < MIN_TRADES_PROD_04C3:
        reject_prod.append("TRADES_PRODUCCION_INSUFICIENTES")
    prod_ok = not reject_prod

    return ResultadoCalendar04C3(
        data_apt=True,
        data_reasons=(),
        opportunities_total=len(rows),
        eligible_trades=len(eligible),
        win_rate=win_rate,
        annual_btc=annual_btc,
        annual_eth=annual_eth,
        annual_portfolio=annual_portfolio,
        quarterly_portfolio=tuple(quarterly_portfolio),
        mean_annual_portfolio=mean_annual / CAPITAL_REFERENCIA_MULTIPLO_04C3,
        worst_year_portfolio=worst_year / CAPITAL_REFERENCIA_MULTIPLO_04C3,
        quarterly_sharpe=sharpe,
        max_drawdown=max_dd,
        worst_stress_intratrade=worst_stress,
        economic_verdict="CALENDAR_ECONOMICAMENTE_APTO_04C3" if econ_ok else "CALENDAR_ECONOMICAMENTE_FALSADO_04C3",
        production_verdict="CALENDAR_CANDIDATO_PRODUCCION_04C3" if prod_ok else "CALENDAR_NO_CANDIDATO_PRODUCCION_04C3",
        reject_economic=tuple(reject_econ),
        reject_production=tuple(reject_prod),
        opportunities=rows,
    )


def cargar_inputs_remotos_04c3(cache: Optional[Cache04C3] = None) -> tuple[Tuple[InputOportunidad04C3, ...], Tuple[str, ...]]:
    cache = cache or Cache04C3()
    try:
        deliveries = cargar_delivery_prices_04c3()
    except Exception as exc:
        return (), (f"delivery:{type(exc).__name__}:{exc}",)
    inputs = []
    errors = []
    for expiry in expiries_04c3():
        for symbol in SIMBOLOS_04C3:
            contract = contract_code_04c3(symbol, expiry)
            try:
                inputs.append(cargar_input_oportunidad_04c3(symbol, expiry, cache=cache, deliveries=deliveries))
            except Exception as exc:
                errors.append(f"{contract}:{type(exc).__name__}:{exc}")
    return tuple(inputs), tuple(errors)
