#!/usr/bin/env python3
"""BOT 2.0-04B-v23: inventaría AggTrades Spot + USD-M, sin retornos."""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.economia.auditoria_aggtrades_v23 import auditar_aggtrades_v23
from backend.economia.historico_aggtrades_v23 import listar_aggtrades_v23
from backend.economia.protocolo_aggtrades_v23 import (
    DESARROLLO_2026_ABIERTO_V23,
    DESDE_V23,
    HASTA_EXCLUSIVO_V23,
    IMPUTACION_PERMITIDA_V23,
    MERCADOS_V23,
    TEST_MAY_JUL_ABIERTO_V23,
    UNIVERSO_AGGTRADES_V23,
    USA_RETORNOS_V23,
)

SALIDA = RAIZ / "artifacts" / "aggtrades-data-audit-v23-2022-2025.json"
MAX_WORKERS = 12


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


def _gib(n: int) -> str:
    return f"{n / (1024 ** 3):.3f}"


def main() -> int:
    assert DESARROLLO_2026_ABIERTO_V23 is False
    assert TEST_MAY_JUL_ABIERTO_V23 is False
    assert IMPUTACION_PERMITIDA_V23 is False
    assert USA_RETORNOS_V23 is False
    assert DESDE_V23.year == 2022
    assert HASTA_EXCLUSIVO_V23.year == 2026 and HASTA_EXCLUSIVO_V23.month == 1

    tareas = [
        (mercado, symbol)
        for mercado in MERCADOS_V23
        for symbol in UNIVERSO_AGGTRADES_V23
    ]
    print(
        f"[04B-v23] inventory AggTrades tasks={len(tareas)} "
        "period=2022-2025 returns=False 2026_OPEN=False"
    )

    resultados = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {
            pool.submit(listar_aggtrades_v23, mercado, symbol): (mercado, symbol)
            for mercado, symbol in tareas
        }
        for fut in as_completed(futuros):
            resultados.append(fut.result())

    listados = {(r.mercado, r.symbol): r for r in resultados}
    audit = auditar_aggtrades_v23(listados)

    reporte = {
        "status": (
            "DATASET_AGGTRADES_INVENTARIO_APTO_V23"
            if audit.dataset_apto
            else "DATASET_AGGTRADES_INVENTARIO_NO_APTO_V23"
        ),
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "usa_retornos": False,
        "imputacion_permitida": False,
        "metodo": (
            "inventario S3 completo de ZIP mensuales Spot y USD-M Futures; "
            "sin descargar contenido y sin retornos"
        ),
        "desde": DESDE_V23.isoformat(),
        "hasta_exclusivo": HASTA_EXCLUSIVO_V23.isoformat(),
        "mercados": MERCADOS_V23,
        "n_simbolos": len(UNIVERSO_AGGTRADES_V23),
        "n_listados_completos": audit.n_listados_completos,
        "n_requests": sum(r.n_requests for r in resultados),
        "n_archivos_listados": sum(len(r.archivos) for r in resultados if r.completa),
        "n_simbolos_pareados_aptos": audit.n_simbolos_pareados_aptos,
        "meses_cross_section_pareada": audit.meses_cross_section_pareada,
        "fraccion_cross_section_pareada": audit.fraccion_cross_section_pareada,
        "min_simbolos_pareados_en_mes": audit.min_simbolos_pareados_en_mes,
        "max_simbolos_pareados_en_mes": audit.max_simbolos_pareados_en_mes,
        "bytes_spot": audit.bytes_spot,
        "bytes_futures_um": audit.bytes_futures_um,
        "bytes_total": audit.bytes_total,
        "gib_spot": _gib(audit.bytes_spot),
        "gib_futures_um": _gib(audit.bytes_futures_um),
        "gib_total": _gib(audit.bytes_total),
        "dataset_apto": audit.dataset_apto,
        "motivos_rechazo": audit.motivos_rechazo,
        "symbol_market": [asdict(x) for x in audit.symbol_market],
        "simbolos_pareados": [asdict(x) for x in audit.simbolos_pareados],
        "anios": [asdict(x) for x in audit.anios],
        "listados_fallidos": [
            {
                "mercado": r.mercado,
                "symbol": r.symbol,
                "n_requests": r.n_requests,
                "error": r.error,
            }
            for r in sorted(resultados, key=lambda x: (x.mercado, x.symbol))
            if not r.completa
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(
        json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print(
        f"[04B-v23] {reporte['status']}: "
        f"listings={audit.n_listados_completos}/{len(tareas)} "
        f"files={reporte['n_archivos_listados']} "
        f"paired_symbols={audit.n_simbolos_pareados_aptos}/{len(UNIVERSO_AGGTRADES_V23)} "
        f"cross={audit.fraccion_cross_section_pareada}"
    )
    print(
        f"[04B-v23] archive_size "
        f"spot={reporte['gib_spot']}GiB "
        f"futures_um={reporte['gib_futures_um']}GiB "
        f"total={reporte['gib_total']}GiB"
    )
    print(
        f"[04B-v23] reject_reasons="
        f"{','.join(audit.motivos_rechazo) or 'ninguno'}"
    )
    for a in audit.anios:
        print(
            f"[04B-v23] year={a.year} "
            f"cross_months={a.meses_cross_section_pareada}/{a.meses} "
            f"cross={a.fraccion_cross_section_pareada} apt={a.apto}"
        )
    for s in audit.simbolos_pareados:
        if not s.apto or s.meses_pareados < 48:
            print(
                f"[04B-v23] symbol={s.symbol} paired={s.meses_pareados}/48 "
                f"coverage={s.fraccion_cobertura_pareada} apt={s.apto}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
