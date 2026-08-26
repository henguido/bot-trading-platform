from backend.simulation.estado_operativo import construir_estado_operativo
from backend.simulation.paper_ledger import EstadoPaper, PosicionPaper


def test_estado_operativo_deriva_capital_motor_y_evidencia_sin_red():
    estado = EstadoPaper(
        initial_capital_usd=500.0,
        capital_usd=470.0,
        posiciones={
            "BTCUSDT": PosicionPaper(cantidad=0.2, coste_medio_neto=100.0),
            "ETHUSDT": PosicionPaper(cantidad=0.1, coste_medio_neto=100.0),
        },
        realized_pnl_usd=5.0,
        fees_total_usd=0.25,
        operaciones=4,
    )
    estrategias = {
        "estrategias": {
            "SCANNER_A": {"cierres": 2},
            "SCANNER_B": {"cierres": 0},
        }
    }

    salida = construir_estado_operativo(
        estado=estado,
        valoracion_completa=True,
        estrategias_paper=estrategias,
    )

    assert salida["modo"] == "PAPER"
    assert salida["live_orders_enabled"] is False
    assert salida["capital_inicial_usd"] == 500.0
    assert salida["capital_disponible_usd"] == 470.0
    assert salida["capital_desplegado_usd"] == 30.0
    assert salida["capital_desplegado_pct"] == 6.0
    assert salida["retorno_realizado_pct"] == 1.0
    assert salida["estrategias_con_cierres"] == 1
    assert salida["cierres_atribuidos"] == 2
    assert salida["evidencia_estrategias_status"] == "DISPONIBLE"
    assert salida["paper_execution_model"] == "ORDER_BOOK_VWAP_TAKER_FEE"
    assert salida["paper_ledger_source"] == "PAPER_OPERACIONES"


def test_estado_operativo_declara_incertidumbre_y_no_inventa_evidencia():
    estado = EstadoPaper(
        initial_capital_usd=500.0,
        capital_usd=500.0,
        posiciones={},
        realized_pnl_usd=0.0,
    )

    salida = construir_estado_operativo(
        estado=estado,
        valoracion_completa=False,
        estrategias_paper={"estrategias": {}},
    )

    assert salida["valoracion_completa"] is False
    assert salida["cierres_atribuidos"] == 0
    assert salida["evidencia_estrategias_status"] == "SIN_CIERRES_REALIZADOS"
    assert salida["profitability_gate_05e_enabled"] is False
    assert salida["profitability_gate_05e_status"] == "PENDIENTE_EVIDENCIA_OOS"
    assert len(salida["mensajes"]) >= 2
