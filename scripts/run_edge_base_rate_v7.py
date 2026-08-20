#!/usr/bin/env python3
"""Ejecuta BOT 2.0-04B-v7 exclusivamente sobre desarrollo 2022-2025.

Salida: artifacts/edge-base-rate-v7-desarrollo-2025.json

No entrena modelo. No abre 2026. Usa datos Spot publicos y mide si 24/48/72h
tienen presupuesto absoluto suficiente para justificar otra familia predictiva.
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
from backend.economia.diagnostico_base_rate_v7 import diagnosticar_base_rate_v7
from backend.economia.diagnostico_edge_desarrollo import DIAGNOSTICO_DESARROLLO_HASTA_MS
from backend.economia.edge_relativo_v2 import construir_observaciones_relativas_v2
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
from backend.economia.protocolo_edge_v7 import (
    CLASE_BASELINE_VIABLE,
    CLASE_SELECCION_POTENCIAL,
    DESARROLLO_2026_ABIERTO_V7,
    HORIZONTES_HORAS_V7,
    HURDLE_ECONOMICO_BPS_V7,
    TEST_MAY_JUL_ABIERTO_V7,
)

SALIDA = RAIZ_PROYECTO / "artifacts" / "edge-base-rate-v7-desarrollo-2025.json"


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


def _resumen_dict(r):
    return {
        "horizonte_horas": r.horizonte_horas,
        "regimen": r.regimen,
        "n_observaciones": r.n_observaciones,
        "n_timestamps": r.n_timestamps,
        "retorno_medio_bps": r.retorno_medio_bps,
        "retorno_p25_bps": r.retorno_p25_bps,
        "retorno_p50_bps": r.retorno_p50_bps,
        "retorno_p75_bps": r.retorno_p75_bps,
        "retorno_p90_bps": r.retorno_p90_bps,
        "retorno_neto_medio_bps": r.retorno_neto_medio_bps,
        "fraccion_observaciones_cubren_hurdle": r.fraccion_observaciones_cubren_hurdle,
        "mfe_p50_bps": r.mfe_p50_bps,
        "mfe_p75_bps": r.mfe_p75_bps,
        "mfe_p90_bps": r.mfe_p90_bps,
        "mae_p10_bps": r.mae_p10_bps,
        "mae_p25_bps": r.mae_p25_bps,
        "mae_p50_bps": r.mae_p50_bps,
        "fraccion_observaciones_mfe_cubre_hurdle": r.fraccion_observaciones_mfe_cubre_hurdle,
        "baseline_timestamp_neto_medio_bps": r.baseline_timestamp_neto_medio_bps,
        "fraccion_timestamps_baseline_neto_positivo": r.fraccion_timestamps_baseline_neto_positivo,
        "oracle_top1_neto_medio_bps": r.oracle_top1_neto_medio_bps,
        "fraccion_timestamps_oracle_neto_positivo": r.fraccion_timestamps_oracle_neto_positivo,
        "dispersion_p75_p25_mediana_bps": r.dispersion_p75_p25_mediana_bps,
        "meses_2025_con_datos": r.meses_2025_con_datos,
        "meses_2025_baseline_neto_positivo": r.meses_2025_baseline_neto_positivo,
        "meses_2025_oracle_neto_positivo": r.meses_2025_oracle_neto_positivo,
        "folds_2025_con_datos": r.folds_2025_con_datos,
        "folds_2025_baseline_neto_positivo": r.folds_2025_baseline_neto_positivo,
    }


def main() -> int:
    end_ms = DIAGNOSTICO_DESARROLLO_HASTA_MS
    assert not DESARROLLO_2026_ABIERTO_V7
    assert not TEST_MAY_JUL_ABIERTO_V7
    assert end_ms < VALIDACION_DESDE_MS
    assert end_ms < TEST_DESDE_MS

    print(
        f"[04B-v7] base-rate 2022-2025, horizontes={HORIZONTES_HORAS_V7}, "
        f"hurdle={HURDLE_ECONOMICO_BPS_V7}bps, "
        "DESARROLLO_2026_OPEN=False, TEST_MAY_JUL_OPEN=False"
    )

    binance = BinanceConnector()
    series, manifest = _descargar_series(
        binance, start_ms=DATASET_DESDE_MS, end_ms=end_ms,
    )
    observaciones = construir_observaciones_relativas_v2(
        series,
        intervalo_horas=INTERVALO_HORAS,
        horizontes_horas=HORIZONTES_HORAS_V7,
    )
    if any(o.estado.timestamp_ms >= VALIDACION_DESDE_MS for o in observaciones):
        raise RuntimeError("violacion: observacion 2026 entro al diagnostico v7")

    symbols_utiles = sorted({o.estado.symbol for o in observaciones})
    base = {
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "intervalo": INTERVALO_KLINE,
        "horizontes_horas": list(HORIZONTES_HORAS_V7),
        "hurdle_economico_bps": HURDLE_ECONOMICO_BPS_V7,
        "n_symbols_utiles": len(symbols_utiles),
        "symbols_utiles": symbols_utiles,
        "n_observaciones_relativas": len(observaciones),
        "manifest": manifest,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    if len(symbols_utiles) < MIN_SYMBOLS_DATASET_VALIDACION_V4:
        base.update({
            "status": "DATASET_INSUFICIENTE_V7",
            "horizonte_candidato": None,
            "clasificaciones": [],
            "resumenes": [],
        })
        SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
        return 0

    diagnostico = diagnosticar_base_rate_v7(observaciones)
    clases = [
        {
            "horizonte_horas": c.horizonte_horas,
            "clase": c.clase,
            "motivos": list(c.motivos),
        }
        for c in diagnostico.clasificaciones_no_negativo
    ]
    if diagnostico.horizontes_baseline_viable:
        status = "BASELINE_LONG_VIABLE_V7"
    elif diagnostico.horizontes_seleccion_potencial:
        status = "PRESUPUESTO_PARA_SELECCION_V7"
    else:
        status = "SIN_PRESUPUESTO_HORIZONTE_LARGO_V7"

    base.update({
        "status": status,
        "horizontes_baseline_viable": list(diagnostico.horizontes_baseline_viable),
        "horizontes_seleccion_potencial": list(diagnostico.horizontes_seleccion_potencial),
        "horizonte_candidato": diagnostico.horizonte_candidato,
        "clasificaciones": clases,
        "resumenes": [_resumen_dict(r) for r in diagnostico.resumenes],
    })
    SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[04B-v7] {status}: utiles={len(symbols_utiles)}, "
        f"obs={len(observaciones)}, candidato={diagnostico.horizonte_candidato}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
