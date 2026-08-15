"""
Migraciones Alembic con estrategia baseline.

Se prueban los dos escenarios sobre SQLite DESECHABLE en tmp_path. Nunca se
toca backend/app.db ni ninguna base de produccion.

  BD nueva    : alembic upgrade head  construye todo desde cero.
  BD antigua  : esquema legacy sin alembic_version -> stamp 0001_baseline
                -> upgrade head, con los datos legacy intactos.
"""
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

RAIZ = Path(__file__).resolve().parents[1]
BASELINE = "0001_baseline"
# Se deriva del repositorio en vez de fijarse a mano: asi anadir una migracion
# no obliga a tocar estas pruebas ni las deja comprobando una revision vieja.
from backend.esquema import revision_esperada  # noqa: E402

HEAD = revision_esperada()


def _alembic(url):
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    os.environ["DATABASE_URL"] = url      # env.py lee de settings.DATABASE_URL
    import importlib
    from backend.config import settings
    importlib.reload(settings)
    return cfg


@pytest.fixture
def url(tmp_path):
    previo = os.environ.get("DATABASE_URL")
    yield f"sqlite:///{tmp_path / 'prueba.db'}"
    if previo is not None:
        os.environ["DATABASE_URL"] = previo
    import importlib
    from backend.config import settings
    importlib.reload(settings)


def _inspector(url):
    return sa.inspect(sa.create_engine(url))


# ── BD NUEVA ────────────────────────────────────────────────────────────────
def test_bd_nueva_upgrade_head_construye_todo(url):
    command.upgrade(_alembic(url), "head")
    insp = _inspector(url)

    esperadas = {"usuarios", "activos", "portafolios", "transacciones",
                 "decision_audit", "ordenes", "fills", "alembic_version"}
    assert esperadas <= set(insp.get_table_names())

    # Las restricciones que sostienen la idempotencia deben existir DE VERDAD.
    unicos_ordenes = [i["name"] for i in insp.get_indexes("ordenes") if i["unique"]]
    assert "ix_ordenes_client_order_id" in unicos_ordenes
    assert "uq_fill_externo" in [c["name"] for c in insp.get_unique_constraints("fills")]
    assert any(c["name"] == "fill_id" for c in insp.get_columns("transacciones"))


def test_bd_nueva_queda_en_head(url):
    command.upgrade(_alembic(url), "head")
    with sa.create_engine(url).connect() as c:
        assert c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == HEAD


# ── BD ANTIGUA ──────────────────────────────────────────────────────────────
def _crear_bd_legacy_con_datos(url):
    """Esquema previo y datos, sin tabla alembic_version."""
    command.upgrade(_alembic(url), BASELINE)
    e = sa.create_engine(url)
    with e.begin() as c:
        c.execute(sa.text("DROP TABLE alembic_version"))
        c.execute(sa.text("INSERT INTO usuarios (id,nombre,email,password_hash) "
                          "VALUES (1,'Legacy','l@e.com','h')"))
        c.execute(sa.text("INSERT INTO activos (id,simbolo,nombre,tipo) "
                          "VALUES (1,'BTCUSDT','BTC','crypto')"))
        c.execute(sa.text("INSERT INTO portafolios (id,usuario_id,nombre,tipo_activo) "
                          "VALUES (1,1,'P','crypto')"))
        c.execute(sa.text("INSERT INTO transacciones "
                          "(id,portafolio_id,activo_id,tipo_operacion,cantidad,precio) "
                          "VALUES (1,1,1,'Compra',0.001,100000)"))
    return e


def test_bd_antigua_stamp_baseline_y_upgrade_conserva_datos(url):
    engine = _crear_bd_legacy_con_datos(url)
    assert "alembic_version" not in _inspector(url).get_table_names()

    # Procedimiento documentado: stamp de la BASELINE, nunca stamp head.
    command.stamp(_alembic(url), BASELINE)
    with engine.connect() as c:
        assert c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == BASELINE

    command.upgrade(_alembic(url), "head")

    insp = _inspector(url)
    assert {"ordenes", "fills"} <= set(insp.get_table_names())
    with engine.connect() as c:
        assert c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == HEAD
        assert c.execute(sa.text("SELECT COUNT(*) FROM transacciones")).scalar() == 1
        assert c.execute(sa.text("SELECT nombre FROM usuarios WHERE id=1")).scalar() == "Legacy"
        # La columna nueva es nullable: las transacciones legacy la dejan a NULL.
        assert c.execute(sa.text("SELECT fill_id FROM transacciones WHERE id=1")).scalar() is None


def test_stamp_head_saltaria_la_migracion_de_ordenes(url):
    """
    Por que el procedimiento dice `stamp 0001_baseline` y NO `stamp head`:
    con stamp head, Alembic creeria que 0002 ya se aplico y las tablas del
    sistema de ordenes nunca se crearian.
    """
    _crear_bd_legacy_con_datos(url)
    command.stamp(_alembic(url), "head")
    command.upgrade(_alembic(url), "head")

    tablas = set(_inspector(url).get_table_names())
    assert "ordenes" not in tablas, (
        "stamp head deja la BD sin las tablas de ordenes: por eso el "
        "procedimiento exige stampear la baseline"
    )


# ── La baseline representa el esquema legacy real ───────────────────────────
def _tablas_creadas(ruta):
    """Tablas realmente creadas por la migracion, via AST (ignora comentarios)."""
    import ast
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    return {n.args[0].value for n in ast.walk(arbol)
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", None) == "create_table"
            and n.args and isinstance(n.args[0], ast.Constant)}


def test_la_baseline_no_crea_tablas_del_sistema_de_ordenes():
    creadas = _tablas_creadas(RAIZ / "migrations" / "versions" / "0001_baseline.py")
    assert creadas == {"usuarios", "activos", "portafolios", "transacciones",
                       "decision_audit"}, f"la baseline crea {creadas}"
    assert not ({"ordenes", "fills"} & creadas), (
        "la baseline debe representar el esquema PREVIO al sistema de ordenes"
    )


def test_la_segunda_revision_crea_ordenes_y_fills():
    creadas = _tablas_creadas(RAIZ / "migrations" / "versions" /
                              "0002_ciclo_de_vida_ordenes.py")
    assert creadas == {"ordenes", "fills"}


def test_la_migracion_de_ordenes_solo_agrega():
    """Segura sobre bases con historico: no altera ni borra datos."""
    fuente = (RAIZ / "migrations" / "versions" /
              "0002_ciclo_de_vida_ordenes.py").read_text(encoding="utf-8")
    upgrade = fuente.split("def upgrade")[1].split("def downgrade")[0]
    for prohibido in ("drop_table", "drop_column", "DELETE", "UPDATE ", "alter_column"):
        assert prohibido not in upgrade, f"la migracion no debe usar {prohibido}"
