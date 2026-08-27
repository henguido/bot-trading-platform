"""
P0-13 · Un unico trading_loop.

Antes, `threading.Thread(target=trading_loop).start()` estaba a nivel de modulo:
importar backend.main arrancaba a operar, y con --reload o --workers N habia
varios procesos con su propio bucle enviando ordenes.

Ninguna prueba aqui ejecuta el bucle real: el objetivo del coordinador es una
funcion inofensiva que solo espera. No se contacta con ningun broker.
"""
import ast
import threading
from pathlib import Path

import pytest

from backend.coordinador import (
    CandadoLocal,
    CoordinadorTrading,
    candado_por_defecto,
)

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def objetivo():
    """Bucle falso cooperativo: espera sobre el mismo Event del coordinador."""
    parar = threading.Event()

    def bucle():
        parar.wait(timeout=10)

    bucle.parar = parar
    yield bucle
    parar.set()


def _coord(objetivo, *, candado=None, nombre="prueba-loop", stop_timeout=1.0):
    return CoordinadorTrading(
        objetivo=objetivo,
        candado=candado,
        nombre=nombre,
        stop_event=objetivo.parar,
        stop_timeout=stop_timeout,
    )


# ── Importar main no arranca nada ───────────────────────────────────────────
def test_importar_main_no_arranca_ningun_bucle():
    import backend.main as m
    assert m.coordinador.activo is False, "importar backend.main no debe operar"
    assert not any("trading" in t.name for t in threading.enumerate())


def test_main_no_arranca_hilos_a_nivel_de_modulo():
    """AST: no puede haber ningun Thread(...).start() fuera de una funcion."""
    arbol = ast.parse(Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        assert "Thread" not in ast.dump(nodo), (
            "el arranque del bucle debe ser explicito, no un efecto del import"
        )


def test_signup_no_arranca_bucles():
    arbol = ast.parse(Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "signup")
    assert "Thread" not in ast.dump(fn)


def test_main_usa_lifespan_explicito():
    fuente = Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8")
    assert "lifespan=lifespan" in fuente, "la app debe declarar un lifespan"
    assert "coordinador.iniciar()" in fuente
    assert "coordinador.detener()" in fuente


# ── Arranque idempotente ────────────────────────────────────────────────────
def test_iniciar_una_vez_deja_exactamente_un_bucle(objetivo):
    coord = _coord(objetivo, nombre="prueba-loop")
    assert coord.activo is False

    assert coord.iniciar() is True
    assert coord.activo is True
    assert coord.es_lider is True
    assert sum(1 for t in threading.enumerate() if t.name == "prueba-loop") == 1

    assert coord.detener() is True


def test_iniciar_repetido_no_crea_bucles_adicionales(objetivo):
    coord = _coord(objetivo, nombre="prueba-idem")
    for _ in range(5):
        assert coord.iniciar() is True

    vivos = sum(1 for t in threading.enumerate() if t.name == "prueba-idem")
    assert vivos == 1, f"se esperaba 1 bucle, hay {vivos}"

    assert coord.detener() is True


# ── Liderazgo: solo uno gana ────────────────────────────────────────────────
def test_dos_candados_sobre_el_mismo_recurso_solo_uno_gana(tmp_path):
    ruta = str(tmp_path / "lider.lock")
    primero, segundo = CandadoLocal(ruta), CandadoLocal(ruta)

    assert primero.adquirir() is True
    assert segundo.adquirir() is False, "dos procesos no pueden liderar a la vez"

    primero.liberar()
    assert segundo.adquirir() is True, "liberado el primero, el segundo puede tomarlo"
    segundo.liberar()


def test_dos_coordinadores_solo_uno_opera(tmp_path, objetivo):
    ruta = str(tmp_path / "lider.lock")
    a = _coord(objetivo, candado=CandadoLocal(ruta), nombre="loop-a")
    b = _coord(objetivo, candado=CandadoLocal(ruta), nombre="loop-b")

    assert a.iniciar() is True
    assert b.iniciar() is False, "el segundo proceso no debe operar"

    assert a.activo is True and a.es_lider is True
    assert b.activo is False and b.es_lider is False
    assert "liderazgo" in b.motivo_inactivo.lower(), \
        "el proceso no lider debe explicar por que no opera"

    assert a.detener() is True


def test_tras_detener_el_liderazgo_queda_libre(tmp_path, objetivo):
    ruta = str(tmp_path / "lider.lock")
    a = _coord(objetivo, candado=CandadoLocal(ruta), nombre="loop-1")
    b = _coord(objetivo, candado=CandadoLocal(ruta), nombre="loop-2")

    assert a.iniciar() is True
    assert a.detener() is True
    assert a.activo is False
    assert a.es_lider is False

    assert b.iniciar() is True, "liberado el candado, otro proceso puede tomar el relevo"
    assert b.detener() is True


def test_hilo_no_cooperativo_retiene_liderazgo_hasta_terminar(tmp_path):
    """Nunca se libera el candado mientras el objetivo anterior siga vivo."""
    ruta = str(tmp_path / "lider.lock")
    liberar = threading.Event()
    stop = threading.Event()

    def no_cooperativo():
        liberar.wait(timeout=1)

    a = CoordinadorTrading(
        objetivo=no_cooperativo,
        candado=CandadoLocal(ruta),
        nombre="loop-no-coop",
        stop_event=stop,
        stop_timeout=0.01,
    )
    b = CoordinadorTrading(
        objetivo=lambda: None,
        candado=CandadoLocal(ruta),
        nombre="loop-relevo",
    )

    assert a.iniciar() is True
    assert a.detener() is False
    assert a.activo is True
    assert a.es_lider is True
    assert "detencion pendiente" in a.motivo_inactivo
    assert b.iniciar() is False, "el relevo no puede entrar mientras el hilo viejo vive"

    liberar.set()
    a._hilo.join(timeout=1)
    assert a.detener() is True
    assert b.iniciar() is True
    assert b.detener() is True


# ── Seleccion de candado ────────────────────────────────────────────────────
def test_postgres_usa_advisory_lock():
    """En produccion el candado debe funcionar entre procesos y maquinas."""
    from backend.coordinador import CandadoPostgres
    fuente = Path(RAIZ, "backend", "coordinador.py").read_text(encoding="utf-8")
    assert "pg_try_advisory_lock" in fuente
    assert "pg_advisory_unlock" in fuente
    assert candado_por_defecto("sqlite:///./x.db").__class__ is CandadoLocal


def test_start_sh_no_usa_reload():
    fuente = Path(RAIZ, "start.sh").read_text(encoding="utf-8")
    assert "--reload" not in fuente, "--reload respawnea el proceso y duplicaria el bucle"
