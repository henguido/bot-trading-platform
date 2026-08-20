#!/usr/bin/env python3
"""Ejecuta diagnostico de desarrollo 2025 para Expected Edge.

Salida: artifacts/edge-diagnostico-desarrollo-2025.json

Usa solo datos publicos Spot hasta 2025-12-31. No abre enero-abril 2026 ni el
holdout final mayo-julio 2026.
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
from backend.economia.diagnostico_edge_desarrollo import (
    DIAGNOSTICO_DESARROLLO_HASTA_MS,
    FOLDS_DIAGNOSTICO_DESARROLLO_2025,
    diagnosticar_edge_desarrollo_2025,
)
from backend.economia.edge_relativo_v2 import construir_observaciones_relativas_v2
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
from backend.economia.protocolo_edge_v4 import (
    HURDLE_EDGE_PREDICHO_BPS_V4,
    MIN_SYMBOLS_DATASET_VALIDACION_V4,
    REGIMEN_MERCADO_MINIMO_BPS_V4,
)

SALIDA = RAIZ_PROYECTO / "artifacts" / "edge-diagnostico-desarrollo-2025.json"


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
    s = resultado.resumen_predichos
    e = resultado.resultado_cost_aware
    r = resultado.resultado_regimen
    er = r.resultado_cost_aware
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
        },
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
        "predichos": {
            "n_predicciones": s.n_predicciones,
            "n_sin_regimen": s.n_sin_regimen,
            "n_regimen_no_negativo": s.n_regimen_no_negativo,
            "n_regimen_negativo": s.n_regimen_negativo,
            "n_sobre_hurdle": s.n_sobre_hurdle,
            "n_sobre_hurdle_regimen_no_negativo": (
                s.n_sobre_hurdle_regimen_no_negativo
            ),
            "n_sobre_hurdle_regimen_negativo": s.n_sobre_hurdle_regimen_negativo,
            "fraccion_sobre_hurdle": s.fraccion_sobre_hurdle,
            "fraccion_sobre_hurdle_regimen_no_negativo": (
                s.fraccion_sobre_hurdle_regimen_no_negativo
            ),
            "predicho_bps_p50": s.predicho_bps_p50,
            "predicho_bps_p75": s.predicho_bps_p75,
            "predicho_bps_p90": s.predicho_bps_p90,
            "predicho_bps_p95": s.predicho_bps_p95,
            "predicho_bps_p99": s.predicho_bps_p99,
            "predicho_bps_max": s.predicho_bps_max,
            "predicho_bps_max_regimen_no_negativo": (
                s.predicho_bps_max_regimen_no_negativo
            ),
            "predicho_bps_max_regimen_negativo": (
                s.predicho_bps_max_regimen_negativo
            ),
        },
        "cost_aware_todos_regimenes": {
            "estado": e.estado,
            "motivo": e.motivo,
            "n_timestamps_evaluables": e.n_timestamps_evaluables,
            "n_timestamps_senal": e.n_timestamps_senal,
            "n_senales": e.n_senales,
            "cobertura_timestamps_senal": e.cobertura_timestamps_senal,
            "retorno_bruto_senales_medio_bps": e.retorno_bruto_senales_medio_bps,
            "retorno_neto_despues_margen_medio_bps": (
                e.retorno_neto_despues_margen_medio_bps
            ),
            "baseline_bruto_medio_bps": e.baseline_bruto_medio_bps,
            "uplift_bruto_medio_bps": e.uplift_bruto_medio_bps,
            "fraccion_timestamps_neto_despues_margen_positivo": (
                e.fraccion_timestamps_neto_despues_margen_positivo
            ),
            "n_meses_con_senal": e.n_meses_con_senal,
            "meses_neto_despues_margen_positivo": (
                e.meses_neto_despues_margen_positivo
            ),
        },
        "regimen_cost_aware": {
            "estado": r.estado,
            "motivo": r.motivo,
            "n_timestamps_entrada": r.n_timestamps_entrada,
            "n_timestamps_regimen_aprobado": r.n_timestamps_regimen_aprobado,
            "cobertura_regimen_timestamps": r.cobertura_regimen_timestamps,
            "n_timestamps_senal": er.n_timestamps_senal,
            "n_senales": er.n_senales,
            "retorno_bruto_senales_medio_bps": er.retorno_bruto_senales_medio_bps,
            "retorno_neto_despues_margen_medio_bps": (
                er.retorno_neto_despues_margen_medio_bps
            ),
            "baseline_bruto_medio_bps": er.baseline_bruto_medio_bps,
            "uplift_bruto_medio_bps": er.uplift_bruto_medio_bps,
            "fraccion_timestamps_neto_despues_margen_positivo": (
                er.fraccion_timestamps_neto_despues_margen_positivo
            ),
            "n_meses_con_senal": er.n_meses_con_senal,
            "meses_neto_despues_margen_positivo": (
                er.meses_neto_despues_margen_positivo
            ),
        },
    }


def main() -> int:
    end_ms = DIAGNOSTICO_DESARROLLO_HASTA_MS
    assert end_ms < VALIDACION_DESDE_MS
    assert end_ms < TEST_DESDE_MS
    print(
        f"[04B-desarrollo] Diagnostico 2025: "
        f"{len(UNIVERSO_VALIDACION_V2)} simbolos, intervalo={INTERVALO_KLINE}, "
        f"regimen_min={REGIMEN_MERCADO_MINIMO_BPS_V4} bps, "
        f"hurdle={HURDLE_EDGE_PREDICHO_BPS_V4} bps, "
        "VALIDACION_2026_OPEN=False, TEST_MAY_JUL_OPEN=False"
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
    if any(o.estado.timestamp_ms >= VALIDACION_DESDE_MS for o in observaciones):
        raise RuntimeError("violacion: observacion de 2026 entro a diagnostico")

    symbols_utiles = sorted({o.estado.symbol for o in observaciones})
    base = {
        "validacion_2026_open": False,
        "test_may_jul_open": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "validacion_2026_desde_ms": VALIDACION_DESDE_MS,
        "test_desde_ms": TEST_DESDE_MS,
        "intervalo": INTERVALO_KLINE,
        "universo": list(UNIVERSO_VALIDACION_V2),
        "folds_desarrollo": [
            {"valid_desde_ms": f.valid_desde_ms, "valid_hasta_ms": f.valid_hasta_ms}
            for f in FOLDS_DIAGNOSTICO_DESARROLLO_2025
        ],
        "regimen_mercado_minimo_bps": REGIMEN_MERCADO_MINIMO_BPS_V4,
        "hurdle_edge_predicho_bps": HURDLE_EDGE_PREDICHO_BPS_V4,
        "n_symbols_utiles": len(symbols_utiles),
        "symbols_utiles": symbols_utiles,
        "n_observaciones_relativas": len(observaciones),
        "manifest": manifest,
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    if len(symbols_utiles) < MIN_SYMBOLS_DATASET_VALIDACION_V4:
        base.update({
            "status": "DATASET_INSUFICIENTE_DESARROLLO",
            "n_configuraciones": 0,
            "n_configuraciones_con_senal_cost_aware": 0,
            "n_configuraciones_con_senal_regimen_cost_aware": 0,
            "resultados": [],
        })
        SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"[04B-desarrollo] DATASET_INSUFICIENTE: utiles={len(symbols_utiles)}/"
            f"{len(UNIVERSO_VALIDACION_V2)}; no se evalua modelo."
        )
        return 0

    diagnostico = diagnosticar_edge_desarrollo_2025(observaciones)
    compactos = [_config_compacta(x) for x in diagnostico.resultados]
    con_senal_cost = diagnostico.n_configuraciones_con_senal_cost_aware
    con_senal_regimen = diagnostico.n_configuraciones_con_senal_regimen_cost_aware
    if con_senal_regimen:
        status = "HAY_SENALES_HURDLE_REGIMEN_DESARROLLO"
    elif con_senal_cost:
        status = "SENALES_HURDLE_SOLO_EN_REGIMENES_NO_APROBADOS_DESARROLLO"
    else:
        status = "SIN_CAPACIDAD_HURDLE_DESARROLLO"

    base.update({
        "status": status,
        "n_observaciones_pre_2026": diagnostico.n_observaciones_pre_2026,
        "n_configuraciones": diagnostico.n_configuraciones,
        "n_configuraciones_con_senal_cost_aware": con_senal_cost,
        "n_configuraciones_con_senal_regimen_cost_aware": con_senal_regimen,
        "resultados": compactos,
    })
    SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[04B-desarrollo] {status}: utiles={len(symbols_utiles)}, "
        f"obs={diagnostico.n_observaciones_pre_2026}, "
        f"configs={diagnostico.n_configuraciones}, "
        f"cost_senal={con_senal_cost}, regimen_senal={con_senal_regimen}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
