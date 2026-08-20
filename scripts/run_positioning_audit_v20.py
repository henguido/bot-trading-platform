#!/usr/bin/env python3
"""BOT 2.0-04B-v20: audita archivo histórico de posicionamiento USD-M."""
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
    DESARROLLO_2026_ABIERTO_V20,
    DESDE_V20,
    HASTA_EXCLUSIVO_V20,
    TEST_MAY_JUL_ABIERTO_V20,
    UNIVERSO_POSICIONAMIENTO_V20,
)

SALIDA = RAIZ / "artifacts" / "positioning-data-audit-v20-2022-2025.json"
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
    assert DESARROLLO_2026_ABIERTO_V20 is False
    assert TEST_MAY_JUL_ABIERTO_V20 is False
    assert DESDE_V20.year == 2022
    assert HASTA_EXCLUSIVO_V20.year == 2026 and HASTA_EXCLUSIVO_V20.month == 1

    print(
        f"[04B-v20] audit positioning symbols={len(UNIVERSO_POSICIONAMIENTO_V20)} "
        "archive=S3 sample=1-dia/symbol/mes 2026_OPEN=False"
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

    audit = auditar_posicionamiento_v20(listados, tuple(resultados_muestra))
    reporte = {
        "status": "DATASET_POSICIONAMIENTO_APTO_V20" if audit.dataset_apto else "DATASET_POSICIONAMIENTO_NO_APTO_V20",
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "fuente_listado": "s3://data.binance.vision/data/futures/um/daily/metrics/",
        "fuente_contenido": "https://data.binance.vision/data/futures/um/daily/metrics/",
        "metodo": "listado S3 completo + un archivo mediano por symbol/mes; sin retornos",
        "desde": DESDE_V20.isoformat(),
        "hasta_exclusivo": HASTA_EXCLUSIVO_V20.isoformat(),
        "n_simbolos": len(UNIVERSO_POSICIONAMIENTO_V20),
        "n_listados_completos": sum(r.completa for r in resultados_listado),
        "n_list_requests": sum(r.n_requests for r in resultados_listado),
        "n_archivos_listados": sum(len(r.archivos) for r in resultados_listado if r.completa),
        "n_simbolos_aptos": audit.n_simbolos_aptos,
        "dias_cross_section_completa": audit.dias_cross_section_completa,
        "fraccion_cross_section_completa": audit.fraccion_cross_section_completa,
        "min_simbolos_en_dia": audit.min_simbolos_en_dia,
        "max_simbolos_en_dia": audit.max_simbolos_en_dia,
        "n_muestras_objetivo": audit.n_muestras_objetivo,
        "n_muestras_solicitadas": len(muestras_archivo),
        "n_muestras_parseadas": audit.n_muestras_parseadas,
        "fraccion_muestras_parseadas": audit.fraccion_muestras_parseadas,
        "n_filas_muestra": audit.n_filas_muestra,
        "duplicados_muestra": audit.duplicados_muestra,
        "no_ascendentes_muestra": audit.no_ascendentes_muestra,
        "fraccion_cadencia_5m": audit.fraccion_cadencia_5m,
        "core_oi_apto": audit.core_oi_apto,
        "campos_ratios_usables": audit.campos_ratios_usables,
        "dataset_apto": audit.dataset_apto,
        "motivos_rechazo": audit.motivos_rechazo,
        "campos": [asdict(c) for c in audit.campos],
        "simbolos": [asdict(c) for c in audit.simbolos],
        "anios": [asdict(a) for a in audit.anios],
        "listados_fallidos": [
            {"symbol": r.symbol, "n_requests": r.n_requests, "error": r.error}
            for r in sorted(resultados_listado, key=lambda x: x.symbol)
            if not r.completa
        ],
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
        f"[04B-v20] {reporte['status']}: listings={reporte['n_listados_completos']}/{len(UNIVERSO_POSICIONAMIENTO_V20)} "
        f"archive_files={reporte['n_archivos_listados']} samples={audit.n_muestras_parseadas}/{audit.n_muestras_objetivo} "
        f"rows={audit.n_filas_muestra} cadence5m={audit.fraccion_cadencia_5m} "
        f"core_oi={audit.core_oi_apto} ratios={','.join(audit.campos_ratios_usables) or 'ninguno'}"
    )
    print(
        f"[04B-v20] reject_reasons={','.join(audit.motivos_rechazo) or 'ninguno'} "
        f"duplicates={audit.duplicados_muestra} nonascending={audit.no_ascendentes_muestra} "
        f"cross={audit.fraccion_cross_section_completa} symbols_apt={audit.n_simbolos_aptos}"
    )
    for a in audit.anios:
        print(
            f"[04B-v20] year={a.year} cross_days={a.dias_cross_section_completa}/{a.dias} "
            f"cross={a.fraccion_cross_section_completa} apt={a.apto}"
        )
    for s in audit.simbolos:
        if (not s.apto) or s.meses_con_archivo < 48 or s.n_dias_unicos < s.dias_esperados:
            print(
                f"[04B-v20] symbol={s.symbol} files={s.n_archivos} days={s.n_dias_unicos}/{s.dias_esperados} "
                f"coverage={s.fraccion_cobertura} months={s.meses_con_archivo} "
                f"dup_dates={s.fechas_duplicadas} zero_size={s.archivos_tamano_cero} apt={s.apto}"
            )
    for c in audit.campos:
        print(
            f"[04B-v20] field={c.nombre} valid={c.fraccion_valida} "
            f"positive={c.fraccion_positiva} usable={c.usable}"
        )
    fallidas = [r for r in sorted(resultados_muestra, key=lambda x: (x.symbol, x.fecha)) if not r.completa]
    for r in fallidas:
        print(
            f"[04B-v20] sample_failed symbol={r.symbol} date={r.fecha.isoformat()} "
            f"error={r.error}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
