#!/usr/bin/env python3
"""Ejecuta BOT 2.0-04B-v9 sobre desarrollo 2022-2025.

Salida: artifacts/factores-v9-desarrollo-2025.json
No usa 2026 y no entrena ningún modelo.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.diagnostico_factores_v9 import diagnosticar_factores_v9
from backend.economia.edge_selector_v8 import construir_observaciones_selector_v8
from backend.economia.experimento_selector_v8 import FIN_2025_MS
from backend.economia.historico_binance import descargar_klines_data_api, descargar_klines_rango
from backend.economia.protocolo_edge_v2 import (
    DATASET_DESDE_MS,
    INTERVALO_HORAS,
    INTERVALO_KLINE,
    TEST_DESDE_MS,
    UNIVERSO_VALIDACION_V2,
    VALIDACION_DESDE_MS,
)
from backend.economia.protocolo_edge_v4 import MIN_SYMBOLS_DATASET_VALIDACION_V4
from backend.economia.protocolo_edge_v9 import (
    DESARROLLO_2026_ABIERTO_V9,
    FACTORES_V9,
    HORIZONTE_HORAS_V9,
    HURDLE_ECONOMICO_BPS_V9,
    TEST_MAY_JUL_ABIERTO_V9,
)

SALIDA = RAIZ_PROYECTO / "artifacts" / "factores-v9-desarrollo-2025.json"


def _jsonable(valor: Any):
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, tuple):
        return [_jsonable(v) for v in valor]
    if isinstance(valor, list):
        return [_jsonable(v) for v in valor]
    if isinstance(valor, dict):
        return {str(k): _jsonable(v) for k, v in valor.items()}
    return valor


def _descargar_series(binance, *, start_ms: int, end_ms: int):
    series = {}
    manifest = []
    for symbol in UNIVERSO_VALIDACION_V2:
        primaria = descargar_klines_rango(
            binance, symbol, interval=INTERVALO_KLINE,
            start_ms=start_ms, end_ms=end_ms, limit=1000,
        )
        descarga = primaria
        error_primaria = None
        if not primaria.completa:
            error_primaria = primaria.error
            descarga = descargar_klines_data_api(
                symbol, interval=INTERVALO_KLINE,
                start_ms=start_ms, end_ms=end_ms, limit=1000,
            )
        if descarga.completa:
            series[symbol] = descarga.velas
        manifest.append({
            "symbol": symbol,
            "completa": descarga.completa,
            "fuente": descarga.fuente,
            "error": descarga.error,
            "error_fuente_primaria": error_primaria,
            "n_requests": primaria.n_requests + descarga.n_requests,
            "n_velas": len(descarga.velas),
        })
    return series, manifest


def _compactar(r):
    return {
        "factor": r.factor,
        "orientacion": r.orientacion,
        "n_timestamps": r.n_timestamps,
        "ic_spearman_medio": r.ic_spearman_medio,
        "fraccion_ic_signo_correcto": r.fraccion_ic_signo_correcto,
        "spread_alto_menos_bajo_medio_bps": r.spread_alto_menos_bajo_medio_bps,
        "spread_orientado_medio_bps": r.spread_orientado_medio_bps,
        "fraccion_timestamps_spread_signo_correcto": r.fraccion_timestamps_spread_signo_correcto,
        "n_meses_spread": r.n_meses_spread,
        "meses_spread_signo_correcto": r.meses_spread_signo_correcto,
        "n_folds_spread": r.n_folds_spread,
        "folds_spread_signo_correcto": r.folds_spread_signo_correcto,
        "n_senales_top1": r.n_senales_top1,
        "retorno_top1_neto_medio_bps": r.retorno_top1_neto_medio_bps,
        "fraccion_top1_neto_positivo": r.fraccion_top1_neto_positivo,
        "n_meses_top1": r.n_meses_top1,
        "meses_top1_netos_positivos": r.meses_top1_netos_positivos,
        "n_folds_top1": r.n_folds_top1,
        "folds_top1_netos_positivos": r.folds_top1_netos_positivos,
        "spread_apto": r.spread_apto,
        "top1_apto": r.top1_apto,
        "apta": r.apta,
        "motivos_rechazo": list(r.motivos_rechazo),
    }


def main() -> int:
    end_ms = FIN_2025_MS - 1
    assert not DESARROLLO_2026_ABIERTO_V9
    assert not TEST_MAY_JUL_ABIERTO_V9
    assert end_ms < VALIDACION_DESDE_MS
    assert end_ms < TEST_DESDE_MS

    print(
        f"[04B-v9] factores={FACTORES_V9}, horizonte={HORIZONTE_HORAS_V9}h, "
        f"hurdle={HURDLE_ECONOMICO_BPS_V9}bps, "
        "DESARROLLO_2026_OPEN=False, TEST_MAY_JUL_OPEN=False"
    )
    binance = BinanceConnector()
    series, manifest = _descargar_series(binance, start_ms=DATASET_DESDE_MS, end_ms=end_ms)
    observaciones = construir_observaciones_selector_v8(
        series,
        intervalo_horas=INTERVALO_HORAS,
        horizontes_horas=(HORIZONTE_HORAS_V9,),
    )
    if any(o.estado.timestamp_ms >= VALIDACION_DESDE_MS for o in observaciones):
        raise RuntimeError("violacion: observacion 2026 entro a v9")

    symbols_utiles = sorted({o.estado.symbol for o in observaciones})
    base = {
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "intervalo": INTERVALO_KLINE,
        "horizonte_horas": HORIZONTE_HORAS_V9,
        "hurdle_economico_bps": HURDLE_ECONOMICO_BPS_V9,
        "factores": list(FACTORES_V9),
        "n_symbols_utiles": len(symbols_utiles),
        "symbols_utiles": symbols_utiles,
        "n_observaciones": len(observaciones),
        "manifest": manifest,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    if len(symbols_utiles) < MIN_SYMBOLS_DATASET_VALIDACION_V4:
        base.update({"status": "DATASET_INSUFICIENTE_V9", "resultados": [], "clasificaciones": []})
        SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
        return 0

    d = diagnosticar_factores_v9(observaciones)
    status = "FACTORES_PROMETEDORES_V9" if d.factores_prometedores else "SIN_FACTORES_PROMETEDORES_V9"
    base.update({
        "status": status,
        "factores_prometedores": list(d.factores_prometedores),
        "clasificaciones": [
            {"factor": c.factor, "clase": c.clase, "orientacion_apta": c.orientacion_apta}
            for c in d.clasificaciones
        ],
        "resultados": [_compactar(r) for r in d.resultados],
    })
    SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[04B-v9] {status}: utiles={len(symbols_utiles)}, prometedores={d.factores_prometedores}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
