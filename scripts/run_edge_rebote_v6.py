#!/usr/bin/env python3
"""Ejecuta BOT 2.0-04B-v6 exclusivamente sobre desarrollo 2025.

Salida: artifacts/edge-rebote-v6-desarrollo-2025.json

No abre enero-abril 2026 ni mayo-julio 2026. Usa solo datos Spot publicos, sin
GPT, RiskEngine, ordenes, LIVE ni Render.
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
    diagnosticar_edge_desarrollo_2025,
)
from backend.economia.diagnostico_rebote_v6 import diagnosticar_rebote_v6
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
from backend.economia.protocolo_edge_v4 import MIN_SYMBOLS_DATASET_VALIDACION_V4
from backend.economia.protocolo_edge_v6 import (
    COSTE_TOTAL_BPS_V6,
    HORIZONTE_HORAS_V6,
    HURDLE_ECONOMICO_BPS_V6,
    MARGEN_SEGURIDAD_BPS_V6,
    POLITICA_AMBIGUEDAD_V6,
    STOP_BRUTO_BPS_V6,
    TARGET_BRUTO_BPS_V6,
    TEST_MAY_JUL_ABIERTO_V6,
    VALIDACION_2026_ABIERTA_V6,
)

SALIDA = RAIZ_PROYECTO / "artifacts" / "edge-rebote-v6-desarrollo-2025.json"


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


def _compactar_config(r):
    x = r.resumen
    return {
        "min_muestras": r.min_muestras,
        "max_radio": r.max_radio,
        "apto_diagnostico": x.apto_diagnostico,
        "motivos_rechazo": list(x.motivos_rechazo),
        "n_senales": x.n_senales,
        "n_stop": x.n_stop,
        "n_target": x.n_target,
        "n_time": x.n_time,
        "n_ambiguas_stop_prioritario": x.n_ambiguas_stop_prioritario,
        "retorno_neto_despues_hurdle_medio_bps": x.retorno_neto_despues_hurdle_medio_bps,
        "fraccion_resultados_positivos": x.fraccion_resultados_positivos,
        "n_meses_con_senal": x.n_meses_con_senal,
        "meses_netos_positivos": x.meses_netos_positivos,
        "n_folds_con_senal": x.n_folds_con_senal,
        "folds_netos_positivos": x.folds_netos_positivos,
    }


def main() -> int:
    end_ms = DIAGNOSTICO_DESARROLLO_HASTA_MS
    assert not VALIDACION_2026_ABIERTA_V6
    assert not TEST_MAY_JUL_ABIERTO_V6
    assert end_ms < VALIDACION_DESDE_MS
    assert end_ms < TEST_DESDE_MS

    print(
        f"[04B-v6] desarrollo 2025, horizonte={HORIZONTE_HORAS_V6}h, "
        f"stop={STOP_BRUTO_BPS_V6}bps, target={TARGET_BRUTO_BPS_V6}bps, "
        f"hurdle={HURDLE_ECONOMICO_BPS_V6}bps, "
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
        raise RuntimeError("violacion: observacion 2026 entro al diagnostico v6")

    symbols_utiles = sorted({o.estado.symbol for o in observaciones})
    base = {
        "status": "PENDIENTE",
        "validacion_2026_open": False,
        "test_may_jul_open": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "intervalo": INTERVALO_KLINE,
        "horizonte_horas": HORIZONTE_HORAS_V6,
        "coste_total_bps": COSTE_TOTAL_BPS_V6,
        "margen_seguridad_bps": MARGEN_SEGURIDAD_BPS_V6,
        "hurdle_economico_bps": HURDLE_ECONOMICO_BPS_V6,
        "stop_bruto_bps": STOP_BRUTO_BPS_V6,
        "target_bruto_bps": TARGET_BRUTO_BPS_V6,
        "politica_ambiguedad": POLITICA_AMBIGUEDAD_V6,
        "n_symbols_utiles": len(symbols_utiles),
        "symbols_utiles": symbols_utiles,
        "n_observaciones_relativas": len(observaciones),
        "manifest": manifest,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    if len(symbols_utiles) < MIN_SYMBOLS_DATASET_VALIDACION_V4:
        base.update({
            "status": "DATASET_INSUFICIENTE_V6",
            "n_configuraciones": 0,
            "n_configuraciones_aptas": 0,
            "familia_apta": False,
            "resultados": [],
        })
        SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
        return 0

    diagnostico_v5 = diagnosticar_edge_desarrollo_2025(observaciones)
    v6 = diagnosticar_rebote_v6(diagnostico_v5, observaciones)
    status = "FAMILIA_REBOTE_V6_APTA_DESARROLLO" if v6.familia_apta else "REBOTE_V6_FALSADO_DESARROLLO"
    base.update({
        "status": status,
        "n_configuraciones": len(v6.resultados),
        "n_configuraciones_aptas": v6.n_configuraciones_aptas,
        "familia_apta": v6.familia_apta,
        "resultados": [_compactar_config(r) for r in v6.resultados],
    })
    SALIDA.write_text(json.dumps(_jsonable(base), indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[04B-v6] {status}: utiles={len(symbols_utiles)}, "
        f"configs_aptas={v6.n_configuraciones_aptas}/{len(v6.resultados)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
