"""Réplica predeclarada BOT 2.0-04C-1: cash-and-carry BTC/ETH.

Descarga solo datos públicos Binance. No usa credenciales ni ejecuta órdenes.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

import requests

getcontext().prec = 34

HURDLE_04C1 = Decimal("0.006")
HURDLE_BPS_04C1 = Decimal("60")
MARGIN_DRAWDOWN_MAX_04C1 = Decimal("0.50")
ENTRY_DAYS_BEFORE_04C1 = 28
ENTRY_HOUR_UTC_04C1 = 8
MIN_TRADES_04C1 = 8
MIN_YEARS_WITH_TRADES_04C1 = 3
MIN_WIN_FRACTION_04C1 = Decimal("0.75")

CONTRACTS_04C1: Tuple[str, ...] = tuple(
    f"{underlying}USDT_{suffix}"
    for underlying in ("BTC", "ETH")
    for suffix in (
        "220325", "220624", "220930", "221230",
        "230331", "230630", "230929", "231229",
        "240329", "240628", "240927", "241227",
        "250328", "250627", "250926", "251226",
    )
)

BINANCE_DATA = "https://data.binance.vision/data"
DELIVERY_FIXTURE_04C1 = Path(__file__).resolve().parent / "data" / "carry_04c1_delivery_prices.json"
TIMEOUT_04C1 = 45


@dataclass(frozen=True)
class InputCarry04C1:
    symbol: str
    underlying: str
    expiry_ms: int
    entry_ms: int
    spot_entry: Decimal
    future_entry: Decimal
    spot_exit: Decimal
    delivery_price: Decimal
    max_mark_price: Decimal


@dataclass(frozen=True)
class ResultadoContrato04C1:
    symbol: str
    underlying: str
    year: int
    basis_bps: Decimal
    eligible: bool
    spot_pnl: Decimal
    future_pnl: Decimal
    gross_pnl: Decimal
    cost_buffer: Decimal
    net_pnl: Decimal
    net_notional: Decimal
    net_committed_capital: Decimal
    annualized_committed: Decimal
    tracking_difference: Decimal
    max_margin_drawdown: Decimal
    margin_safe: bool


@dataclass(frozen=True)
class ResultadoCarry04C1:
    contracts_total: int
    trades: int
    years_with_trades: Tuple[int, ...]
    net_pnl_total: Decimal
    mean_net_notional: Decimal
    mean_annualized_committed: Decimal
    win_fraction: Decimal
    unsafe_trades: int
    yearly_net: Tuple[Tuple[int, Decimal, int], ...]
    btc_net: Decimal
    eth_net: Decimal
    verdict: str
    reject_reasons: Tuple[str, ...]
    contracts: Tuple[ResultadoContrato04C1, ...]


def _d(value) -> Decimal:
    return Decimal(str(value))


def _ms_from_csv(raw: str) -> int:
    value = int(raw)
    if value >= 100_000_000_000_000:
        return value // 1000
    return value


def _expiry_from_symbol(symbol: str) -> datetime:
    suffix = symbol.rsplit("_", 1)[1]
    dt = datetime.strptime(suffix, "%y%m%d").replace(
        hour=ENTRY_HOUR_UTC_04C1, tzinfo=timezone.utc
    )
    if dt.year not in {2022, 2023, 2024, 2025}:
        raise ValueError(f"expiry fuera de ventana: {symbol}")
    return dt


def _month_key(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def _spot_url(pair: str, dt: datetime) -> str:
    ym = _month_key(dt)
    return f"{BINANCE_DATA}/spot/monthly/klines/{pair}/1h/{pair}-1h-{ym}.zip"


def _future_url(symbol: str, dt: datetime) -> str:
    ym = _month_key(dt)
    return f"{BINANCE_DATA}/futures/um/monthly/klines/{symbol}/1h/{symbol}-1h-{ym}.zip"


def _mark_url(symbol: str, dt: datetime) -> str:
    ym = _month_key(dt)
    return f"{BINANCE_DATA}/futures/um/monthly/markPriceKlines/{symbol}/1h/{symbol}-1h-{ym}.zip"


class CacheZip04C1:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.cache: Dict[str, bytes] = {}

    def bytes(self, url: str) -> bytes:
        if url not in self.cache:
            r = self.session.get(url, timeout=TIMEOUT_04C1)
            r.raise_for_status()
            self.cache[url] = r.content
        return self.cache[url]


def _csv_rows(zip_bytes: bytes) -> Iterable[Sequence[str]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"ZIP debe contener un CSV, contiene {len(names)}")
        with zf.open(names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            for row in csv.reader(text):
                if not row:
                    continue
                try:
                    _ms_from_csv(row[0])
                except (ValueError, TypeError):
                    continue
                yield row


def _price_at(zip_bytes: bytes, target_ms: int) -> Decimal:
    for row in _csv_rows(zip_bytes):
        if _ms_from_csv(row[0]) == target_ms:
            if len(row) < 2:
                raise ValueError("kline sin open")
            price = _d(row[1])
            if price <= 0:
                raise ValueError("precio no positivo")
            return price
    raise ValueError(f"timestamp 1h no encontrado: {target_ms}")


def _max_mark_between(zip_payloads: Iterable[bytes], start_ms: int, end_ms: int) -> Decimal:
    max_price: Optional[Decimal] = None
    for payload in zip_payloads:
        for row in _csv_rows(payload):
            ts = _ms_from_csv(row[0])
            if ts < start_ms or ts >= end_ms:
                continue
            if len(row) < 3:
                raise ValueError("mark kline sin high")
            high = _d(row[2])
            if high <= 0:
                raise ValueError("mark high no positivo")
            max_price = high if max_price is None or high > max_price else max_price
    if max_price is None:
        raise ValueError("mark path vacio")
    return max_price


def _months_covering(start: datetime, end: datetime) -> Tuple[datetime, ...]:
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


def fetch_delivery_prices_04c1(session: Optional[requests.Session] = None) -> Dict[Tuple[str, int], Decimal]:
    """Carga settlement oficiales congelados antes del PnL.

    GitHub-hosted runners reciben HTTP 451 desde fapi.binance.com. El fixture
    contiene la respuesta pública oficial capturada para los 32 expiries del
    protocolo y evita convertir el geoblocking en una modificación económica.
    """
    del session
    payload = json.loads(DELIVERY_FIXTURE_04C1.read_text(encoding="utf-8"))
    prices = payload.get("prices")
    if not isinstance(prices, dict):
        raise ValueError("fixture delivery prices invalido")
    if set(prices) != set(CONTRACTS_04C1):
        raise ValueError("fixture delivery prices no cubre exactamente 32 contratos")
    out: Dict[Tuple[str, int], Decimal] = {}
    for symbol in CONTRACTS_04C1:
        expiry_ms = int(_expiry_from_symbol(symbol).timestamp() * 1000)
        pair = f"{symbol[:3]}USDT"
        price = _d(prices[symbol])
        if price <= 0:
            raise ValueError(f"deliveryPrice no positivo: {symbol}")
        out[(pair, expiry_ms)] = price
    return out


def cargar_input_contrato_04c1(
    symbol: str,
    *,
    cache: CacheZip04C1,
    delivery_prices: Dict[Tuple[str, int], Decimal],
) -> InputCarry04C1:
    expiry = _expiry_from_symbol(symbol)
    entry = expiry - timedelta(days=ENTRY_DAYS_BEFORE_04C1)
    expiry_ms = int(expiry.timestamp() * 1000)
    entry_ms = int(entry.timestamp() * 1000)
    underlying = symbol[:3]
    pair = f"{underlying}USDT"

    spot_entry = _price_at(cache.bytes(_spot_url(pair, entry)), entry_ms)
    future_entry = _price_at(cache.bytes(_future_url(symbol, entry)), entry_ms)
    spot_exit = _price_at(cache.bytes(_spot_url(pair, expiry)), expiry_ms)
    delivery_key = (pair, expiry_ms)
    if delivery_key not in delivery_prices:
        raise ValueError(f"deliveryPrice no encontrado: {pair} {expiry_ms}")
    delivery_price = delivery_prices[delivery_key]
    mark_payloads = [cache.bytes(_mark_url(symbol, m)) for m in _months_covering(entry, expiry)]
    max_mark = _max_mark_between(mark_payloads, entry_ms, expiry_ms)

    return InputCarry04C1(
        symbol=symbol,
        underlying=underlying,
        expiry_ms=expiry_ms,
        entry_ms=entry_ms,
        spot_entry=spot_entry,
        future_entry=future_entry,
        spot_exit=spot_exit,
        delivery_price=delivery_price,
        max_mark_price=max_mark,
    )


def evaluar_contrato_04c1(x: InputCarry04C1) -> ResultadoContrato04C1:
    s0, f0, s1, d = x.spot_entry, x.future_entry, x.spot_exit, x.delivery_price
    if min(s0, f0, s1, d) <= 0:
        raise ValueError("precios deben ser positivos")
    basis = (f0 / s0 - Decimal("1")) * Decimal("10000")
    eligible = basis > HURDLE_BPS_04C1
    year = datetime.fromtimestamp(x.expiry_ms / 1000, tz=timezone.utc).year

    spot_pnl = s1 - s0 if eligible else Decimal("0")
    future_pnl = f0 - d if eligible else Decimal("0")
    gross = spot_pnl + future_pnl if eligible else Decimal("0")
    cost = HURDLE_04C1 * s0 if eligible else Decimal("0")
    net = gross - cost if eligible else Decimal("0")
    net_notional = net / s0 if eligible else Decimal("0")
    net_capital = net / (Decimal("2") * s0) if eligible else Decimal("0")
    annualized = net_capital * Decimal("365") / Decimal(str(ENTRY_DAYS_BEFORE_04C1)) if eligible else Decimal("0")
    tracking = s1 - d if eligible else Decimal("0")
    margin_dd = max(Decimal("0"), (x.max_mark_price - f0) / s0) if eligible else Decimal("0")
    safe = margin_dd < MARGIN_DRAWDOWN_MAX_04C1 if eligible else True

    return ResultadoContrato04C1(
        symbol=x.symbol,
        underlying=x.underlying,
        year=year,
        basis_bps=basis,
        eligible=eligible,
        spot_pnl=spot_pnl,
        future_pnl=future_pnl,
        gross_pnl=gross,
        cost_buffer=cost,
        net_pnl=net,
        net_notional=net_notional,
        net_committed_capital=net_capital,
        annualized_committed=annualized,
        tracking_difference=tracking,
        max_margin_drawdown=margin_dd,
        margin_safe=safe,
    )


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def evaluar_portafolio_04c1(inputs: Sequence[InputCarry04C1]) -> ResultadoCarry04C1:
    if len(inputs) != len(CONTRACTS_04C1):
        raise ValueError(f"se requieren {len(CONTRACTS_04C1)} contratos, llegaron {len(inputs)}")
    symbols = [x.symbol for x in inputs]
    if set(symbols) != set(CONTRACTS_04C1) or len(set(symbols)) != len(symbols):
        raise ValueError("universo de contratos 04C-1 no coincide")

    rows = tuple(evaluar_contrato_04c1(x) for x in inputs)
    trades = tuple(r for r in rows if r.eligible)
    years = tuple(sorted({r.year for r in trades}))
    net_total = sum((r.net_pnl for r in trades), Decimal("0"))
    mean_net = _mean([r.net_notional for r in trades])
    mean_ann = _mean([r.annualized_committed for r in trades])
    wins = sum(r.net_pnl > 0 for r in trades)
    win_frac = Decimal(wins) / Decimal(len(trades)) if trades else Decimal("0")
    unsafe = sum(not r.margin_safe for r in trades)

    yearly = []
    for year in sorted({r.year for r in rows}):
        ys = [r for r in trades if r.year == year]
        yearly.append((year, sum((r.net_pnl for r in ys), Decimal("0")), len(ys)))
    btc_net = sum((r.net_pnl for r in trades if r.underlying == "BTC"), Decimal("0"))
    eth_net = sum((r.net_pnl for r in trades if r.underlying == "ETH"), Decimal("0"))

    reasons = []
    if len(trades) < MIN_TRADES_04C1:
        reasons.append("OPERACIONES_ELEGIBLES_INSUFICIENTES")
    if len(years) < MIN_YEARS_WITH_TRADES_04C1:
        reasons.append("ANIOS_CON_OPERACIONES_INSUFICIENTES")
    if net_total <= 0:
        reasons.append("PNL_NETO_AGREGADO_NO_POSITIVO")
    if mean_net <= 0:
        reasons.append("MEDIA_NET_NOTIONAL_NO_POSITIVA")
    if mean_ann <= 0:
        reasons.append("MEDIA_ANUALIZADA_CAPITAL_NO_POSITIVA")
    if win_frac < MIN_WIN_FRACTION_04C1:
        reasons.append("FRACCION_OPERACIONES_POSITIVAS_INSUFICIENTE")
    if any(n > 0 and net < 0 for _, net, n in yearly):
        reasons.append("ANIO_CON_OPERACIONES_PNL_NEGATIVO")
    if unsafe:
        reasons.append("STRESS_MARGEN_50PCT_INCUMPLIDO")

    verdict = "CARRY_APTO_04C1" if not reasons else "CARRY_FALSADO_04C1"
    return ResultadoCarry04C1(
        contracts_total=len(rows),
        trades=len(trades),
        years_with_trades=years,
        net_pnl_total=net_total,
        mean_net_notional=mean_net,
        mean_annualized_committed=mean_ann,
        win_fraction=win_frac,
        unsafe_trades=unsafe,
        yearly_net=tuple(yearly),
        btc_net=btc_net,
        eth_net=eth_net,
        verdict=verdict,
        reject_reasons=tuple(reasons),
        contracts=rows,
    )
