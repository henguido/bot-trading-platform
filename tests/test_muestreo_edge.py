"""Pruebas de la rejilla temporal no solapada para Expected Edge."""
from decimal import Decimal

import pytest

from backend.economia.edge_historico import EstadoHistorico, EtiquetaHorizonte, ObservacionEdge
from backend.economia.muestreo_edge import submuestrear_no_solapado
from backend.economia.validacion_edge import HORA_MS


def obs(symbol: str, cierre_hora: int, h: int = 4) -> ObservacionEdge:
    # close_time Binance: un ms antes del limite horario.
    t = cierre_hora * HORA_MS - 1
    estado = EstadoHistorico(
        symbol=symbol, timestamp_ms=t, close=Decimal("100"),
        quote_volume_24h=Decimal("1000"), trades_24h=100,
        rango_24h=Decimal("0.03"), momentum_cierre_24h_pct=Decimal("1"),
    )
    return ObservacionEdge(
        estado=estado,
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=h,
            retorno_cierre=Decimal("0.01"),
            mfe=Decimal("0.02"), mae=Decimal("-0.01")),),
    )


def test_h4_conserva_4_8_12_y_todos_los_simbolos_del_timestamp():
    datos = []
    for hora in range(1, 13):
        datos.extend((obs("BTCUSDT", hora), obs("ETHUSDT", hora)))
    salida = submuestrear_no_solapado(datos, horizonte_horas=4)
    horas = [(o.estado.timestamp_ms + 1) // HORA_MS for o in salida]
    assert sorted(set(horas)) == [4, 8, 12]
    assert len(salida) == 6
    assert {o.estado.symbol for o in salida if horas[salida.index(o)] == 4} == {"BTCUSDT", "ETHUSDT"}


def test_ventanas_consecutivas_no_se_solapan():
    datos = [obs("BTCUSDT", hora) for hora in range(1, 25)]
    salida = submuestrear_no_solapado(datos, horizonte_horas=4)
    horas = [(o.estado.timestamp_ms + 1) // HORA_MS for o in salida]
    assert horas == [4, 8, 12, 16, 20, 24]
    assert all(b - a == 4 for a, b in zip(horas, horas[1:]))


def test_fase_es_explicita_y_determinista():
    datos = [obs("BTCUSDT", hora) for hora in range(1, 13)]
    a = submuestrear_no_solapado(datos, horizonte_horas=4, fase_horas=1)
    b = submuestrear_no_solapado(reversed(datos), horizonte_horas=4, fase_horas=1)
    assert a == b
    assert [(o.estado.timestamp_ms + 1) // HORA_MS for o in a] == [1, 5, 9]


def test_timestamp_no_alineado_falla_no_se_redondea():
    o = obs("BTCUSDT", 4)
    roto = ObservacionEdge(
        estado=EstadoHistorico(
            symbol=o.estado.symbol, timestamp_ms=o.estado.timestamp_ms - 100,
            close=o.estado.close, quote_volume_24h=o.estado.quote_volume_24h,
            trades_24h=o.estado.trades_24h, rango_24h=o.estado.rango_24h,
            momentum_cierre_24h_pct=o.estado.momentum_cierre_24h_pct),
        etiquetas=o.etiquetas)
    with pytest.raises(ValueError, match="no alineado"):
        submuestrear_no_solapado([roto], horizonte_horas=4)


@pytest.mark.parametrize("h,fase", [(0, 0), (4.5, 0), (4, -1), (4, 4), (4, True)])
def test_parametros_invalidos_fallan_cerrado(h, fase):
    with pytest.raises(ValueError):
        submuestrear_no_solapado([obs("BTCUSDT", 4)],
                                  horizonte_horas=h, fase_horas=fase)
