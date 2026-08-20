from decimal import Decimal

import pytest

from backend.economia.edge_historico import vela_desde_kline, velas_desde_klines
from backend.economia.factores_v10 import construir_observaciones_factores_v10

HORA = 60 * 60 * 1000


def kline(i, *, close=None, high=None, low=None, qv="1000", taker_qv="400",
          incluir_taker=True):
    c = Decimal(str(close if close is not None else 100 + i))
    h = Decimal(str(high if high is not None else c + Decimal("2")))
    l = Decimal(str(low if low is not None else c - Decimal("2")))
    t0 = i * 4 * HORA
    base = [
        t0, str(c), str(h), str(l), str(c), "10", t0 + 4 * HORA - 1,
        str(qv), 100 + i,
    ]
    if incluir_taker:
        # campo 9 = taker buy base, campo 10 = taker buy quote.
        base.extend(["4", str(taker_qv), "0"])
    return base


def serie(n=20, **kw):
    return velas_desde_klines([kline(i, **kw) for i in range(n)])


def test_parser_conserva_taker_buy_y_ausente_permanece_none():
    v = vela_desde_kline(kline(0, qv="1000", taker_qv="375"))
    assert v.taker_buy_base_volume == Decimal("4")
    assert v.taker_buy_quote_volume == Decimal("375")

    sin = vela_desde_kline(kline(0, incluir_taker=False))
    assert sin.taker_buy_base_volume is None
    assert sin.taker_buy_quote_volume is None


def test_parser_rechaza_taker_buy_mayor_que_volumen_total():
    with pytest.raises(ValueError, match="taker-buy no puede exceder"):
        vela_desde_kline(kline(0, qv="1000", taker_qv="1001"))


def test_factores_v10_se_calculan_solo_con_ultimas_24h_conocidas():
    obs = construir_observaciones_factores_v10({"BTCUSDT": serie()})
    assert obs
    o = obs[0]  # t = barra i=6
    e = o.estado

    assert e.close == Decimal("106")
    assert e.retorno_24h == Decimal("106") / Decimal("100") - Decimal("1")

    retornos = tuple(
        Decimal(str(100 + j)) / Decimal(str(100 + j - 1)) - Decimal("1")
        for j in range(1, 7)
    )
    vol = sum((r * r for r in retornos), Decimal("0")).sqrt()
    assert e.volatilidad_realizada_24h == vol
    assert e.momentum_ajustado_riesgo_24h == e.retorno_24h / vol
    assert e.max_retorno_4h_24h == max(retornos)

    # Barras i=1..6: low minimo 99, high maximo 108, close 106.
    assert e.posicion_cierre_rango_24h == Decimal("7") / Decimal("9")
    assert e.taker_buy_share_24h == Decimal("0.4")


def test_taker_buy_desconocido_no_se_convierte_en_cero():
    obs = construir_observaciones_factores_v10({
        "BTCUSDT": serie(incluir_taker=False),
    })
    assert obs == ()


def test_serie_completamente_plana_falla_cerrado_por_volatilidad_cero():
    filas = [
        kline(i, close="100", high="101", low="99")
        for i in range(20)
    ]
    obs = construir_observaciones_factores_v10({
        "BTCUSDT": velas_desde_klines(filas),
    })
    assert obs == ()


def test_cambiar_futuro_no_contamina_estado_v10_pero_si_label():
    base = [kline(i) for i in range(20)]
    alterada = [list(f) for f in base]
    # Primera observacion v10 cierra en i=6. i=10 pertenece solo al futuro 24h.
    alterada[10] = kline(10, close="500", high="505", low="495")

    a = construir_observaciones_factores_v10({
        "BTCUSDT": velas_desde_klines(base),
    })[0]
    b = construir_observaciones_factores_v10({
        "BTCUSDT": velas_desde_klines(alterada),
    })[0]

    assert a.estado == b.estado
    assert a.etiqueta(24) != b.etiqueta(24)


def test_parametros_fuera_del_protocolo_v10_se_rechazan():
    velas = serie()
    with pytest.raises(ValueError, match="velas 4h"):
        construir_observaciones_factores_v10({"BTCUSDT": velas}, intervalo_horas=1)
    with pytest.raises(ValueError, match="horizonte exclusivamente"):
        construir_observaciones_factores_v10({"BTCUSDT": velas}, horizonte_horas=48)
