from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services.ordenes import Lado
from backend.portafolio.carteras import CarteraPaper
from backend.risk.motor import DecisionRiesgo
from backend.simulation.paper_api import resumen_paper


def _fabrica():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_resumen_distingue_realizado_neto_de_mtm_pre_coste_salida():
    engine, fabrica = _fabrica()
    try:
        with fabrica() as db:
            user = models.User(nombre="P", email="pnl@test.local", password_hash="x")
            db.add(user)
            db.commit()
            db.refresh(user)
            uid = user.id

        cartera = CarteraPaper(
            usuario_id=uid,
            session_factory=fabrica,
            initial_capital_usd=500.0,
            fee_taker_bps_por_lado=10.0,
            order_book_provider=lambda _s: {
                "asks": [["100", "2"]],
                "bids": [["99", "2"]],
            },
        )
        r = cartera.ejecutar(DecisionRiesgo(
            aprobado=True,
            symbol="BTCUSDT",
            side=Lado.COMPRA,
            approved_base_quantity=None,
            approved_quote_amount=10.0,
        ), 100.0)
        assert r.success is True

        with fabrica() as db:
            salida = resumen_paper(
                db,
                usuario_id=uid,
                initial_capital_usd=500.0,
                obtener_precio=lambda _s: 110.0,
            )

        assert salida["pnl_realizado_metodologia"] == "NETO_DE_FEES_DE_FILLS_REALIZADOS"
        assert salida["pnl_no_realizado_metodologia"] == "MTM_INCLUYE_COSTE_ENTRADA_NO_COSTE_SALIDA"
        assert salida["pnl_total_metodologia"] == "REALIZADO_NETO_MAS_MTM_PRE_COSTE_SALIDA"
        assert salida["pnl_total_es_neto_liquidacion"] is False
        assert salida["posiciones_abiertas"] == 1
        btc = next(x for x in salida["resumen"] if x["symbol"] == "BTCUSDT")
        assert btc["pnl_metodologia"] == "MTM_INCLUYE_COSTE_ENTRADA_NO_COSTE_SALIDA"
    finally:
        engine.dispose()
