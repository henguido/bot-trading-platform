#!/usr/bin/env python3
"""BOT 2.0-04B-v17: perpetual basis cross-sectional -> Spot t+1."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.economia.basis_spot_v17 import construir_observaciones_basis_v17
from backend.economia.evaluacion_basis_v17 import evaluar_basis_v17
from backend.economia.historico_perp_v16 import descargar_perp_mes_v16
from backend.economia.historico_spot_diario_v15 import descargar_spot_diario_v15
from backend.economia.protocolo_basis_v17 import (
    DESARROLLO_2026_ABIERTO_V17, HURDLE_ECONOMICO_BPS_V17,
    TEST_MAY_JUL_ABIERTO_V17, TOP_K_V17, UNIVERSO_V17,
)
from backend.economia.protocolo_perp_v16 import DESDE_V16, HASTA_EXCLUSIVO_V16

SALIDA = RAIZ / "artifacts" / "basis-v17-desarrollo-2022-2025.json"
MAX_WORKERS = 8


def _jsonable(x):
    if isinstance(x, Decimal): return str(x)
    if isinstance(x, tuple): return [_jsonable(v) for v in x]
    if isinstance(x, list): return [_jsonable(v) for v in x]
    if isinstance(x, dict): return {str(k): _jsonable(v) for k, v in x.items()}
    return x


def _anual(a):
    return {
        "year": a.year,
        "n_dias": a.n_dias,
        "n_simbolos_min": a.n_simbolos_min,
        "n_simbolos_max": a.n_simbolos_max,
        "retorno_top_basis_neto_medio_bps": a.retorno_low5_neto_medio_bps,
        "retorno_top_basis_neto_mediano_bps": a.retorno_low5_neto_mediano_bps,
        "hit_rate_top_basis_neto": a.hit_rate_low5_neto,
        "retorno_benchmark_neto_medio_bps": a.retorno_benchmark_neto_medio_bps,
        "exceso_medio_bps": a.exceso_medio_bps,
        "exceso_mediano_bps": a.exceso_mediano_bps,
        "spread_top_basis_minus_bottom_basis_medio_bps": a.spread_low5_high5_medio_bps,
        "spread_top_basis_minus_bottom_basis_mediano_bps": a.spread_low5_high5_mediano_bps,
        "meses_portfolio_positivos": a.meses_portfolio_positivos,
        "folds_portfolio_positivos": a.folds_portfolio_positivos,
        "meses_exceso_positivos": a.meses_exceso_positivos,
        "folds_exceso_positivos": a.folds_exceso_positivos,
        "meses_spread_positivos": a.meses_spread_positivos,
        "folds_spread_positivos": a.folds_spread_positivos,
        "apto": a.apto,
        "motivos_rechazo": list(a.motivos_rechazo),
    }


def main() -> int:
    assert DESARROLLO_2026_ABIERTO_V17 is False
    assert TEST_MAY_JUL_ABIERTO_V17 is False
    tareas = [(s, y, m) for s in UNIVERSO_V17 for y in range(2022, 2026) for m in range(1, 13)]
    print(f"[04B-v17] top-{TOP_K_V17} basis_perp -> Spot t+1 hurdle={HURDLE_ECONOMICO_BPS_V17}bps 2026_OPEN=False")

    resultados_fut = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(descargar_perp_mes_v16, s, y, m): (s, y, m) for s, y, m in tareas}
        for f in as_completed(futs): resultados_fut.append(f.result())
    futures = defaultdict(list)
    for r in resultados_fut:
        if r.completa: futures[r.symbol].extend(r.velas)
    futures = {s: tuple(sorted(v, key=lambda x: x.open_time_ms)) for s, v in futures.items()}

    desde_ms = int(DESDE_V16.timestamp() * 1000)
    hasta_ms = int(HASTA_EXCLUSIVO_V16.timestamp() * 1000)
    resultados_spot = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(descargar_spot_diario_v15, s, start_ms=desde_ms, end_ms=hasta_ms): s for s in UNIVERSO_V17}
        for f in as_completed(futs): resultados_spot.append(f.result())
    spot = {r.symbol: r.barras for r in resultados_spot if r.completa and r.barras}

    obs = construir_observaciones_basis_v17(futures, spot)
    resultado = evaluar_basis_v17(obs)
    reporte = {
        "status": resultado.clase,
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "hipotesis": "basis_perp=(SpotClose-FuturesClose)/FuturesClose alto -> long Spot siguiente dia",
        "top_k": TOP_K_V17,
        "hurdle_bps": HURDLE_ECONOMICO_BPS_V17,
        "futures_meses_ok": sum(r.completa for r in resultados_fut),
        "futures_meses_total": len(resultados_fut),
        "spot_simbolos_ok": len(spot),
        "spot_simbolos_total": len(UNIVERSO_V17),
        "spot_requests": sum(r.n_requests for r in resultados_spot),
        "n_observaciones": len(obs),
        "anios_aptos": resultado.anios_aptos,
        "anuales": [_anual(a) for a in resultado.anuales],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[04B-v17] {resultado.clase}: anios_aptos={resultado.anios_aptos}/4 futures_ok={reporte['futures_meses_ok']}/{len(tareas)} spot_ok={len(spot)}/{len(UNIVERSO_V17)} obs={len(obs)}")
    for a in reporte["anuales"]:
        print(f"[04B-v17] {a['year']}: dias={a['n_dias']} net={a['retorno_top_basis_neto_medio_bps']} exceso={a['exceso_medio_bps']} spread={a['spread_top_basis_minus_bottom_basis_medio_bps']} apto={a['apto']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
