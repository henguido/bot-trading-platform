#!/usr/bin/env python3
"""Ejecuta validacion 04B-v2 enero-abril 2026 sin abrir holdout final.

Salida: artifacts/edge-validation-v2-jan-apr-2026.json

Este script usa solo datos publicos Spot. No requiere secretos, no importa GPT,
no toca RiskEngine y no ejecuta ordenes.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.edge_relativo_v2 import construir_observaciones_relativas_v2
from backend.economia.experimento_edge_v2 import evaluar_validacion_v2_predeclarada
from backend.economia.historico_binance import (
    descargar_klines_data_api,
    descargar_klines_rango,
)
from backend.economia.protocolo_edge_v2 import (
    DATASET_DESDE_MS,
    INTERVALO_HORAS,
    INTERVALO_KLINE,
    MIN_DIMENSIONES_VECINAS_ROBUSTAS,
    MIN_SYMBOLS_DATASET_VALIDACION,
    SURVIVORSHIP_PENDIENTE,
    TEST_DESDE_MS,
    UNIVERSO_FUENTE,
    UNIVERSO_VALIDACION_V2,
    VALIDACION_HASTA_MS,
)

SALIDA = RAIZ_PROYECTO / "artifacts" / "edge-validation-v2-jan-apr-2026.json"


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
            binance,
            symbol,
            interval=INTERVALO_KLINE,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=1000,
        )
        descarga = primaria
        error_primaria = None
        if not primaria.completa:
            error_primaria = primaria.error
            descarga = descargar_klines_data_api(
                symbol,
                interval=INTERVALO_KLINE,
                start_ms=start_ms,
                end_ms=end_ms,
                limit=1000,
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
            "inicio_open_ms": descarga.velas[0].open_time_ms if descarga.velas else None,
            "fin_open_ms": descarga.velas[-1].open_time_ms if descarga.velas else None,
        })
    return series, manifest


def _fold_compacto(fold_resultado):
    return {
        "valid_desde_ms": fold_resultado.fold.valid_desde_ms,
        "valid_hasta_ms": fold_resultado.fold.valid_hasta_ms,
        "estado": fold_resultado.estado,
        "n_train_crudo": fold_resultado.n_train_crudo,
        "n_train_no_solapado": fold_resultado.n_train_no_solapado,
        "n_validacion_cruda": fold_resultado.n_validacion_cruda,
        "n_validacion_no_solapada": fold_resultado.n_validacion_no_solapada,
        "n_descartadas_embargo": fold_resultado.n_descartadas_embargo,
        "n_predicciones": len(fold_resultado.predicciones),
        "motivo": fold_resultado.motivo,
    }


def _config_compacta(resultado):
    c = resultado.configuracion
    r = resultado.resultado
    return {
        "config": {
            "horizonte_horas": c.horizonte_horas,
            "rank_bins": c.rank_bins,
            "regimen_bins": c.regimen_bins,
            "min_muestras": c.min_muestras,
            "max_radio": c.max_radio,
            "min_symbols": c.min_symbols,
            "min_timestamps": c.min_timestamps,
            "min_symbols_por_timestamp": c.min_symbols_por_timestamp,
            "fase_horas": c.fase_horas,
        },
        "supera_criterios_minimos": resultado.supera_criterios_minimos,
        "robusta_grid": resultado.robusta_grid,
        "dimensiones_vecinas_robustas": list(resultado.dimensiones_vecinas_robustas),
        "motivos_rechazo": list(resultado.motivos_rechazo),
        "folds_cross_section_positivos": resultado.folds_cross_section_positivos,
        "n_folds_disponibles": r.n_folds_disponibles,
        "n_objetivo": r.n_objetivo,
        "n_estimadas": r.n_estimadas,
        "cobertura": r.cobertura,
        "mae_prediccion": r.mae_prediccion,
        "exactitud_direccional": r.exactitud_direccional,
        "uplift_cross_section_medio": r.uplift_cross_section_medio,
        "fraccion_timestamps_uplift_positivo": r.fraccion_timestamps_uplift_positivo,
        "n_meses_cross_section": r.n_meses_cross_section,
        "meses_uplift_positivo": r.meses_uplift_positivo,
        "uplift_mensual_min": r.uplift_mensual_min,
        "uplift_mensual_p25": r.uplift_mensual_p25,
        "uplift_mensual_p50": r.uplift_mensual_p50,
        "folds": [_fold_compacto(f) for f in r.folds],
    }


def main() -> int:
    end_ms = VALIDACION_HASTA_MS
    assert end_ms < TEST_DESDE_MS
    print(
        f"[04B-v2] Validacion relativa: {len(UNIVERSO_VALIDACION_V2)} simbolos, "
        f"intervalo={INTERVALO_KLINE}, TEST_MAY_JUL_OPEN=False"
    )

    binance = BinanceConnector()
    series, manifest = _descargar_series(
        binance,
        start_ms=DATASET_DESDE_MS,
        end_ms=end_ms,
    )
    observaciones = construir_observaciones_relativas_v2(
        series,
        intervalo_horas=INTERVALO_HORAS,
    )
    if any(o.estado.timestamp_ms >= TEST_DESDE_MS for o in observaciones):
        raise RuntimeError("violacion: observacion de holdout final entro a validacion v2")

    symbols_utiles = sorted({o.estado.symbol for o in observaciones})
    base = {
        "test_may_jul_open": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "test_desde_ms": TEST_DESDE_MS,
        "intervalo": INTERVALO_KLINE,
        "universo": list(UNIVERSO_VALIDACION_V2),
        "universo_fuente": UNIVERSO_FUENTE,
        "sesgo_supervivencia_pendiente": SURVIVORSHIP_PENDIENTE,
        "min_symbols_dataset": MIN_SYMBOLS_DATASET_VALIDACION,
        "min_dimensiones_vecinas_robustas": MIN_DIMENSIONES_VECINAS_ROBUSTAS,
        "n_symbols_utiles": len(symbols_utiles),
        "symbols_utiles": symbols_utiles,
        "n_observaciones_relativas": len(observaciones),
        "manifest": manifest,
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    if len(symbols_utiles) < MIN_SYMBOLS_DATASET_VALIDACION:
        base.update({
            "status": "DATASET_INSUFICIENTE",
            "n_configuraciones": 0,
            "n_superan_minimos": 0,
            "n_robustas_grid": 0,
            "horizontes_robustos": [],
            "configuracion_preferida_no_performance": None,
            "motivos_rechazo_conteo": {},
            "resultados": [],
        })
        SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"[04B-v2] DATASET_INSUFICIENTE: utiles={len(symbols_utiles)}/"
            f"{len(UNIVERSO_VALIDACION_V2)}; no se evalua modelo."
        )
        return 0

    validacion = evaluar_validacion_v2_predeclarada(observaciones)
    compactos = [_config_compacta(x) for x in validacion.resultados]
    conteo_motivos = Counter(
        motivo
        for x in validacion.resultados
        for motivo in x.motivos_rechazo
    )
    if validacion.n_robustas_grid > 0:
        status = "FAMILIA_ROBUSTA_VALIDACION_V2"
    elif validacion.n_superan_minimos > 0:
        status = "APTAS_AISLADAS_SIN_ROBUSTEZ_GRID_V2"
    else:
        status = "SIN_CONFIGURACIONES_APTAS_VALIDACION_V2"

    preferida = validacion.configuracion_preferida_no_performance
    base.update({
        "status": status,
        "n_observaciones_pre_test": validacion.n_observaciones_pre_test,
        "n_configuraciones": validacion.n_configuraciones,
        "n_superan_minimos": validacion.n_superan_minimos,
        "n_robustas_grid": validacion.n_robustas_grid,
        "horizontes_robustos": list(validacion.horizontes_robustos),
        "configuracion_preferida_no_performance": (
            None if preferida is None else {
                "horizonte_horas": preferida.horizonte_horas,
                "rank_bins": preferida.rank_bins,
                "regimen_bins": preferida.regimen_bins,
                "min_muestras": preferida.min_muestras,
                "max_radio": preferida.max_radio,
            }
        ),
        "motivos_rechazo_conteo": dict(sorted(conteo_motivos.items())),
        "resultados": compactos,
    })
    SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[04B-v2] {status}: utiles={len(symbols_utiles)}, "
        f"obs={validacion.n_observaciones_pre_test}, "
        f"configs={validacion.n_configuraciones}, "
        f"aptas={validacion.n_superan_minimos}, robustas={validacion.n_robustas_grid}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
