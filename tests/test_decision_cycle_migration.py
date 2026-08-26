import os
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

RAIZ = Path(__file__).resolve().parents[1]
MIGRACION = RAIZ / "migrations" / "versions" / "0007_decision_cycle_audit.py"


def _configurar(url):
    os.environ["DATABASE_URL"] = url
    from backend.config import settings
    import importlib
    importlib.reload(settings)
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_0007_encadena_desde_0006():
    fuente = MIGRACION.read_text(encoding="utf-8")
    assert 'revision = "0007_decision_cycle_audit"' in fuente
    assert 'down_revision = "0006_paper_ledger"' in fuente


def test_upgrade_head_crea_auditoria_de_ciclos_y_conserva_paper(tmp_path):
    url = f"sqlite:///{tmp_path / 'decision-cycle.db'}"
    previo = os.environ.get("DATABASE_URL")
    try:
        cfg = _configurar(url)
        command.upgrade(cfg, "head")
        engine = sa.create_engine(url)
        insp = sa.inspect(engine)
        tablas = set(insp.get_table_names())

        assert {"decision_cycle_audit", "paper_ledgers", "paper_operaciones"} <= tablas
        cols = {c["name"] for c in insp.get_columns("decision_cycle_audit")}
        assert {
            "id", "usuario_id", "ciclo_id", "timestamp", "modo",
            "decision_engine", "resumen_json",
        } <= cols

        unicos = {
            c["name"] for c in insp.get_unique_constraints("decision_cycle_audit")
        }
        assert "uq_decision_cycle_audit_ciclo_id" in unicos
        fks = insp.get_foreign_keys("decision_cycle_audit")
        assert any(
            fk.get("referred_table") == "usuarios"
            and fk.get("constrained_columns") == ["usuario_id"]
            for fk in fks
        )

        with engine.connect() as c:
            assert c.execute(sa.text(
                "SELECT version_num FROM alembic_version"
            )).scalar() == "0007_decision_cycle_audit"
    finally:
        if previo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previo
        from backend.config import settings
        import importlib
        importlib.reload(settings)


def test_0007_solo_agrega_tabla_de_observabilidad(tmp_path):
    url = f"sqlite:///{tmp_path / 'solo-agrega.db'}"
    previo = os.environ.get("DATABASE_URL")
    try:
        cfg = _configurar(url)
        command.upgrade(cfg, "0006_paper_ledger")
        engine = sa.create_engine(url)
        insp = sa.inspect(engine)
        antes = {
            tabla: tuple(c["name"] for c in insp.get_columns(tabla))
            for tabla in ("transacciones", "ordenes", "fills",
                          "paper_ledgers", "paper_operaciones")
        }

        command.upgrade(cfg, "0007_decision_cycle_audit")
        insp = sa.inspect(engine)
        despues = {
            tabla: tuple(c["name"] for c in insp.get_columns(tabla))
            for tabla in antes
        }
        assert despues == antes
        assert "decision_cycle_audit" in set(insp.get_table_names())
    finally:
        if previo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previo
        from backend.config import settings
        import importlib
        importlib.reload(settings)
