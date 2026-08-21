#!/usr/bin/env python3
"""BOT 2.0-04B-v23a: auditoría acotada de contenido AggTrades, sin retornos."""
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

from backend.economia.auditoria_contenido_aggtrades_v23a import auditar_contenido_aggtrades_v23a
from backend.economia.contenido_aggtrades_v23a import (
    descargar_resumir_v23a,
    seleccionar_muestra_diaria_v23a,
)
from backend.economia.protocolo_aggtrades_v23a import (
    DESARROLLO_2026_ABIERTO_V23A,
    MAX_BYTES_TOTAL_MUESTRA_V23A,
    MERCADOS_V23A,
    N_MUESTRAS_OBJETIVO_V23A,
    PERIODOS_MUESTRA_V23A,
    PERMITE_IMPUTACION_V23A,
    SIMBOLOS_MUESTRA_V23A,
    TEST_MAY_JUL_ABIERTO_V23A,
    USA_GPT_V23A,
    USA_LABELS_V23A,
    USA_RETORNOS_V23A,
)

SALIDA = RAIZ / "artifacts" / "aggtrades-content-audit-v23a-2022-2025.json"


def _gib(n: int) -> str:
    return f"{n / (1024 ** 3):.3f}"


def main() -> int:
    assert DESARROLLO_2026_ABIERTO_V23A is False
    assert TEST_MAY_JUL_ABIERTO_V23A is False
    assert PERMITE_IMPUTACION_V23A is False
    assert USA_RETORNOS_V23A is False
    assert USA_LABELS_V23A is False
    assert USA_GPT_V23A is False

    tareas = [
        (mercado, symbol, year, month)
        for mercado in MERCADOS_V23A
        for year, month in PERIODOS_MUESTRA_V23A
        for symbol in SIMBOLOS_MUESTRA_V23A
    ]
    assert len(tareas) == N_MUESTRAS_OBJETIVO_V23A
    print(
        f"[04B-v23a] start samples={len(tareas)} symbols={','.join(SIMBOLOS_MUESTRA_V23A)} "
        f"returns=False 2026_OPEN=False"
    )

    selecciones = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {
            pool.submit(seleccionar_muestra_diaria_v23a, mercado, symbol, year, month): tarea
            for tarea in tareas
            for mercado, symbol, year, month in [tarea]
        }
        for fut in as_completed(futs):
            selecciones.append(fut.result())
    selecciones.sort(key=lambda s: (s.mercado, s.year, s.month, s.symbol))

    bytes_objetivo = sum(
        s.archivo.size for s in selecciones if s.completa and s.archivo is not None
    )
    print(
        f"[04B-v23a] selected={sum(s.completa for s in selecciones)}/{len(selecciones)} "
        f"target_size={_gib(bytes_objetivo)}GiB cap={_gib(MAX_BYTES_TOTAL_MUESTRA_V23A)}GiB"
    )

    resumenes = []
    if bytes_objetivo <= MAX_BYTES_TOTAL_MUESTRA_V23A:
        archivos = [s.archivo for s in selecciones if s.completa and s.archivo is not None]
        # Máximo 2 descargas/parsers concurrentes para acotar RAM al procesar CSV grandes.
        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = {pool.submit(descargar_resumir_v23a, a): a for a in archivos}
            for fut in as_completed(futs):
                resumenes.append(fut.result())
    resumenes.sort(key=lambda r: (r.mercado, r.fecha, r.symbol))

    audit = auditar_contenido_aggtrades_v23a(selecciones, resumenes)
    status = (
        "DATASET_AGGTRADES_CONTENIDO_APTO_V23A"
        if audit.dataset_apto
        else "DATASET_AGGTRADES_CONTENIDO_NO_APTO_V23A"
    )
    reporte = {
        "status": status,
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "usa_retornos": False,
        "usa_labels": False,
        "imputacion_permitida": False,
        "seleccion": "ZIP diario mediano por tamaño dentro de estratos predeclarados",
        "simbolos_muestra": SIMBOLOS_MUESTRA_V23A,
        "periodos_muestra": PERIODOS_MUESTRA_V23A,
        "audit": asdict(audit),
        "selecciones": [asdict(s) for s in selecciones],
        "muestras": [asdict(r) for r in resumenes],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(
        f"[04B-v23a] {status}: valid={audit.n_muestras_validas}/{audit.n_objetivo} "
        f"fraction={audit.fraccion_muestras_validas} rows={audit.filas_validas} "
        f"headers={audit.headers_detectados}"
    )
    print(
        f"[04B-v23a] units spot_ms={audit.muestras_spot_ms} spot_us={audit.muestras_spot_us} "
        f"futures_ms={audit.muestras_futures_ms}"
    )
    print(
        f"[04B-v23a] aggressor_counts buy={audit.taker_buy_trades} sell={audit.taker_sell_trades} "
        f"reject_reasons={','.join(audit.motivos_rechazo) or 'ninguno'}"
    )
    for e in audit.estratos:
        print(
            f"[04B-v23a] stratum={e.mercado}:{e.year}-{e.month:02d} "
            f"valid={e.n_validas}/{e.n_objetivo} apt={e.apto}"
        )
    for s in selecciones:
        if not s.completa:
            print(f"[04B-v23a] selection_error={s.mercado}:{s.symbol}:{s.year}-{s.month:02d} {s.error}")
    for r in resumenes:
        if not r.completa:
            print(f"[04B-v23a] content_error={r.mercado}:{r.symbol}:{r.fecha} {r.error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
