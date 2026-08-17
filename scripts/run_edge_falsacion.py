#!/usr/bin/env python3
"""Ejecuta la Fase A predeclarada de Expected Edge sin abrir TEST 2026.

Salida: artifacts/edge-validation-2025.json

Este script es de investigacion OFFLINE. Usa solo datos publicos Spot, no
credenciales privadas, no GPT, no RiskEngine y no ejecuta ordenes.
"""
from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.experimento_edge import (
    evaluar_validacion_predeclarada,
    preparar_dataset_falsacion,
)
from backend.economia.protocolo_experimento_edge import (
    CORTE_TEST_MS,
    DATASET_DESDE_MS,
    INTERVALO_KLINE,
    MIN_SYMBOLS_DATASET_FALSACION,
    SURVIVORSHIP_PENDIENTE,
    UNIVERSO_FALSACION,
    UNIVERSO_FUENTE,
)

SALIDA = Path("artifacts/edge-validation-2025.json")


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
            "n_bins": c.n_bins,
            "min_muestras": c.min_muestras,
            "max_radio": c.max_radio,
            "min_symbols": c.min_symbols,
            "min_timestamps": c.min_timestamps,
            "fase_horas": c.fase_horas,
        },
        "supera_criterios_minimos": resultado.supera_criterios_minimos,
        "motivos_rechazo": list(resultado.motivos_rechazo),
        "folds_con_uplift_positivo": resultado.folds_con_uplift_positivo,
        "folds_cross_section_positivos": resultado.folds_cross_section_positivos,
        "n_folds_disponibles": r.n_folds_disponibles,
        "n_objetivo": r.n_objetivo,
        "n_estimadas": r.n_estimadas,
        "cobertura": r.cobertura,
        "retorno_real_objetivo_medio": r.retorno_real_objetivo_medio,
        "retorno_real_estimadas_medio": r.retorno_real_estimadas_medio,
        "sesgo_seleccion_cobertura": r.sesgo_seleccion_cobertura,
        "mae_prediccion": r.mae_prediccion,
        "exactitud_direccional": r.exactitud_direccional,
        "retorno_real_top25_predicho": r.retorno_real_top25_predicho,
        "uplift_top25_vs_estimadas": r.uplift_top25_vs_estimadas,
        "uplift_top25_vs_objetivo": r.uplift_top25_vs_objetivo,
        "radio_p95": r.radio_p95,
        "max_symbol_share_p95": r.max_symbol_share_p95,
        "max_timestamp_share_p95": r.max_timestamp_share_p95,
        "n_timestamps_cross_section": r.n_timestamps_cross_section,
        "uplift_cross_section_medio": r.uplift_cross_section_medio,
        "fraccion_timestamps_uplift_positivo": r.fraccion_timestamps_uplift_positivo,
        "n_meses_cross_section": r.n_meses_cross_section,
        "meses_uplift_positivo": r.meses_uplift_positivo,
        "uplift_mensual_min": r.uplift_mensual_min,
        "uplift_mensual_p25": r.uplift_mensual_p25,
        "uplift_mensual_p50": r.uplift_mensual_p50,
        "folds": [_fold_compacto(f) for f in r.folds],
    }


def _manifest(dataset):
    return [
        {
            "symbol": d.symbol,
            "completa": d.completa,
            "util_para_experimento": d.util_para_experimento,
            "error": d.error,
            "n_requests": d.n_requests,
            "n_velas": d.n_velas,
            "inicio_open_ms": d.inicio_open_ms,
            "fin_open_ms": d.fin_open_ms,
            "n_gaps": d.n_gaps,
            "horas_faltantes_estimadas": d.horas_faltantes_estimadas,
            "n_observaciones_4h": d.n_observaciones_4h,
        }
        for d in dataset.descargas
    ]


def main() -> int:
    # TEST se excluye tambien de la DESCARGA, no solo del evaluador.
    end_validacion_ms = CORTE_TEST_MS - 1
    assert end_validacion_ms < CORTE_TEST_MS

    print(
        f"[04B] Fase A: {len(UNIVERSO_FALSACION)} simbolos, "
        f"intervalo={INTERVALO_KLINE}, TEST_ABIERTO=False"
    )
    binance = BinanceConnector()
    dataset = preparar_dataset_falsacion(
        binance,
        symbols=UNIVERSO_FALSACION,
        start_ms=DATASET_DESDE_MS,
        end_ms=end_validacion_ms,
    )

    if any(o.estado.timestamp_ms >= CORTE_TEST_MS for o in dataset.observaciones_4h):
        raise RuntimeError("violacion: observacion de TEST entro al dataset de validacion")

    base = {
        "test_abierto": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_validacion_ms,
        "intervalo": INTERVALO_KLINE,
        "universo": list(UNIVERSO_FALSACION),
        "universo_fuente": UNIVERSO_FUENTE,
        "sesgo_supervivencia_pendiente": SURVIVORSHIP_PENDIENTE,
        "min_symbols_dataset": MIN_SYMBOLS_DATASET_FALSACION,
        "n_symbols_http_completos": dataset.n_symbols_completos,
        "n_symbols_utiles": dataset.n_symbols_utiles,
        "n_observaciones_4h": len(dataset.observaciones_4h),
        "manifest": _manifest(dataset),
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    if dataset.n_symbols_utiles < MIN_SYMBOLS_DATASET_FALSACION:
        base.update({
            "status": "DATASET_INSUFICIENTE",
            "n_configuraciones": 0,
            "n_superan_minimos": 0,
            "motivos_rechazo_conteo": {},
            "resultados": [],
        })
        SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"[04B] DATASET_INSUFICIENTE: utiles={dataset.n_symbols_utiles}/"
            f"{len(UNIVERSO_FALSACION)}; no se evalua el modelo."
        )
        return 0

    validacion = evaluar_validacion_predeclarada(dataset.observaciones_4h)
    compactos = [_config_compacta(x) for x in validacion.resultados]
    conteo_motivos = Counter(
        motivo
        for x in validacion.resultados
        for motivo in x.motivos_rechazo
    )
    status = (
        "CONFIGURACIONES_APTAS_VALIDACION"
        if validacion.n_superan_minimos > 0
        else "SIN_CONFIGURACIONES_APTAS_FASE_A"
    )
    base.update({
        "status": status,
        "n_observaciones_desarrollo": validacion.n_observaciones_desarrollo,
        "n_configuraciones": validacion.n_configuraciones,
        "n_superan_minimos": validacion.n_superan_minimos,
        "motivos_rechazo_conteo": dict(sorted(conteo_motivos.items())),
        # Orden canonico predeclarado; NO se ordena por performance.
        "resultados": compactos,
    })
    SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[04B] {status}: utiles={dataset.n_symbols_utiles}, "
        f"obs={validacion.n_observaciones_desarrollo}, "
        f"configs={validacion.n_configuraciones}, aptas={validacion.n_superan_minimos}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
