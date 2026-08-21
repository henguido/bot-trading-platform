#!/usr/bin/env python3
"""BOT 2.0-04B-v24: OFI Spot residual al retorno contemporáneo -> 7 días."""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.economia.evaluacion_orderflow_v24 import construir_observaciones_v24, evaluar_orderflow_v24
from backend.economia.historico_binance import descargar_klines_data_api
from backend.economia.orderflow_v24 import archivo_v24, descargar_resumir_v24
from backend.economia.protocolo_orderflow_v24 import (
    DESARROLLO_2026_ABIERTO_V24,
    FECHAS_FEATURE_V24,
    FRACCION_ARCHIVOS_AGGTRADES_COMPLETOS_MIN_V24,
    FRACCION_FECHAS_CON_MIN_SIMBOLOS_V24,
    HURDLE_TOTAL_BPS_V24,
    IMPUTACION_PERMITIDA_V24,
    INTERVALO_SPOT_V24,
    MIN_SIMBOLOS_POR_TIMESTAMP_V24,
    MIN_SIMBOLOS_SPOT_COMPLETOS_V24,
    PERMITE_AJUSTAR_UMBRALES_POST_RESULTADO_V24,
    PERMITE_CAMBIAR_FECHAS_POST_RESULTADO_V24,
    PERMITE_CAMBIAR_HORIZONTE_POST_RESULTADO_V24,
    PERMITE_INVERTIR_SIGNO_V24,
    REINTENTOS_TRANSPORTE_AGGTRADES_V24,
    TEST_MAY_JUL_ABIERTO_V24,
    UNIVERSO_V24,
)

SALIDA = RAIZ / "artifacts" / "orderflow-v24-desarrollo-2022-2025.json"
MAX_WORKERS_AGGTRADES = 2
MAX_WORKERS_SPOT = 8
_LOCAL = threading.local()


def _jsonable(x):
    if isinstance(x, Decimal):
        return str(x)
    if isinstance(x, tuple):
        return [_jsonable(v) for v in x]
    if isinstance(x, list):
        return [_jsonable(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    return x


def _http_get(url, **kwargs):
    sesion = getattr(_LOCAL, "session", None)
    if sesion is None:
        sesion = requests.Session()
        sesion.headers.update({"User-Agent": "bot-trading-platform-research-v24/1.0"})
        _LOCAL.session = sesion
    return sesion.get(url, **kwargs)


def _descargar_flow(a):
    return descargar_resumir_v24(a, http_get=_http_get)


def _descargar_spot(symbol: str):
    primera = FECHAS_FEATURE_V24[0]
    ultima = FECHAS_FEATURE_V24[-1] + timedelta(days=8)
    inicio = datetime(primera.year, primera.month, primera.day, tzinfo=timezone.utc)
    fin = datetime(ultima.year, ultima.month, ultima.day, tzinfo=timezone.utc)
    return descargar_klines_data_api(
        symbol,
        interval=INTERVALO_SPOT_V24,
        start_ms=int(inicio.timestamp() * 1000),
        end_ms=int(fin.timestamp() * 1000),
        limit=1000,
        http_get=_http_get,
    )


def _descargar_tareas(tareas):
    resultados = {}
    # Dos procesos: el hot path es CPU-bound y el runner hosted ofrece pocos
    # cores. Cada proceso mantiene su propia Session y solo devuelve agregados.
    with ProcessPoolExecutor(max_workers=MAX_WORKERS_AGGTRADES) as pool:
        futuros = {pool.submit(_descargar_flow, a): a for a in tareas}
        for i, fut in enumerate(as_completed(futuros), 1):
            a = futuros[fut]
            try:
                r = fut.result()
            except Exception as exc:
                from backend.economia.orderflow_v24 import FlujoDiaV24
                r = FlujoDiaV24(
                    a.symbol, a.fecha, a.key, False, 0, 0,
                    Decimal("0"), Decimal("0"), None, None,
                    f"{type(exc).__name__}: {str(exc)[:300]}",
                )
            resultados[a.key] = r
            if i % 100 == 0 or i == len(tareas):
                completos = sum(1 for x in resultados.values() if x.completa)
                print(f"[04B-v24] aggtrades progress={i}/{len(tareas)} complete={completos}", flush=True)
    return resultados


def main() -> int:
    assert DESARROLLO_2026_ABIERTO_V24 is False
    assert TEST_MAY_JUL_ABIERTO_V24 is False
    assert IMPUTACION_PERMITIDA_V24 is False
    assert PERMITE_INVERTIR_SIGNO_V24 is False
    assert PERMITE_AJUSTAR_UMBRALES_POST_RESULTADO_V24 is False
    assert PERMITE_CAMBIAR_FECHAS_POST_RESULTADO_V24 is False
    assert PERMITE_CAMBIAR_HORIZONTE_POST_RESULTADO_V24 is False

    tareas = tuple(archivo_v24(s, d) for d in FECHAS_FEATURE_V24 for s in UNIVERSO_V24)
    print(
        f"[04B-v24] start symbols={len(UNIVERSO_V24)} dates={len(FECHAS_FEATURE_V24)} "
        f"files={len(tareas)} hurdle={HURDLE_TOTAL_BPS_V24}bps 2026_OPEN=False",
        flush=True,
    )

    resultados = _descargar_tareas(tareas)
    for intento in range(REINTENTOS_TRANSPORTE_AGGTRADES_V24):
        fallidos = [a for a in tareas if not resultados[a.key].completa]
        if not fallidos:
            break
        print(f"[04B-v24] retry={intento+1} failed={len(fallidos)}", flush=True)
        reintento = _descargar_tareas(tuple(fallidos))
        for key, r in reintento.items():
            if r.completa:
                resultados[key] = r

    flujos = tuple(resultados[a.key] for a in tareas)
    completos = tuple(r for r in flujos if r.completa)
    frac_flows = Decimal(len(completos)) / Decimal(len(tareas))
    bytes_zip = sum(r.bytes_zip for r in completos)
    filas = sum(r.n_filas for r in completos)
    unidades = {
        "milliseconds": sum(1 for r in completos if r.unidad_timestamp == "milliseconds"),
        "microseconds": sum(1 for r in completos if r.unidad_timestamp == "microseconds"),
    }
    print(
        f"[04B-v24] aggtrades complete={len(completos)}/{len(tareas)} fraction={frac_flows} "
        f"size={Decimal(bytes_zip)/Decimal(1024**3):.6f}GiB rows={filas} units={unidades}",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=MAX_WORKERS_SPOT) as pool:
        spot_descargas = list(pool.map(_descargar_spot, UNIVERSO_V24))
    spot_completos = {r.symbol: r.velas for r in spot_descargas if r.completa and r.velas}
    observaciones = construir_observaciones_v24(completos, spot_completos)
    conteo_fecha = {d.isoformat(): 0 for d in FECHAS_FEATURE_V24}
    for o in observaciones:
        conteo_fecha[o.fecha] = conteo_fecha.get(o.fecha, 0) + 1
    fechas_aptas = sum(1 for n in conteo_fecha.values() if n >= MIN_SIMBOLOS_POR_TIMESTAMP_V24)
    frac_fechas = Decimal(fechas_aptas) / Decimal(len(FECHAS_FEATURE_V24))
    print(
        f"[04B-v24] spot complete={len(spot_completos)}/{len(UNIVERSO_V24)} "
        f"observations={len(observaciones)} dates={fechas_aptas}/{len(FECHAS_FEATURE_V24)} "
        f"symbols/date={min(conteo_fecha.values())}-{max(conteo_fecha.values())}",
        flush=True,
    )

    datos_suficientes = (
        frac_flows >= FRACCION_ARCHIVOS_AGGTRADES_COMPLETOS_MIN_V24
        and len(spot_completos) >= MIN_SIMBOLOS_SPOT_COMPLETOS_V24
        and frac_fechas >= FRACCION_FECHAS_CON_MIN_SIMBOLOS_V24
    )
    evaluacion = evaluar_orderflow_v24(observaciones) if datos_suficientes else None
    if not datos_suficientes:
        status = "DATOS_INSUFICIENTES_V24"
    elif evaluacion is not None and evaluacion.apta:
        status = "ORDERFLOW_RESIDUAL_APTO_V24"
    else:
        status = "ORDERFLOW_RESIDUAL_FALSADO_V24"

    fallidos = [r for r in flujos if not r.completa]
    reporte = {
        "status": status,
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "imputacion_permitida": False,
        "permite_invertir_signo": False,
        "permite_ajustar_umbrales_post_resultado": False,
        "permite_cambiar_fechas_post_resultado": False,
        "permite_cambiar_horizonte_post_resultado": False,
        "hurdle_total_bps": HURDLE_TOTAL_BPS_V24,
        "n_archivos_objetivo": len(tareas),
        "n_archivos_completos": len(completos),
        "fraccion_archivos_completos": frac_flows,
        "bytes_zip_completos": bytes_zip,
        "gib_zip_completos": Decimal(bytes_zip) / Decimal(1024**3),
        "n_filas_aggtrades": filas,
        "unidades_timestamp": unidades,
        "n_spot_completos": len(spot_completos),
        "n_observaciones": len(observaciones),
        "n_fechas_aptas": fechas_aptas,
        "fraccion_fechas_aptas": frac_fechas,
        "min_simbolos_fecha": min(conteo_fecha.values()),
        "max_simbolos_fecha": max(conteo_fecha.values()),
        "datos_suficientes": datos_suficientes,
        "fallos_aggtrades_muestra": [
            {"symbol": r.symbol, "fecha": r.fecha.isoformat(), "key": r.key, "error": r.error}
            for r in fallidos[:100]
        ],
        "evaluacion": None if evaluacion is None else {
            "n_timestamps_con_senal": evaluacion.n_timestamps_con_senal,
            "n_meses_con_senal": evaluacion.n_meses_con_senal,
            "n_anios_con_senal": evaluacion.n_anios_con_senal,
            "media_bruta_bps": evaluacion.media_bruta_bps,
            "media_neta_bps": evaluacion.media_neta_bps,
            "media_universo_bps": evaluacion.media_universo_bps,
            "media_precio_only_bps": evaluacion.media_precio_only_bps,
            "media_ofi_crudo_bps": evaluacion.media_ofi_crudo_bps,
            "media_uplift_universo_bps": evaluacion.media_uplift_universo_bps,
            "media_uplift_precio_only_bps": evaluacion.media_uplift_precio_only_bps,
            "media_uplift_ofi_crudo_bps": evaluacion.media_uplift_ofi_crudo_bps,
            "fraccion_timestamps_neto_positivo": evaluacion.fraccion_timestamps_neto_positivo,
            "n_meses_neto_positivo": evaluacion.n_meses_neto_positivo,
            "n_anios_neto_positivo": evaluacion.n_anios_neto_positivo,
            "n_anios_uplift_universo_positivo": evaluacion.n_anios_uplift_universo_positivo,
            "n_anios_uplift_precio_only_positivo": evaluacion.n_anios_uplift_precio_only_positivo,
            "apta": evaluacion.apta,
            "motivos_rechazo": evaluacion.motivos_rechazo,
            "meses": [asdict(x) for x in evaluacion.meses],
            "anios": [asdict(x) for x in evaluacion.anios],
            "timestamps": [asdict(x) for x in evaluacion.timestamps],
        },
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(_jsonable(reporte), indent=2, ensure_ascii=False), encoding="utf-8")

    if evaluacion is None:
        print(f"[04B-v24] {status}: no se emite veredicto economico", flush=True)
    else:
        print(
            f"[04B-v24] {status}: timestamps={evaluacion.n_timestamps_con_senal} "
            f"gross={evaluacion.media_bruta_bps}bps net={evaluacion.media_neta_bps}bps "
            f"universe={evaluacion.media_universo_bps}bps price_only={evaluacion.media_precio_only_bps}bps "
            f"raw_ofi={evaluacion.media_ofi_crudo_bps}bps "
            f"uplift_universe={evaluacion.media_uplift_universo_bps}bps "
            f"uplift_price={evaluacion.media_uplift_precio_only_bps}bps "
            f"uplift_raw_ofi={evaluacion.media_uplift_ofi_crudo_bps}bps",
            flush=True,
        )
        print(
            f"[04B-v24] stability months={evaluacion.n_meses_con_senal} "
            f"positive_months={evaluacion.n_meses_neto_positivo} years={evaluacion.n_anios_con_senal} "
            f"positive_years={evaluacion.n_anios_neto_positivo} "
            f"uplift_universe_years={evaluacion.n_anios_uplift_universo_positivo} "
            f"uplift_price_years={evaluacion.n_anios_uplift_precio_only_positivo}",
            flush=True,
        )
        print(f"[04B-v24] reject_reasons={','.join(evaluacion.motivos_rechazo) or 'ninguno'}", flush=True)
        for a in evaluacion.anios:
            print(
                f"[04B-v24] year={a.periodo} n={a.n_timestamps} net={a.media_neta_bps}bps "
                f"uplift_universe={a.media_uplift_universo_bps}bps "
                f"uplift_price={a.media_uplift_precio_only_bps}bps "
                f"uplift_raw_ofi={a.media_uplift_ofi_crudo_bps}bps",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
