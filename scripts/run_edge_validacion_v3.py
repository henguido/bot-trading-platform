#!/usr/bin/env python3
"""Ejecuta validacion 04B-v3 cost-aware sin abrir holdout final.

Salida: artifacts/edge-validation-v3-jan-apr-2026.json

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
from backend.economia.experimento_edge_v3 import evaluar_validacion_v3_predeclarada
from backend.economia.historico_binance import (
    descargar_klines_data_api,
    descargar_klines_rango,
)
from backend.economia.protocolo_edge_v3 import (
    DATASET_DESDE_MS,
    FOLDS_NETOS_POSITIVOS_MINIMOS_V3,
    HURDLE_EDGE_PREDICHO_BPS,
    INTERVALO_HORAS,
    INTERVALO_KLINE,
    MIN_CONFIGS_COST_AWARE_APTAS_V3,
    MIN_SYMBOLS_DATASET_VALIDACION_V3,
    SURVIVORSHIP_PENDIENTE_V3,
    TEST_DESDE_MS,
    UNIVERSO_FUENTE_V3,
    UNIVERSO_VALIDACION_V2,
    VALIDACION_HASTA_MS,
)

SALIDA = RAIZ_PROYECTO / "artifacts" / "edge-validation-v3-jan-apr-2026.json"


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
    e = resultado.resultado_cost_aware
    return {
        "config": {
            "horizonte_horas": c.horizonte_horas,
            "rank_bins": c.rank_bins,
            "regimen_bins": c.regimen_bins,
            "min_muestras": c.min_muestras,
            "max_radio": c.max_radio,
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
        f"[04B-v3] Validacion cost-aware: {len(UNIVERSO_VALIDACION_V2)} simbolos, "
        f"intervalo={INTERVALO_KLINE}, hurdle={HURDLE_EDGE_PREDICHO_BPS} bps, "
        "TEST_MAY_JUL_OPEN=False"
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
        raise RuntimeError("violacion: observacion de holdout final entro a validacion v3")

    symbols_utiles = sorted({o.estado.symbol for o in observaciones})
    base = {
        "test_may_jul_open": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "test_desde_ms": TEST_DESDE_MS,
        "intervalo": INTERVALO_KLINE,
        "universo": list(UNIVERSO_VALIDACION_V2),
        "universo_fuente": UNIVERSO_FUENTE_V3,
        "sesgo_supervivencia_pendiente": SURVIVORSHIP_PENDIENTE_V3,
        "min_symbols_dataset": MIN_SYMBOLS_DATASET_VALIDACION_V3,
        "min_configs_cost_aware_aptas": MIN_CONFIGS_COST_AWARE_APTAS_V3,
        "folds_netos_positivos_minimos": FOLDS_NETOS_POSITIVOS_MINIMOS_V3,
        "hurdle_edge_predicho_bps": HURDLE_EDGE_PREDICHO_BPS,
        "n_symbols_utiles": len(symbols_utiles),
        "symbols_utiles": symbols_utiles,
        "n_observaciones_relativas": len(observaciones),
        "manifest": manifest,
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    if len(symbols_utiles) < MIN_SYMBOLS_DATASET_VALIDACION_V3:
        base.update({
            "status": "DATASET_INSUFICIENTE_V3",
            "n_configuraciones": 0,
            "n_superan_minimos": 0,
            "familia_cost_aware_robusta": False,
            "configuracion_preferida_no_performance": None,
            "motivos_rechazo_conteo": {},
            "resultados": [],
        })
        SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"[04B-v3] DATASET_INSUFICIENTE: utiles={len(symbols_utiles)}/"
            f"{len(UNIVERSO_VALIDACION_V2)}; no se evalua modelo."
        )
        return 0

    validacion = evaluar_validacion_v3_predeclarada(observaciones)
    compactos = [_config_compacta(x) for x in validacion.resultados]
    conteo_motivos = Counter(
        motivo
        for x in validacion.resultados
        for motivo in x.motivos_rechazo
    )
    if validacion.familia_cost_aware_robusta:
        status = "FAMILIA_COST_AWARE_ROBUSTA_V3"
    elif validacion.n_superan_minimos > 0:
        status = "APTAS_AISLADAS_COST_AWARE_V3"
    else:
        status = "SIN_CONFIGURACIONES_COST_AWARE_V3"

    preferida = validacion.configuracion_preferida_no_performance
    base.update({
        "status": status,
        "n_observaciones_pre_test": validacion.n_observaciones_pre_test,
        "n_configuraciones": validacion.n_configuraciones,
        "n_superan_minimos": validacion.n_superan_minimos,
        "familia_cost_aware_robusta": validacion.familia_cost_aware_robusta,
        "configuracion_preferida_no_performance": (
            None if preferida is None else {
                "horizonte_horas": preferida.horizonte_horas,
                "rank_bins": preferida.rank_bins,
                "regimen_bins": preferida.regimen_bins,
                "min_muestras": preferida.min_muestras,
                "max_radio": preferida.max_radio,
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
        f"[04B-v3] {status}: utiles={len(symbols_utiles)}, "
        f"obs={validacion.n_observaciones_pre_test}, "
        f"configs={validacion.n_configuraciones}, "
        f"aptas={validacion.n_superan_minimos}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
