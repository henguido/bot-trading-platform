#!/usr/bin/env python3
"""BOT 2.0-04B-v19: funding diario negativo -> Spot t+1."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.economia.evaluacion_funding_v19 import evaluar_funding_v19
from backend.economia.funding_spot_v19 import construir_observaciones_funding_v19
from backend.economia.historico_funding_v18 import descargar_funding_mes_v18
from backend.economia.historico_spot_diario_v15 import descargar_spot_diario_v15
from backend.economia.protocolo_funding_v19 import (
    DESARROLLO_2026_ABIERTO_V19,
    DESDE_V19,
    HASTA_EXCLUSIVO_V19,
    HURDLE_ECONOMICO_BPS_V19,
    TEST_MAY_JUL_ABIERTO_V19,
    TOP_K_V19,
    UNIVERSO_V19,
)

SALIDA = RAIZ / "artifacts" / "funding-v19-desarrollo-2022-2025.json"
MAX_WORKERS = 8


def _jsonable(x):
    if isinstance(x, Decimal): return str(x)
    if isinstance(x, tuple): return [_jsonable(v) for v in x]
    if isinstance(x, list): return [_jsonable(v) for v in x]
    if isinstance(x, dict): return {str(k): _jsonable(v) for k, v in x.items()}
    return x


def main() -> int:
    assert DESARROLLO_2026_ABIERTO_V19 is False
    assert TEST_MAY_JUL_ABIERTO_V19 is False
    assert HASTA_EXCLUSIVO_V19.year == 2026 and HASTA_EXCLUSIVO_V19.month == 1

    tareas = [(s, y, m) for s in UNIVERSO_V19 for y in range(2022, 2026) for m in range(1, 13)]
    print(
        f"[04B-v19] bottom-{TOP_K_V19} funding diario -> Spot t+1 "
        f"hurdle={HURDLE_ECONOMICO_BPS_V19}bps tareas_funding={len(tareas)} 2026_OPEN=False"
    )

    resultados_funding = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(descargar_funding_mes_v18, s, y, m): (s, y, m) for s, y, m in tareas}
        for fut in as_completed(futuros):
            resultados_funding.append(fut.result())

    funding = defaultdict(list)
    for r in resultados_funding:
        if r.completa:
            funding[r.symbol].extend(r.eventos)
    funding = {s: tuple(sorted(v, key=lambda e: e.funding_time_ms)) for s, v in funding.items()}

    desde_ms = int(DESDE_V19.timestamp() * 1000)
    hasta_ms = int(HASTA_EXCLUSIVO_V19.timestamp() * 1000)
    resultados_spot = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {
            pool.submit(descargar_spot_diario_v15, s, start_ms=desde_ms, end_ms=hasta_ms): s
            for s in UNIVERSO_V19
        }
        for fut in as_completed(futuros):
            resultados_spot.append(fut.result())
    spot = {r.symbol: r.barras for r in resultados_spot if r.completa and r.barras}

    observaciones = construir_observaciones_funding_v19(funding, spot)
    resultado = evaluar_funding_v19(observaciones)
    meses_ok = sum(r.completa for r in resultados_funding)
    meses_404 = sum(r.status_http == 404 for r in resultados_funding)
    meses_error = len(resultados_funding) - meses_ok - meses_404

    reporte = {
        "status": resultado.clase,
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "hipotesis": "suma funding diaria mas negativa -> long Spot siguiente dia",
        "agregacion": "suma de settlements reales del dia UTC",
        "top_k": TOP_K_V19,
        "hurdle_bps": HURDLE_ECONOMICO_BPS_V19,
        "funding_meses_ok": meses_ok,
        "funding_meses_total": len(resultados_funding),
        "funding_meses_404": meses_404,
        "funding_meses_error": meses_error,
        "funding_eventos": sum(len(r.eventos) for r in resultados_funding if r.completa),
        "spot_simbolos_ok": len(spot),
        "spot_simbolos_total": len(UNIVERSO_V19),
        "spot_requests": sum(r.n_requests for r in resultados_spot),
        "n_observaciones": len(observaciones),
        "anios_aptos": resultado.anios_aptos,
        "anuales": [asdict(x) for x in resultado.anuales],
        "spot_fallidos": [
            {"symbol": r.symbol, "n_requests": r.n_requests, "error": r.error}
            for r in sorted(resultados_spot, key=lambda x: x.symbol) if not r.completa
        ],
        "funding_fallidos": [
            {"symbol": r.symbol, "year": r.year, "month": r.month, "status_http": r.status_http, "error": r.error}
            for r in sorted(resultados_funding, key=lambda x: (x.symbol, x.year, x.month)) if not r.completa
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"[04B-v19] {resultado.clase}: anios_aptos={resultado.anios_aptos}/4 "
        f"funding_ok={meses_ok}/{len(tareas)} spot_ok={len(spot)}/{len(UNIVERSO_V19)} obs={len(observaciones)}"
    )
    for a in resultado.anuales:
        print(
            f"[04B-v19] {a.year}: dias={a.n_dias} net={a.retorno_bottom5_neto_medio_bps} "
            f"mediana={a.retorno_bottom5_neto_mediano_bps} exceso={a.exceso_medio_bps} "
            f"spread={a.spread_bottom5_top5_medio_bps} apto={a.apto}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
