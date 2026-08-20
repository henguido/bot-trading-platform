#!/usr/bin/env python3
"""BOT 2.0-04B-v21: prueba OI + taker pressure -> Spot 8h, 2022-2025."""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.economia.evaluacion_posicionamiento_v21 import (
    evaluar_posicionamiento_v21,
    retornos_spot_open_a_open_v21,
)
from backend.economia.historico_binance import descargar_klines_data_api
from backend.economia.historico_posicionamiento_v20 import listar_metricas_v20
from backend.economia.posicionamiento_v21 import descargar_ventanas_archivo_v21
from backend.economia.protocolo_posicionamiento_v21 import (
    DESARROLLO_2026_ABIERTO_V21,
    DESDE_V21,
    FRACCION_ARCHIVOS_METRICAS_COMPLETOS_MIN_V21,
    HASTA_EXCLUSIVO_V21,
    HURDLE_TOTAL_BPS_V21,
    IMPUTACION_PERMITIDA_V21,
    INTERVALO_SPOT_V21,
    MIN_SIMBOLOS_SPOT_COMPLETOS_V21,
    PERMITE_AJUSTAR_UMBRALES_POST_RESULTADO_V21,
    PERMITE_INVERTIR_SIGNO_V21,
    TEST_MAY_JUL_ABIERTO_V21,
    UNIVERSO_V21,
)

SALIDA = RAIZ / "artifacts" / "positioning-v21-desarrollo-2022-2025.json"
MAX_WORKERS_LISTADO = 8
MAX_WORKERS_METRICAS = 32
MAX_WORKERS_SPOT = 8
REINTENTOS_TRANSPORTE_METRICAS = 1
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
        sesion.headers.update({"User-Agent": "bot-trading-platform-research-v21/1.0"})
        _LOCAL.session = sesion
    return sesion.get(url, **kwargs)


def _descargar_archivo(a):
    return descargar_ventanas_archivo_v21(a, http_get=_http_get)


def _descargar_spot(symbol: str):
    inicio_ms = int(DESDE_V21.timestamp() * 1000)
    # Incluye open(2026-01-01 00:00) solo como precio de salida del último T 2025.
    fin_ms = int(HASTA_EXCLUSIVO_V21.timestamp() * 1000)
    return descargar_klines_data_api(
        symbol,
        interval=INTERVALO_SPOT_V21,
        start_ms=inicio_ms,
        end_ms=fin_ms,
        limit=1000,
    )


def main() -> int:
    assert DESARROLLO_2026_ABIERTO_V21 is False
    assert TEST_MAY_JUL_ABIERTO_V21 is False
    assert IMPUTACION_PERMITIDA_V21 is False
    assert PERMITE_INVERTIR_SIGNO_V21 is False
    assert PERMITE_AJUSTAR_UMBRALES_POST_RESULTADO_V21 is False
    assert HASTA_EXCLUSIVO_V21.year == 2026 and HASTA_EXCLUSIVO_V21.month == 1

    print(
        f"[04B-v21] start symbols={len(UNIVERSO_V21)} period=2022-2025 "
        f"hurdle={HURDLE_TOTAL_BPS_V21}bps 2026_OPEN=False"
    )

    # 1) Inventario completo del archivo público, sin retornos.
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_LISTADO) as pool:
        resultados_listado = list(pool.map(
            lambda s: listar_metricas_v20(s, http_get=_http_get),
            UNIVERSO_V21,
        ))
    listados_completos = [r for r in resultados_listado if r.completa]
    archivos = [a for r in listados_completos for a in r.archivos]
    print(
        f"[04B-v21] archive listings={len(listados_completos)}/{len(UNIVERSO_V21)} "
        f"files={len(archivos)}"
    )

    # 2) Descarga/parseo de cada ZIP diario. Un retry técnico; no modifica datos.
    resultados_por_key = {}
    if archivos:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS_METRICAS) as pool:
            for r in pool.map(_descargar_archivo, archivos):
                resultados_por_key[r.key] = r
        for _ in range(REINTENTOS_TRANSPORTE_METRICAS):
            fallidos = [a for a in archivos if not resultados_por_key[a.key].completa]
            if not fallidos:
                break
            with ThreadPoolExecutor(max_workers=MAX_WORKERS_METRICAS) as pool:
                for r in pool.map(_descargar_archivo, fallidos):
                    if r.completa:
                        resultados_por_key[r.key] = r

    resultados_metricas = [resultados_por_key[a.key] for a in archivos if a.key in resultados_por_key]
    completos_metricas = [r for r in resultados_metricas if r.completa]
    frac_archivos = (
        Decimal(len(completos_metricas)) / Decimal(len(archivos)) if archivos else Decimal("0")
    )
    features = [v for r in completos_metricas for v in r.ventanas]
    print(
        f"[04B-v21] metrics complete={len(completos_metricas)}/{len(archivos)} "
        f"fraction={frac_archivos} features={len(features)}"
    )

    # 3) Etiquetas Spot futuras se descargan después de que la regla ya está fija.
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_SPOT) as pool:
        descargas_spot = list(pool.map(_descargar_spot, UNIVERSO_V21))
    spot_completos = {
        r.symbol: r.velas for r in descargas_spot if r.completa and len(r.velas) > 0
    }
    retornos_spot = retornos_spot_open_a_open_v21(spot_completos)
    print(
        f"[04B-v21] spot complete={len(spot_completos)}/{len(UNIVERSO_V21)} "
        f"labels={len(retornos_spot)}"
    )

    datos_suficientes = (
        len(listados_completos) == len(UNIVERSO_V21)
        and frac_archivos >= FRACCION_ARCHIVOS_METRICAS_COMPLETOS_MIN_V21
        and len(spot_completos) >= MIN_SIMBOLOS_SPOT_COMPLETOS_V21
    )

    evaluacion = evaluar_posicionamiento_v21(features, retornos_spot) if datos_suficientes else None
    if not datos_suficientes:
        status = "DATOS_INSUFICIENTES_V21"
    elif evaluacion is not None and evaluacion.apta:
        status = "SENAL_OI_TAKER_APTA_V21"
    else:
        status = "SENAL_OI_TAKER_FALSADA_V21"

    fallidos = [r for r in resultados_metricas if not r.completa]
    reporte = {
        "status": status,
        "desarrollo_2026_open": False,
        "test_may_jul_open": False,
        "imputacion_permitida": False,
        "permite_invertir_signo": False,
        "permite_ajustar_umbrales_post_resultado": False,
        "periodo": [DESDE_V21.isoformat(), HASTA_EXCLUSIVO_V21.isoformat()],
        "hurdle_total_bps": HURDLE_TOTAL_BPS_V21,
        "n_listados_completos": len(listados_completos),
        "n_archivos_objetivo": len(archivos),
        "n_archivos_metricas_completos": len(completos_metricas),
        "fraccion_archivos_metricas_completos": frac_archivos,
        "n_archivos_metricas_fallidos": len(fallidos),
        "n_features": len(features),
        "n_spot_completos": len(spot_completos),
        "n_labels_spot": len(retornos_spot),
        "datos_suficientes": datos_suficientes,
        "fallos_metricas_muestra": [
            {"symbol": r.symbol, "fecha": r.fecha, "key": r.key, "error": r.error}
            for r in fallidos[:100]
        ],
        "listados_fallidos": [
            {"symbol": r.symbol, "error": r.error, "n_requests": r.n_requests}
            for r in resultados_listado if not r.completa
        ],
        "spot_fallidos": [
            {"symbol": r.symbol, "error": r.error, "n_requests": r.n_requests}
            for r in descargas_spot if not (r.completa and len(r.velas) > 0)
        ],
        "evaluacion": None if evaluacion is None else {
            "n_timestamps_con_senal": evaluacion.n_timestamps_con_senal,
            "n_meses_con_senal": evaluacion.n_meses_con_senal,
            "n_anios_con_senal": evaluacion.n_anios_con_senal,
            "media_bruta_bps": evaluacion.media_bruta_bps,
            "media_neta_bps": evaluacion.media_neta_bps,
            "media_baseline_bps": evaluacion.media_baseline_bps,
            "media_uplift_bps": evaluacion.media_uplift_bps,
            "fraccion_timestamps_neto_positivo": evaluacion.fraccion_timestamps_neto_positivo,
            "n_meses_neto_positivo": evaluacion.n_meses_neto_positivo,
            "n_anios_neto_positivo": evaluacion.n_anios_neto_positivo,
            "n_anios_uplift_positivo": evaluacion.n_anios_uplift_positivo,
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
        print(f"[04B-v21] {status}: no se emite veredicto económico")
    else:
        print(
            f"[04B-v21] {status}: timestamps={evaluacion.n_timestamps_con_senal} "
            f"gross={evaluacion.media_bruta_bps}bps net={evaluacion.media_neta_bps}bps "
            f"baseline={evaluacion.media_baseline_bps}bps uplift={evaluacion.media_uplift_bps}bps "
            f"positive_ts={evaluacion.fraccion_timestamps_neto_positivo}"
        )
        print(
            f"[04B-v21] stability months={evaluacion.n_meses_con_senal} "
            f"positive_months={evaluacion.n_meses_neto_positivo} years={evaluacion.n_anios_con_senal} "
            f"positive_years={evaluacion.n_anios_neto_positivo} "
            f"uplift_positive_years={evaluacion.n_anios_uplift_positivo}"
        )
        print(f"[04B-v21] reject_reasons={','.join(evaluacion.motivos_rechazo) or 'ninguno'}")
        for a in evaluacion.anios:
            print(
                f"[04B-v21] year={a.periodo} n={a.n_timestamps} "
                f"net={a.media_neta_bps}bps uplift={a.media_uplift_bps}bps"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
