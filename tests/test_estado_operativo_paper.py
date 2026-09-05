from backend.config import settings
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
    assert salida["paper_execution_model"] == "ORDER_BOOK_VWAP_SLIPPAGE_FEE_VERIFICABLE"
    assert salida["paper_fee_policy"] == (
        "TAKER_FEE_SOLO_CON_FUENTE_VERIFICABLE; DESCONOCIDO_NO_ES_CERO"
    )
    assert salida["paper_ledger_source"] == "PAPER_OPERACIONES"

    limites = salida["limites_riesgo"]
    asignacion = settings.LIMITE_ASIGNACION_POR_OPERACION
    esperado_efectivo = min(
        settings.MONTO_MAXIMO_USDT,
        estado.capital_usd * asignacion,
        estado.capital_usd,
        settings.MAX_EXPOSICION_TOTAL_USDT - estado.exposicion_coste_usd,
    )
    assert limites["asignacion_maxima_por_operacion_pct"] == asignacion * 100.0
    assert limites["monto_maximo_por_operacion_usd"] == esperado_efectivo
    assert limites["monto_maximo_configurado_por_operacion_usd"] == settings.MONTO_MAXIMO_USDT
    assert limites["monto_maximo_por_operacion_es_cota_pre_activo"] is True
    assert limites["perdida_realizada_diaria_maxima_usd"] == settings.MAX_DAILY_LOSS_USDT
    assert limites["exposicion_total_maxima_usd"] == settings.MAX_EXPOSICION_TOTAL_USDT
    assert limites["exposicion_por_activo_maxima_usd"] == settings.MAX_EXPOSICION_POR_ACTIVO_USDT
    assert limites["timezone_dia_riesgo"] == settings.RISK_TIMEZONE


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
    assert salida["profitability_gate_05e_status"] == "APAGADO_EVIDENCIA_OOS_INSUFICIENTE"
    assert "DESCONOCIDO_NO_ES_CERO" in salida["paper_fee_policy"]
    assert any("05E apagado por seguridad" in mensaje for mensaje in salida["mensajes"])
    assert len(salida["mensajes"]) >= 2


def test_tope_operacion_disminuye_con_capital_disponible_y_no_supera_hard_cap():
    estado = EstadoPaper(
        initial_capital_usd=500.0,
        capital_usd=456.95,
        posiciones={},
        realized_pnl_usd=0.0,
    )

    salida = construir_estado_operativo(
        estado=estado,
        valoracion_completa=True,
        estrategias_paper={"estrategias": {}},
    )

    limites = salida["limites_riesgo"]
    assert limites["monto_maximo_por_operacion_usd"] == 456.95 * settings.LIMITE_ASIGNACION_POR_OPERACION
    assert limites["monto_maximo_por_operacion_usd"] < limites["monto_maximo_configurado_por_operacion_usd"]
