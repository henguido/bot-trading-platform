"""Smoke de release PAPER v1: configuracion + ledger + endpoints reales."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services.ordenes import Lado
from backend.config import settings
from backend.portafolio.carteras import CarteraPaper
from backend.risk.motor import DecisionRiesgo
import backend.main as main


class BookProvider:
    def __init__(self):
        self.book = {
            "asks": [["100", "2"]],
            "bids": [["99", "2"]],
        }
        self.calls = []

    def __call__(self, symbol):
        self.calls.append(symbol)
        return self.book


def _fabrica():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _veredicto_compra(symbol="BTCUSDT", quote=10.0):
    return DecisionRiesgo(
        aprobado=True,
        symbol=symbol,
        side=Lado.COMPRA,
        approved_base_quantity=None,
        approved_quote_amount=quote,
    )


def test_defaults_release_paper_v1_son_500_usdt_y_2_por_ciento():
    assert settings.DEFAULT_INITIAL_CAPITAL_USD == 500.0
    assert settings.DEFAULT_LIMITE_ASIGNACION_POR_OPERACION == 0.02
    # CI fija los mismos valores explicitamente; esta prueba protege el default
    # usado por una instalacion nueva que aun no tenga esas variables en .env.
    assert settings.INITIAL_CAPITAL_USD == 500.0
    assert settings.LIMITE_ASIGNACION_POR_OPERACION == 0.02


def test_cors_de_main_sale_de_settings_y_no_esta_hardcodeado():
    fuente = (main.Path(__file__).resolve().parents[1] / "backend" / "main.py") \
        if hasattr(main, "Path") else None
    # No dependemos de internals de Starlette; el contrato de codigo es que la
    # lista autorizada venga de la fuente canonica settings.
    texto = __import__("pathlib").Path(main.__file__).read_text(encoding="utf-8")
    assert "allow_origins=list(settings.CORS_ORIGINS)" in texto
    assert 'allow_origins=["http://localhost:5173"]' not in texto
    assert settings.CORS_ORIGINS
    assert "*" not in settings.CORS_ORIGINS


def test_endpoint_paper_usa_ledger_y_no_balance_privado_binance(monkeypatch):
    engine, fabrica = _fabrica()
    try:
        with fabrica() as db:
            user = models.User(
                nombre="Release PAPER",
                email="release-paper@test.local",
                password_hash="x",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            uid = user.id

        provider = BookProvider()
        cartera = CarteraPaper(
            usuario_id=uid,
            session_factory=fabrica,
            initial_capital_usd=500.0,
            fee_taker_bps_por_lado=10.0,
            order_book_provider=provider,
        )
        compra = cartera.ejecutar(_veredicto_compra(), 100.0)
        assert compra.success is True
        assert provider.calls == ["BTCUSDT"]

        # Si /api/resumen intenta volver al balance privado del exchange, el
        # smoke debe fallar. PAPER solo necesita un precio publico para MTM.
        def balance_privado_prohibido(*_a, **_k):
            raise AssertionError("PAPER no debe consultar get_account_balance")

        monkeypatch.setattr(main.binance, "get_account_balance", balance_privado_prohibido)
        monkeypatch.setattr(main.binance, "get_current_price", lambda symbol: 110.0)

        with fabrica() as db:
            user = db.query(models.User).filter(models.User.id == uid).one()
            resumen = main.resumen_portafolio(db=db, current_user=user)
            historial = main.get_historial(db=db, current_user=user)

        assert resumen["modo"] == "PAPER"
        assert resumen["initial_capital_usd"] == 500.0
        assert resumen["capital_disponible_usd"] < 500.0
        assert resumen["fees_total_usd"] > 0
        assert resumen["operaciones"] == 1
        btc = next(x for x in resumen["resumen"] if x["symbol"] == "BTCUSDT")
        assert btc["cantidad"] > 0
        assert btc["precio_actual"] == 110.0
        assert btc["pnl"] is not None

        assert len(historial) == 1
        assert historial[0]["symbol"] == "BTCUSDT"
        assert historial[0]["action"] == "COMPRAR"
        assert historial[0]["fee_usd"] > 0
        assert historial[0]["decision_gpt"] is None

        # Reinicio: otra CarteraPaper reconstruye exactamente el mismo libro.
        reiniciada = CarteraPaper(
            usuario_id=uid,
            session_factory=fabrica,
            initial_capital_usd=9999.0,
            fee_taker_bps_por_lado=10.0,
            order_book_provider=provider,
        )
        assert reiniciada.cantidad_disponible("BTCUSDT") == cartera.cantidad_disponible("BTCUSDT")
        assert reiniciada.capital_disponible() == cartera.capital_disponible()
    finally:
        engine.dispose()
