#!/usr/bin/env python3
"""BOT 2.0-04B-v10: diagnóstico offline exclusivo de desarrollo 2022-2025."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.diagnostico_factores_v10 import diagnosticar_factores_v10
from backend.economia.factores_v10 import construir_observaciones_factores_v10
from backend.economia.historico_binance import descargar_klines_data_api, descargar_klines_rango
from backend.economia.protocolo_edge_v2 import (
    DATASET_DESDE_MS, INTERVALO_KLINE, TEST_DESDE_MS,
    UNIVERSO_VALIDACION_V2, VALIDACION_DESDE_MS,
)
from backend.economia.protocolo_edge_v4 import MIN_SYMBOLS_DATASET_VALIDACION_V4
from backend.economia.protocolo_edge_v8 import FIN_2025_MS
from backend.economia.protocolo_edge_v10 import (
    DESARROLLO_2026_ABIERTO_V10, FACTORES_V10, HORIZONTE_HORAS_V10,
    HURDLE_ECONOMICO_BPS_V10, TEST_MAY_JUL_ABIERTO_V10,
)

SALIDA = RAIZ / "artifacts" / "factores-v10-desarrollo-2025.json"


def jsonable(x):
    if isinstance(x, Decimal):
        return str(x)
    if isinstance(x, (tuple, list)):
        return [jsonable(v) for v in x]
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    return x


def descargar_series():
    series, manifest = {}, []
    for symbol in UNIVERSO_VALIDACION_V2:
        primaria = descargar_klines_rango(
            BinanceConnector(), symbol, interval=INTERVALO_KLINE,
            start_ms=DATASET_DESDE_MS, end_ms=FIN_2025_MS - 1, limit=1000,
        )
        usada = primaria
        error_primaria = None
        if not primaria.completa:
            error_primaria = primaria.error
            usada = descargar_klines_data_api(
                symbol, interval=INTERVALO_KLINE,
                start_ms=DATASET_DESDE_MS, end_ms=FIN_2025_MS - 1, limit=1000,
            )
        if usada.completa:
            series[symbol] = usada.velas
        manifest.append({
            "symbol": symbol, "completa": usada.completa,
            "fuente": usada.fuente, "error": usada.error,
            "error_fuente_primaria": error_primaria,
            "n_velas": len(usada.velas),
            "n_requests": primaria.n_requests + usada.n_requests,
        })
    return series, manifest


def compactar(r):
    return {
        "factor": r.factor, "orientacion": r.orientacion,
        "n_timestamps_regimen": r.n_timestamps_regimen,
        "ic_spearman_medio": r.ic_spearman_medio,
        "fraccion_ic_signo_correcto": r.fraccion_ic_signo_correcto,
        "spread_alto_menos_bajo_medio_bps": r.spread_alto_menos_bajo_medio_bps,
        "spread_orientado_medio_bps": r.spread_orientado_medio_bps,
        "fraccion_timestamps_spread_signo_correcto": r.fraccion_timestamps_spread_signo_correcto,
        "meses_spread_signo_correcto": r.meses_spread_signo_correcto,
        "folds_spread_signo_correcto": r.folds_spread_signo_correcto,
        "n_senales_top1": r.n_senales_top1,
        "retorno_top1_neto_medio_bps": r.retorno_top1_neto_medio_bps,
        "fraccion_top1_neto_positivo": r.fraccion_top1_neto_positivo,
        "n_meses_top1": r.n_meses_top1,
        "meses_top1_netos_positivos": r.meses_top1_netos_positivos,
        "n_folds_top1": r.n_folds_top1,
        "folds_top1_netos_positivos": r.folds_top1_netos_positivos,
        "spread_apto": r.spread_apto, "top1_apto": r.top1_apto,
        "apta": r.apta, "motivos_rechazo": list(r.motivos_rechazo),
    }


def main() -> int:
    end_ms = FIN_2025_MS - 1
    assert DESARROLLO_2026_ABIERTO_V10 is False
    assert TEST_MAY_JUL_ABIERTO_V10 is False
    assert end_ms < VALIDACION_DESDE_MS and end_ms < TEST_DESDE_MS

    print(
        f"[04B-v10] horizonte={HORIZONTE_HORAS_V10}h hurdle={HURDLE_ECONOMICO_BPS_V10}bps "
        "regimen=NO_NEGATIVO 2026_OPEN=False"
    )
    series, manifest = descargar_series()
    observaciones = construir_observaciones_factores_v10(series)
    if any(o.estado.timestamp_ms >= VALIDACION_DESDE_MS for o in observaciones):
        raise RuntimeError("observacion 2026 detectada en v10")

    symbols = sorted({o.estado.symbol for o in observaciones})
    reporte = {
        "status": "PENDIENTE", "desarrollo_2026_open": False,
        "test_may_jul_open": False, "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms, "intervalo": INTERVALO_KLINE,
        "horizonte_horas": HORIZONTE_HORAS_V10,
        "hurdle_economico_bps": HURDLE_ECONOMICO_BPS_V10,
        "regimen": "MEDIANA_RETORNO_24H_MERCADO_GTE_0",
        "factores": list(FACTORES_V10), "n_symbols_utiles": len(symbols),
        "symbols_utiles": symbols, "n_observaciones": len(observaciones),
        "manifest": manifest,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    if len(symbols) < MIN_SYMBOLS_DATASET_VALIDACION_V4:
        reporte.update({
            "status": "DATASET_INSUFICIENTE_V10",
            "n_timestamps_regimen_no_negativo": 0,
            "factores_prometedores": [], "clasificaciones": [], "resultados": [],
        })
    else:
        d = diagnosticar_factores_v10(observaciones)
        estado = "FACTORES_PROMETEDORES_V10" if d.factores_prometedores else "SIN_FACTORES_PROMETEDORES_V10"
        reporte.update({
            "status": estado,
            "n_timestamps_regimen_no_negativo": d.n_timestamps_regimen_no_negativo,
            "factores_prometedores": list(d.factores_prometedores),
            "clasificaciones": [
                {"factor": c.factor, "clase": c.clase, "orientacion_apta": c.orientacion_apta}
                for c in d.clasificaciones
            ],
            "resultados": [compactar(r) for r in d.resultados],
        })
        print(
            f"[04B-v10] {estado}: utiles={len(symbols)} "
            f"timestamps_regimen={d.n_timestamps_regimen_no_negativo} "
            f"prometedores={d.factores_prometedores}"
        )
    SALIDA.write_text(json.dumps(jsonable(reporte), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
