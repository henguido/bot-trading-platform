"""Regresion de continuidad PAPER tras reiniciar el proceso.

El objetivo no es probar SQLite en si, sino el contrato de produccion: el estado
PAPER debe reconstruirse desde `paper_operaciones`, no desde memoria del proceso.
"""
import importlib
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.simulation.paper_ledger import estado_desde_db, obtener_o_crear_ledger

RAIZ = Path(__file__).resolve().parents[1]


def _migrar(url: str) -> None:
    """Migra exactamente la BD temporal; env.py toma DATABASE_URL, no alembic.ini."""
    previo = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = url
        from backend.config import settings
        importlib.reload(settings)

        cfg = Config(str(RAIZ / "alembic.ini"))
        cfg.set_main_option("script_location", str(RAIZ / "migrations"))
        command.upgrade(cfg, "0006_paper_ledger")
    finally:
        if previo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previo
        from backend.config import settings
        importlib.reload(settings)


def test_restart_reconstruye_capital_posicion_fees_y_pnl_desde_db(tmp_path):
    ruta = tmp_path / "paper-restart.db"
    url = f"sqlite:///{ruta}"
    _migrar(url)

    # Proceso A: crea usuario, ledger y dos fills PAPER persistidos.
    engine_a = sa.create_engine(url)
    SessionA = sessionmaker(bind=engine_a)
    with SessionA() as db:
        usuario = models.User(
            nombre="Paper Restart",
            email="paper-restart@example.test",
            password_hash="hash-sintetico-no-autenticable",
        )
        db.add(usuario)
        db.flush()

        ledger = obtener_o_crear_ledger(
            db,
            usuario_id=usuario.id,
            initial_capital_usd=500.0,
        )
        db.add_all([
            models.PaperOperacion(
                ledger_id=ledger.id,
                symbol="BTCUSDT",
                side="BUY",
                reference_price=100.0,
                fill_price=100.0,
                base_quantity=0.1,
                quote_gross=10.0,
                fee_usd=0.01,
                quote_net=10.01,
                slippage_bps=0.0,
                fee_taker_bps=10.0,
                strategy="RESTART_TEST",
            ),
            models.PaperOperacion(
                ledger_id=ledger.id,
                symbol="BTCUSDT",
                side="SELL",
                reference_price=120.0,
                fill_price=120.0,
                base_quantity=0.05,
                quote_gross=6.0,
                fee_usd=0.006,
                quote_net=5.994,
                slippage_bps=0.0,
                fee_taker_bps=10.0,
                strategy="RESTART_TEST",
            ),
        ])
        db.commit()
        ledger_id = ledger.id
    engine_a.dispose()

    # Proceso B: engine y Session completamente nuevos sobre el mismo archivo.
    # No se reutiliza ningun objeto EstadoPaper ni cache del proceso A.
    engine_b = sa.create_engine(url)
    SessionB = sessionmaker(bind=engine_b)
    with SessionB() as db:
        ledger = db.get(models.PaperLedger, ledger_id)
        assert ledger is not None
        assert ledger.initial_capital_usd == 500.0

        estado = estado_desde_db(db, ledger)
        assert estado.operaciones == 2
        assert estado.capital_usd == pytest.approx(495.984)
        assert estado.fees_total_usd == pytest.approx(0.016)
        assert estado.realized_pnl_usd == pytest.approx(0.989)
        assert estado.posiciones["BTCUSDT"].cantidad == pytest.approx(0.05)
        assert estado.posiciones["BTCUSDT"].coste_medio_neto == pytest.approx(100.1)

        # Volver a pedir el ledger con otro capital NO lo reinicializa.
        mismo = obtener_o_crear_ledger(
            db,
            usuario_id=ledger.usuario_id,
            initial_capital_usd=999.0,
        )
        assert mismo.id == ledger_id
        assert mismo.initial_capital_usd == 500.0
    engine_b.dispose()
