"""Orquestador remoto 04H-1 con fallback exacto priceHistory -> open_interest.

No altera la definición económica. Solo construye el dataset de mark/oracle y
entrega las series al evaluador, que sigue bloqueando PnL si el gate falla.
"""
from __future__ import annotations

from backend.economia.auditoria_crossvenue_funding_04h0 import fetch_hl_funding_04h0
from backend.economia.carry_crossvenue_04h1 import (
    evaluate_from_series_04h1,
    load_binance_04h1,
    parse_hl_funding_04h1,
)
from backend.economia.fuente_0xarchive_04h1 import (
    coverage_04h1,
    fetch_open_interest_context_04h1,
    fetch_price_history_04h1,
    merge_exact_oi_fallback_04h1,
)
from backend.economia.protocolo_crossvenue_carry_04h1 import (
    ACTIVOS_04H1,
    COBERTURA_PRECIOS_MIN_04H1,
    DESDE_04H1,
    HASTA_EXCLUSIVO_04H1,
    HORAS_ESPERADAS_04H1,
)
from datetime import datetime


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def build_exact_price_context_04h1(asset: str, start_ms: int, end_ms: int, api_key: str):
    primary = fetch_price_history_04h1(asset, start_ms, end_ms, api_key)
    primary_coverage = coverage_04h1(primary, HORAS_ESPERADAS_04H1)
    if primary_coverage >= float(COBERTURA_PRECIOS_MIN_04H1):
        return primary

    oi_context = fetch_open_interest_context_04h1(asset, start_ms, end_ms, api_key)
    return merge_exact_oi_fallback_04h1(primary, oi_context, start_ms, end_ms)


def run_remote_exact_04h1(api_key: str):
    lo, hi = _ms(DESDE_04H1), _ms(HASTA_EXCLUSIVO_04H1)
    datasets = {}
    for asset in ACTIVOS_04H1:
        points = build_exact_price_context_04h1(asset, lo, hi, api_key)
        hl_funding = parse_hl_funding_04h1(fetch_hl_funding_04h0(asset))
        bn = load_binance_04h1(asset)
        datasets[asset] = (points, hl_funding, bn)
    return evaluate_from_series_04h1(datasets)
