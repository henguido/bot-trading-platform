"""Réplica literature-first BOT 2.0-04C-2: long Spot + short USD-M perpetual.

Solo datos públicos. No usa credenciales, no ejecuta órdenes y no abre 2026.
"""
from __future__ import annotations

import csv
import io
import math
import statistics
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, getcontext
from typing import Dict, Iterable, Mapping, Sequence, Tuple

import requests

from backend.economia.protocolo_carry_04c2 import (
    ANIOS_04C2,
    BINANCE_DATA_04C2,
    CAPITAL_REFERENCIA_MULTIPLO_04C2,
    COBERTURA_ALINEADA_MIN_04C2,
    DAILY_ARCHIVE_FALLBACK_04C2,
    DESDE_04C2,
    DRAG_ANUAL_NOTIONAL_04C2,
    FUNDING_ALIGNMENT_MAX_OFFSET_MS_04C2,
    HASTA_EXCLUSIVO_04C2,
    MAX_DRAWDOWN_ECONOMICO_04C2,
    MAX_DRAWDOWN_PROD_04C2,
    MAX_WORKERS_04C2,
    MEDIA_ANUAL_COMMITTED_PROD_MIN_04C2,
    PEOR_ANIO_COMMITTED_PROD_MIN_04C2,
    REINTENTOS_04C2,
    SHARPE_ECONOMICO_MIN_04C2,
    SHARPE_PROD_MIN_04C2,
    SIMBOLOS_04C2,
    TIMEOUT_04C2_SEGUNDOS,
)

getcontext().prec = 34
_DIA_MS = 86_400_000
_HORA_MS = 3_600_000


@dataclass(frozen=True)
class PuntoPrecio04C2:
    open: Decimal
    high: Decimal


@dataclass(frozen=True)
class EventoFunding04C2:
    ts_ms: int
    interval_hours: int
    rate: Decimal


@dataclass(frozen=True)
class SerieSimbolo04C2:
    symbol: str
    funding: Tuple[EventoFunding04C2, ...]
    spot: Mapping[int, PuntoPrecio04C2]
    perp: Mapping[int, PuntoPrecio04C2]
    mark: Mapping[int, PuntoPrecio04C2]
    meses_ok: Mapping[str, int]
    errores: Tuple[str, ...]


@dataclass(frozen=True)
class AuditoriaSimbolo04C2:
    symbol: str
    funding_events: int
    aligned_events: int
    coverage: Decimal
    funding_months: int
    spot_months: int
    perp_months: int
    mark_months: int
    duplicate_funding: int
    noncontiguous_intervals: int
    interval_hours: Tuple[Tuple[int, int], ...]
    years: Tuple[int, ...]
    apt: bool
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoAnualActivo04C2:
    symbol: str
    year: int
    intervals: int
    start_spot: Decimal
    start_perp: Decimal
    funding_return_notional: Decimal
    basis_return_notional: Decimal
    gross_return_notional: Decimal
    net_return_notional: Decimal
    net_return_committed: Decimal
    max_mark_excursion: Decimal


@dataclass(frozen=True)
class ResultadoAnualPortafolio04C2:
    year: int
    net_return_notional: Decimal
    net_return_committed: Decimal
    funding_return_notional: Decimal


@dataclass(frozen=True)
class ResultadoCarry04C2:
    data_apt: bool
    data_reasons: Tuple[str, ...]
    audits: Tuple[AuditoriaSimbolo04C2, ...]
    annual_assets: Tuple[ResultadoAnualActivo04C2, ...]
    annual_portfolio: Tuple[ResultadoAnualPortafolio04C2, ...]
    mean_annual_net_notional: Decimal
    mean_annual_net_committed: Decimal
    worst_year_net_committed: Decimal
    daily_sharpe_net: Decimal
    max_drawdown_net: Decimal
    worst_day_net: Decimal
    positive_day_fraction: Decimal
    total_funding_return_notional: Decimal
    economic_verdict: str
    production_verdict: str
    reject_economic: Tuple[str, ...]
    reject_production: Tuple[str, ...]


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
    # Binance Spot usa microsegundos en archivos recientes; normalizamos a ms.
    return value // 1000 if value >= 100_000_000_000_000 else value


def _normalizar_funding_ts_04c2(raw_ts: int) -> int:
    """Mapea fundingTime al inicio de su hora nominal solo dentro del gate pre-PnL.

    Auditoría completa 2022-2025 previa a PnL: 8,766 eventos BTC/ETH,
    offset máximo 31 ms y p99 22 ms. Cualquier offset >1 s falla cerrado.
    """
    if raw_ts < 0:
        raise ValueError("funding timestamp negativo")
    offset = raw_ts % _HORA_MS
    if offset > FUNDING_ALIGNMENT_MAX_OFFSET_MS_04C2:
        raise ValueError(f"funding timestamp fuera de tolerancia: offset_ms={offset}")
    return raw_ts - offset


def _iter_months() -> Iterable[Tuple[int, int]]:
    for year in ANIOS_04C2:
        for month in range(1, 13):
            yield year, month


def _url(kind: str, symbol: str, year: int, month: int) -> str:
    ym = f"{year:04d}-{month:02d}"
    if kind == "spot":
        return f"{BINANCE_DATA_04C2}/spot/monthly/klines/{symbol}/1h/{symbol}-1h-{ym}.zip"
    if kind == "perp":
        return f"{BINANCE_DATA_04C2}/futures/um/monthly/klines/{symbol}/1h/{symbol}-1h-{ym}.zip"
    if kind == "mark":
        return f"{BINANCE_DATA_04C2}/futures/um/monthly/markPriceKlines/{symbol}/1h/{symbol}-1h-{ym}.zip"
    if kind == "funding":
        return f"{BINANCE_DATA_04C2}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{ym}.zip"
    raise ValueError(f"kind desconocido: {kind}")


def _daily_mark_url(symbol: str, dt: date) -> str:
    ds = dt.isoformat()
    return (
        f"{BINANCE_DATA_04C2}/futures/um/daily/markPriceKlines/"
        f"{symbol}/1h/{symbol}-1h-{ds}.zip"
    )


def _download(url: str) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(REINTENTOS_04C2 + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT_04C2_SEGUNDOS)
            r.raise_for_status()
            if not r.content:
                raise ValueError("respuesta vacia")
            return r.content
        except Exception as exc:  # transporte solamente; el protocolo no cambia
            last_exc = exc
            if attempt < REINTENTOS_04C2:
                time.sleep(0.4 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _single_csv(payload: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"ZIP debe contener exactamente un archivo, tiene {len(names)}")
        return zf.read(names[0])


def parse_klines_04c2(payload: bytes) -> Dict[int, PuntoPrecio04C2]:
    out: Dict[int, PuntoPrecio04C2] = {}
    text = _single_csv(payload).decode("utf-8-sig")
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        try:
            ts = _ms(row[0])
        except (ValueError, TypeError):
            continue  # header
        if len(row) < 3:
            raise ValueError("kline incompleta")
        op = _d(row[1], "open")
        high = _d(row[2], "high")
        if op <= 0 or high <= 0 or high < op:
            raise ValueError("kline con precio invalido")
        if ts in out:
            raise ValueError("timestamp kline duplicado")
        out[ts] = PuntoPrecio04C2(op, high)
    if not out:
        raise ValueError("kline vacia")
    return out


def parse_funding_04c2(payload: bytes) -> Tuple[EventoFunding04C2, ...]:
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
            continue  # header
        if len(row) < 3 or raw_ts < 0 or interval <= 0:
            raise ValueError("funding incompleto/invalido")
        ts = _normalizar_funding_ts_04c2(raw_ts)
        rate = _d(row[2], "funding_rate")
        if ts in seen:
            raise ValueError("funding timestamp normalizado duplicado")
        seen.add(ts)
        out.append(EventoFunding04C2(ts, interval, rate))
    out.sort(key=lambda x: x.ts_ms)
    return tuple(out)


def _completar_mark_diario_04c2(
    symbol: str,
    funding: Sequence[EventoFunding04C2],
    mark: Dict[int, PuntoPrecio04C2],
    errors: list[str],
) -> None:
    """Recupera solo huecos mark en funding hours desde el archivo daily oficial.

    No interpola. Si el daily no existe o tampoco contiene la hora, se deja el
    hueco para que el gate de datos falle cerrado.
    """
    if not DAILY_ARCHIVE_FALLBACK_04C2:
        return
    missing_ts = sorted({e.ts_ms for e in funding if e.ts_ms not in mark})
    if not missing_ts:
        return
    by_day: Dict[date, list[int]] = defaultdict(list)
    for ts in missing_ts:
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        by_day[dt.date()].append(ts)
    for day, wanted in sorted(by_day.items()):
        url = _daily_mark_url(symbol, day)
        try:
            rows = parse_klines_04c2(_download(url))
        except Exception as exc:
            errors.append(f"daily_mark:{day}:{type(exc).__name__}:{exc}:{url}")
            continue
        for ts in wanted:
            if ts in rows:
                mark[ts] = rows[ts]


def cargar_serie_remota_04c2(symbol: str) -> SerieSimbolo04C2:
    if symbol not in SIMBOLOS_04C2:
        raise ValueError("symbol fuera del protocolo")
    tasks = []
    for year, month in _iter_months():
        for kind in ("spot", "perp", "mark", "funding"):
            tasks.append((kind, year, month, _url(kind, symbol, year, month)))

    payloads: Dict[Tuple[str, int, int], bytes] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_04C2) as pool:
        futures = {pool.submit(_download, url): (kind, year, month, url) for kind, year, month, url in tasks}
        for fut in as_completed(futures):
            kind, year, month, url = futures[fut]
            try:
                payloads[(kind, year, month)] = fut.result()
            except Exception as exc:
                errors.append(f"{kind}:{year:04d}-{month:02d}:{type(exc).__name__}:{exc}:{url}")

    spot: Dict[int, PuntoPrecio04C2] = {}
    perp: Dict[int, PuntoPrecio04C2] = {}
    mark: Dict[int, PuntoPrecio04C2] = {}
    funding = []
    meses = Counter()
    for (kind, year, month), payload in sorted(payloads.items()):
        try:
            if kind == "funding":
                rows = parse_funding_04c2(payload)
                lo = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)
                if month == 12:
                    hi_dt = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
                else:
                    hi_dt = datetime(year, month + 1, 1, tzinfo=timezone.utc)
                hi = int(hi_dt.timestamp() * 1000)
                if any(not (lo <= e.ts_ms < hi) for e in rows):
                    raise ValueError("funding fuera del mes nominal")
                funding.extend(rows)
            else:
                rows = parse_klines_04c2(payload)
                target = {"spot": spot, "perp": perp, "mark": mark}[kind]
                overlap = set(target).intersection(rows)
                if overlap:
                    raise ValueError(f"timestamps duplicados entre meses: {len(overlap)}")
                target.update(rows)
            meses[kind] += 1
        except Exception as exc:
            errors.append(f"parse:{kind}:{year:04d}-{month:02d}:{type(exc).__name__}:{exc}")

    funding.sort(key=lambda x: x.ts_ms)
    _completar_mark_diario_04c2(symbol, funding, mark, errors)
    return SerieSimbolo04C2(
        symbol=symbol,
        funding=tuple(funding),
        spot=spot,
        perp=perp,
        mark=mark,
        meses_ok=dict(meses),
        errores=tuple(sorted(errors)),
    )


def auditar_serie_04c2(s: SerieSimbolo04C2) -> AuditoriaSimbolo04C2:
    times = [e.ts_ms for e in s.funding]
    duplicates = len(times) - len(set(times))
    aligned = [e for e in s.funding if e.ts_ms in s.spot and e.ts_ms in s.perp and e.ts_ms in s.mark]
    coverage = Decimal(len(aligned)) / Decimal(len(s.funding)) if s.funding else Decimal("0")
    intervals = Counter(e.interval_hours for e in s.funding)
    years = tuple(sorted({datetime.fromtimestamp(e.ts_ms / 1000, tz=timezone.utc).year for e in aligned}))

    noncontiguous = 0
    by_year = defaultdict(list)
    for e in aligned:
        by_year[datetime.fromtimestamp(e.ts_ms / 1000, tz=timezone.utc).year].append(e)
    for year, events in by_year.items():
        if year not in ANIOS_04C2:
            continue
        for prev, cur in zip(events, events[1:]):
            delta = cur.ts_ms - prev.ts_ms
            if delta != cur.interval_hours * _HORA_MS:
                noncontiguous += 1

    reasons = list(s.errores)
    for kind in ("funding", "spot", "perp", "mark"):
        if s.meses_ok.get(kind, 0) != 48:
            reasons.append(f"MESES_{kind.upper()}_{s.meses_ok.get(kind, 0)}_DE_48")
    if duplicates:
        reasons.append("FUNDING_DUPLICADO")
    if coverage < COBERTURA_ALINEADA_MIN_04C2:
        reasons.append("COBERTURA_ALINEADA_INSUFICIENTE")
    if years != ANIOS_04C2:
        reasons.append("ANIOS_INCOMPLETOS")
    if any(not (int(DESDE_04C2.timestamp() * 1000) <= ts < int(HASTA_EXCLUSIVO_04C2.timestamp() * 1000)) for ts in times):
        reasons.append("FUNDING_FUERA_2022_2025")
    if noncontiguous:
        reasons.append("INTERVALOS_FUNDING_NO_CONTIGUOS")

    return AuditoriaSimbolo04C2(
        symbol=s.symbol,
        funding_events=len(s.funding),
        aligned_events=len(aligned),
        coverage=coverage,
        funding_months=s.meses_ok.get("funding", 0),
        spot_months=s.meses_ok.get("spot", 0),
        perp_months=s.meses_ok.get("perp", 0),
        mark_months=s.meses_ok.get("mark", 0),
        duplicate_funding=duplicates,
        noncontiguous_intervals=noncontiguous,
        interval_hours=tuple(sorted(intervals.items())),
        years=years,
        apt=not reasons,
        reasons=tuple(reasons),
    )


def _annual_asset(s: SerieSimbolo04C2, year: int) -> tuple[ResultadoAnualActivo04C2, Dict[date, Decimal]]:
    events = [
        e for e in s.funding
        if datetime.fromtimestamp(e.ts_ms / 1000, tz=timezone.utc).year == year
        and e.ts_ms in s.spot and e.ts_ms in s.perp and e.ts_ms in s.mark
    ]
    if len(events) < 2:
        raise ValueError(f"eventos insuficientes {s.symbol} {year}")

    first = events[0]
    last = events[-1]
    s_start = s.spot[first.ts_ms].open
    f_start = s.perp[first.ts_ms].open
    s_end = s.spot[last.ts_ms].open
    f_end = s.perp[last.ts_ms].open

    funding_pnl = Decimal("0")
    daily = defaultdict(lambda: Decimal("0"))
    for prev, cur in zip(events, events[1:]):
        expected = cur.interval_hours * _HORA_MS
        if cur.ts_ms - prev.ts_ms != expected:
            raise ValueError(f"intervalo no contiguo {s.symbol} {year}: {prev.ts_ms}->{cur.ts_ms}")
        s0 = s.spot[prev.ts_ms].open
        s1 = s.spot[cur.ts_ms].open
        f0 = s.perp[prev.ts_ms].open
        f1 = s.perp[cur.ts_ms].open
        m1 = s.mark[cur.ts_ms].open
        fp = cur.rate * m1
        pnl = (s1 - s0) + (f0 - f1) + fp
        if s0 <= 0:
            raise ValueError("spot denominator no positivo")
        r = pnl / s0
        day = datetime.fromtimestamp(cur.ts_ms / 1000, tz=timezone.utc).date()
        daily[day] += r
        funding_pnl += fp

    basis_pnl = (s_end - s_start) + (f_start - f_end)
    gross_pnl = basis_pnl + funding_pnl
    funding_ret = funding_pnl / s_start
    basis_ret = basis_pnl / s_start
    gross_ret = gross_pnl / s_start
    net_ret = gross_ret - DRAG_ANUAL_NOTIONAL_04C2
    committed_ret = net_ret / CAPITAL_REFERENCIA_MULTIPLO_04C2

    max_mark = max(s.mark[e.ts_ms].high for e in events)
    excursion = max(Decimal("0"), (max_mark - f_start) / s_start)
    return (
        ResultadoAnualActivo04C2(
            symbol=s.symbol,
            year=year,
            intervals=len(events) - 1,
            start_spot=s_start,
            start_perp=f_start,
            funding_return_notional=funding_ret,
            basis_return_notional=basis_ret,
            gross_return_notional=gross_ret,
            net_return_notional=net_ret,
            net_return_committed=committed_ret,
            max_mark_excursion=excursion,
        ),
        dict(daily),
    )


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def _sharpe_daily(values: Sequence[Decimal]) -> Decimal:
    if len(values) < 2:
        return Decimal("0")
    xs = [float(v) for v in values]
    sd = statistics.stdev(xs)
    if sd == 0:
        return Decimal("999") if statistics.mean(xs) > 0 else Decimal("0")
    return Decimal(str(statistics.mean(xs) / sd * math.sqrt(365)))


def _max_drawdown(values: Sequence[Decimal]) -> Decimal:
    wealth = Decimal("1")
    peak = Decimal("1")
    max_dd = Decimal("0")
    for r in values:
        wealth *= Decimal("1") + r
        if wealth > peak:
            peak = wealth
        if peak > 0:
            dd = (peak - wealth) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def evaluar_carry_04c2(series: Mapping[str, SerieSimbolo04C2]) -> ResultadoCarry04C2:
    audits = tuple(auditar_serie_04c2(series[symbol]) for symbol in SIMBOLOS_04C2)
    data_reasons = tuple(reason for audit in audits for reason in audit.reasons)
    if any(not a.apt for a in audits):
        return ResultadoCarry04C2(
            data_apt=False,
            data_reasons=data_reasons,
            audits=audits,
            annual_assets=(),
            annual_portfolio=(),
            mean_annual_net_notional=Decimal("0"),
            mean_annual_net_committed=Decimal("0"),
            worst_year_net_committed=Decimal("0"),
            daily_sharpe_net=Decimal("0"),
            max_drawdown_net=Decimal("0"),
            worst_day_net=Decimal("0"),
            positive_day_fraction=Decimal("0"),
            total_funding_return_notional=Decimal("0"),
            economic_verdict="DATOS_INSUFICIENTES_04C2",
            production_verdict="NO_EVALUABLE_PRODUCCION_04C2",
            reject_economic=data_reasons,
            reject_production=("DATOS_INSUFICIENTES_04C2",),
        )

    annual = []
    daily_by_symbol_year: Dict[Tuple[str, int], Dict[date, Decimal]] = {}
    for symbol in SIMBOLOS_04C2:
        for year in ANIOS_04C2:
            row, daily = _annual_asset(series[symbol], year)
            annual.append(row)
            daily_by_symbol_year[(symbol, year)] = daily

    portfolio = []
    all_daily_net = []
    for year in ANIOS_04C2:
        rows = [r for r in annual if r.year == year]
        if len(rows) != len(SIMBOLOS_04C2):
            raise ValueError(f"portfolio anual incompleto {year}")
        net = _mean([r.net_return_notional for r in rows])
        committed = net / CAPITAL_REFERENCIA_MULTIPLO_04C2
        funding = _mean([r.funding_return_notional for r in rows])
        portfolio.append(ResultadoAnualPortafolio04C2(year, net, committed, funding))

        daily_maps = [daily_by_symbol_year[(s, year)] for s in SIMBOLOS_04C2]
        common_days = sorted(set(daily_maps[0]).intersection(daily_maps[1]))
        days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
        daily_cost = DRAG_ANUAL_NOTIONAL_04C2 / Decimal(days_in_year)
        for day in common_days:
            gross = _mean([m[day] for m in daily_maps])
            all_daily_net.append(gross - daily_cost)

    mean_net = _mean([r.net_return_notional for r in portfolio])
    mean_committed = _mean([r.net_return_committed for r in portfolio])
    worst_committed = min((r.net_return_committed for r in portfolio), default=Decimal("0"))
    sharpe = _sharpe_daily(all_daily_net)
    max_dd = _max_drawdown(all_daily_net)
    worst_day = min(all_daily_net, default=Decimal("0"))
    positive_fraction = (
        Decimal(sum(v > 0 for v in all_daily_net)) / Decimal(len(all_daily_net))
        if all_daily_net else Decimal("0")
    )
    funding_total = sum((r.funding_return_notional for r in portfolio), Decimal("0"))

    reject_econ = []
    if any(r.net_return_notional <= 0 for r in portfolio):
        reject_econ.append("NO_4_DE_4_ANIOS_POSITIVOS")
    if mean_net <= 0:
        reject_econ.append("MEDIA_ANUAL_NETA_NO_POSITIVA")
    if sharpe < SHARPE_ECONOMICO_MIN_04C2:
        reject_econ.append("SHARPE_ECONOMICO_INSUFICIENTE")
    if max_dd > MAX_DRAWDOWN_ECONOMICO_04C2:
        reject_econ.append("DRAWDOWN_ECONOMICO_EXCESIVO")
    if funding_total <= 0:
        reject_econ.append("FUNDING_AGREGADO_NO_POSITIVO")
    econ_ok = not reject_econ

    reject_prod = []
    if not econ_ok:
        reject_prod.append("GATE_ECONOMICO_NO_SUPERADO")
    if mean_committed < MEDIA_ANUAL_COMMITTED_PROD_MIN_04C2:
        reject_prod.append("MEDIA_COMMITTED_MENOR_5PCT")
    if worst_committed < PEOR_ANIO_COMMITTED_PROD_MIN_04C2:
        reject_prod.append("PEOR_ANIO_COMMITTED_MENOR_2PCT")
    if sharpe < SHARPE_PROD_MIN_04C2:
        reject_prod.append("SHARPE_PRODUCCION_MENOR_2")
    if max_dd > MAX_DRAWDOWN_PROD_04C2:
        reject_prod.append("DRAWDOWN_PRODUCCION_MAYOR_7_5PCT")
    prod_ok = not reject_prod

    return ResultadoCarry04C2(
        data_apt=True,
        data_reasons=(),
        audits=audits,
        annual_assets=tuple(annual),
        annual_portfolio=tuple(portfolio),
        mean_annual_net_notional=mean_net,
        mean_annual_net_committed=mean_committed,
        worst_year_net_committed=worst_committed,
        daily_sharpe_net=sharpe,
        max_drawdown_net=max_dd,
        worst_day_net=worst_day,
        positive_day_fraction=positive_fraction,
        total_funding_return_notional=funding_total,
        economic_verdict="CARRY_ECONOMICAMENTE_APTO_04C2" if econ_ok else "CARRY_ECONOMICAMENTE_FALSADO_04C2",
        production_verdict="CARRY_CANDIDATO_PRODUCCION_04C2" if prod_ok else "CARRY_NO_CANDIDATO_PRODUCCION_04C2",
        reject_economic=tuple(reject_econ),
        reject_production=tuple(reject_prod),
    )
