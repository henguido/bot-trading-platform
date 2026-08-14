"""
P0-4 y P0-5 · Ciclo de vida y refresco del estado del portafolio.

P0-4: si no habia usuarios al arrancar, las globales `estado`,
      `ultimos_movimientos` y `ultimos_precios_venta` no se definian nunca.
      Si alguien se registraba despues, el bucle moria con NameError.
P0-5: si si habia usuario, esas globales se cargaban una unica vez al importar
      el modulo, asi que el precio promedio quedaba congelado para siempre.

Todo se prueba contra SQLite en memoria inyectando la session_factory.
No se importa backend.main ni se contacta con Binance, Alpaca, OANDA u OpenAI.
"""
import ast
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services.real_trading import (
    cargar_contexto_usuario,
    guardar_transaccion_real,
)

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def fabrica_sesiones():
    """SQLite en memoria, aislado por prueba. Nunca toca la BD real."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


def _crear_usuario(fabrica, email="trader@ejemplo.com"):
    with fabrica() as db:
        u = models.User(nombre="Trader", email=email, password_hash="hash-irrelevante")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id


# ── P0-4 · la ausencia de usuario es estado NORMAL ───────────────────────────
def test_sin_usuarios_devuelve_contexto_vacio_sin_excepcion(fabrica_sesiones):
    ctx = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    assert ctx.usuario_id is None
    assert ctx.estado == {}
    assert ctx.ultimos_movimientos == {}
    assert ctx.ultimos_precios_venta == {}


def test_usuario_registrado_despues_se_detecta_sin_reiniciar(fabrica_sesiones):
    """Simula P0-4: primero no hay nadie, luego alguien hace /signup."""
    assert cargar_contexto_usuario(session_factory=fabrica_sesiones).usuario_id is None

    uid = _crear_usuario(fabrica_sesiones)

    ctx = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    assert ctx.usuario_id == uid, "el bot debe reincorporarse solo tras el alta"
    assert ctx.estado == {}


def test_usuario_sin_transacciones_da_estado_vacio(fabrica_sesiones):
    _crear_usuario(fabrica_sesiones)
    ctx = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    assert ctx.usuario_id is not None
    assert ctx.estado == {}


# ── P0-5 · el precio promedio se actualiza ENTRE iteraciones ─────────────────
def test_el_precio_promedio_se_actualiza_entre_iteraciones(fabrica_sesiones):
    """
    Escenario exigido:
        estado inicial            -> 0 BTC
        compra 0.001 @ 100000     -> siguiente carga: 0.001, avg 100000
        compra 0.001 @ 120000     -> siguiente carga: 0.002, avg 110000

    Antes de P0-5 la segunda y tercera lectura habrian devuelto siempre el
    valor congelado del arranque.
    """
    uid = _crear_usuario(fabrica_sesiones)
    SIMBOLO = "BTCUSDT"

    # ── iteracion 1: sin posicion ───────────────────────────────────────────
    ctx1 = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    assert ctx1.estado.get(SIMBOLO) is None, "no deberia haber posicion inicial"

    # compra 0.001 @ 100.000
    with fabrica_sesiones() as db:
        guardar_transaccion_real(db, usuario_id=uid, symbol=SIMBOLO,
                                 action="COMPRAR", price=100000.0, quantity=0.001)

    # ── iteracion 2: contexto FRESCO ────────────────────────────────────────
    ctx2 = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    pos2 = ctx2.estado[SIMBOLO]
    assert pos2["cantidad"] == pytest.approx(0.001)
    assert pos2["precio_promedio"] == pytest.approx(100000.0)

    # compra adicional 0.001 @ 120.000
    with fabrica_sesiones() as db:
        guardar_transaccion_real(db, usuario_id=uid, symbol=SIMBOLO,
                                 action="COMPRAR", price=120000.0, quantity=0.001)

    # ── iteracion 3: contexto FRESCO otra vez ───────────────────────────────
    ctx3 = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    pos3 = ctx3.estado[SIMBOLO]
    assert pos3["cantidad"] == pytest.approx(0.002)
    assert pos3["precio_promedio"] == pytest.approx(110000.0), (
        "el coste base debe ser la media ponderada (100000+120000)/2"
    )

    # Y el valor NO quedo congelado en la primera lectura.
    assert pos3["precio_promedio"] != pos2["precio_promedio"]


def test_la_venta_actualiza_el_contexto(fabrica_sesiones):
    uid = _crear_usuario(fabrica_sesiones)
    with fabrica_sesiones() as db:
        guardar_transaccion_real(db, usuario_id=uid, symbol="BTCUSDT",
                                 action="COMPRAR", price=100000.0, quantity=0.002)
        guardar_transaccion_real(db, usuario_id=uid, symbol="BTCUSDT",
                                 action="VENDER", price=110000.0, quantity=0.002)

    ctx = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    assert ctx.estado["BTCUSDT"]["cantidad"] == pytest.approx(0.0)
    assert ctx.ultimos_precios_venta["BTCUSDT"] == pytest.approx(110000.0)
    assert "BTCUSDT" in ctx.ultimos_movimientos


# ── Sesion corta ─────────────────────────────────────────────────────────────
def test_la_sesion_se_cierra_al_terminar(fabrica_sesiones):
    """No debe quedar ninguna sesion viva entre iteraciones del bot."""
    abiertas, cerradas = [], []

    class FabricaVigilada:
        def __call__(self):
            sesion = fabrica_sesiones()
            abiertas.append(sesion)
            cerrar_original = sesion.close

            def cerrar():
                cerradas.append(sesion)
                return cerrar_original()

            sesion.close = cerrar
            return sesion

    _crear_usuario(fabrica_sesiones)
    cargar_contexto_usuario(session_factory=FabricaVigilada())

    assert len(abiertas) == 1, "debe abrir exactamente una sesion"
    assert len(cerradas) == 1, "la sesion debe cerrarse antes de devolver el contexto"


# ── Garantias estructurales sobre main.py ────────────────────────────────────
def _arbol_main():
    return ast.parse(Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8"))


def test_main_no_tiene_estado_financiero_global():
    """Regresion de P0-4/P0-5: no basta con inicializar, deben NO existir."""
    prohibidas = {"usuario_id", "estado", "ultimos_movimientos",
                  "ultimos_precios_venta", "primer_usuario"}
    globales = set()
    for nodo in _arbol_main().body:          # solo nivel de modulo
        for sub in ast.walk(nodo) if isinstance(nodo, (ast.With, ast.If, ast.For)) else [nodo]:
            if isinstance(sub, ast.Assign):
                globales |= {d.id for d in sub.targets if isinstance(d, ast.Name)}
    assert not (globales & prohibidas), f"estado financiero global: {globales & prohibidas}"


def test_main_no_usa_declaraciones_global():
    declaraciones = [n for n in ast.walk(_arbol_main()) if isinstance(n, ast.Global)]
    assert not declaraciones, f"quedan 'global': {[n.names for n in declaraciones]}"


def test_el_contexto_se_recarga_dentro_del_bucle():
    """cargar_contexto_usuario debe invocarse en CADA iteracion, no al importar."""
    bucle = None
    for nodo in ast.walk(_arbol_main()):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "trading_loop":
            bucle = next((n for n in nodo.body if isinstance(n, ast.While)), None)
    assert bucle is not None, "no se encontro el while de trading_loop"

    llamadas = [
        n for n in ast.walk(bucle)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "cargar_contexto_usuario"
    ]
    assert llamadas, "el contexto debe recargarse dentro del bucle, no al importar el modulo"


def test_signup_ya_no_lanza_hilos_de_trading():
    """Dos altas simultaneas podian arrancar dos bucles de trading a la vez."""
    for nodo in ast.walk(_arbol_main()):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "signup":
            fuente = ast.dump(nodo)
            assert "Thread" not in fuente, "signup no debe arrancar hilos"
            return
    pytest.fail("no se encontro el handler signup")
