import os
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

RAIZ = Path(__file__).resolve().parents[1]


def test_upgrade_head_crea_ledger_paper_separado(tmp_path):
    url = f"sqlite:///{tmp_path / 'paper.db'}"
    previo = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = url
        from backend.config import settings
        import importlib
        importlib.reload(settings)

        cfg = Config(str(RAIZ / "alembic.ini"))
        cfg.set_main_option("script_location", str(RAIZ / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")

        insp = sa.inspect(sa.create_engine(url))
        tablas = set(insp.get_table_names())
        assert {"paper_ledgers", "paper_operaciones"} <= tablas

        cols = {c["name"] for c in insp.get_columns("paper_operaciones")}
        assert {
            "reference_price", "fill_price", "base_quantity", "quote_gross",
            "fee_usd", "quote_net", "slippage_bps", "fee_taker_bps",
            "strategy", "expected_edge_bps", "expected_cost_bps",
            "expected_net_bps",
        } <= cols

        unicos = {c["name"] for c in insp.get_unique_constraints("paper_ledgers")}
        assert "uq_paper_ledger_usuario" in unicos
    finally:
        if previo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previo
        from backend.config import settings
        import importlib
        importlib.reload(settings)
