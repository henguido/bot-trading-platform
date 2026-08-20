#!/usr/bin/env python3
"""BOT 2.0-04B-v11: diagnóstico semanal offline exclusivo de 2022-2025."""
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
from backend.economia.diagnostico_momentum_v11 import diagnosticar_momentum_v11
from backend.economia.historico_binance import descargar_klines_data_api, descargar_klines_rango
from backend.economia.momentum_semanal_v11 import construir_observaciones_momentum_v11
from backend.economia.protocolo_edge_v2 import (
    DATASET_DESDE_MS,
    INTERVALO_KLINE,
    TEST_DESDE_MS,
    UNIVERSO_VALIDACION_V2,
    VALIDACION_DESDE_MS,
)
from backend.economia.protocolo_edge_v4 import MIN_SYMBOLS_DATASET_VALIDACION_V4
from backend.economia.protocolo_edge_v11 import (
    DESARROLLO_2026_ABIERTO_V11,
    FACTORES_V11,
    HORIZONTE_HORAS_V11,
    HURDLE_ECONOMICO_BPS_V11,
    TEST_MAY_JUL_ABIERTO_V11,
)
from backend.economia.replica_rmom3_v11b import replicar_rmom3_v11b

SALIDA = RAIZ / "artifacts" / "momentum-v11-desarrollo-2025.json"
FIN_2025_MS = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def jsonable(x):
    if isinstance(x, Decimal):
        return str(x)
    if isinstance(x, (tuple, list)):
        return [jsonable(v) for v in x]
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    return x


def descargar_series():
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


def compactar(r):
    return {
        "factor": r.factor,
        "n_timestamps": r.n_timestamps,
        "ic_spearman_medio": r.ic_spearman_medio,
        "fraccion_ic_positivo": r.fraccion_ic_positivo,
        "spread_alto_menos_bajo_medio_bps": r.spread_alto_menos_bajo_medio_bps,
        "fraccion_spread_positivo": r.fraccion_spread_positivo,
        "n_meses_spread": r.n_meses_spread,
        "meses_spread_positivos": r.meses_spread_positivos,
        "n_folds_spread": r.n_folds_spread,
        "folds_spread_positivos": r.folds_spread_positivos,
        "n_senales_top1": r.n_senales_top1,
        "retorno_top1_neto_medio_bps": r.retorno_top1_neto_medio_bps,
        "fraccion_top1_neto_positivo": r.fraccion_top1_neto_positivo,
        "n_meses_top1": r.n_meses_top1,
        "meses_top1_netos_positivos": r.meses_top1_netos_positivos,
        "n_folds_top1": r.n_folds_top1,
        "folds_top1_netos_positivos": r.folds_top1_netos_positivos,
        "spread_apto": r.spread_apto,
        "top1_apto": r.top1_apto,
        "apto": r.apto,
        "motivos_rechazo": list(r.motivos_rechazo),
    }


def compactar_replica(r):
    return {
        "year": r.year,
        "n_timestamps": r.n_timestamps,
        "spread_medio_bps": r.spread_medio_bps,
        "fraccion_spread_positivo": r.fraccion_spread_positivo,
        "meses_spread_positivos": r.meses_spread_positivos,
        "folds_spread_positivos": r.folds_spread_positivos,
        "retorno_top1_neto_medio_bps": r.retorno_top1_neto_medio_bps,
        "fraccion_top1_neto_positivo": r.fraccion_top1_neto_positivo,
        "n_meses_top1": r.n_meses_top1,
        "meses_top1_netos_positivos": r.meses_top1_netos_positivos,
        "n_folds_top1": r.n_folds_top1,
        "folds_top1_netos_positivos": r.folds_top1_netos_positivos,
        "spread_apto": r.spread_apto,
        "top1_apto": r.top1_apto,
        "apto": r.apto,
        "motivos_rechazo": list(r.motivos_rechazo),
    }


def main() -> int:
    end_ms = FIN_2025_MS - 1
    assert DESARROLLO_2026_ABIERTO_V11 is False
    assert TEST_MAY_JUL_ABIERTO_V11 is False
    assert end_ms < VALIDACION_DESDE_MS and end_ms < TEST_DESDE_MS

    print(
        f"[04B-v11] horizonte={HORIZONTE_HORAS_V11}h "
        f"hurdle={HURDLE_ECONOMICO_BPS_V11}bps rebalance=SEMANAL 2026_OPEN=False"
    )
    series, manifest = descargar_series()
    observaciones = construir_observaciones_momentum_v11(series)
    if any(o.estado.timestamp_ms >= VALIDACION_DESDE_MS for o in observaciones):
        raise RuntimeError("observacion 2026 detectada en v11")

    symbols = sorted({o.estado.symbol for o in observaciones})
    reporte = {
        "status": "PENDIENTE",
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "dataset_desde_ms": DATASET_DESDE_MS,
        "dataset_hasta_ms": end_ms,
        "intervalo": INTERVALO_KLINE,
        "horizonte_horas": HORIZONTE_HORAS_V11,
        "hurdle_economico_bps": HURDLE_ECONOMICO_BPS_V11,
        "rebalance": "CIERRE_DOMINGO_LIMITE_LUNES_00_UTC",
        "factores": list(FACTORES_V11),
        "n_symbols_utiles": len(symbols),
        "symbols_utiles": symbols,
        "n_observaciones": len(observaciones),
        "manifest": manifest,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    if len(symbols) < MIN_SYMBOLS_DATASET_VALIDACION_V4:
        reporte.update({
            "status": "DATASET_INSUFICIENTE_V11",
            "n_timestamps": 0,
            "factores_prometedores": [],
            "clasificaciones": [],
            "resultados": [],
            "replica_rmom3_v11b": None,
        })
    else:
        d = diagnosticar_momentum_v11(observaciones)
        status = "FACTORES_PROMETEDORES_V11" if d.factores_prometedores else "SIN_FACTORES_PROMETEDORES_V11"
        reporte.update({
            "status": status,
            "n_timestamps": d.n_timestamps,
            "factores_prometedores": list(d.factores_prometedores),
            "clasificaciones": [
                {"factor": c.factor, "clase": c.clase}
                for c in d.clasificaciones
            ],
            "resultados": [compactar(r) for r in d.resultados],
        })
        print(
            f"[04B-v11] {status}: utiles={len(symbols)} "
            f"timestamps={d.n_timestamps} prometedores={d.factores_prometedores}"
        )

        replica = replicar_rmom3_v11b(observaciones)
        reporte["replica_rmom3_v11b"] = {
            "anios_aptos": replica.anios_aptos,
            "replica_consistente": replica.replica_consistente,
            "anuales": [compactar_replica(r) for r in replica.anuales],
        }
        print(
            f"[04B-v11b] RMOM3 replica: anios_aptos={replica.anios_aptos}/3 "
            f"consistente={replica.replica_consistente}"
        )

    SALIDA.write_text(json.dumps(jsonable(reporte), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
