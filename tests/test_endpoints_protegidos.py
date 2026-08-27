"""
P0-3 · Verificacion estatica de que los endpoints financieros exigen autenticacion.

Se analiza el AST de los modulos de rutas en lugar de importarlos. Motivo:
importar `backend.main` arrancaria el hilo de trading e instanciaria clientes
de Binance y Alpaca. Aqui no se ejecuta ni una linea del backend.

Politica aplicada:
  PUBLIC        -> /login, /signup  (necesarios para obtener credenciales)
  AUTHENTICATED -> todo lo que exponga balances, transacciones, posiciones,
                   decisiones o historial financiero
"""
import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

# (archivo, ruta, ¿debe exigir autenticacion?)
ENDPOINTS = [
    ("backend/main.py",                        "/api/historial",             True),
    ("backend/main.py",                        "/api/resumen",               True),
    ("backend/main.py",                        "/login",                     False),
    ("backend/main.py",                        "/signup",                    False),
    # Sonda de vida y liderazgo (P0-13). Publica a proposito: las sondas de
    # infraestructura no llevan token. No expone saldos, posiciones ni
    # transacciones; solo modo de ejecucion y quien lidera el bucle.
    ("backend/main.py",                        "/health",                    False),
    ("backend/routes/binance_routes.py",       "/balance",                   True),
    # Readiness resume postura operativa/configuracion. Aunque no expone
    # detalles de checks ni secretos, sigue siendo diagnostico interno.
    ("backend/routes/binance_routes.py",       "/api/readiness",             True),
    ("backend/routes/transacciones_routes.py", "/api/transacciones-reales", True),
    # Expone diagnostico del embudo de decision del usuario (candidatos,
    # rechazos, ejecuciones). Es dato operativo/financiero y debe quedar aislado.
    ("backend/routes/transacciones_routes.py", "/api/decision-cycles",       True),
    ("backend/routes/historial_routes.py",     "/api/historial",             True),
]

METODOS = {"get", "post", "put", "delete", "patch"}


def _handlers(ruta_archivo):
    """Devuelve {ruta_http: nodo_funcion} de un modulo con decoradores de ruta."""
    arbol = ast.parse(Path(RAIZ, ruta_archivo).read_text(encoding="utf-8"))
    encontrados = {}
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in nodo.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            if dec.func.attr not in METODOS:
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant):
                continue
            encontrados[dec.args[0].value] = nodo
    return encontrados


def _exige_autenticacion(nodo_funcion):
    """True si algun parametro tiene por defecto Depends(get_current_user)."""
    for defecto in nodo_funcion.args.defaults + nodo_funcion.args.kw_defaults:
        if not (isinstance(defecto, ast.Call) and getattr(defecto.func, "id", None) == "Depends"):
            continue
        if defecto.args and getattr(defecto.args[0], "id", None) == "get_current_user":
            return True
    return False


@pytest.mark.parametrize("archivo,ruta,protegido", ENDPOINTS)
def test_politica_de_autenticacion_por_endpoint(archivo, ruta, protegido):
    handlers = _handlers(archivo)
    assert ruta in handlers, f"no se encontro el endpoint {ruta} en {archivo}"
    real = _exige_autenticacion(handlers[ruta])
    if protegido:
        assert real, f"{ruta} ({archivo}) expone datos financieros SIN autenticacion"
    else:
        assert not real, f"{ruta} ({archivo}) debe seguir siendo publico"


def test_ningun_endpoint_financiero_quedo_sin_revisar():
    """Si alguien anade una ruta nueva, esta prueba obliga a clasificarla."""
    declarados = {(a, r) for a, r, _ in ENDPOINTS}
    for archivo in {a for a, _, _ in ENDPOINTS}:
        for ruta in _handlers(archivo):
            assert (archivo, ruta) in declarados, (
                f"endpoint sin clasificar: {ruta} en {archivo}. "
                "Anadelo a ENDPOINTS indicando si debe ser publico o autenticado."
            )


def test_las_pruebas_no_importan_conectores_reales():
    """
    Salvaguarda: ningun modulo de test debe importar los conectores, cuyos
    constructores pueden abrir conexiones.

    `backend.main` SI puede importarse desde P0-13/P1-7: ya no arranca el bucle
    al importarse y el cliente de Binance es perezoso. Lo demuestran
    test_coordinador.test_importar_main_no_arranca_ningun_bucle y
    test_main_no_arranca_hilos_a_nivel_de_modulo.
    """
    # openai_connector NO esta en la lista: su __init__ solo guarda cadenas y
    # no abre ninguna conexion (lo demuestra
    # test_el_constructor_de_openai_no_abre_red, mas abajo). Las pruebas de
    # telemetria necesitan importarlo, y siempre sustituyen requests.post por
    # un doble. Los otros tres SI construyen clientes de red en __init__.
    prohibidos = ("real_trading_connector", "alpaca_connector",
                  "oanda_connector")
    for archivo in Path(RAIZ, "tests").glob("*.py"):
        texto = archivo.read_text(encoding="utf-8")
        for p in prohibidos:
            assert f"import {p}" not in texto and f"from {p}" not in texto, (
                f"{archivo.name} importa {p}: podria abrir conexiones reales"
            )


def test_el_constructor_de_openai_no_abre_red():
    """
    Justifica la excepcion de la salvaguarda anterior: construir
    OpenAIConnector no debe hacer ninguna peticion. Si algun dia deja de ser
    cierto, esta prueba falla y hay que devolverlo a la lista de prohibidos.
    """
    import requests

    llamadas = []
    originales = {n: getattr(requests, n) for n in ("post", "get", "request")}
    for n in originales:
        setattr(requests, n, lambda *a, **k: llamadas.append(1))
    try:
        from backend.connectors.apis.openai_connector import OpenAIConnector
        OpenAIConnector()
    finally:
        for n, f in originales.items():
            setattr(requests, n, f)

    assert llamadas == [], "el constructor de OpenAIConnector no puede hacer red"


def test_modo_paper_durante_las_pruebas():
    """Regla permanente: las pruebas jamas corren con LIVE habilitado."""
    from backend.config import settings
    assert settings.TRADING_MODE == "PAPER"
    assert settings.MODO_REAL is False
