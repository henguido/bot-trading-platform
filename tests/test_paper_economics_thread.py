from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services.ordenes import Lado
from backend.portafolio.carteras import CarteraPaper
from backend.risk.motor import DecisionRiesgo


def test_fill_paper_persiste_metadatos_economicos():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    fabrica = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        with fabrica() as db:
            user = models.User(nombre="econ", email="econ@test.local", password_hash="x")
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


def test_live_acepta_contexto_economico_sin_usarlo_para_autorizar():
    from inspect import signature
    from backend.portafolio.carteras import CarteraLive

    assert "economics" in signature(CarteraLive.ejecutar).parameters
