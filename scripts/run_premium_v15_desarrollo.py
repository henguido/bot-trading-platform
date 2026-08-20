#!/usr/bin/env python3
"""BOT 2.0-04B-v15: premiumIndex diario -> selección Spot del día siguiente."""
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

from backend.economia.evaluacion_premium_v15 import evaluar_premium_v15
from backend.economia.historico_derivados_v14 import descargar_premium_mes_v14
from backend.economia.historico_spot_diario_v15 import descargar_spot_diario_v15
from backend.economia.premium_spot_v15 import construir_observaciones_premium_v15
from backend.economia.protocolo_premium_v15 import (
    DESARROLLO_2026_ABIERTO_V15,
    DESDE_V15,
    HASTA_EXCLUSIVO_V15,
    HURDLE_ECONOMICO_BPS_V15,
    TEST_MAY_JUL_ABIERTO_V15,
    TOP_K_V15,
    UNIVERSO_V15,
)

SALIDA = RAIZ / "artifacts" / "premium-v15-desarrollo-2022-2025.json"
MAX_WORKERS = 8


def _jsonable(x):
    if isinstance(x, Decimal):
        return str(x)
    if isinstance(x, tuple):
        return [_jsonable(v) for v in x]
    if isinstance(x, list):
        return [_jsonable(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    return x


def main() -> int:
    assert DESARROLLO_2026_ABIERTO_V15 is False
    assert TEST_MAY_JUL_ABIERTO_V15 is False
    assert HASTA_EXCLUSIVO_V15.year == 2026 and HASTA_EXCLUSIVO_V15.month == 1

    tareas = [
        (symbol, year, month)
        for symbol in UNIVERSO_V15
        for year in range(DESDE_V15.year, HASTA_EXCLUSIVO_V15.year)
        for month in range(1, 13)
    ]
    print(
        f"[04B-v15] premium low-{TOP_K_V15} -> Spot t+1 "
        f"hurdle={HURDLE_ECONOMICO_BPS_V15}bps tareas_premium={len(tareas)} "
        "2026_OPEN=False"
    )

    resultados_premium = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {
            pool.submit(descargar_premium_mes_v14, s, y, m): (s, y, m)
            for s, y, m in tareas
        }
        for fut in as_completed(futuros):
            resultados_premium.append(fut.result())

    premium = defaultdict(list)
    for r in resultados_premium:
        if r.completa:
            premium[r.symbol].extend(r.barras)
    premium = {s: tuple(sorted(v, key=lambda x: x.open_time_ms)) for s, v in premium.items()}

    desde_ms = int(DESDE_V15.timestamp() * 1000)
    hasta_ms = int(HASTA_EXCLUSIVO_V15.timestamp() * 1000)
    resultados_spot = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {
            pool.submit(
                descargar_spot_diario_v15,
                symbol,
                start_ms=desde_ms,
                end_ms=hasta_ms,
            ): symbol
            for symbol in UNIVERSO_V15
        }
        for fut in as_completed(futuros):
            resultados_spot.append(fut.result())

    spot = {
        r.symbol: r.barras
        for r in resultados_spot
        if r.completa and r.barras
    }
    observaciones = construir_observaciones_premium_v15(premium, spot)
    resultado = evaluar_premium_v15(observaciones)

    reporte = {
        "status": resultado.clase,
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "hipotesis": "premiumIndex.close bajo -> long Spot siguiente dia",
        "top_k": TOP_K_V15,
        "hurdle_bps": HURDLE_ECONOMICO_BPS_V15,
        "premium_meses_ok": sum(r.completa for r in resultados_premium),
        "premium_meses_total": len(resultados_premium),
        "spot_simbolos_ok": len(spot),
        "spot_simbolos_total": len(UNIVERSO_V15),
        "spot_requests": sum(r.n_requests for r in resultados_spot),
        "n_observaciones": len(observaciones),
        "anios_aptos": resultado.anios_aptos,
        "anuales": [asdict(x) for x in resultado.anuales],
        "spot_fallidos": [
            {"symbol": r.symbol, "n_requests": r.n_requests, "error": r.error}
            for r in sorted(resultados_spot, key=lambda x: x.symbol)
            if not r.completa
        ],
        "premium_fallidos": [
            {
                "symbol": r.symbol, "year": r.year, "month": r.month,
                "status_http": r.status_http, "error": r.error,
            }
            for r in sorted(resultados_premium, key=lambda x: (x.symbol, x.year, x.month))
            if not r.completa
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"[04B-v15] {resultado.clase}: anios_aptos={resultado.anios_aptos}/4 "
        f"premium_ok={reporte['premium_meses_ok']}/{len(tareas)} "
        f"spot_ok={len(spot)}/{len(UNIVERSO_V15)} obs={len(observaciones)}"
    )
    for a in resultado.anuales:
        print(
            f"[04B-v15] {a.year}: dias={a.n_dias} "
            f"low5_net={a.retorno_low5_neto_medio_bps} "
            f"exceso={a.exceso_medio_bps} spread={a.spread_low5_high5_medio_bps} "
            f"apto={a.apto}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
