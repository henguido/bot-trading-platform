#!/usr/bin/env python3
"""BOT 2.0-04B-v18: audita funding USD-M real 2022-2025."""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.economia.auditoria_funding_v18 import auditar_funding_v18
from backend.economia.historico_funding_v18 import descargar_funding_rango_v18
from backend.economia.protocolo_funding_v18 import (
    DESARROLLO_2026_ABIERTO_V18,
    DESDE_V18,
    HASTA_EXCLUSIVO_V18,
    TEST_MAY_JUL_ABIERTO_V18,
    UNIVERSO_FUNDING_V18,
)

SALIDA = RAIZ / "artifacts" / "funding-data-audit-v18-2022-2025.json"
MAX_WORKERS = 4


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
    assert DESARROLLO_2026_ABIERTO_V18 is False
    assert TEST_MAY_JUL_ABIERTO_V18 is False
    assert HASTA_EXCLUSIVO_V18.year == 2026 and HASTA_EXCLUSIVO_V18.month == 1
    desde_ms = int(DESDE_V18.timestamp() * 1000)
    hasta_ms = int(HASTA_EXCLUSIVO_V18.timestamp() * 1000)

    print(
        f"[04B-v18] audit funding symbols={len(UNIVERSO_FUNDING_V18)} "
        f"workers={MAX_WORKERS} 2026_OPEN=False"
    )
    resultados = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {
            pool.submit(descargar_funding_rango_v18, symbol, desde_ms, hasta_ms): symbol
            for symbol in UNIVERSO_FUNDING_V18
        }
        for fut in as_completed(futuros):
            resultados.append(fut.result())

    por_symbol = {r.symbol: r.eventos for r in resultados if r.completa}
    audit = auditar_funding_v18(por_symbol)
    descargas_completas = sum(r.completa for r in resultados)
    n_requests = sum(r.n_requests for r in resultados)
    descargas_ok = descargas_completas == len(UNIVERSO_FUNDING_V18)
    dataset_apto = audit.dataset_apto and descargas_ok
    motivos = list(audit.motivos_rechazo)
    if not descargas_ok:
        motivos.append("DESCARGA_FUNDING_INCOMPLETA")

    reporte = {
        "status": "DATASET_FUNDING_APTO_V18" if dataset_apto else "DATASET_FUNDING_NO_APTO_V18",
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "fuente": "https://fapi.binance.com/fapi/v1/fundingRate",
        "desde": DESDE_V18.isoformat(),
        "hasta_exclusivo": HASTA_EXCLUSIVO_V18.isoformat(),
        "n_simbolos": len(UNIVERSO_FUNDING_V18),
        "descargas_completas": descargas_completas,
        "n_requests": n_requests,
        "n_eventos_total": sum(len(r.eventos) for r in resultados if r.completa),
        "n_simbolos_aptos": audit.n_simbolos_aptos,
        "dias_cross_section_completa": audit.dias_cross_section_completa,
        "fraccion_cross_section_completa": audit.fraccion_cross_section_completa,
        "min_simbolos_en_dia": audit.min_simbolos_en_dia,
        "max_simbolos_en_dia": audit.max_simbolos_en_dia,
        "dataset_apto": dataset_apto,
        "motivos_rechazo": motivos,
        "simbolos": [
            {
                "symbol": c.symbol,
                "n_eventos": c.n_eventos,
                "n_dias_con_evento": c.n_dias_con_evento,
                "fraccion_cobertura_diaria": c.fraccion_cobertura_diaria,
                "duplicados": c.duplicados,
                "gaps_mayores_24h": c.gaps_mayores_24h,
                "max_gap_horas": c.max_gap_horas,
                "intervalos_horas": dict(c.intervalos_horas),
                "apto": c.apto,
            }
            for c in audit.simbolos
        ],
        "anios": [
            {
                "year": a.year,
                "dias": a.dias,
                "dias_cross_section_completa": a.dias_cross_section_completa,
                "fraccion_cross_section_completa": a.fraccion_cross_section_completa,
                "apto": a.apto,
            }
            for a in audit.anios
        ],
        "descargas_fallidas": [
            {
                "symbol": r.symbol,
                "n_requests": r.n_requests,
                "status_http": r.status_http,
                "error": r.error,
            }
            for r in sorted(resultados, key=lambda x: x.symbol)
            if not r.completa
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(
        json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[04B-v18] {reporte['status']}: downloads={descargas_completas}/{len(UNIVERSO_FUNDING_V18)} "
        f"requests={n_requests} events={reporte['n_eventos_total']} "
        f"symbols_aptos={audit.n_simbolos_aptos} cross={audit.fraccion_cross_section_completa}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
