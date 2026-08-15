"""
El trading no arranca si el esquema no esta alineado.

La API puede levantarse para permitir diagnostico, pero operar contra una base
cuyo esquema no conocemos escribiria ordenes y transacciones en tablas que
podrian no existir o tener otra forma. Con MODO_REAL=True eso seria dinero real
sobre un ledger no garantizado. Fallo cerrado.

Ningun test aqui aplica migraciones ni contacta con brokers.
"""
import ast
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from backend.coordinador import CandadoLocal, CoordinadorTrading
from backend.esquema import (
    ALINEADO,
    DESCONOCIDO,
    MIGRACION_REQUERIDA,
    SIN_ALEMBIC,
    EstadoEsquema,
)

RAIZ = Path(__file__).resolve().parents[1]


def _cfg(url):
    import importlib
    import os
    os.environ["DATABASE_URL"] = url
    from backend.config import settings
    importlib.reload(settings)
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def objetivo():
    import threading
    parar = threading.Event()

    def bucle():
        parar.wait(timeout=10)

    yield bucle
    parar.set()


def precondicion_con(estado):
    """Reproduce la precondicion real de main.py sobre un estado dado."""
    def verificar():
        if estado.estado == ALINEADO:
            return True, ""
        return False, (f"esquema no alineado [{estado.estado}] "
                       f"actual={estado.revision_actual} "
                       f"esperada={estado.revision_esperada}. {estado.detalle or ''}")
    return verificar


# ── OK -> puede iniciar ─────────────────────────────────────────────────────
def test_esquema_ok_permite_iniciar(objetivo, tmp_path):
    coord = CoordinadorTrading(
        objetivo=objetivo, candado=CandadoLocal(str(tmp_path / "l.lock")),
        nombre="loop-ok",
        precondiciones=(precondicion_con(EstadoEsquema(ALINEADO, "0002_ordenes",
                                                       "0002_ordenes")),))
    assert coord.iniciar() is True
    assert coord.activo is True and coord.es_lider is True
    coord.detener()


# ── Cualquier otro estado -> 0 trading loops ────────────────────────────────
@pytest.mark.parametrize("estado", [
    EstadoEsquema(MIGRACION_REQUERIDA, "0001_baseline", "0002_ordenes",
                  "falta aplicar 0002"),
    EstadoEsquema(SIN_ALEMBIC, None, "0002_ordenes", "sin alembic_version"),
    EstadoEsquema(DESCONOCIDO, None, "0002_ordenes", "BD inaccesible"),
])
def test_esquema_no_alineado_no_arranca_el_bucle(objetivo, tmp_path, estado):
    import threading
    coord = CoordinadorTrading(
        objetivo=objetivo, candado=CandadoLocal(str(tmp_path / "l.lock")),
        nombre=f"loop-{estado.estado}",
        precondiciones=(precondicion_con(estado),))

    assert coord.iniciar() is False, f"{estado.estado} no debe permitir operar"
    assert coord.activo is False
    assert coord.es_lider is False
    assert estado.estado in coord.motivo_inactivo
    assert not any(t.name.startswith("loop-") for t in threading.enumerate())


def test_la_precondicion_se_evalua_antes_del_candado(objetivo, tmp_path):
    """
    Un proceso que no puede operar NO debe retener el liderazgo: si lo hiciera,
    bloquearia a otro proceso con el esquema correcto.
    """
    ruta = str(tmp_path / "l.lock")
    roto = CoordinadorTrading(
        objetivo=objetivo, candado=CandadoLocal(ruta), nombre="loop-roto",
        precondiciones=(precondicion_con(
            EstadoEsquema(MIGRACION_REQUERIDA, "0001_baseline", "0002_ordenes")),))
    sano = CoordinadorTrading(
        objetivo=objetivo, candado=CandadoLocal(ruta), nombre="loop-sano",
        precondiciones=(precondicion_con(
            EstadoEsquema(ALINEADO, "0002_ordenes", "0002_ordenes")),))

    assert roto.iniciar() is False
    assert sano.iniciar() is True, "el proceso roto no debe haber retenido el candado"
    sano.detener()


# ── MODO_REAL + esquema desalineado = fallo cerrado ─────────────────────────
def test_modo_real_con_esquema_desalineado_no_opera(objetivo, tmp_path, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "MODO_REAL", True)

    coord = CoordinadorTrading(
        objetivo=objetivo, candado=CandadoLocal(str(tmp_path / "l.lock")),
        nombre="loop-live",
        precondiciones=(precondicion_con(
            EstadoEsquema(MIGRACION_REQUERIDA, "0001_baseline", "0002_ordenes")),))

    assert coord.iniciar() is False, "LIVE con esquema desalineado debe fallar cerrado"
    assert coord.activo is False


# ── Ninguna de estas rutas migra ────────────────────────────────────────────
def test_ninguna_precondicion_ejecuta_migraciones(tmp_path, monkeypatch):
    """Comprobar el esquema jamas debe aplicar una migracion."""
    aplicadas = []
    monkeypatch.setattr(command, "upgrade",
                        lambda *a, **k: aplicadas.append("upgrade"))
    monkeypatch.setattr(command, "stamp", lambda *a, **k: aplicadas.append("stamp"))

    url = f"sqlite:///{tmp_path / 'atrasada.db'}"
    cfg = _cfg(url)
    # Se aplica la baseline con el comando real ANTES de instrumentar:
    monkeypatch.undo()
    command.upgrade(cfg, "0001_baseline")
    monkeypatch.setattr(command, "upgrade",
                        lambda *a, **k: aplicadas.append("upgrade"))
    monkeypatch.setattr(command, "stamp", lambda *a, **k: aplicadas.append("stamp"))

    from backend.esquema import estado_esquema
    e = sa.create_engine(url)
    antes = set(sa.inspect(e).get_table_names())
    for _ in range(3):
        estado_esquema(engine=e)

    assert aplicadas == [], f"la comprobacion migro: {aplicadas}"
    assert set(sa.inspect(e).get_table_names()) == antes


def test_main_declara_la_precondicion_de_esquema():
    """Guarda estructural: el coordinador real la lleva conectada."""
    fuente = (RAIZ / "backend" / "main.py").read_text(encoding="utf-8")
    assert "_precondicion_esquema" in fuente
    arbol = ast.parse(fuente)
    llamada = next(n for n in ast.walk(arbol)
                   if isinstance(n, ast.Call)
                   and getattr(n.func, "id", None) == "CoordinadorTrading")
    claves = {k.arg for k in llamada.keywords}
    assert "precondiciones" in claves, \
        "el coordinador real debe recibir la precondicion de esquema"


def test_importar_main_sigue_sin_conectar_ni_migrar(monkeypatch):
    """La precondicion no puede haber reintroducido efectos en el import."""
    conexiones, ddl = [], []
    original = sa.engine.Engine.connect
    monkeypatch.setattr(sa.engine.Engine, "connect",
                        lambda self, *a, **k: (conexiones.append(str(self.url)),
                                               original(self, *a, **k))[1])
    monkeypatch.setattr(sa.MetaData, "create_all",
                        lambda self, *a, **k: ddl.append("create_all"))

    import importlib
    import backend.main
    importlib.reload(backend.main)

    assert conexiones == [], f"importar abrio conexiones: {conexiones}"
    assert ddl == [], f"importar ejecuto DDL: {ddl}"
