"""
P0-16 · Alembic es la unica autoridad del esquema.

backend/main.py ejecutaba models.Base.metadata.create_all(bind=engine) AL
IMPORTAR. Con DATABASE_URL apuntando a Render, importar el modulo abria
conexion contra produccion y habria creado alli `ordenes` y `fills` fuera de
Alembic, dejando la base con el esquema nuevo y sin fila en alembic_version.

INVARIANTE: el codigo de aplicacion no modifica el esquema. Nunca.
"""
import ast
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from backend.esquema import (
    ALINEADO,
    MIGRACION_REQUERIDA,
    SIN_ALEMBIC,
    estado_esquema,
    revision_esperada,
)

RAIZ = Path(__file__).resolve().parents[1]
CODIGO_APP = [p for p in (RAIZ / "backend").rglob("*.py")]


def _cfg(url):
    # migrations/env.py toma la URL de settings.DATABASE_URL, no del ini, para
    # no versionar credenciales. Hay que fijar el entorno y recargar settings.
    import importlib
    import os

    os.environ["DATABASE_URL"] = url
    from backend.config import settings
    importlib.reload(settings)

    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


# ── 1 y 2 · Importar main no conecta ni ejecuta DDL ─────────────────────────
def test_1_importar_main_no_abre_ninguna_conexion(monkeypatch):
    """
    Se instrumenta el Engine: si algo fuerza una conexion durante el import,
    la prueba lo detecta. Crear el objeto Engine (perezoso) no cuenta.
    """
    import backend.app.database as bd

    conexiones = []
    original = sa.engine.Engine.connect

    def espia(self, *a, **k):
        conexiones.append(str(self.url))
        return original(self, *a, **k)

    monkeypatch.setattr(sa.engine.Engine, "connect", espia)

    import importlib
    import backend.main
    importlib.reload(backend.main)

    assert conexiones == [], f"importar backend.main abrio conexiones: {conexiones}"


def test_2_importar_main_no_ejecuta_ddl(monkeypatch):
    """Ninguna sentencia CREATE/ALTER/DROP puede salir durante el import."""
    ddl = []
    original = sa.MetaData.create_all

    def espia(self, *a, **k):
        ddl.append("create_all")
        return original(self, *a, **k)

    monkeypatch.setattr(sa.MetaData, "create_all", espia)
    monkeypatch.setattr(sa.MetaData, "drop_all",
                        lambda self, *a, **k: ddl.append("drop_all"))

    import importlib
    import backend.main
    importlib.reload(backend.main)

    assert ddl == [], f"importar backend.main ejecuto DDL: {ddl}"


# ── 3 · No hay create_all/drop_all en el codigo de aplicacion ───────────────
def test_3_el_codigo_de_aplicacion_no_modifica_el_esquema():
    ofensores = []
    for archivo in CODIGO_APP:
        if "__pycache__" in archivo.parts:
            continue
        arbol = ast.parse(archivo.read_text(encoding="utf-8", errors="replace"))
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr in ("create_all", "drop_all")):
                ofensores.append(f"{archivo.relative_to(RAIZ)}:{nodo.lineno} "
                                 f"{nodo.func.attr}()")
    assert not ofensores, ("el codigo de aplicacion no puede tocar el esquema:\n"
                           + "\n".join(ofensores))


def test_3b_main_no_contiene_create_all():
    arbol = ast.parse((RAIZ / "backend" / "main.py").read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        assert not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr == "create_all"), \
            "main.py no puede crear el esquema al arrancar"


def test_3c_borrar_historial_sigue_siendo_una_herramienta_explicita():
    """
    La herramienta administrativa puede seguir usando drop_all/create_all, pero
    solo dentro de una funcion y nunca por import (protecciones de P0-7).
    """
    fuente = (RAIZ / "borrar_historial.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for nodo in arbol.body:            # nivel de modulo
        if isinstance(nodo, (ast.FunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            continue
        if isinstance(nodo, ast.If) and "__main__" in ast.dump(nodo.test):
            continue
        if isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Constant):
            continue
        volcado = ast.dump(nodo)
        assert "drop_all" not in volcado and "create_all" not in volcado, \
            "borrar_historial.py no puede tocar el esquema al importarse"


# ── 4 · Ningun upgrade automatico ───────────────────────────────────────────
def test_4_no_existe_alembic_upgrade_automatico():
    ofensores = []
    for archivo in CODIGO_APP:
        if "__pycache__" in archivo.parts:
            continue
        texto = archivo.read_text(encoding="utf-8", errors="replace")
        arbol = ast.parse(texto)
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr in ("upgrade", "downgrade", "stamp")
                    and "command" in ast.dump(nodo.func)):
                ofensores.append(f"{archivo.relative_to(RAIZ)}:{nodo.lineno}")
    assert not ofensores, f"migracion automatica en el codigo de app: {ofensores}"


# ── 5 y 6 · Alembic si construye el esquema ─────────────────────────────────
def test_5_bd_vacia_upgrade_head_crea_todo(tmp_path):
    url = f"sqlite:///{tmp_path / 'nueva.db'}"
    command.upgrade(_cfg(url), "head")
    tablas = set(sa.inspect(sa.create_engine(url)).get_table_names())
    assert {"usuarios", "activos", "portafolios", "transacciones",
            "decision_audit", "ordenes", "fills"} <= tablas


def test_6_bd_legacy_baseline_y_upgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    command.upgrade(_cfg(url), "0001_baseline")
    e = sa.create_engine(url)
    with e.begin() as c:
        c.execute(sa.text("DROP TABLE alembic_version"))
        c.execute(sa.text("INSERT INTO usuarios (id,nombre,email,password_hash) "
                          "VALUES (1,'L','l@e.com','h')"))

    command.stamp(_cfg(url), "0001_baseline")
    command.upgrade(_cfg(url), "head")

    tablas = set(sa.inspect(e).get_table_names())
    assert {"ordenes", "fills"} <= tablas
    with e.connect() as c:
        assert c.execute(sa.text("SELECT nombre FROM usuarios WHERE id=1")).scalar() == "L"


# ── 7 · Ejecutar la app no altera el esquema ────────────────────────────────
def test_7_importar_la_app_no_altera_una_bd_existente(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'existente.db'}"
    command.upgrade(_cfg(url), "0001_baseline")
    antes = set(sa.inspect(sa.create_engine(url)).get_table_names())

    monkeypatch.setenv("DATABASE_URL", url)
    import importlib
    from backend.config import settings
    importlib.reload(settings)
    import backend.app.database as bd
    importlib.reload(bd)
    import backend.main
    importlib.reload(backend.main)

    despues = set(sa.inspect(sa.create_engine(url)).get_table_names())
    assert antes == despues, (
        f"importar la app modifico el esquema: anadio {despues - antes}")
    assert "ordenes" not in despues, "la app no puede crear las tablas nuevas"


# ── Fail-safe: detectar desfase sin migrar ──────────────────────────────────
def test_estado_esquema_detecta_base_sin_alembic(tmp_path):
    url = f"sqlite:///{tmp_path / 'sinalembic.db'}"
    command.upgrade(_cfg(url), "0001_baseline")
    e = sa.create_engine(url)
    with e.begin() as c:
        c.execute(sa.text("DROP TABLE alembic_version"))

    r = estado_esquema(engine=e)
    assert r.estado == SIN_ALEMBIC
    assert r.alineado is False
    assert "stamp 0001_baseline" in r.detalle
    assert "stamp head" in r.detalle    # advierte explicitamente contra ello


def test_estado_esquema_detecta_migracion_pendiente(tmp_path):
    url = f"sqlite:///{tmp_path / 'atrasada.db'}"
    command.upgrade(_cfg(url), "0001_baseline")

    r = estado_esquema(engine=sa.create_engine(url))
    assert r.estado == MIGRACION_REQUERIDA
    assert r.revision_actual == "0001_baseline"
    assert r.revision_esperada == revision_esperada()


def test_estado_esquema_alineado(tmp_path):
    url = f"sqlite:///{tmp_path / 'aldia.db'}"
    command.upgrade(_cfg(url), "head")
    r = estado_esquema(engine=sa.create_engine(url))
    assert r.estado == ALINEADO and r.alineado is True


def test_la_comprobacion_no_modifica_la_base(tmp_path):
    """El fail-safe solo MIRA."""
    url = f"sqlite:///{tmp_path / 'intacta.db'}"
    command.upgrade(_cfg(url), "0001_baseline")
    e = sa.create_engine(url)
    antes = set(sa.inspect(e).get_table_names())

    for _ in range(5):
        estado_esquema(engine=e)

    assert set(sa.inspect(e).get_table_names()) == antes
