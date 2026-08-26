from decimal import Decimal

from backend.economia.ejecucion_paper import (
    calcular_fill_compra,
    calcular_fill_venta,
)


def test_compra_paper_cammina_asks_y_suma_fee_al_efectivo_consumido():
    book = {
        "asks": [["100", "0.05"], ["101", "1"]],
        "bids": [["99", "1"]],
    }
    fill = calcular_fill_compra(
        order_book=book,
        quote_amount="10",
        fee_taker_bps_por_lado="10",
    )
    assert fill.completo is True
    assert fill.precio_vwap > Decimal("100")
    assert fill.slippage_bps > 0
    assert fill.quote_bruto == Decimal("10.00")
    assert fill.fee_usd == Decimal("0.01000")
    assert fill.quote_neto == Decimal("10.01000")


def test_venta_paper_cammina_bids_y_resta_fee_del_efectivo_recibido():
    book = {
        "bids": [["100", "0.05"], ["99", "1"]],
        "asks": [["101", "1"]],
    }
    fill = calcular_fill_venta(
        order_book=book,
        base_quantity="0.10",
        fee_taker_bps_por_lado="10",
    )
    assert fill.completo is True
    assert fill.precio_vwap < Decimal("100")
    assert fill.slippage_bps > 0
    assert fill.quote_bruto == Decimal("9.950")
    assert fill.fee_usd == Decimal("0.009950")
    assert fill.quote_neto == Decimal("9.940050")


def test_fill_paper_falla_cerrado_si_no_hay_profundidad_suficiente():
    fill = calcular_fill_compra(
        order_book={"asks": [["100", "0.01"]]},
        quote_amount="10",
        fee_taker_bps_por_lado="10",
    )
    assert fill.completo is False
    assert fill.base_ejecutada is None
    assert fill.quote_neto is None


def test_fee_desconocida_no_se_interpreta_como_cero():
    try:
        calcular_fill_venta(
            order_book={"bids": [["100", "1"]]},
            base_quantity="0.1",
            fee_taker_bps_por_lado=None,
        )
    except ValueError as exc:
        assert "fee_taker_bps_por_lado" in str(exc)
    else:
        raise AssertionError("fee desconocida debe fallar cerrado")


def test_compra_paper_cuantiza_base_al_step_antes_del_vwap():
    fill = calcular_fill_compra(
        order_book={"asks": [["100", "1"]]},
        quote_amount="10",
        fee_taker_bps_por_lado="10",
        step_size="0.03",
        min_qty="0.03",
        max_qty="10",
        min_notional="5",
    )

    # 10 / 100 = 0.10 base, pero Binance solo admitiría múltiplos de 0.03.
    # PAPER debe ejecutar 0.09 y dejar el remanente en caja, no inventar 0.10.
    assert fill.completo is True
    assert fill.base_ejecutada == Decimal("0.090000")
    assert fill.quote_bruto == Decimal("9.000000")
    assert fill.fee_usd == Decimal("0.009000000")
    assert fill.quote_neto == Decimal("9.009000000")


def test_compra_paper_rechaza_notional_inferior_al_exchange():
    fill = calcular_fill_compra(
        order_book={"asks": [["100", "1"]]},
        quote_amount="4.99",
        fee_taker_bps_por_lado="10",
        step_size="0.001",
        min_qty="0.001",
        max_qty="10",
        min_notional="5",
    )

    assert fill.completo is False
    assert fill.motivo == "MIN_NOTIONAL_INALCANZABLE"
    assert fill.base_ejecutada is None
    assert fill.quote_neto is None


def test_venta_paper_cuantiza_base_al_step_antes_de_caminar_bids():
    fill = calcular_fill_venta(
        order_book={"bids": [["100", "1"]]},
        base_quantity="0.10",
        fee_taker_bps_por_lado="10",
        step_size="0.03",
        min_qty="0.03",
        max_qty="10",
        min_notional="5",
    )

    assert fill.completo is True
    assert fill.base_ejecutada == Decimal("0.090000")
    assert fill.quote_bruto == Decimal("9.000000")
    assert fill.fee_usd == Decimal("0.009000000")
    assert fill.quote_neto == Decimal("8.991000000")


def test_step_que_deja_cantidad_cero_falla_cerrado():
    fill = calcular_fill_venta(
        order_book={"bids": [["100", "1"]]},
        base_quantity="0.01",
        fee_taker_bps_por_lado="10",
        step_size="0.03",
        min_qty="0.03",
        max_qty="10",
        min_notional="5",
    )

    assert fill.completo is False
    assert fill.motivo == "LOT_SIZE_CANTIDAD_CERO"
    assert fill.quote_neto is None
