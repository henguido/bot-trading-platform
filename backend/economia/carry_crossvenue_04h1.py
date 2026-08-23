"""BOT 2.0-04H-1: falsación económica long Binance perp / short Hyperliquid perp.

Solo investigación histórica 2024-2025. No usa credenciales de trading, no ejecuta
órdenes y no abre 2026. El PnL se calcula únicamente si el gate de datos completo
pasa dentro de la misma ejecución.
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
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, getcontext
from typing import Dict, Iterable, Mapping, Sequence

import requests

from backend.economia.auditoria_crossvenue_funding_04h0 import fetch_hl_funding_04h0
from backend.economia.fuente_0xarchive_04h1 import PricePoint04H1, fetch_price_history_04h1
from backend.economia.protocolo_crossvenue_carry_04h1 import (
    ACTIVOS_04H1,
    ANIOS_04H1,
    BARRAS_8H_ESPERADAS_04H1,
    BASE_UNITS_04H1,
    BINANCE_DATA_URL_04H1,
    BINANCE_INTERVALO_PRECIO_04H1,
    BINANCE_SYMBOLS_04H1,
    CALCULAR_PNL_SI_GATE_COMPLETO_PASA_04H1,
    CALCULAR_PNL_SIN_GATE_PERMITIDO_04H1,
    COBERTURA_ALINEADA_8H_MIN_04H1,
    COBERTURA_FUNDING_HL_MIN_04H1,
    COBERTURA_PRECIOS_MIN_04H1,
    COSTE_PRIMARIO_BPS_ANUAL_04H1,
    COSTE_STRESS_BPS_ANUAL_04H1,
    DESDE_04H1,
    HAC_LAG_DIAS_04H1,
    HASTA_EXCLUSIVO_04H1,
    HORAS_ESPERADAS_04H1,
    MAX_DRAWDOWN_ECONOMICO_04H1,
    MAX_DRAWDOWN_PRODUCCION_04H1,
    MIN_ACTIVOS_POSITIVOS_POR_ANIO_04H1,
    PEOR_ANIO_CAPITAL_MIN_04H1,
    RETORNO_MEDIO_ANUAL_CAPITAL_MIN_04H1,
    SHARPE_ECONOMICO_MIN_04H1,
    SHARPE_PRODUCCION_MIN_04H1,
    TSTAT_HAC_ABS_MIN_04H1,
)

getcontext().prec = 34
_HORA_MS = 3_600_000
_TIMEOUT = 40
_RETRIES = 4
_MAX_WORKERS = 10


@dataclass(frozen=True)
class FundingEvent04H1:
    ts_ms: int
    rate: Decimal


@dataclass(frozen=True)
class BinanceSerie04H1:
    asset: str
    perp: Mapping[int, Decimal]
    mark: Mapping[int, Decimal]
    funding: tuple[FundingEvent04H1, ...]
    months_perp: int
    months_mark: int
    months_funding: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class DataAudit04H1:
    asset: str
    ox_price_records: int
    ox_price_coverage: Decimal
    hl_funding_records: int
    hl_funding_coverage: Decimal
    binance_perp_months: int
    binance_mark_months: int
    binance_funding_months: int
    aligned_8h_bars: int
    aligned_8h_coverage: Decimal
    apt: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AnnualAsset04H1:
    asset: str
    year: int
    intervals: int
    reference_notional: Decimal
    funding_hl_return: Decimal
    funding_binance_return: Decimal
    funding_total_return: Decimal
    basis_return: Decimal
    gross_return: Decimal
    net_primary_return: Decimal
    net_stress_return: Decimal


@dataclass(frozen=True)
class AnnualPortfolio04H1:
    year: int
    funding_total_return: Decimal
    basis_return: Decimal
    gross_return: Decimal
    net_primary_return: Decimal
    net_stress_return: Decimal
    positive_assets: int


@dataclass(frozen=True)
class Result04H1:
    data_apt: bool
    data_reasons: tuple[str, ...]
    audits: tuple[DataAudit04H1, ...]
    annual_assets: tuple[AnnualAsset04H1, ...]
    annual_portfolio: tuple[AnnualPortfolio04H1, ...]
    mean_annual_primary: Decimal
    mean_annual_stress: Decimal
    worst_year_primary: Decimal
    total_funding_return: Decimal
    daily_sharpe_primary: Decimal
    max_drawdown_primary: Decimal
    worst_day_primary: Decimal
    positive_day_fraction: Decimal
    hac_tstat_primary: Decimal
    economic_verdict: str
    production_verdict: str
    reject_economic: tuple[str, ...]
    reject_production: tuple[str, ...]

    def to_dict(self) -> dict:
        def convert(x):
            if isinstance(x, Decimal):
                return float(x)
            if isinstance(x, tuple):
                return [convert(v) for v in x]
            if isinstance(x, dict):
                return {k: convert(v) for k, v in x.items()}
            if hasattr(x, "__dataclass_fields__"):
                return {k: convert(v) for k, v in asdict(x).items()}
            return x
        return convert(self)


def _d(value: object, name: str) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name}_INVALID") from exc
    if not out.is_finite():
        raise ValueError(f"{name}_NONFINITE")
    return out


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def _months() -> Iterable[tuple[int, int]]:
    for year in ANIOS_04H1:
        for month in range(1, 13):
            yield year, month


def _download(url: str) -> bytes:
    last: Exception | None = None
    for attempt in range(_RETRIES + 1):
        try:
            response = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "bot-trading-research-04h1/1.0"})
            response.raise_for_status()
            if not response.content:
                raise ValueError("EMPTY_RESPONSE")
            return response.content
        except Exception as exc:
            last = exc
            if attempt < _RETRIES:
                time.sleep(0.5 * (attempt + 1))
    assert last is not None
    raise last


def _csv_from_zip(payload: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
        if len(names) != 1:
            raise ValueError("ZIP_CSV_COUNT")
        text = zf.read(names[0]).decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def parse_binance_8h_04h1(payload: bytes) -> Dict[int, Decimal]:
    out: Dict[int, Decimal] = {}
    for row in _csv_from_zip(payload):
        if not row:
            continue
        try:
            raw_ts = int(row[0])
        except (ValueError, TypeError):
            continue
        if len(row) != 12:
            raise ValueError("BINANCE_KLINE_SCHEMA")
        ts = raw_ts // 1000 if raw_ts >= 100_000_000_000_000 else raw_ts
        px = _d(row[1], "BINANCE_OPEN")
        if px <= 0:
            raise ValueError("BINANCE_PRICE_NONPOSITIVE")
        if ts in out:
            raise ValueError("BINANCE_KLINE_DUPLICATE")
        out[ts] = px
    if not out:
        raise ValueError("BINANCE_KLINE_EMPTY")
    return out


def parse_binance_funding_04h1(payload: bytes) -> tuple[FundingEvent04H1, ...]:
    out: list[FundingEvent04H1] = []
    seen: set[int] = set()
    for row in _csv_from_zip(payload):
        if not row:
            continue
        try:
            raw_ts = int(row[0])
        except (ValueError, TypeError):
            continue
        if len(row) < 3:
            raise ValueError("BINANCE_FUNDING_SCHEMA")
        offset = raw_ts % _HORA_MS
        if offset > 1000:
            raise ValueError("BINANCE_FUNDING_OFFSET_GT_1S")
        ts = raw_ts - offset
        rate = _d(row[2], "BINANCE_FUNDING_RATE")
        if ts in seen:
            raise ValueError("BINANCE_FUNDING_DUPLICATE")
        seen.add(ts)
        out.append(FundingEvent04H1(ts, rate))
    out.sort(key=lambda e: e.ts_ms)
    return tuple(out)


def _binance_url(kind: str, symbol: str, year: int, month: int) -> str:
    ym = f"{year:04d}-{month:02d}"
    interval = BINANCE_INTERVALO_PRECIO_04H1
    if kind == "perp":
        return f"{BINANCE_DATA_URL_04H1}/futures/um/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{ym}.zip"
    if kind == "mark":
        return f"{BINANCE_DATA_URL_04H1}/futures/um/monthly/markPriceKlines/{symbol}/{interval}/{symbol}-{interval}-{ym}.zip"
    if kind == "funding":
        return f"{BINANCE_DATA_URL_04H1}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{ym}.zip"
    raise ValueError("BINANCE_KIND_UNKNOWN")


def load_binance_04h1(asset: str) -> BinanceSerie04H1:
    symbol = BINANCE_SYMBOLS_04H1[asset]
    tasks = [(kind, y, m, _binance_url(kind, symbol, y, m)) for y, m in _months() for kind in ("perp", "mark", "funding")]
    payloads: dict[tuple[str, int, int], bytes] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_download, url): (kind, y, m, url) for kind, y, m, url in tasks}
        for future in as_completed(futures):
            kind, y, m, url = futures[future]
            try:
                payloads[(kind, y, m)] = future.result()
            except Exception as exc:
                errors.append(f"DOWNLOAD:{kind}:{y:04d}-{m:02d}:{type(exc).__name__}:{url}")

    perp: Dict[int, Decimal] = {}
    mark: Dict[int, Decimal] = {}
    funding: list[FundingEvent04H1] = []
    months = Counter()
    for (kind, y, m), payload in sorted(payloads.items()):
        try:
            if kind == "funding":
                rows = parse_binance_funding_04h1(payload)
                funding.extend(rows)
            else:
                rows = parse_binance_8h_04h1(payload)
                target = perp if kind == "perp" else mark
                if set(target).intersection(rows):
                    raise ValueError("BINANCE_MONTH_OVERLAP")
                target.update(rows)
            months[kind] += 1
        except Exception as exc:
            errors.append(f"PARSE:{kind}:{y:04d}-{m:02d}:{type(exc).__name__}:{exc}")
    funding.sort(key=lambda e: e.ts_ms)
    return BinanceSerie04H1(asset, perp, mark, tuple(funding), months["perp"], months["mark"], months["funding"], tuple(sorted(errors)))


def parse_hl_funding_04h1(rows: Sequence[Mapping[str, object]]) -> tuple[FundingEvent04H1, ...]:
    out: list[FundingEvent04H1] = []
    seen: set[int] = set()
    lo, hi = _ms(DESDE_04H1), _ms(HASTA_EXCLUSIVO_04H1)
    for row in rows:
        ts = int(row["time"])
        if not (lo <= ts < hi):
            continue
        rate = _d(row["fundingRate"], "HL_FUNDING_RATE")
        if ts in seen:
            raise ValueError("HL_FUNDING_DUPLICATE")
        seen.add(ts)
        out.append(FundingEvent04H1(ts, rate))
    out.sort(key=lambda e: e.ts_ms)
    return tuple(out)


def _price_maps(points: Sequence[PricePoint04H1]) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
    mark = {p.timestamp_ms: _d(p.mark_price, "HL_MARK") for p in points}
    oracle = {p.timestamp_ms: _d(p.oracle_price, "HL_ORACLE") for p in points}
    return mark, oracle


def _audit_asset(asset: str, points: Sequence[PricePoint04H1], hl_funding: Sequence[FundingEvent04H1], bn: BinanceSerie04H1) -> DataAudit04H1:
    reasons = list(bn.errors)
    price_cov = Decimal(len(points)) / Decimal(HORAS_ESPERADAS_04H1)
    funding_cov = Decimal(len(hl_funding)) / Decimal(HORAS_ESPERADAS_04H1)
    mark, _ = _price_maps(points)
    aligned = sorted(set(bn.perp).intersection(bn.mark).intersection(mark))
    aligned = [ts for ts in aligned if _ms(DESDE_04H1) <= ts < _ms(HASTA_EXCLUSIVO_04H1)]
    aligned_cov = Decimal(len(aligned)) / Decimal(BARRAS_8H_ESPERADAS_04H1)
    if price_cov < COBERTURA_PRECIOS_MIN_04H1:
        reasons.append("OX_PRICE_COVERAGE")
    if funding_cov < COBERTURA_FUNDING_HL_MIN_04H1:
        reasons.append("HL_FUNDING_COVERAGE")
    if bn.months_perp != 24:
        reasons.append(f"BINANCE_PERP_MONTHS_{bn.months_perp}_OF_24")
    if bn.months_mark != 24:
        reasons.append(f"BINANCE_MARK_MONTHS_{bn.months_mark}_OF_24")
    if bn.months_funding != 24:
        reasons.append(f"BINANCE_FUNDING_MONTHS_{bn.months_funding}_OF_24")
    if aligned_cov < COBERTURA_ALINEADA_8H_MIN_04H1:
        reasons.append("ALIGNED_8H_COVERAGE")
    return DataAudit04H1(asset, len(points), price_cov, len(hl_funding), funding_cov, bn.months_perp, bn.months_mark, bn.months_funding, len(aligned), aligned_cov, not reasons, tuple(reasons))


def _year(ts_ms: int) -> int:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).year


def _day(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()


def _annual_asset(asset: str, year: int, points: Sequence[PricePoint04H1], hl_funding: Sequence[FundingEvent04H1], bn: BinanceSerie04H1) -> tuple[AnnualAsset04H1, dict[str, Decimal]]:
    hl_mark, hl_oracle = _price_maps(points)
    aligned = sorted(ts for ts in set(bn.perp).intersection(bn.mark).intersection(hl_mark) if _year(ts) == year)
    if len(aligned) < 2:
        raise ValueError(f"NO_ALIGNED_INTERVALS:{asset}:{year}")
    start = aligned[0]
    ref = (bn.perp[start] + hl_mark[start]) / Decimal("2") * BASE_UNITS_04H1
    if ref <= 0:
        raise ValueError("REFERENCE_NOTIONAL_INVALID")

    hl_by_interval: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for event in hl_funding:
        if _year(event.ts_ms) != year:
            continue
        oracle = hl_oracle.get(event.ts_ms)
        if oracle is None:
            continue
        # El short HL recibe cuando funding es positivo.
        hl_by_interval[event.ts_ms] += event.rate * oracle * BASE_UNITS_04H1

    bn_by_ts: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for event in bn.funding:
        if _year(event.ts_ms) != year:
            continue
        mark_px = bn.mark.get(event.ts_ms)
        if mark_px is None:
            continue
        # El long Binance paga cuando funding es positivo.
        bn_by_ts[event.ts_ms] += -event.rate * mark_px * BASE_UNITS_04H1

    daily: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    funding_hl = funding_bn = basis = Decimal("0")
    intervals = 0
    hl_events = sorted((e.ts_ms, hl_by_interval[e.ts_ms]) for e in hl_funding if _year(e.ts_ms) == year and e.ts_ms in hl_oracle)
    hl_idx = 0
    for t0, t1 in zip(aligned, aligned[1:]):
        if t1 - t0 != 8 * _HORA_MS:
            continue
        price_pnl = (bn.perp[t1] - bn.perp[t0]) * BASE_UNITS_04H1 + (hl_mark[t0] - hl_mark[t1]) * BASE_UNITS_04H1
        hlf = Decimal("0")
        while hl_idx < len(hl_events) and hl_events[hl_idx][0] <= t0:
            hl_idx += 1
        scan = hl_idx
        while scan < len(hl_events) and hl_events[scan][0] <= t1:
            hlf += hl_events[scan][1]
            scan += 1
        hl_idx = scan
        bnf = bn_by_ts.get(t1, Decimal("0"))
        pnl = price_pnl + hlf + bnf
        basis += price_pnl
        funding_hl += hlf
        funding_bn += bnf
        daily[_day(t1)] += pnl / ref
        intervals += 1

    gross = (basis + funding_hl + funding_bn) / ref
    primary_cost = COSTE_PRIMARIO_BPS_ANUAL_04H1 / Decimal("10000")
    stress_cost = COSTE_STRESS_BPS_ANUAL_04H1 / Decimal("10000")
    annual = AnnualAsset04H1(
        asset=asset,
        year=year,
        intervals=intervals,
        reference_notional=ref,
        funding_hl_return=funding_hl / ref,
        funding_binance_return=funding_bn / ref,
        funding_total_return=(funding_hl + funding_bn) / ref,
        basis_return=basis / ref,
        gross_return=gross,
        net_primary_return=gross - primary_cost,
        net_stress_return=gross - stress_cost,
    )
    days = 366 if year == 2024 else 365
    daily_cost = primary_cost / Decimal(days)
    daily_net = {d: r - daily_cost for d, r in daily.items()}
    return annual, daily_net


def _sharpe(values: Sequence[Decimal]) -> Decimal:
    if len(values) < 2:
        return Decimal("0")
    xs = [float(x) for x in values]
    sd = statistics.stdev(xs)
    if sd == 0:
        return Decimal("0")
    return Decimal(str(statistics.mean(xs) / sd * math.sqrt(365)))


def _max_drawdown(values: Sequence[Decimal]) -> Decimal:
    wealth = Decimal("1")
    peak = Decimal("1")
    max_dd = Decimal("0")
    for r in values:
        wealth *= Decimal("1") + r
        peak = max(peak, wealth)
        if peak > 0:
            max_dd = max(max_dd, (peak - wealth) / peak)
    return max_dd


def hac_tstat_mean_04h1(values: Sequence[Decimal], lag: int = HAC_LAG_DIAS_04H1) -> Decimal:
    n = len(values)
    if n < 3:
        return Decimal("0")
    xs = [float(v) for v in values]
    mean = statistics.mean(xs)
    centered = [x - mean for x in xs]
    gamma0 = sum(x * x for x in centered) / n
    lrv = gamma0
    max_lag = min(lag, n - 1)
    for k in range(1, max_lag + 1):
        gamma = sum(centered[t] * centered[t - k] for t in range(k, n)) / n
        weight = 1.0 - k / (max_lag + 1.0)
        lrv += 2.0 * weight * gamma
    if lrv <= 0:
        return Decimal("0")
    se_mean = math.sqrt(lrv / n)
    if se_mean == 0:
        return Decimal("0")
    return Decimal(str(mean / se_mean))


def evaluate_from_series_04h1(
    datasets: Mapping[str, tuple[Sequence[PricePoint04H1], Sequence[FundingEvent04H1], BinanceSerie04H1]],
) -> Result04H1:
    audits = tuple(_audit_asset(asset, *datasets[asset]) for asset in ACTIVOS_04H1)
    data_reasons = tuple(f"{a.asset}:{r}" for a in audits for r in a.reasons)
    if data_reasons:
        if CALCULAR_PNL_SIN_GATE_PERMITIDO_04H1:
            raise AssertionError("PNL_WITH_FAILED_GATE_FORBIDDEN")
        return Result04H1(False, data_reasons, audits, (), (), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "DATOS_ECONOMICOS_INSUFICIENTES_04H1", "NO_EVALUADO_04H1", (), ())
    if not CALCULAR_PNL_SI_GATE_COMPLETO_PASA_04H1:
        raise AssertionError("PNL_NOT_AUTHORIZED_AFTER_GATE")

    annual_assets: list[AnnualAsset04H1] = []
    asset_daily: dict[tuple[str, int], dict[str, Decimal]] = {}
    for asset in ACTIVOS_04H1:
        points, hlf, bn = datasets[asset]
        for year in ANIOS_04H1:
            annual, daily = _annual_asset(asset, year, points, hlf, bn)
            annual_assets.append(annual)
            asset_daily[(asset, year)] = daily

    annual_portfolio: list[AnnualPortfolio04H1] = []
    portfolio_daily: list[Decimal] = []
    for year in ANIOS_04H1:
        rows = [r for r in annual_assets if r.year == year]
        annual_portfolio.append(AnnualPortfolio04H1(
            year=year,
            funding_total_return=sum((r.funding_total_return for r in rows), Decimal("0")) / Decimal(len(rows)),
            basis_return=sum((r.basis_return for r in rows), Decimal("0")) / Decimal(len(rows)),
            gross_return=sum((r.gross_return for r in rows), Decimal("0")) / Decimal(len(rows)),
            net_primary_return=sum((r.net_primary_return for r in rows), Decimal("0")) / Decimal(len(rows)),
            net_stress_return=sum((r.net_stress_return for r in rows), Decimal("0")) / Decimal(len(rows)),
            positive_assets=sum(1 for r in rows if r.net_primary_return > 0),
        ))
        all_days = sorted(set().union(*(asset_daily[(a, year)].keys() for a in ACTIVOS_04H1)))
        for day in all_days:
            vals = [asset_daily[(a, year)].get(day, Decimal("0")) for a in ACTIVOS_04H1]
            portfolio_daily.append(sum(vals, Decimal("0")) / Decimal(len(vals)))

    mean_primary = sum((r.net_primary_return for r in annual_portfolio), Decimal("0")) / Decimal(len(annual_portfolio))
    mean_stress = sum((r.net_stress_return for r in annual_portfolio), Decimal("0")) / Decimal(len(annual_portfolio))
    worst = min(r.net_primary_return for r in annual_portfolio)
    total_funding = sum((r.funding_total_return for r in annual_portfolio), Decimal("0"))
    sharpe = _sharpe(portfolio_daily)
    max_dd = _max_drawdown(portfolio_daily)
    worst_day = min(portfolio_daily) if portfolio_daily else Decimal("0")
    positive_fraction = Decimal(sum(1 for r in portfolio_daily if r > 0)) / Decimal(len(portfolio_daily)) if portfolio_daily else Decimal("0")
    hac = hac_tstat_mean_04h1(portfolio_daily)

    reject_econ: list[str] = []
    if any(r.net_primary_return <= 0 for r in annual_portfolio): reject_econ.append("YEAR_NOT_POSITIVE")
    if mean_primary <= 0: reject_econ.append("MEAN_NOT_POSITIVE")
    if total_funding <= 0: reject_econ.append("FUNDING_NOT_POSITIVE")
    if sharpe < SHARPE_ECONOMICO_MIN_04H1: reject_econ.append("SHARPE_BELOW_1")
    if max_dd > MAX_DRAWDOWN_ECONOMICO_04H1: reject_econ.append("DRAWDOWN_ABOVE_10PCT")
    if mean_stress <= 0: reject_econ.append("STRESS_NOT_POSITIVE")
    if abs(hac) < TSTAT_HAC_ABS_MIN_04H1: reject_econ.append("HAC_NOT_SIGNIFICANT")
    econ = "CROSSVENUE_ECONOMICAMENTE_APTO_04H1" if not reject_econ else "CROSSVENUE_ECONOMICAMENTE_FALSADO_04H1"

    reject_prod: list[str] = []
    if reject_econ: reject_prod.append("ECONOMIC_GATE_FAILED")
    if mean_primary < RETORNO_MEDIO_ANUAL_CAPITAL_MIN_04H1: reject_prod.append("MEAN_CAPITAL_BELOW_5PCT")
    if worst < PEOR_ANIO_CAPITAL_MIN_04H1: reject_prod.append("WORST_YEAR_BELOW_2PCT")
    if sharpe < SHARPE_PRODUCCION_MIN_04H1: reject_prod.append("SHARPE_BELOW_2")
    if max_dd > MAX_DRAWDOWN_PRODUCCION_04H1: reject_prod.append("DRAWDOWN_ABOVE_7_5PCT")
    if any(r.positive_assets < MIN_ACTIVOS_POSITIVOS_POR_ANIO_04H1 for r in annual_portfolio): reject_prod.append("DEPENDS_ON_SINGLE_ASSET")
    if mean_stress <= 0: reject_prod.append("STRESS_NOT_POSITIVE")
    prod = "CROSSVENUE_CANDIDATO_INGENIERIA_04H1" if not reject_prod else "CROSSVENUE_NO_CANDIDATO_PRODUCCION_04H1"

    return Result04H1(True, (), audits, tuple(annual_assets), tuple(annual_portfolio), mean_primary, mean_stress, worst, total_funding, sharpe, max_dd, worst_day, positive_fraction, hac, econ, prod, tuple(reject_econ), tuple(reject_prod))


def run_remote_04h1(api_key: str) -> Result04H1:
    lo, hi = _ms(DESDE_04H1), _ms(HASTA_EXCLUSIVO_04H1)
    datasets = {}
    for asset in ACTIVOS_04H1:
        points = fetch_price_history_04h1(asset, lo, hi, api_key)
        hl_funding = parse_hl_funding_04h1(fetch_hl_funding_04h0(asset))
        bn = load_binance_04h1(asset)
        datasets[asset] = (points, hl_funding, bn)
    return evaluate_from_series_04h1(datasets)
