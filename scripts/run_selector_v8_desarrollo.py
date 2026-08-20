#!/usr/bin/env python3
"""Ejecuta BOT 2.0-04B-v8 exclusivamente sobre desarrollo 2022-2025.

Salida: artifacts/selector-v8-desarrollo-2025.json

No usa 2026. Sin GPT, RiskEngine, ordenes, LIVE ni Render.
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
from backend.economia.edge_selector_v8 import construir_observaciones_selector_v8
from backend.economia.experimento_selector_v8 import (
    FIN_2025_MS,
    evaluar_selector_v8_desarrollo,
)
from backend.economia.historico_binance import (
    descargar_klines_data_api,
    descargar_klines_rango,
)
from backend.economia.protocolo_edge_v2 import (
    DATASET_DESDE_MS,
    INTERVALO_HORAS,
    INTERVALO_KLINE,
    TEST_DESDE_MS,
    UNIVERSO_VALIDACION_V2,
    VALIDACION_DESDE_MS,
)
from backend.economia.protocolo_edge_v4 import MIN_SYMBOLS_DATASET_VALIDACION_V4
from backend.economia.protocolo_edge_v8 import (
    DESARROLLO_2026_ABIERTO_V8,
    HORIZONTE_HORAS_V8,
    HURDLE_ECONOMICO_BPS_V8,
    PROBABILIDAD_SUPERAR_HURDLE_MIN_V8,
    TEST_MAY_JUL_ABIERTO_V8,
)

SALIDA = RAIZ_PROYECTO / "artifacts" / "selector-v8-desarrollo-2025.json"


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


def _config_dict(c):
    if c is None:
        return None
    return {
        "rank_bins": c.rank_bins,
        "regimen_bins": c.regimen_bins,
        "dispersion_bins": c.dispersion_bins,
        "min_muestras": c.min_muestras,
        "max_radio": c.max_radio,
    }


def _compactar(r):
    return {
        "config": _config_dict(r.configuracion),
        "n_timestamps_evaluables": r.n_timestamps_evaluables,
        "n_senales": r.n_senales,
        "retorno_neto_medio_bps": r.retorno_neto_medio_bps,
        "fraccion_senales_neto_positivo": r.fraccion_senales_neto_positivo,
        "n_meses_con_senal": r.n_meses_con_senal,
        "meses_netos_positivos": r.meses_netos_positivos,
        "n_folds_con_senal": r.n_folds_con_senal,
        "folds_netos_positivos": r.folds_netos_positivos,
        "supera_criterios": r.supera_criterios,
        "motivos_rechazo": list(r.motivos_rechazo),
        "robusta_grid": r.robusta_grid,
        "dimensiones_vecinas_robustas": list(r.dimensiones_vecinas_robustas),
    }


def main() -> int:
    end_ms = FIN_2025_MS - 1
    assert not DESARROLLO_2026_ABIERTO_V8
    assert not TEST_MAY_JUL_ABIERTO_V8
    assert end_ms < VALIDACION_DESDE_MS
    assert end_ms < TEST_DESDE_MS

    print(
        f"[04B-v8] desarrollo hasta 2025-12-31, horizonte={HORIZONTE_HORAS_V8}h, "
        f"hurdle={HURDLE_ECONOMICO_BPS_V8}bps, "
        f"prob_min={PROBABILIDAD_SUPERAR_HURDLE_MIN_V8}, "
        "DESARROLLO_2026_OPEN=False, TEST_MAY_JUL_OPEN=False"
    )

    binance = BinanceConnector()
    series, manifest = _descargar_series(
        binance,
        start_ms=DATASET_DESDE_MS,
        end_ms=end_ms,
    )
    observaciones = construir_observaciones_selector_v8(
        series,
        intervalo_horas=INTERVALO_HORAS,
        horizontes_horas=(HORIZONTE_HORAS_V8,),
    )
    if any(o.estado.timestamp_ms >= VALIDACION_DESDE_MS for o in observaciones):
        raise RuntimeError("violacion: observacion 2026 entro a v8")

    symbols_utiles = sorted({o.estado.symbol for o in observaciones})
    base = {
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "intervalo": INTERVALO_KLINE,
        "horizonte_horas": HORIZONTE_HORAS_V8,
        "hurdle_economico_bps": HURDLE_ECONOMICO_BPS_V8,
        "probabilidad_superar_hurdle_min": PROBABILIDAD_SUPERAR_HURDLE_MIN_V8,
        "n_symbols_utiles": len(symbols_utiles),
        "symbols_utiles": symbols_utiles,
        "n_observaciones_selector": len(observaciones),
        "manifest": manifest,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    if len(symbols_utiles) < MIN_SYMBOLS_DATASET_VALIDACION_V4:
        base.update({
            "status": "DATASET_INSUFICIENTE_V8",
            "n_configuraciones": 0,
            "n_superan_criterios": 0,
            "n_robustas": 0,
            "configuracion_preferida": None,
            "resultados": [],
        })
        SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
        return 0

    experimento = evaluar_selector_v8_desarrollo(observaciones)
    preferida = experimento.configuracion_preferida_no_performance
    if experimento.n_robustas > 0 and preferida is not None:
        status = "FAMILIA_SELECTOR_V8_APTA_DESARROLLO"
    elif experimento.n_superan_criterios > 0:
        status = "CONFIGURACIONES_V8_AISLADAS_NO_APTAS"
    else:
        status = "SELECTOR_V8_FALSADO_DESARROLLO"

    base.update({
        "status": status,
        "n_observaciones_desarrollo": experimento.n_observaciones_desarrollo,
        "n_configuraciones": experimento.n_configuraciones,
        "n_superan_criterios": experimento.n_superan_criterios,
        "n_robustas": experimento.n_robustas,
        "configuracion_preferida": _config_dict(preferida),
        "resultados": [_compactar(r) for r in experimento.resultados],
    })
    SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[04B-v8] {status}: utiles={len(symbols_utiles)}, "
        f"configs={experimento.n_configuraciones}, "
        f"pasan={experimento.n_superan_criterios}, robustas={experimento.n_robustas}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
