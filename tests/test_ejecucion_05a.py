from decimal import Decimal

from backend.economia.ejecucion_05a import comparar_ejecucion, extraer_maker_bps


def test_extraer_maker_bps_usa_campo_explicito():
    cuenta = {"commissionRates": {"maker": "0.0008", "taker": "0.0010"}}
    assert extraer_maker_bps(cuenta) == Decimal("8.0000")


def test_extraer_maker_bps_desconocido_no_es_cero():
    assert extraer_maker_bps({}) is None
    assert extraer_maker_bps({"commissionRates": {"maker": "x"}}) is None
    assert extraer_maker_bps({"commissionRates": {"maker": "-0.001"}}) is None


def test_comparacion_separa_fee_y_microfriccion():
    c = comparar_ejecucion(
        fee_taker_bps_por_lado=10,
        fee_maker_bps_por_lado=8,
        spread_bps=1,
        slippage_bps_por_lado=0.25,
    )
    assert c.estado == "DISPONIBLE"
    assert c.coste_taker_roundtrip_bps == 21.5
    assert c.coste_maker_fee_only_roundtrip_bps == 16.0
    assert c.ahorro_fee_roundtrip_bps == 4.0
    assert c.microfriccion_taker_bps == 1.5
    assert c.ahorro_maximo_teorico_bps == 5.5
    assert c.maker_es_estimacion_ejecutable is False


def test_comparacion_falla_cerrado_si_falta_maker():
    c = comparar_ejecucion(
        fee_taker_bps_por_lado=10,
        fee_maker_bps_por_lado=None,
        spread_bps=1,
        slippage_bps_por_lado=0.2,
    )
    assert c.estado == "NO_EVALUABLE"
    assert c.coste_taker_roundtrip_bps is None
    assert c.ahorro_maximo_teorico_bps is None
