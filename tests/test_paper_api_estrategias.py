import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.simulation.paper_api import resumen_paper


def test_resumen_api_atribuye_pnl_neto_a_estrategia_de_entrada():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    fabrica = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        with fabrica() as db:
            user = models.User(nombre="estrategia", email="strategy@test.local", password_hash="x")
            db.add(user)
            db.flush()
            ledger = models.PaperLedger(usuario_id=user.id, initial_capital_usd=500.0)
            db.add(ledger)
            db.flush()
            db.add(models.PaperOperacion(
                ledger_id=ledger.id,
                symbol="BTCUSDT",
                side="BUY",
                reference_price=100.0,
                fill_price=100.0,
                base_quantity=1.0,
                quote_gross=100.0,
                fee_usd=0.1,
                quote_net=100.1,
                slippage_bps=0.0,
                fee_taker_bps=10.0,
                strategy="MOMENTUM_VALIDADO",
                expected_edge_bps=80.0,
                expected_cost_bps=30.0,
                expected_net_bps=50.0,
            ))
            db.add(models.PaperOperacion(
                ledger_id=ledger.id,
                symbol="BTCUSDT",
                side="SELL",
                reference_price=110.0,
                fill_price=110.0,
                base_quantity=1.0,
                quote_gross=110.0,
                fee_usd=0.11,
                quote_net=109.89,
                slippage_bps=0.0,
                fee_taker_bps=10.0,
                strategy="MOMENTUM_VALIDADO",
            ))
            db.commit()
            uid = user.id

        llamadas = []
        with fabrica() as db:
            resumen = resumen_paper(
                db,
                usuario_id=uid,
                initial_capital_usd=9999.0,
                obtener_precio=lambda symbol: llamadas.append(symbol) or 999.0,
            )

        assert llamadas == [], "sin posiciones abiertas no debe pedir precio MTM"
        assert resumen["pnl_realizado_usd"] == pytest.approx(9.79)
        estrategia = resumen["estrategias_paper"]["estrategias"]["MOMENTUM_VALIDADO"]
        assert estrategia["pnl_realizado_neto_usd"] == pytest.approx(9.79)
        assert estrategia["coste_cerrado_usd"] == pytest.approx(100.1)
        assert estrategia["expected_net_bps_ponderado"] == pytest.approx(50.0)
        assert estrategia["cierres"] == 1
        assert estrategia["positive_rate"] == pytest.approx(1.0)
        assert estrategia["cantidad_abierta"] == pytest.approx(0.0)
    finally:
        engine.dispose()
