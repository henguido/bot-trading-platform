from types import SimpleNamespace

import pytest

import backend.economia.integracion_05e as integ


class BinanceQueNoDebeUsarse:
    def __getattr__(self, nombre):
        raise AssertionError(f"binance no debe usarse con 05E desactivado: {nombre}")


def test_05e_desactivado_no_cambia_candidatos_ni_hace_red():
    activos = [
        {"symbol": "BTCUSDT", "_position_detected": False},
        {"symbol": "ETHUSDT", "_position_detected": True},
    ]

    r = integ.aplicar_pre_llm_05e(
        activos,
        {},
        fee_taker_bps_por_lado=10.0,
        notional_por_symbol={},
        binance=BinanceQueNoDebeUsarse(),
        enabled=False,
        modo_real=False,
    )

    assert r.aplicado is False
    assert list(r.activos) == activos
    assert r.evaluaciones == {}
    assert r.motivo == "DESACTIVADO_PENDIENTE_EVIDENCIA_OOS"


def test_05e_activo_bloquea_live():
    with pytest.raises(RuntimeError, match="LIVE"):
        integ.aplicar_pre_llm_05e(
            [],
            {},
            fee_taker_bps_por_lado=10.0,
            notional_por_symbol={},
            binance=object(),
            enabled=True,
            modo_real=True,
        )


def test_05e_activo_delega_al_filtro_paper(monkeypatch):
    evaluacion = {"rentabilidad": SimpleNamespace(apta=True)}

    def fake_filtro(activos, metricas, **kwargs):
        assert kwargs["fee_taker_bps_por_lado"] == 10.0
        return [activos[0]], {"BTCUSDT": evaluacion}

    monkeypatch.setattr(integ, "filtrar_compras_rentables", fake_filtro)
    activos = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
    r = integ.aplicar_pre_llm_05e(
        activos,
        {"BTCUSDT": {}},
        fee_taker_bps_por_lado=10.0,
        notional_por_symbol={"BTCUSDT": 10.0},
        binance=object(),
        enabled=True,
        modo_real=False,
    )

    assert r.aplicado is True
    assert [a["symbol"] for a in r.activos] == ["BTCUSDT"]
    assert r.evaluaciones["BTCUSDT"] is evaluacion


def test_post_llm_desactivado_no_bloquea_compra():
    permitido, motivo = integ.compra_post_llm_permitida_05e(
        "BTCUSDT", {}, enabled=False
    )
    assert permitido is True
    assert motivo == "DESACTIVADO_PENDIENTE_EVIDENCIA_OOS"


def test_post_llm_activo_exige_rentabilidad_apta():
    permitido, motivo = integ.compra_post_llm_permitida_05e(
        "BTCUSDT", {}, enabled=True
    )
    assert permitido is False
    assert motivo == "SIN_EVALUACION_RENTABILIDAD"

    permitido, motivo = integ.compra_post_llm_permitida_05e(
        "BTCUSDT",
        {"BTCUSDT": {"rentabilidad": SimpleNamespace(apta=False)}},
        enabled=True,
    )
    assert permitido is False
    assert motivo == "RENTABILIDAD_NO_APTA"

    permitido, motivo = integ.compra_post_llm_permitida_05e(
        "BTCUSDT",
        {"BTCUSDT": {"rentabilidad": SimpleNamespace(apta=True)}},
        enabled=True,
    )
    assert permitido is True
    assert motivo == "RENTABILIDAD_APTA"
