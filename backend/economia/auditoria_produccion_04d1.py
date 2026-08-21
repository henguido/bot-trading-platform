"""04D-1: auditor read-only de factibilidad operativa del carry 04C-2."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Mapping, Sequence

import requests

from backend.economia.protocolo_produccion_04d1 import (
    CAPITAL_SPOT_MULTIPLO_04D1,
    CAPITAL_TOTAL_REFERENCIA_04C2,
    DEPTH_LIMIT_04D1,
    DRAG_ALL_IN_BPS_HEREDADO_04C2,
    FUTURES_DEPTH_URL_04D1,
    MARGEN_FUTURES_ESTATICO_MULTIPLO_04D1,
    MAX_FRICCION_LIBRO_ROUNDTRIP_BPS_04D1,
    NOTIONALES_USD_04D1,
    REINTENTOS_04D1,
    SIMBOLOS_04D1,
    SPOT_DEPTH_URL_04D1,
    TIMEOUT_04D1_SEGUNDOS,
)

getcontext().prec = 34
INPUTS_04C2 = Path(__file__).resolve().parent / "data" / "carry_04c2_inputs_04d1.json"
_BPS = Decimal("10000")


@dataclass(frozen=True)
class Llenado04D1:
    side: str
    base_qty: Decimal
    vwap: Decimal
    best_price: Decimal
    impact_bps: Decimal
    levels: int


@dataclass(frozen=True)
class Liquidez04D1:
    symbol: str
    notional_usd: Decimal
    base_qty: Decimal
    spot_buy: Llenado04D1
    spot_sell: Llenado04D1
    futures_sell: Llenado04D1
    futures_buy: Llenado04D1
    roundtrip_book_friction_bps: Decimal
    residual_drag_budget_bps: Decimal
    apt: bool


@dataclass(frozen=True)
class StressMargen04D1:
    symbol: str
    year: int
    mark_excursion: Decimal
    minimum_futures_margin_multiple_no_maintenance: Decimal
    minimum_total_capital_multiple_no_maintenance: Decimal
    lower_bound_topup_from_1x: Decimal
    static_2x_not_disproven: bool


@dataclass(frozen=True)
class Resultado04D1:
    data_apt: bool
    data_reasons: tuple[str, ...]
    liquidity_status: str
    margin_status: str
    overall_status: str
    liquidity: tuple[Liquidez04D1, ...]
    margin_stress: tuple[StressMargen04D1, ...]
    max_roundtrip_book_friction_bps: Decimal
    max_minimum_total_capital_multiple: Decimal
    authenticated_metadata_required: tuple[str, ...]


def _d(raw, name: str = "valor") -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} invalido") from exc
    if not value.is_finite():
        raise ValueError(f"{name} no finito")
    return value


def _fetch_json(url: str, symbol: str, session: requests.Session) -> Mapping:
    last: Exception | None = None
    for attempt in range(REINTENTOS_04D1 + 1):
        try:
            r = session.get(
                url,
                params={"symbol": symbol, "limit": DEPTH_LIMIT_04D1},
                timeout=TIMEOUT_04D1_SEGUNDOS,
            )
            r.raise_for_status()
            payload = r.json()
            if not isinstance(payload, dict):
                raise ValueError("payload depth no es objeto")
            return payload
        except Exception as exc:
            last = exc
            if attempt < REINTENTOS_04D1:
                time.sleep(0.4 * (attempt + 1))
    assert last is not None
    raise last


def _levels(payload: Mapping, key: str) -> tuple[tuple[Decimal, Decimal], ...]:
    raw = payload.get(key)
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"depth {key} vacio")
    out = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            raise ValueError("nivel depth invalido")
        p, q = _d(row[0], "price"), _d(row[1], "qty")
        if p <= 0 or q <= 0:
            raise ValueError("nivel no positivo")
        out.append((p, q))
    return tuple(out)


def _fill_base(levels: Sequence[tuple[Decimal, Decimal]], qty: Decimal, *, side: str) -> Llenado04D1:
    if qty <= 0:
        raise ValueError("qty no positiva")
    remaining = qty
    quote = Decimal("0")
    used = 0
    for price, available in levels:
        take = min(remaining, available)
        quote += take * price
        remaining -= take
        used += 1
        if remaining <= 0:
            break
    if remaining > Decimal("0.000000000001"):
        raise ValueError(f"depth insuficiente para qty={qty}")
    vwap = quote / qty
    best = levels[0][0]
    if side == "buy":
        impact = (vwap / best - Decimal("1")) * _BPS
    elif side == "sell":
        impact = (Decimal("1") - vwap / best) * _BPS
    else:
        raise ValueError("side invalido")
    return Llenado04D1(side, qty, vwap, best, max(Decimal("0"), impact), used)


def _fill_spot_buy_quote(asks: Sequence[tuple[Decimal, Decimal]], quote_target: Decimal) -> Llenado04D1:
    if quote_target <= 0:
        raise ValueError("notional no positivo")
    remaining_quote = quote_target
    base = Decimal("0")
    quote = Decimal("0")
    used = 0
    for price, available in asks:
        level_quote = price * available
        take_quote = min(remaining_quote, level_quote)
        take_base = take_quote / price
        base += take_base
        quote += take_quote
        remaining_quote -= take_quote
        used += 1
        if remaining_quote <= Decimal("0.00000001"):
            break
    if remaining_quote > Decimal("0.01"):
        raise ValueError(f"depth spot insuficiente para ${quote_target}")
    vwap = quote / base
    best = asks[0][0]
    impact = (vwap / best - Decimal("1")) * _BPS
    return Llenado04D1("buy", base, vwap, best, max(Decimal("0"), impact), used)


def auditar_liquidez_symbol_04d1(symbol: str, session: requests.Session) -> tuple[Liquidez04D1, ...]:
    spot = _fetch_json(SPOT_DEPTH_URL_04D1, symbol, session)
    fut = _fetch_json(FUTURES_DEPTH_URL_04D1, symbol, session)
    spot_bids, spot_asks = _levels(spot, "bids"), _levels(spot, "asks")
    fut_bids, fut_asks = _levels(fut, "bids"), _levels(fut, "asks")
    rows = []
    for notional in NOTIONALES_USD_04D1:
        spot_buy = _fill_spot_buy_quote(spot_asks, notional)
        qty = spot_buy.base_qty
        spot_sell = _fill_base(spot_bids, qty, side="sell")
        futures_sell = _fill_base(fut_bids, qty, side="sell")
        futures_buy = _fill_base(fut_asks, qty, side="buy")
        # Round-trip hipotético al mismo snapshot: cruza ambos libros al abrir/cerrar.
        friction = (
            (spot_buy.vwap - spot_sell.vwap)
            + (futures_buy.vwap - futures_sell.vwap)
        ) / spot_buy.vwap * _BPS
        residual = DRAG_ALL_IN_BPS_HEREDADO_04C2 - friction
        rows.append(Liquidez04D1(
            symbol=symbol,
            notional_usd=notional,
            base_qty=qty,
            spot_buy=spot_buy,
            spot_sell=spot_sell,
            futures_sell=futures_sell,
            futures_buy=futures_buy,
            roundtrip_book_friction_bps=friction,
            residual_drag_budget_bps=residual,
            apt=friction <= MAX_FRICCION_LIBRO_ROUNDTRIP_BPS_04D1,
        ))
    return tuple(rows)


def auditar_stress_margen_04d1() -> tuple[StressMargen04D1, ...]:
    raw = json.loads(INPUTS_04C2.read_text(encoding="utf-8"))
    if raw.get("economic_verdict") != "CARRY_ECONOMICAMENTE_APTO_04C2":
        raise ValueError("fixture 04C-2 sin veredicto esperado")
    rows = []
    for symbol in SIMBOLOS_04D1:
        years = raw["assets"][symbol]
        for year_s, values in sorted(years.items()):
            excursion = _d(values["mark_excursion"], "mark_excursion")
            # Lower bound favorable: ignora maintenance margin y cualquier fee/basis.
            min_fut = excursion
            min_total = CAPITAL_SPOT_MULTIPLO_04D1 + min_fut
            topup = max(Decimal("0"), excursion - MARGEN_FUTURES_ESTATICO_MULTIPLO_04D1)
            rows.append(StressMargen04D1(
                symbol=symbol,
                year=int(year_s),
                mark_excursion=excursion,
                minimum_futures_margin_multiple_no_maintenance=min_fut,
                minimum_total_capital_multiple_no_maintenance=min_total,
                lower_bound_topup_from_1x=topup,
                static_2x_not_disproven=min_total < CAPITAL_TOTAL_REFERENCIA_04C2,
            ))
    return tuple(rows)


def ejecutar_auditoria_04d1(session: requests.Session | None = None) -> Resultado04D1:
    session = session or requests.Session()
    errors = []
    liquidity = []
    for symbol in SIMBOLOS_04D1:
        try:
            liquidity.extend(auditar_liquidez_symbol_04d1(symbol, session))
        except Exception as exc:
            errors.append(f"depth:{symbol}:{type(exc).__name__}:{exc}")

    try:
        margin = auditar_stress_margen_04d1()
    except Exception as exc:
        errors.append(f"margin:{type(exc).__name__}:{exc}")
        margin = ()

    expected_liq = len(SIMBOLOS_04D1) * len(NOTIONALES_USD_04D1)
    data_apt = not errors and len(liquidity) == expected_liq and len(margin) == 8
    liq_apt = data_apt and all(r.apt for r in liquidity)
    static_rejected = bool(margin) and any(not r.static_2x_not_disproven for r in margin)

    max_friction = max((r.roundtrip_book_friction_bps for r in liquidity), default=Decimal("0"))
    max_total = max((r.minimum_total_capital_multiple_no_maintenance for r in margin), default=Decimal("0"))

    return Resultado04D1(
        data_apt=data_apt,
        data_reasons=tuple(errors),
        liquidity_status=("EJECUCION_PUBLICA_APTA_04D1" if liq_apt else "EJECUCION_PUBLICA_NO_VERIFICADA_04D1"),
        margin_status=("MARGEN_ESTATICO_2X_INSUFICIENTE_04D1" if static_rejected else "MARGEN_ESTATICO_2X_NO_FALSADO_04D1"),
        overall_status="PRODUCCION_NO_AUTORIZADA_04D1",
        liquidity=tuple(liquidity),
        margin_stress=tuple(margin),
        max_roundtrip_book_friction_bps=max_friction,
        max_minimum_total_capital_multiple=max_total,
        authenticated_metadata_required=(
            "fee tier real Spot y USD-M",
            "leverage brackets y maintenance margin BTCUSDT/ETHUSDT",
            "collateral ratios/haircuts de Multi-Assets Mode",
            "margin mode y balances disponibles para top-ups",
        ),
    )
