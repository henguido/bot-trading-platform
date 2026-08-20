#!/usr/bin/env python3
"""Ejecuta validacion 04B-v4 sin abrir holdout final.

Salida: artifacts/edge-validation-v4-jan-apr-2026.json

Usa solo datos publicos Spot. No requiere secretos, no importa GPT, no toca
RiskEngine y no ejecuta ordenes.
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
from backend.economia.experimento_edge_v4 import evaluar_validacion_v4_predeclarada
from backend.economia.historico_binance import (
    descargar_klines_data_api,
    descargar_klines_rango,
)
from backend.economia.protocolo_edge_v4 import (
    COBERTURA_REGIMEN_TIMESTAMPS_MINIMA_V4,
    COBERTURA_TOTAL_TIMESTAMPS_SENAL_MINIMA_V4,
    DATASET_DESDE_MS,
    FOLDS_NETOS_POSITIVOS_MINIMOS_V4,
    HURDLE_EDGE_PREDICHO_BPS_V4,
    INTERVALO_HORAS,
    INTERVALO_KLINE,
    MIN_CONFIGS_REGIMEN_COST_AWARE_APTAS_V4,
    MIN_SYMBOLS_DATASET_VALIDACION_V4,
    REGIMEN_MERCADO_MINIMO_BPS_V4,
    SURVIVORSHIP_PENDIENTE_V4,
    TEST_DESDE_MS,
    UNIVERSO_FUENTE_V4,
    UNIVERSO_VALIDACION_V2,
    VALIDACION_HASTA_MS,
)

SALIDA = RAIZ_PROYECTO / "artifacts" / "edge-validation-v4-jan-apr-2026.json"


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


def _config_compacta(resultado):
    c = resultado.configuracion
    m = resultado.resultado_modelo
    r = resultado.resultado_regimen
    e = r.resultado_cost_aware
    return {
        "config": {
            "horizonte_horas": c.horizonte_horas,
            "rank_bins": c.rank_bins,
            "regimen_bins": c.regimen_bins,
            "min_muestras": c.min_muestras,
            "max_radio": c.max_radio,
            "regimen_minimo_bps": c.regimen_minimo_bps,
            "coste_total_bps": c.coste_total_bps,
            "margen_seguridad_bps": c.margen_seguridad_bps,
            "hurdle_predicho_bps": c.hurdle_predicho_bps,
            "max_senales_por_timestamp": c.max_senales_por_timestamp,
            "min_symbols_por_timestamp": c.min_symbols_por_timestamp,
            "fase_horas": c.fase_horas,
        },
        "supera_criterios_minimos": resultado.supera_criterios_minimos,
        "motivos_rechazo": list(resultado.motivos_rechazo),
        "modelo": {
            "n_folds_disponibles": m.n_folds_disponibles,
            "n_objetivo": m.n_objetivo,
            "n_estimadas": m.n_estimadas,
            "cobertura": m.cobertura,
            "uplift_cross_section_medio": m.uplift_cross_section_medio,
            "fraccion_timestamps_uplift_positivo": m.fraccion_timestamps_uplift_positivo,
            "n_meses_cross_section": m.n_meses_cross_section,
            "meses_uplift_positivo": m.meses_uplift_positivo,
        },
        "regimen": {
            "estado": r.estado,
            "motivo": r.motivo,
            "n_predicciones_entrada": r.n_predicciones_entrada,
            "n_predicciones_sin_regimen": r.n_predicciones_sin_regimen,
            "n_predicciones_regimen_aprobado": r.n_predicciones_regimen_aprobado,
            "n_timestamps_entrada": r.n_timestamps_entrada,
            "n_timestamps_sin_regimen": r.n_timestamps_sin_regimen,
            "n_timestamps_regimen_aprobado": r.n_timestamps_regimen_aprobado,
            "cobertura_regimen_timestamps": r.cobertura_regimen_timestamps,
            "cobertura_total_timestamps_senal": r.cobertura_total_timestamps_senal,
        },
        "cost_aware": {
            "estado": e.estado,
            "motivo": e.motivo,
            "n_timestamps_evaluables": e.n_timestamps_evaluables,
            "n_timestamps_senal": e.n_timestamps_senal,
            "n_senales": e.n_senales,
            "cobertura_timestamps_senal": e.cobertura_timestamps_senal,
            "retorno_bruto_senales_medio_bps": e.retorno_bruto_senales_medio_bps,
            "retorno_neto_senales_medio_bps": e.retorno_neto_senales_medio_bps,
            "retorno_neto_despues_margen_medio_bps": (
                e.retorno_neto_despues_margen_medio_bps
            ),
            "baseline_bruto_medio_bps": e.baseline_bruto_medio_bps,
            "uplift_bruto_medio_bps": e.uplift_bruto_medio_bps,
            "fraccion_timestamps_neto_despues_margen_positivo": (
                e.fraccion_timestamps_neto_despues_margen_positivo
            ),
            "fraccion_timestamps_uplift_positivo": e.fraccion_timestamps_uplift_positivo,
            "n_meses_con_senal": e.n_meses_con_senal,
            "meses_neto_despues_margen_positivo": (
                e.meses_neto_despues_margen_positivo
            ),
            "n_folds_con_senal": e.n_folds_con_senal,
            "folds_neto_despues_margen_positivo": (
                e.folds_neto_despues_margen_positivo
            ),
        },
    }


def main() -> int:
    end_ms = VALIDACION_HASTA_MS
    assert end_ms < TEST_DESDE_MS
    print(
        f"[04B-v4] Validacion regimen+cost-aware: "
        f"{len(UNIVERSO_VALIDACION_V2)} simbolos, intervalo={INTERVALO_KLINE}, "
        f"regimen_min={REGIMEN_MERCADO_MINIMO_BPS_V4} bps, "
        f"hurdle={HURDLE_EDGE_PREDICHO_BPS_V4} bps, TEST_MAY_JUL_OPEN=False"
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
        raise RuntimeError("violacion: observacion de holdout final entro a validacion v4")

    symbols_utiles = sorted({o.estado.symbol for o in observaciones})
    base = {
        "test_may_jul_open": False,
        "validacion_informada_por_v3": True,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "test_desde_ms": TEST_DESDE_MS,
        "intervalo": INTERVALO_KLINE,
        "universo": list(UNIVERSO_VALIDACION_V2),
        "universo_fuente": UNIVERSO_FUENTE_V4,
        "sesgo_supervivencia_pendiente": SURVIVORSHIP_PENDIENTE_V4,
        "min_symbols_dataset": MIN_SYMBOLS_DATASET_VALIDACION_V4,
        "min_configs_regimen_cost_aware_aptas": (
            MIN_CONFIGS_REGIMEN_COST_AWARE_APTAS_V4
        ),
        "folds_netos_positivos_minimos": FOLDS_NETOS_POSITIVOS_MINIMOS_V4,
        "regimen_mercado_minimo_bps": REGIMEN_MERCADO_MINIMO_BPS_V4,
        "cobertura_regimen_timestamps_minima": (
            COBERTURA_REGIMEN_TIMESTAMPS_MINIMA_V4
        ),
        "cobertura_total_timestamps_senal_minima": (
            COBERTURA_TOTAL_TIMESTAMPS_SENAL_MINIMA_V4
        ),
        "hurdle_edge_predicho_bps": HURDLE_EDGE_PREDICHO_BPS_V4,
        "n_symbols_utiles": len(symbols_utiles),
        "symbols_utiles": symbols_utiles,
        "n_observaciones_relativas": len(observaciones),
        "manifest": manifest,
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    if len(symbols_utiles) < MIN_SYMBOLS_DATASET_VALIDACION_V4:
        base.update({
            "status": "DATASET_INSUFICIENTE_V4",
            "n_configuraciones": 0,
            "n_superan_minimos": 0,
            "familia_regimen_cost_aware_robusta": False,
            "configuracion_preferida_no_performance": None,
            "motivos_rechazo_conteo": {},
            "resultados": [],
        })
        SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"[04B-v4] DATASET_INSUFICIENTE: utiles={len(symbols_utiles)}/"
            f"{len(UNIVERSO_VALIDACION_V2)}; no se evalua modelo."
        )
        return 0

    validacion = evaluar_validacion_v4_predeclarada(observaciones)
    compactos = [_config_compacta(x) for x in validacion.resultados]
    conteo_motivos = Counter(
        motivo
        for x in validacion.resultados
        for motivo in x.motivos_rechazo
    )
    if validacion.familia_regimen_cost_aware_robusta:
        status = "FAMILIA_REGIMEN_COST_AWARE_ROBUSTA_V4"
    elif validacion.n_superan_minimos > 0:
        status = "APTAS_AISLADAS_REGIMEN_COST_AWARE_V4"
    else:
        status = "SIN_CONFIGURACIONES_REGIMEN_COST_AWARE_V4"

    preferida = validacion.configuracion_preferida_no_performance
    base.update({
        "status": status,
        "n_observaciones_pre_test": validacion.n_observaciones_pre_test,
        "n_configuraciones": validacion.n_configuraciones,
        "n_superan_minimos": validacion.n_superan_minimos,
        "familia_regimen_cost_aware_robusta": (
            validacion.familia_regimen_cost_aware_robusta
        ),
        "configuracion_preferida_no_performance": (
            None if preferida is None else {
                "horizonte_horas": preferida.horizonte_horas,
                "rank_bins": preferida.rank_bins,
                "regimen_bins": preferida.regimen_bins,
                "min_muestras": preferida.min_muestras,
                "max_radio": preferida.max_radio,
                "regimen_minimo_bps": preferida.regimen_minimo_bps,
                "coste_total_bps": preferida.coste_total_bps,
                "margen_seguridad_bps": preferida.margen_seguridad_bps,
                "hurdle_predicho_bps": preferida.hurdle_predicho_bps,
            }
        ),
        "motivos_rechazo_conteo": dict(sorted(conteo_motivos.items())),
        "resultados": compactos,
    })
    SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[04B-v4] {status}: utiles={len(symbols_utiles)}, "
        f"obs={validacion.n_observaciones_pre_test}, "
        f"configs={validacion.n_configuraciones}, "
        f"aptas={validacion.n_superan_minimos}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
