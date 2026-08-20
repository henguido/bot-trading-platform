#!/usr/bin/env python3
"""BOT 2.0-04B-v20.1: reaudita metrics con orden canónico por create_time."""
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

from backend.economia.auditoria_posicionamiento_v20 import auditar_posicionamiento_v20
from backend.economia.historico_posicionamiento_v20 import (
    descargar_resumir_archivo_v20,
    listar_metricas_v20,
    seleccionar_muestras_mensuales_v20,
)
from backend.economia.protocolo_posicionamiento_v20 import (
    DESDE_V20,
    HASTA_EXCLUSIVO_V20,
    UNIVERSO_POSICIONAMIENTO_V20,
)
from backend.economia.protocolo_posicionamiento_v20a import (
    DESARROLLO_2026_ABIERTO_V20A,
    DUPLICADOS_FAIL_CLOSED_V20A,
    FECHA_FUERA_ARCHIVO_FAIL_CLOSED_V20A,
    IMPUTACION_PERMITIDA_V20A,
    ORDEN_CANONICO_CREATE_TIME_V20A,
    TEST_MAY_JUL_ABIERTO_V20A,
)

SALIDA = RAIZ / "artifacts" / "positioning-data-audit-v20a-2022-2025.json"
MAX_WORKERS_LISTADO = 8
MAX_WORKERS_MUESTRAS = 12


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
    assert DESARROLLO_2026_ABIERTO_V20A is False
    assert TEST_MAY_JUL_ABIERTO_V20A is False
    assert ORDEN_CANONICO_CREATE_TIME_V20A is True
    assert DUPLICADOS_FAIL_CLOSED_V20A is True
    assert FECHA_FUERA_ARCHIVO_FAIL_CLOSED_V20A is True
    assert IMPUTACION_PERMITIDA_V20A is False
    assert DESDE_V20.year == 2022
    assert HASTA_EXCLUSIVO_V20.year == 2026 and HASTA_EXCLUSIVO_V20.month == 1

    print(
        f"[04B-v20.1] audit positioning symbols={len(UNIVERSO_POSICIONAMIENTO_V20)} "
        "canonical=create_time sample=1-dia/symbol/mes 2026_OPEN=False"
    )

    resultados_listado = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_LISTADO) as pool:
        futuros = {
            pool.submit(listar_metricas_v20, symbol): symbol
            for symbol in UNIVERSO_POSICIONAMIENTO_V20
        }
        for fut in as_completed(futuros):
            resultados_listado.append(fut.result())
    listados = {r.symbol: r for r in resultados_listado}

    muestras_archivo = []
    for symbol in UNIVERSO_POSICIONAMIENTO_V20:
        r = listados.get(symbol)
        if r is not None and r.completa:
            muestras_archivo.extend(seleccionar_muestras_mensuales_v20(r.archivos))

    resultados_muestra = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_MUESTRAS) as pool:
        futuros = {
            pool.submit(descargar_resumir_archivo_v20, archivo): archivo.key
            for archivo in muestras_archivo
        }
        for fut in as_completed(futuros):
            resultados_muestra.append(fut.result())

    audit = auditar_posicionamiento_v20(
        listados,
        tuple(resultados_muestra),
        rechazar_no_ascendentes=False,
    )
    reporte = {
        "status": "DATASET_POSICIONAMIENTO_APTO_V20A" if audit.dataset_apto else "DATASET_POSICIONAMIENTO_NO_APTO_V20A",
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "orden_canonico_create_time": True,
        "duplicados_fail_closed": True,
        "fecha_fuera_archivo_fail_closed": True,
        "imputacion_permitida": False,
        "fuente_listado": "s3://data.binance.vision/data/futures/um/daily/metrics/",
        "fuente_contenido": "https://data.binance.vision/data/futures/um/daily/metrics/",
        "metodo": "mismos datos/umbrales v20; orden físico normalizable por create_time; sin retornos",
        "desde": DESDE_V20.isoformat(),
        "hasta_exclusivo": HASTA_EXCLUSIVO_V20.isoformat(),
        "n_simbolos": len(UNIVERSO_POSICIONAMIENTO_V20),
        "n_listados_completos": sum(r.completa for r in resultados_listado),
        "n_list_requests": sum(r.n_requests for r in resultados_listado),
        "n_archivos_listados": sum(len(r.archivos) for r in resultados_listado if r.completa),
        "n_simbolos_aptos": audit.n_simbolos_aptos,
        "fraccion_cross_section_completa": audit.fraccion_cross_section_completa,
        "n_muestras_objetivo": audit.n_muestras_objetivo,
        "n_muestras_solicitadas": len(muestras_archivo),
        "n_muestras_parseadas": audit.n_muestras_parseadas,
        "fraccion_muestras_parseadas": audit.fraccion_muestras_parseadas,
        "n_filas_muestra": audit.n_filas_muestra,
        "duplicados_muestra": audit.duplicados_muestra,
        "no_ascendentes_observados": audit.no_ascendentes_muestra,
        "fraccion_cadencia_5m": audit.fraccion_cadencia_5m,
        "core_oi_apto": audit.core_oi_apto,
        "campos_ratios_usables": audit.campos_ratios_usables,
        "dataset_apto": audit.dataset_apto,
        "motivos_rechazo": audit.motivos_rechazo,
        "campos": [asdict(c) for c in audit.campos],
        "simbolos": [asdict(c) for c in audit.simbolos],
        "anios": [asdict(a) for a in audit.anios],
        "muestras_fallidas": [
            {"symbol": r.symbol, "fecha": r.fecha.isoformat(), "key": r.key, "error": r.error}
            for r in sorted(resultados_muestra, key=lambda x: (x.symbol, x.fecha))
            if not r.completa
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(
        json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print(
        f"[04B-v20.1] {reporte['status']}: listings={reporte['n_listados_completos']}/{len(UNIVERSO_POSICIONAMIENTO_V20)} "
        f"archive_files={reporte['n_archivos_listados']} samples={audit.n_muestras_parseadas}/{audit.n_muestras_objetivo} "
        f"rows={audit.n_filas_muestra} cadence5m={audit.fraccion_cadencia_5m} "
        f"reordered={audit.no_ascendentes_muestra} duplicates={audit.duplicados_muestra} "
        f"core_oi={audit.core_oi_apto} ratios={','.join(audit.campos_ratios_usables) or 'ninguno'}"
    )
    print(f"[04B-v20.1] reject_reasons={','.join(audit.motivos_rechazo) or 'ninguno'}")
    for c in audit.campos:
        print(
            f"[04B-v20.1] field={c.nombre} valid={c.fraccion_valida} "
            f"positive={c.fraccion_positiva} usable={c.usable}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
