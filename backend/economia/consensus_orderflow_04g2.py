"""Ejecución reproducible BOT 2.0-04G-2.

Descarga únicamente datos públicos Spot monthly klines 1d de Binance Vision,
construye consensus order flow causal y ejecuta el protocolo SGB OOS congelado.
No usa credenciales ni toca componentes operativos del BOT.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import mean, stdev
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import requests

from backend.economia.protocolo_consensus_orderflow_04g2 import *

_MONTH_RE = re.compile(r"-(?P<year>\d{4})-(?P<month>\d{2})\.zip$")
MAX_WORKERS_LIST_04G2 = 20
MAX_WORKERS_DOWNLOAD_04G2 = 24
TIMEOUT_04G2 = 45
RETRIES_04G2 = 1


@dataclass(frozen=True)
class Obj:
    base: str
    quote: str
    symbol: str
    month: date
    key: str
    size: int


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    quote_volume: float
    taker_buy_quote: float

    @property
    def taker_sell_quote(self) -> float:
        return self.quote_volume - self.taker_buy_quote


@dataclass(frozen=True)
class Content:
    base: str
    quote: str
    month: date
    bars: Tuple[Bar, ...]
    compressed_bytes: int
    errors: Tuple[str, ...]


@dataclass(frozen=True)
class Row:
    base: str
    decision_day: date
    consensus_of: float
    usdt_of: float
    lag_return: float
    target_return: float
    n_quotes: int

    @property
    def x(self) -> Tuple[float, float, float]:
        return (self.consensus_of, self.usdt_of, self.lag_return)


def _tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(root: ET.Element, name: str) -> Optional[str]:
    for e in root.iter():
        if _tag(e.tag) == name and e.text is not None:
            return e.text
    return None


def _get(url: str, *, params: Optional[Mapping[str, str]] = None) -> requests.Response:
    last: Optional[Exception] = None
    for attempt in range(RETRIES_04G2 + 1):
        try:
            r = requests.get(
                url,
                params=params,
                headers={"User-Agent": "bot-trading-research-04g2/1.0"},
                timeout=TIMEOUT_04G2,
            )
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last = exc
            if attempt < RETRIES_04G2:
                time.sleep(0.35 * (attempt + 1))
    assert last is not None
    raise last


def _list_pair(base: str, quote: str) -> Tuple[str, str, bool, Tuple[Obj, ...], Optional[str]]:
    symbol = f"{base}{quote}"
    prefix = f"{ROOT_PREFIX_04G2}/{symbol}/{INTERVALO_04G2}/"
    token: Optional[str] = None
    out: List[Obj] = []
    try:
        while True:
            params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
            if token:
                params["continuation-token"] = token
            root = ET.fromstring(_get(S3_LIST_URL_04G2, params=params).content)
            for node in root.iter():
                if _tag(node.tag) != "Contents":
                    continue
                key = None
                size = None
                for child in node:
                    if _tag(child.tag) == "Key":
                        key = child.text
                    elif _tag(child.tag) == "Size":
                        size = child.text
                if not key or size is None or not key.endswith(".zip"):
                    continue
                m = _MONTH_RE.search(key)
                if not m:
                    continue
                month = date(int(m.group("year")), int(m.group("month")), 1)
                if ARCHIVO_DESDE_04G2 <= month <= ARCHIVO_HASTA_04G2 and int(size) > 0:
                    out.append(Obj(base, quote, symbol, month, key, int(size)))
            if (_first(root, "IsTruncated") or "false").lower() != "true":
                return base, quote, True, tuple(sorted(out, key=lambda x: x.month)), None
            nxt = _first(root, "NextContinuationToken")
            if not nxt or nxt == token:
                return base, quote, False, tuple(sorted(out, key=lambda x: x.month)), "LIST_TRUNCATED"
            token = nxt
    except Exception as exc:
        return base, quote, False, (), f"{type(exc).__name__}:{exc}"


def _timestamp_day(raw: str) -> Tuple[date, bool]:
    v = int(raw)
    divisor = 1_000_000 if v >= 100_000_000_000_000 else 1_000
    dt = datetime.fromtimestamp(v / divisor, tz=timezone.utc)
    return dt.date(), (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0)


def parse_zip(payload: bytes, obj: Obj) -> Content:
    bars: List[Bar] = []
    errors: List[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
            if len(names) != 1:
                return Content(obj.base, obj.quote, obj.month, (), len(payload), ("ZIP_CSV_COUNT",))
            with z.open(names[0]) as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
                for n, row in enumerate(reader, 1):
                    if not row:
                        continue
                    if n == 1:
                        try:
                            int(row[0])
                        except ValueError:
                            continue
                    if len(row) != 12:
                        errors.append("COLUMN_COUNT")
                        continue
                    try:
                        d, aligned = _timestamp_day(row[0])
                        op = float(row[1])
                        qv = float(row[7])
                        tbq = float(row[10])
                    except (ValueError, InvalidOperation, OverflowError):
                        errors.append("PARSE")
                        continue
                    if not aligned:
                        errors.append("TIME_NOT_UTC_DAY")
                    if (d.year, d.month) != (obj.month.year, obj.month.month):
                        errors.append("DAY_OUTSIDE_MONTH")
                    if not all(math.isfinite(x) for x in (op, qv, tbq)) or op <= 0 or qv < 0 or tbq < 0 or tbq > qv:
                        errors.append("DOMAIN")
                    bars.append(Bar(d, op, qv, tbq))
    except (zipfile.BadZipFile, OSError, UnicodeError) as exc:
        return Content(obj.base, obj.quote, obj.month, (), len(payload), (f"ZIP:{type(exc).__name__}",))
    days = [b.day for b in bars]
    if days != sorted(days):
        errors.append("UNSORTED")
    if len(days) != len(set(days)):
        errors.append("DUPLICATE_DAY")
    return Content(obj.base, obj.quote, obj.month, tuple(bars), len(payload), tuple(sorted(set(errors))))


def _download(obj: Obj) -> Content:
    try:
        return parse_zip(_get(f"{DATA_BASE_URL_04G2}/{obj.key}").content, obj)
    except Exception as exc:
        return Content(obj.base, obj.quote, obj.month, (), 0, (f"DOWNLOAD:{type(exc).__name__}",))


def _raw_of(bar: Bar) -> Optional[float]:
    buy = bar.taker_buy_quote
    sell = bar.taker_sell_quote
    if buy <= 0 or sell <= 0 or not math.isfinite(buy) or not math.isfinite(sell):
        return None
    value = math.log(buy) - math.log(sell)
    return value if math.isfinite(value) else None


def _std_series(series: Mapping[date, Bar]) -> Dict[date, float]:
    raw = {d: _raw_of(b) for d, b in series.items()}
    out: Dict[date, float] = {}
    for d in sorted(raw):
        vals = [raw.get(d - timedelta(days=i)) for i in range(VENTANA_STD_DIAS_04G2 - 1, -1, -1)]
        if any(v is None for v in vals):
            continue
        nums = [float(v) for v in vals if v is not None]
        if len(nums) != VENTANA_STD_DIAS_04G2:
            continue
        sigma = stdev(nums)
        if sigma <= 0 or not math.isfinite(sigma):
            continue
        value = nums[-1] / sigma
        if math.isfinite(value):
            out[d] = value
    return out


def build_rows(contents: Sequence[Content]) -> Tuple[Tuple[Row, ...], Dict[str, object]]:
    daily: Dict[Tuple[str, str], Dict[date, Bar]] = defaultdict(dict)
    error_files = 0
    duplicate_cross = 0
    for c in contents:
        if c.errors:
            error_files += 1
            continue
        target = daily[(c.base, c.quote)]
        for bar in c.bars:
            if bar.day in target:
                duplicate_cross += 1
            else:
                target[bar.day] = bar

    standardized = {key: _std_series(series) for key, series in daily.items()}
    rows: List[Row] = []
    quote_counts: List[int] = []
    for base in BASES_04G2:
        usdt_bars = daily.get((base, "USDT"), {})
        usdt_std = standardized.get((base, "USDT"), {})
        d = date(2021, 12, 1)
        last_feature = date(2025, 12, 29)
        while d <= last_feature:
            decision = d + timedelta(days=1)
            exit_day = d + timedelta(days=2)
            if not (DESARROLLO_DESDE_04G2 <= decision <= TEST_HASTA_04G2):
                d += timedelta(days=1)
                continue
            vals = [
                standardized[(base, q)][d]
                for q in QUOTES_04G2
                if d in standardized.get((base, q), {})
            ]
            if len(vals) < MIN_QUOTES_CONSENSUS_04G2 or d not in usdt_std:
                d += timedelta(days=1)
                continue
            b0 = usdt_bars.get(d)
            b1 = usdt_bars.get(decision)
            b2 = usdt_bars.get(exit_day)
            if not b0 or not b1 or not b2:
                d += timedelta(days=1)
                continue
            lag = b1.open / b0.open - 1.0
            target = b2.open / b1.open - 1.0
            consensus = sum(vals) / len(vals)
            if all(math.isfinite(x) for x in (lag, target, consensus, usdt_std[d])):
                rows.append(Row(base, decision, consensus, usdt_std[d], lag, target, len(vals)))
                quote_counts.append(len(vals))
            d += timedelta(days=1)
    rows.sort(key=lambda r: (r.decision_day, r.base))
    return tuple(rows), {
        "content_error_files": error_files,
        "cross_file_duplicates": duplicate_cross,
        "row_count": len(rows),
        "quotes_per_row_min": min(quote_counts) if quote_counts else 0,
        "quotes_per_row_max": max(quote_counts) if quote_counts else 0,
        "quotes_per_row_mean": mean(quote_counts) if quote_counts else 0.0,
    }


def _grid() -> Tuple[Tuple[int, float, int], ...]:
    return tuple(
        sorted(
            (n, float(lr), depth)
            for n in GRID_N_ESTIMATORS_04G2
            for lr in GRID_LEARNING_RATE_04G2
            for depth in GRID_MAX_DEPTH_04G2
        )
    )


def _xy(rows: Sequence[Row]):
    import numpy as np
    return np.asarray([r.x for r in rows], dtype=float), np.asarray([r.target_return for r in rows], dtype=float)


def select_hyperparameters(rows: Sequence[Row]) -> Tuple[Tuple[int, float, int], List[Dict[str, float]]]:
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler

    train = [r for r in rows if r.decision_day.year == 2022]
    valid = [r for r in rows if r.decision_day.year == 2023]
    if not train or not valid:
        raise ValueError("TRAIN_OR_VALIDATION_EMPTY")
    x_train, y_train = _xy(train)
    x_valid, y_valid = _xy(valid)
    scaler = StandardScaler().fit(x_train)
    xt = scaler.transform(x_train)
    xv = scaler.transform(x_valid)
    results: List[Dict[str, float]] = []
    best_key = None
    best_cfg = None
    for n, lr, depth in _grid():
        model = GradientBoostingRegressor(
            loss=LOSS_04G2,
            n_estimators=n,
            learning_rate=lr,
            max_depth=depth,
            subsample=float(SUBSAMPLE_04G2),
            min_samples_leaf=MIN_SAMPLES_LEAF_04G2,
            random_state=RANDOM_STATE_04G2,
        )
        model.fit(xt, y_train)
        pred = model.predict(xv)
        mse = float(((pred - y_valid) ** 2).mean())
        results.append({"n_estimators": n, "learning_rate": lr, "max_depth": depth, "validation_mse": mse})
        key = (mse, n, lr, depth)
        if best_key is None or key < best_key:
            best_key = key
            best_cfg = (n, lr, depth)
    assert best_cfg is not None
    return best_cfg, results


def _month_starts(start: date, end: date) -> Iterable[date]:
    d = date(start.year, start.month, 1)
    while d <= end:
        yield d
        d = date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)


def predict_oos(rows: Sequence[Row], cfg: Tuple[int, float, int]) -> Dict[date, List[Tuple[Row, float]]]:
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler

    n, lr, depth = cfg
    out: Dict[date, List[Tuple[Row, float]]] = defaultdict(list)
    for month in _month_starts(TEST_DESDE_04G2, TEST_HASTA_04G2):
        next_month = date(month.year + (month.month == 12), 1 if month.month == 12 else month.month + 1, 1)
        train = [r for r in rows if r.decision_day < month]
        test = [r for r in rows if month <= r.decision_day < next_month and r.decision_day <= TEST_HASTA_04G2]
        if not train or not test:
            continue
        x_train, y_train = _xy(train)
        x_test, _ = _xy(test)
        scaler = StandardScaler().fit(x_train)
        model = GradientBoostingRegressor(
            loss=LOSS_04G2,
            n_estimators=n,
            learning_rate=lr,
            max_depth=depth,
            subsample=float(SUBSAMPLE_04G2),
            min_samples_leaf=MIN_SAMPLES_LEAF_04G2,
            random_state=RANDOM_STATE_04G2,
        )
        model.fit(scaler.transform(x_train), y_train)
        preds = model.predict(scaler.transform(x_test))
        for row, pred in zip(test, preds):
            out[row.decision_day].append((row, float(pred)))
    for d in out:
        out[d].sort(key=lambda rp: rp[0].base)
    return dict(sorted(out.items()))


def _weights(selected: Sequence[Row]) -> Dict[str, float]:
    if not selected:
        return {}
    w = 1.0 / len(selected)
    return {r.base: w for r in selected}


def _turnover(prev: Mapping[str, float], cur: Mapping[str, float]) -> float:
    if not prev:
        return 1.0 if cur else 0.0
    names = set(prev) | set(cur)
    return 0.5 * sum(abs(cur.get(k, 0.0) - prev.get(k, 0.0)) for k in names)


def _portfolio_series(predictions: Mapping[date, Sequence[Tuple[Row, float]]], selector: str, cost_bps: float):
    series: List[Tuple[date, float, float, float, int]] = []
    prev: Dict[str, float] = {}
    for d, items in predictions.items():
        if len(items) < MIN_ACTIVOS_POR_DIA_04G2:
            continue
        rows = [r for r, _ in items]
        if selector == "model":
            ranked = sorted(items, key=lambda rp: (-rp[1], rp[0].base))
            k = max(1, math.ceil(len(ranked) * float(FRACCION_TOP_04G2)))
            selected = [r for r, _ in ranked[:k]]
        elif selector == "consensus":
            ranked_rows = sorted(rows, key=lambda r: (-r.consensus_of, r.base))
            k = max(1, math.ceil(len(ranked_rows) * float(FRACCION_TOP_04G2)))
            selected = ranked_rows[:k]
        elif selector == "equal":
            selected = rows
        else:
            raise ValueError(selector)
        cur = _weights(selected)
        turnover = _turnover(prev, cur)
        gross = sum(r.target_return for r in selected) / len(selected)
        net = gross - (cost_bps / 10000.0) * turnover
        series.append((d, gross, net, turnover, len(selected)))
        prev = cur
    return series


def _metrics(series: Sequence[Tuple[date, float, float, float, int]]) -> Dict[str, object]:
    if not series:
        return {"n_days": 0}
    nets = [x[2] for x in series]
    gross = [x[1] for x in series]
    mu = mean(nets)
    sigma = stdev(nets) if len(nets) > 1 else 0.0
    sharpe = mu / sigma * math.sqrt(365.0) if sigma > 0 else 0.0
    wealth = 1.0
    peak = 1.0
    max_dd = 0.0
    by_month: Dict[str, float] = defaultdict(lambda: 1.0)
    by_year: Dict[str, float] = defaultdict(lambda: 1.0)
    for d, _, net, _, _ in series:
        wealth *= 1.0 + net
        peak = max(peak, wealth)
        if peak > 0:
            max_dd = max(max_dd, 1.0 - wealth / peak)
        by_month[f"{d.year:04d}-{d.month:02d}"] *= 1.0 + net
        by_year[str(d.year)] *= 1.0 + net
    month_returns = {k: v - 1.0 for k, v in sorted(by_month.items())}
    year_returns = {k: v - 1.0 for k, v in sorted(by_year.items())}
    return {
        "n_days": len(series),
        "gross_mean_daily_bps": mean(gross) * 10000.0,
        "net_mean_daily_bps": mu * 10000.0,
        "annualized_sharpe": sharpe,
        "cumulative_return": wealth - 1.0,
        "max_drawdown": max_dd,
        "mean_turnover": mean(x[3] for x in series),
        "mean_positions": mean(x[4] for x in series),
        "positive_months": sum(v > 0 for v in month_returns.values()),
        "months": len(month_returns),
        "positive_years": sum(v > 0 for v in year_returns.values()),
        "years": year_returns,
        "monthly_returns": month_returns,
    }


def evaluate(rows: Sequence[Row], predictions: Mapping[date, Sequence[Tuple[Row, float]]], cfg, grid_results, data_meta):
    import numpy as np

    expected_days = (date(2025, 12, 30) - TEST_DESDE_04G2).days + 1
    usable_days = [d for d, items in predictions.items() if len(items) >= MIN_ACTIVOS_POR_DIA_04G2]
    usable_fraction = Decimal(len(usable_days)) / Decimal(expected_days)

    reasons_data: List[str] = []
    if data_meta["content_error_files"]:
        reasons_data.append("CONTENT_ERRORS")
    if data_meta["cross_file_duplicates"]:
        reasons_data.append("CROSS_FILE_DUPLICATES")
    if usable_fraction < FRACCION_DIAS_TEST_USABLES_MIN_04G2:
        reasons_data.append("TEST_DAY_COVERAGE_INSUFFICIENT")
    if reasons_data:
        status = STATUS_DATOS_INSUFICIENTES_04G2
    else:
        status = None

    pooled = [(r, p) for d, items in predictions.items() if d in set(usable_days) for r, p in items]
    targets = np.asarray([r.target_return for r, _ in pooled], dtype=float)
    preds = np.asarray([p for _, p in pooled], dtype=float)
    mse_model = float(((preds - targets) ** 2).mean()) if len(targets) else float("nan")
    mse_zero = float((targets ** 2).mean()) if len(targets) else float("nan")
    r2_oos = 1.0 - mse_model / mse_zero if mse_zero > 0 else float("nan")

    model25 = _portfolio_series(predictions, "model", float(COSTE_PRIMARIO_BPS_04G2))
    model50 = _portfolio_series(predictions, "model", float(COSTE_STRESS_BPS_04G2))
    eq25 = _portfolio_series(predictions, "equal", float(COSTE_PRIMARIO_BPS_04G2))
    con25 = _portfolio_series(predictions, "consensus", float(COSTE_PRIMARIO_BPS_04G2))
    m25 = _metrics(model25)
    m50 = _metrics(model50)
    meq = _metrics(eq25)
    mcon = _metrics(con25)

    reasons_econ: List[str] = []
    if not reasons_data:
        if not math.isfinite(r2_oos) or Decimal(str(r2_oos)) <= R2_OOS_MIN_EXCLUSIVA_04G2:
            reasons_econ.append("R2_OOS_NOT_POSITIVE")
        if Decimal(str(m25["net_mean_daily_bps"])) <= MEDIA_NETA_25_BPS_MIN_EXCLUSIVA_04G2:
            reasons_econ.append("NET_MEAN_25_NOT_POSITIVE")
        if Decimal(str(m25["annualized_sharpe"])) < SHARPE_NETO_25_MIN_04G2:
            reasons_econ.append("SHARPE_25_BELOW_GATE")
        if int(m25["positive_months"]) < MIN_MESES_NETO_25_POSITIVOS_04G2:
            reasons_econ.append("POSITIVE_MONTHS_25_BELOW_GATE")
        if int(m25["positive_years"]) < MIN_ANIOS_NETO_25_POSITIVOS_04G2:
            reasons_econ.append("POSITIVE_YEARS_25_BELOW_GATE")
        uplift_eq = Decimal(str(m25["net_mean_daily_bps"] - meq["net_mean_daily_bps"]))
        uplift_con = Decimal(str(m25["net_mean_daily_bps"] - mcon["net_mean_daily_bps"]))
        if uplift_eq <= UPLIFT_MEDIA_VS_EQUAL_WEIGHT_MIN_EXCLUSIVA_04G2:
            reasons_econ.append("NO_UPLIFT_VS_EQUAL_WEIGHT")
        if uplift_con <= UPLIFT_MEDIA_VS_CONSENSUS_MIN_EXCLUSIVA_04G2:
            reasons_econ.append("NO_UPLIFT_VS_CONSENSUS")
        if Decimal(str(m50["net_mean_daily_bps"])) <= MEDIA_NETA_50_BPS_MIN_EXCLUSIVA_04G2:
            reasons_econ.append("NET_MEAN_50_NOT_POSITIVE")
        if Decimal(str(m50["annualized_sharpe"])) < SHARPE_NETO_50_MIN_04G2:
            reasons_econ.append("SHARPE_50_BELOW_GATE")
        status = STATUS_APTO_04G2 if not reasons_econ else STATUS_FALSADO_04G2

    return {
        "status": status,
        "data_reasons": reasons_data,
        "economic_reasons": reasons_econ,
        "selected_hyperparameters": {
            "n_estimators": cfg[0], "learning_rate": cfg[1], "max_depth": cfg[2],
            "loss": LOSS_04G2, "subsample": float(SUBSAMPLE_04G2),
            "min_samples_leaf": MIN_SAMPLES_LEAF_04G2, "random_state": RANDOM_STATE_04G2,
        },
        "validation_grid": grid_results,
        "rows": data_meta,
        "test_days_expected": expected_days,
        "test_days_usable": len(usable_days),
        "test_days_usable_fraction": float(usable_fraction),
        "pooled_oos_observations": len(pooled),
        "r2_oos_vs_zero": r2_oos,
        "mse_model": mse_model,
        "mse_zero": mse_zero,
        "model_25bps": m25,
        "model_50bps": m50,
        "equal_weight_25bps": meq,
        "consensus_sort_25bps": mcon,
        "uplift_mean_bps_vs_equal_weight": m25.get("net_mean_daily_bps", 0.0) - meq.get("net_mean_daily_bps", 0.0),
        "uplift_mean_bps_vs_consensus": m25.get("net_mean_daily_bps", 0.0) - mcon.get("net_mean_daily_bps", 0.0),
        "future_return_calculated": True,
        "ml_trained": True,
        "pnl_calculated": True,
        "credentials_used": False,
        "paper_operational": False,
        "live_used": False,
        "render_used": False,
        "development_2026_open": False,
    }


def run_04g2(output_path: str | Path = "artifacts/consensus-orderflow-sgb-04g2.json") -> Dict[str, object]:
    targets = [(b, q) for b in BASES_04G2 for q in QUOTES_04G2]
    listings = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_LIST_04G2) as ex:
        futs = [ex.submit(_list_pair, b, q) for b, q in targets]
        for fut in as_completed(futs):
            listings.append(fut.result())
    listings.sort(key=lambda x: (x[0], x[1]))
    incomplete = [(b, q, err) for b, q, complete, _, err in listings if not complete]
    objects = [obj for _, _, _, objs, _ in listings for obj in objs]

    contents: List[Content] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_DOWNLOAD_04G2) as ex:
        futs = [ex.submit(_download, obj) for obj in objects]
        for fut in as_completed(futs):
            contents.append(fut.result())
    contents.sort(key=lambda c: (c.base, c.quote, c.month))

    rows, meta = build_rows(contents)
    meta.update({
        "pair_listings": len(listings),
        "pair_listings_incomplete": len(incomplete),
        "downloaded_files": len(contents),
        "downloaded_rows": sum(len(c.bars) for c in contents),
        "compressed_gib": sum(c.compressed_bytes for c in contents) / (1024 ** 3),
    })
    if incomplete:
        meta["content_error_files"] = int(meta["content_error_files"]) + len(incomplete)

    try:
        cfg, grid_results = select_hyperparameters(rows)
        predictions = predict_oos(rows, cfg)
        result = evaluate(rows, predictions, cfg, grid_results, meta)
    except Exception as exc:
        result = {
            "status": STATUS_DATOS_INSUFICIENTES_04G2,
            "data_reasons": [f"EXECUTION:{type(exc).__name__}:{exc}"],
            "economic_reasons": [],
            "rows": meta,
            "future_return_calculated": False,
            "ml_trained": False,
            "pnl_calculated": False,
            "credentials_used": False,
            "paper_operational": False,
            "live_used": False,
            "render_used": False,
            "development_2026_open": False,
        }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result
