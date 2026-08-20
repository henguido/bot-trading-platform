#!/usr/bin/env python3
"""BOT 2.0-04B-v12: top-5 factor vs benchmark, exclusivamente 2022-2025."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.historico_binance import descargar_klines_data_api, descargar_klines_rango
from backend.economia.momentum_semanal_v11 import construir_observaciones_momentum_v11
from backend.economia.portfolio_factor_v12 import evaluar_portfolios_v12
from backend.economia.protocolo_edge_v2 import (
    DATASET_DESDE_MS,
    INTERVALO_KLINE,
    TEST_DESDE_MS,
    UNIVERSO_VALIDACION_V2,
    VALIDACION_DESDE_MS,
)
from backend.economia.protocolo_edge_v4 import MIN_SYMBOLS_DATASET_VALIDACION_V4
from backend.economia.protocolo_portfolio_v12 import (
    ANIOS_V12,
    DESARROLLO_2026_ABIERTO_V12,
    FACTORES_V12,
    HORIZONTE_HORAS_V12,
    HURDLE_ECONOMICO_BPS_V12,
    MIN_ANIOS_APTOS_V12,
    TEST_MAY_JUL_ABIERTO_V12,
    TOP_K_V12,
)

SALIDA = RAIZ / "artifacts" / "portfolio-v12-desarrollo-2022-2025.json"
FIN_2025_MS = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def _jsonable(x):
    if isinstance(x, Decimal):
        return str(x)
    if isinstance(x, (tuple, list)):
        return [_jsonable(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    return x


def _descargar_series():
    series, manifest = {}, []
    binance = BinanceConnector()
    for symbol in UNIVERSO_VALIDACION_V2:
        primaria = descargar_klines_rango(
            binance,
            symbol,
            interval=INTERVALO_KLINE,
            start_ms=DATASET_DESDE_MS,
            end_ms=FIN_2025_MS - 1,
            limit=1000,
        )
        usada = primaria
        error_primaria = None
        if not primaria.completa:
            error_primaria = primaria.error
            usada = descargar_klines_data_api(
                symbol,
                interval=INTERVALO_KLINE,
                start_ms=DATASET_DESDE_MS,
                end_ms=FIN_2025_MS - 1,
                limit=1000,
            )
        if usada.completa:
            series[symbol] = usada.velas
        manifest.append({
            "symbol": symbol,
            "completa": usada.completa,
            "fuente": usada.fuente,
            "error": usada.error,
            "error_fuente_primaria": error_primaria,
            "n_velas": len(usada.velas),
            "n_requests": primaria.n_requests + usada.n_requests,
        })
    return series, manifest


def _compactar_anual(r):
    return {
        "factor": r.factor,
        "year": r.year,
        "n_semanas": r.n_semanas,
        "retorno_portfolio_neto_medio_bps": r.retorno_portfolio_neto_medio_bps,
        "fraccion_portfolio_neto_positivo": r.fraccion_portfolio_neto_positivo,
        "retorno_benchmark_neto_medio_bps": r.retorno_benchmark_neto_medio_bps,
        "exceso_medio_bps": r.exceso_medio_bps,
        "fraccion_exceso_positivo": r.fraccion_exceso_positivo,
        "meses_portfolio_netos_positivos": r.meses_portfolio_netos_positivos,
        "folds_portfolio_netos_positivos": r.folds_portfolio_netos_positivos,
        "meses_exceso_positivos": r.meses_exceso_positivos,
        "folds_exceso_positivos": r.folds_exceso_positivos,
        "portfolio_apto": r.portfolio_apto,
        "exceso_apto": r.exceso_apto,
        "apto": r.apto,
        "motivos_rechazo": list(r.motivos_rechazo),
    }


def main() -> int:
    end_ms = FIN_2025_MS - 1
    assert DESARROLLO_2026_ABIERTO_V12 is False
    assert TEST_MAY_JUL_ABIERTO_V12 is False
    assert end_ms < VALIDACION_DESDE_MS and end_ms < TEST_DESDE_MS

    print(
        f"[04B-v12] top={TOP_K_V12} horizonte={HORIZONTE_HORAS_V12}h "
        f"hurdle={HURDLE_ECONOMICO_BPS_V12}bps anios={ANIOS_V12} 2026_OPEN=False"
    )
    series, manifest = _descargar_series()
    observaciones = construir_observaciones_momentum_v11(series)
    if any(o.estado.timestamp_ms >= VALIDACION_DESDE_MS for o in observaciones):
        raise RuntimeError("observacion 2026 detectada en v12")

    symbols = sorted({o.estado.symbol for o in observaciones})
    reporte = {
        "status": "PENDIENTE",
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "intervalo": INTERVALO_KLINE,
        "horizonte_horas": HORIZONTE_HORAS_V12,
        "top_k": TOP_K_V12,
        "hurdle_economico_bps": HURDLE_ECONOMICO_BPS_V12,
        "anios": list(ANIOS_V12),
        "min_anios_aptos": MIN_ANIOS_APTOS_V12,
        "factores": list(FACTORES_V12),
        "n_symbols_utiles": len(symbols),
        "symbols_utiles": symbols,
        "n_observaciones": len(observaciones),
        "manifest": manifest,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    if len(symbols) < MIN_SYMBOLS_DATASET_VALIDACION_V4:
        reporte.update({
            "status": "DATASET_INSUFICIENTE_V12",
            "factores_prometedores": [],
            "clasificaciones": [],
            "resultados_anuales": [],
        })
    else:
        d = evaluar_portfolios_v12(observaciones)
        status = "PORTFOLIOS_PROMETEDORES_V12" if d.factores_prometedores else "SIN_PORTFOLIOS_PROMETEDORES_V12"
        reporte.update({
            "status": status,
            "factores_prometedores": list(d.factores_prometedores),
            "clasificaciones": [
                {"factor": c.factor, "anios_aptos": c.anios_aptos, "clase": c.clase}
                for c in d.clasificaciones
            ],
            "resultados_anuales": [_compactar_anual(r) for r in d.anuales],
        })
        print(
            f"[04B-v12] {status}: utiles={len(symbols)} "
            f"prometedores={d.factores_prometedores}"
        )

    SALIDA.write_text(json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
