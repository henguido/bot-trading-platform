from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services.ordenes import Lado
from backend.economia.estadisticas_paper import resumen_por_estrategia
from backend.portafolio.carteras import CarteraPaper
from backend.risk.motor import DecisionRiesgo


RAIZ = Path(__file__).resolve().parents[1]


def _fabrica_con_usuario():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    fabrica = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with fabrica() as db:
        user = models.User(nombre="econ", email="econ@test.local", password_hash="x")
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = user.id
    return engine, fabrica, uid


def _symbol_info(*, step="0.001", min_qty="0.001", max_qty="10", min_notional="5"):
    return {
        "symbol": "BTCUSDT",
        "status": "TRADING",
        "isSpotTradingAllowed": True,
        "filters": [
            {
                "filterType": "LOT_SIZE",
                "minQty": min_qty,
                "maxQty": max_qty,
                "stepSize": step,
            },
            {"filterType": "NOTIONAL", "minNotional": min_notional},
        ],
    }


def test_fill_paper_persiste_metadatos_economicos():
    engine, fabrica, uid = _fabrica_con_usuario()
    try:
        cartera = CarteraPaper(
            usuario_id=uid,
            session_factory=fabrica,
            initial_capital_usd=500.0,
            fee_taker_bps_por_lado=10.0,
            order_book_provider=lambda _s: {
                "asks": [["100", "1"]],
                "bids": [["99", "1"]],
            },
        )
        veredicto = DecisionRiesgo(
            aprobado=True,
            symbol="BTCUSDT",
            side=Lado.COMPRA,
            approved_quote_amount=10.0,
        )
        resultado = cartera.ejecutar(
            veredicto,
            100.0,
            economics={
                "strategy": "SCANNER_DETERMINISTA",
                "expected_edge_bps": 42.0,
                "expected_cost_bps": 18.0,
                "expected_net_bps": 24.0,
            },
        )

        assert resultado.success is True
        with fabrica() as db:
            op = db.query(models.PaperOperacion).one()
            assert op.strategy == "SCANNER_DETERMINISTA"
            assert op.expected_edge_bps == 42.0
            assert op.expected_cost_bps == 18.0
            assert op.expected_net_bps == 24.0
    finally:
        engine.dispose()


def test_cartera_paper_productiva_cuantiza_al_lot_size_del_exchange():
    engine, fabrica, uid = _fabrica_con_usuario()
    try:
        info = _symbol_info(step="0.03", min_qty="0.03", min_notional="5")
        cartera = CarteraPaper(
            usuario_id=uid,
            session_factory=fabrica,
            initial_capital_usd=500.0,
            fee_taker_bps_por_lado=10.0,
            order_book_provider=lambda _s: {
                "asks": [["100", "1"]],
                "bids": [["99", "1"]],
            },
            symbol_info_provider=lambda symbol: info if symbol == "BTCUSDT" else None,
        )
        veredicto = DecisionRiesgo(
            aprobado=True,
            symbol="BTCUSDT",
            side=Lado.COMPRA,
            approved_quote_amount=10.0,
        )

        resultado = cartera.ejecutar(veredicto, 100.0)

        assert resultado.success is True
        assert resultado.executed_base_quantity == pytest.approx(0.09)
        with fabrica() as db:
            op = db.query(models.PaperOperacion).one()
            assert op.base_quantity == pytest.approx(0.09)
            assert op.quote_gross == pytest.approx(9.0)
            assert op.quote_net == pytest.approx(9.009)
    finally:
        engine.dispose()


def test_cartera_paper_con_proveedor_pero_sin_filtros_falla_sin_persistir_fill():
    engine, fabrica, uid = _fabrica_con_usuario()
    try:
        cartera = CarteraPaper(
            usuario_id=uid,
            session_factory=fabrica,
            initial_capital_usd=500.0,
            fee_taker_bps_por_lado=10.0,
            order_book_provider=lambda _s: {
                "asks": [["100", "1"]],
                "bids": [["99", "1"]],
            },
            symbol_info_provider=lambda _symbol: {"symbol": "BTCUSDT", "filters": []},
        )
        veredicto = DecisionRiesgo(
            aprobado=True,
            symbol="BTCUSDT",
            side=Lado.COMPRA,
            approved_quote_amount=10.0,
        )

        resultado = cartera.ejecutar(veredicto, 100.0)

        assert resultado.success is False
        with fabrica() as db:
            assert db.query(models.PaperOperacion).count() == 0
    finally:
        engine.dispose()


def test_expected_llega_hasta_error_contra_resultado_realizado():
    engine, fabrica, uid = _fabrica_con_usuario()
    try:
        # La compra entra a 100 y la salida usa bid 102. La estadistica no usa
        # un retorno teorico: consume los dos fills persistidos, incluyendo fee.
        books = iter((
            {"asks": [["100", "1"]], "bids": [["99", "1"]]},
            {"asks": [["103", "1"]], "bids": [["102", "1"]]},
        ))
        cartera = CarteraPaper(
            usuario_id=uid,
            session_factory=fabrica,
            initial_capital_usd=500.0,
            fee_taker_bps_por_lado=10.0,
            order_book_provider=lambda _s: next(books),
        )
        compra = DecisionRiesgo(
            aprobado=True,
            symbol="BTCUSDT",
            side=Lado.COMPRA,
            approved_quote_amount=10.0,
        )
        fill_compra = cartera.ejecutar(
            compra,
            100.0,
            economics={
                "strategy": "MOMENTUM_OOS",
                "expected_edge_bps": 44.0,
                "expected_cost_bps": 20.0,
                "expected_net_bps": 24.0,
            },
        )
        assert fill_compra.success is True
        qty = fill_compra.executed_base_quantity
        assert qty and qty > 0

        venta = DecisionRiesgo(
            aprobado=True,
            symbol="BTCUSDT",
            side=Lado.VENTA,
            approved_base_quantity=qty,
        )
        fill_venta = cartera.ejecutar(venta, 102.0, economics={})
        assert fill_venta.success is True

        with fabrica() as db:
            operaciones = (
                db.query(models.PaperOperacion)
                .order_by(models.PaperOperacion.id.asc())
                .all()
            )
            resumen = resumen_por_estrategia(operaciones)

        fila = resumen["estrategias"]["MOMENTUM_OOS"]
        assert fila["cierres"] == 1
        assert fila["expected_net_bps_ponderado"] == pytest.approx(24.0)
        assert fila["retorno_realizado_neto_bps"] is not None
        assert fila["error_expected_vs_realizado_bps"] == pytest.approx(
            fila["retorno_realizado_neto_bps"] - 24.0
        )
        assert fila["pnl_realizado_neto_usd"] > 0
    finally:
        engine.dispose()


def test_main_conecta_economia_despues_de_decision_y_antes_del_fill():
    fuente = (RAIZ / "backend" / "main.py").read_text(encoding="utf-8")

    normaliza = fuente.index("decision_engine.contexto_economico_para_ejecucion(")
    riesgo = fuente.index("veredicto = motor_riesgo.evaluar(", normaliza)
    ejecuta = fuente.index("ejecucion = cartera.ejecutar(", riesgo)

    assert normaliza < riesgo < ejecuta
    bloque_ejecucion = fuente[ejecuta:ejecuta + 500]
    assert "economics=economics" in bloque_ejecucion


def test_prioridad_post_scanner_usa_las_claves_internas_reales():
    fuente = (RAIZ / "backend" / "main.py").read_text(encoding="utf-8")
    assert 'a.get("_balance_detected") or a.get("_position_detected")' in fuente
    assert 'a.get("balance_detected") or a.get("position_detected")' not in fuente


def test_live_acepta_contexto_economico_sin_usarlo_para_autorizar():
    from inspect import signature
    from backend.portafolio.carteras import CarteraLive

    assert "economics" in signature(CarteraLive.ejecutar).parameters
