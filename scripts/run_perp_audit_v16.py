#!/usr/bin/env python3
"""BOT 2.0-04B-v16: audita klines Futures perpetual 1d 2022-2025."""
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

from backend.economia.auditoria_perp_v16 import auditar_perp_v16
from backend.economia.historico_perp_v16 import descargar_perp_mes_v16
from backend.economia.protocolo_perp_v16 import (
    DESARROLLO_2026_ABIERTO_V16, DESDE_V16, HASTA_EXCLUSIVO_V16,
    INTERVALO_V16, TEST_MAY_JUL_ABIERTO_V16, UNIVERSO_PERP_V16,
)

SALIDA = RAIZ / "artifacts" / "perp-data-audit-v16-2022-2025.json"
MAX_WORKERS = 8


def _jsonable(x):
    if isinstance(x, Decimal): return str(x)
    if isinstance(x, tuple): return [_jsonable(v) for v in x]
    if isinstance(x, list): return [_jsonable(v) for v in x]
    if isinstance(x, dict): return {str(k): _jsonable(v) for k, v in x.items()}
    return x


def main() -> int:
    assert DESARROLLO_2026_ABIERTO_V16 is False
    assert TEST_MAY_JUL_ABIERTO_V16 is False
    assert HASTA_EXCLUSIVO_V16.year == 2026 and HASTA_EXCLUSIVO_V16.month == 1
    tareas = [
        (symbol, year, month)
        for symbol in UNIVERSO_PERP_V16
        for year in range(DESDE_V16.year, HASTA_EXCLUSIVO_V16.year)
        for month in range(1, 13)
    ]
    print(f"[04B-v16] audit perp klines {INTERVALO_V16} tareas={len(tareas)} workers={MAX_WORKERS} 2026_OPEN=False")

    resultados = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(descargar_perp_mes_v16, s, y, m): (s, y, m) for s, y, m in tareas}
        for fut in as_completed(futuros):
            resultados.append(fut.result())

    series = defaultdict(list)
    for r in resultados:
        if r.completa:
            series[r.symbol].extend(r.velas)
    series = {s: tuple(sorted(v, key=lambda x: x.open_time_ms)) for s, v in series.items()}
    audit = auditar_perp_v16(series)

    meses_ok = sum(r.completa for r in resultados)
    meses_404 = sum(r.status_http == 404 for r in resultados)
    meses_error = len(resultados) - meses_ok - meses_404
    reporte = {
        "status": "DATASET_PERP_APTO_V16" if audit.dataset_apto else "DATASET_PERP_NO_APTO_V16",
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "fuente": "data.binance.vision/futures/um/monthly/klines",
        "intervalo": INTERVALO_V16,
        "n_tareas_mensuales": len(tareas),
        "meses_ok": meses_ok,
        "meses_404": meses_404,
        "meses_error": meses_error,
        "n_simbolos_aptos": audit.n_simbolos_aptos,
        "dias_cross_section_completa": audit.dias_cross_section_completa,
        "fraccion_cross_section_completa": audit.fraccion_cross_section_completa,
        "min_simbolos_en_dia": audit.min_simbolos_en_dia,
        "max_simbolos_en_dia": audit.max_simbolos_en_dia,
        "dataset_apto": audit.dataset_apto,
        "motivos_rechazo": list(audit.motivos_rechazo),
        "simbolos": [
            {"symbol": c.symbol, "n_dias": c.n_dias, "fraccion_cobertura": c.fraccion_cobertura,
             "n_gaps": c.n_gaps, "max_gap_dias": c.max_gap_dias, "apto": c.apto}
            for c in audit.simbolos
        ],
        "anios": [
            {"year": a.year, "dias": a.dias, "dias_cross_section_completa": a.dias_cross_section_completa,
             "fraccion_cross_section_completa": a.fraccion_cross_section_completa, "apto": a.apto}
            for a in audit.anios
        ],
        "meses_fallidos": [
            {"symbol": r.symbol, "year": r.year, "month": r.month,
             "status_http": r.status_http, "error": r.error}
            for r in sorted(resultados, key=lambda x: (x.symbol, x.year, x.month)) if not r.completa
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[04B-v16] {reporte['status']}: meses_ok={meses_ok}/{len(tareas)} 404={meses_404} errors={meses_error} symbols_aptos={audit.n_simbolos_aptos} cross={audit.fraccion_cross_section_completa}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
