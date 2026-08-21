import io
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.economia.edge_historico import Vela
from backend.economia.evaluacion_orderflow_v24 import (
    ObservacionV24,
    construir_observaciones_v24,
    evaluar_orderflow_v24,
)
from backend.economia.orderflow_v24 import archivo_v24, resumir_aggtrades_v24
from backend.economia.protocolo_orderflow_v24 import (
    DESARROLLO_2026_ABIERTO_V24,
    FECHAS_FEATURE_V24,
    HORIZONTE_RETORNO_DIAS_V24,
    HURDLE_TOTAL_BPS_V24,
    IMPUTACION_PERMITIDA_V24,
    PERMITE_AJUSTAR_UMBRALES_POST_RESULTADO_V24,
    PERMITE_CAMBIAR_FECHAS_POST_RESULTADO_V24,
    PERMITE_CAMBIAR_HORIZONTE_POST_RESULTADO_V24,
    PERMITE_INVERTIR_SIGNO_V24,
    TEST_MAY_JUL_ABIERTO_V24,
    UNIVERSO_V24,
)


def _zip_csv(texto: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sample.csv", texto)
    return out.getvalue()


def _ts_ms(d: date, segundos=0):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000) + segundos * 1000


def _vela(ts, open_):
    d = Decimal(str(open_))
    return Vela(ts, d, d, d, d, Decimal("1"), ts + 1, d, 1)


def test_v24_candados_y_calendario_permanecen_fijos():
    assert len(UNIVERSO_V24) == 20
    assert len(FECHAS_FEATURE_V24) == 96
    assert HORIZONTE_RETORNO_DIAS_V24 == 7
    assert HURDLE_TOTAL_BPS_V24 == Decimal("25")
    assert PERMITE_INVERTIR_SIGNO_V24 is False
    assert PERMITE_AJUSTAR_UMBRALES_POST_RESULTADO_V24 is False
    assert PERMITE_CAMBIAR_FECHAS_POST_RESULTADO_V24 is False
    assert PERMITE_CAMBIAR_HORIZONTE_POST_RESULTADO_V24 is False
    assert IMPUTACION_PERMITIDA_V24 is False
    assert DESARROLLO_2026_ABIERTO_V24 is False
    assert TEST_MAY_JUL_ABIERTO_V24 is False


def test_parser_v24_reconstruye_lado_agresor_y_ofi_en_ms():
    d = date(2024, 6, 3)
    t = _ts_ms(d)
    csv = "\n".join([
        f"1,100,2,10,10,{t},false,true",
        f"2,100,1,11,11,{t+1000},true,true",
    ])
    r = resumir_aggtrades_v24(archivo_v24("BTCUSDT", d), _zip_csv(csv))
    assert r.completa is True
    assert r.unidad_timestamp == "milliseconds"
    assert r.taker_buy_quote == Decimal("200")
    assert r.taker_sell_quote == Decimal("100")
    assert r.ofi == Decimal("1") / Decimal("3")


def test_parser_v24_acepta_header_y_microsegundos_spot_2025():
    d = date(2025, 6, 2)
    t_us = _ts_ms(d) * 1000
    csv = "\n".join([
        "aggTradeId,price,quantity,firstTradeId,lastTradeId,timestamp,isBuyerMaker,isBestMatch",
        f"1,10,1,1,1,{t_us},false,true",
        f"2,10,1,2,2,{t_us+1000},true,false",
    ])
    r = resumir_aggtrades_v24(archivo_v24("ETHUSDT", d), _zip_csv(csv))
    assert r.completa is True
    assert r.unidad_timestamp == "microseconds"
    assert r.ofi == Decimal("0")


def test_construccion_v24_entra_despues_del_lunes_y_sale_siete_dias_despues():
    d = date(2024, 6, 3)
    t = _ts_ms(d)
    flujo = resumir_aggtrades_v24(
        archivo_v24("BTCUSDT", d),
        _zip_csv(f"1,100,1,1,1,{t},false,true"),
    )
    velas = {
        "BTCUSDT": (
            _vela(t, 100),
            _vela(t + 24 * 60 * 60 * 1000, 110),
            _vela(t + 8 * 24 * 60 * 60 * 1000, 121),
        )
    }
    obs = construir_observaciones_v24((flujo,), velas)
    assert len(obs) == 1
    assert obs[0].retorno_contemporaneo == Decimal("0.1")
    assert obs[0].retorno_futuro == Decimal("0.1")


def test_evaluacion_v24_pasa_caso_sintetico_con_edge_residual_estable():
    observaciones = []
    for fecha in FECHAS_FEATURE_V24:
        q = []
        for i, symbol in enumerate(UNIVERSO_V24):
            x = Decimal(i) - Decimal("9.5")
            q.append(x * x)
        media_q = sum(q, Decimal("0")) / Decimal(len(q))
        for i, symbol in enumerate(UNIVERSO_V24):
            r0 = (Decimal(i) - Decimal("9.5")) / Decimal("1000")
            residual = (q[i] - media_q) / Decimal("1000")
            ofi = Decimal("2") * r0 + residual
            futuro = Decimal("0.01") if i in {0, 1, 2, 17, 18, 19} else Decimal("-0.002")
            observaciones.append(
                ObservacionV24(symbol, fecha.isoformat(), ofi, r0, futuro)
            )
    e = evaluar_orderflow_v24(tuple(observaciones))
    assert e.n_timestamps_con_senal == 96
    assert e.n_meses_con_senal == 48
    assert e.n_anios_con_senal == 4
    assert e.media_neta_bps > 0
    assert e.media_uplift_universo_bps > 0
    assert e.media_uplift_precio_only_bps > 0
    assert e.n_anios_neto_positivo == 4
    assert e.apta is True
    assert e.motivos_rechazo == ()


def test_evaluacion_v24_falsa_senal_sin_edge_aunque_haya_datos():
    observaciones = []
    fecha = FECHAS_FEATURE_V24[0]
    for i, symbol in enumerate(UNIVERSO_V24):
        r0 = Decimal(i) / Decimal("1000")
        ofi = r0 + (Decimal(i % 3) - Decimal("1")) / Decimal("10000")
        observaciones.append(ObservacionV24(symbol, fecha.isoformat(), ofi, r0, Decimal("0")))
    e = evaluar_orderflow_v24(tuple(observaciones))
    assert e.apta is False
    assert "MEDIA_NETA_NO_POSITIVA" in e.motivos_rechazo
