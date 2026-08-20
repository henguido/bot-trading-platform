#!/usr/bin/env python3
"""BOT 2.0-04B-v14: audita premiumIndex histórico 2022-2025."""
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

from backend.economia.auditoria_derivados_v14 import auditar_derivados_v14
from backend.economia.historico_derivados_v14 import descargar_premium_mes_v14
from backend.economia.protocolo_derivados_v14 import (
    DESARROLLO_2026_ABIERTO_V14,
    DESDE_V14,
    HASTA_EXCLUSIVO_V14,
    INTERVALO_PREMIUM_V14,
    TEST_MAY_JUL_ABIERTO_V14,
    UNIVERSO_DERIVADOS_V14,
)

SALIDA = RAIZ / "artifacts" / "derivatives-data-audit-v14-2022-2025.json"
MAX_WORKERS = 8


def _jsonable(x):
    if isinstance(x, Decimal): return str(x)
    if isinstance(x, (tuple, list)): return [_jsonable(v) for v in x]
    if isinstance(x, dict): return {str(k): _jsonable(v) for k, v in x.items()}
    return x


def main() -> int:
    assert DESARROLLO_2026_ABIERTO_V14 is False
    assert TEST_MAY_JUL_ABIERTO_V14 is False
    assert HASTA_EXCLUSIVO_V14.year == 2026 and HASTA_EXCLUSIVO_V14.month == 1
    tareas = [
        (symbol, year, month)
        for symbol in UNIVERSO_DERIVADOS_V14
        for year in range(DESDE_V14.year, HASTA_EXCLUSIVO_V14.year)
        for month in range(1, 13)
    ]
    print(
        f"[04B-v14] audit premiumIndex {INTERVALO_PREMIUM_V14} "
        f"tareas={len(tareas)} workers={MAX_WORKERS} 2026_OPEN=False"
    )

    resultados = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {
            pool.submit(descargar_premium_mes_v14, s, y, m): (s, y, m)
            for s, y, m in tareas
        }
        for fut in as_completed(futuros):
            resultados.append(fut.result())

    series = defaultdict(list)
    for r in resultados:
        if r.completa:
            series[r.symbol].extend(r.barras)
    series = {s: tuple(sorted(v, key=lambda x: x.open_time_ms)) for s, v in series.items()}
    audit = auditar_derivados_v14(series)

    meses_ok = sum(r.completa for r in resultados)
    meses_404 = sum(r.status_http == 404 for r in resultados)
    meses_error = len(resultados) - meses_ok - meses_404
    reporte = {
        "status": "DATASET_DERIVADOS_APTO_V14" if audit.dataset_apto else "DATASET_DERIVADOS_NO_APTO_V14",
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "fuente": "data.binance.vision/futures/um/monthly/premiumIndexKlines",
        "intervalo": INTERVALO_PREMIUM_V14,
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
            {
                "symbol": c.symbol, "n_dias": c.n_dias,
                "dias_esperados": c.dias_esperados,
                "fraccion_cobertura": c.fraccion_cobertura,
                "n_gaps": c.n_gaps, "max_gap_dias": c.max_gap_dias,
                "apto": c.apto,
            }
            for c in audit.simbolos
        ],
        "anios": [
            {
                "year": a.year, "dias": a.dias,
                "dias_cross_section_completa": a.dias_cross_section_completa,
                "fraccion_cross_section_completa": a.fraccion_cross_section_completa,
                "apto": a.apto,
            }
            for a in audit.anios
        ],
        "meses_fallidos": [
            {
                "symbol": r.symbol, "year": r.year, "month": r.month,
                "status_http": r.status_http, "error": r.error,
            }
            for r in sorted(resultados, key=lambda x: (x.symbol, x.year, x.month))
            if not r.completa
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[04B-v14] {reporte['status']}: meses_ok={meses_ok}/{len(tareas)} "
        f"symbols_aptos={audit.n_simbolos_aptos} cross={audit.fraccion_cross_section_completa}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
