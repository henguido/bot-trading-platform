import os
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

RAIZ = Path(__file__).resolve().parents[1]
MIGRACION = RAIZ / "migrations" / "versions" / "0006_paper_ledger.py"


def _configurar(url):
    os.environ["DATABASE_URL"] = url
    from backend.config import settings
    import importlib
    importlib.reload(settings)

    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_0006_encadena_exclusivamente_desde_0005():
    fuente = MIGRACION.read_text(encoding="utf-8")
    assert 'revision = "0006_paper_ledger"' in fuente
    assert 'down_revision = "0005_telemetria_http"' in fuente


def test_upgrade_0006_crea_ledger_paper_separado(tmp_path):
    """Prueba 0006 de forma aislada aunque el repositorio tenga heads posteriores."""
    url = f"sqlite:///{tmp_path / 'paper.db'}"
    previo = os.environ.get("DATABASE_URL")
    try:
        cfg = _configurar(url)
        command.upgrade(cfg, "0006_paper_ledger")

        engine = sa.create_engine(url)
        insp = sa.inspect(engine)
        tablas = set(insp.get_table_names())
        assert {"paper_ledgers", "paper_operaciones"} <= tablas
        assert {"transacciones", "ordenes", "fills"} <= tablas
        assert "decision_cycle_audit" not in tablas

        cols = {c["name"] for c in insp.get_columns("paper_operaciones")}
        assert {
            "reference_price", "fill_price", "base_quantity", "quote_gross",
            "fee_usd", "quote_net", "slippage_bps", "fee_taker_bps",
            "strategy", "expected_edge_bps", "expected_cost_bps",
            "expected_net_bps",
        } <= cols

        unicos = {c["name"] for c in insp.get_unique_constraints("paper_ledgers")}
        assert "uq_paper_ledger_usuario" in unicos

        with engine.connect() as c:
            assert c.execute(sa.text(
                "SELECT version_num FROM alembic_version"
            )).scalar() == "0006_paper_ledger"
    finally:
        if previo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previo
        from backend.config import settings
        import importlib
        importlib.reload(settings)


def test_0006_no_altera_columnas_del_ledger_live(tmp_path):
    """Agregar PAPER no modifica las tres tablas economicas del camino LIVE."""
    url = f"sqlite:///{tmp_path / 'separacion.db'}"
    previo = os.environ.get("DATABASE_URL")
    try:
        cfg = _configurar(url)
        command.upgrade(cfg, "0005_telemetria_http")
        engine = sa.create_engine(url)
        insp = sa.inspect(engine)
        antes = {
            tabla: tuple(c["name"] for c in insp.get_columns(tabla))
            for tabla in ("transacciones", "ordenes", "fills")
        }

        command.upgrade(cfg, "0006_paper_ledger")
        insp = sa.inspect(engine)
        despues = {
            tabla: tuple(c["name"] for c in insp.get_columns(tabla))
            for tabla in ("transacciones", "ordenes", "fills")
        }

        assert despues == antes
    finally:
        if previo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previo
        from backend.config import settings
        import importlib
        importlib.reload(settings)
