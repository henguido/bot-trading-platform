"""
Persistir antes de esperar  (correccion descubierta en el benchmark de 03A).

EL PROBLEMA
    Las salidas tempranas de `trading_loop` hacian `time.sleep(WAIT_TIME)`
    DENTRO del `try`, o sea ANTES del `finally` que vuelca la telemetria. El
    `finally` garantizaba que se volcase, pero no que se volcase pronto: con
    WAIT_TIME=14400 el dato tardaba 4 horas en aparecer.

    Se observo de verdad: el primer benchmark de 03A dio "0 elegibles" -que con
    el Eligibility Gate es un resultado NORMAL- y `ciclo_http_audit` seguia
    vacia diez minutos despues.

LA CORRECCION
    Las ramas solo MARCAN que hay que esperar; el sueno ocurre en el `finally`,
    detras del volcado:

        fin logico del ciclo -> volcar() -> WAIT_TIME -> siguiente iteracion

    La cadencia NO cambia: cada rama espera exactamente las veces que esperaba
    antes, y la salida normal sigue sin esperar.

Ninguna prueba sale a la red.
"""
import ast
import pathlib
import threading
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

RAIZ = pathlib.Path(__file__).resolve().parents[1]
MAIN = RAIZ / "backend" / "main.py"


class _Parar(BaseException):
    """Corta el `while True` sin pasar por su `except Exception`."""


FILTROS_OK = [{"filterType": "LOT_SIZE", "minQty": "0.00001",
               "maxQty": "9000", "stepSize": "0.00001"},
              {"filterType": "NOTIONAL", "minNotional": "0.10"}]
FILTROS_CAROS = [{"filterType": "LOT_SIZE", "minQty": "0.00001",
                  "maxQty": "9000", "stepSize": "0.00001"},
                 {"filterType": "NOTIONAL", "minNotional": "5.00"}]


def _metricas_sanas(precios):
    """
    Metricas de ticker/24hr que pasan todos los filtros duros del scanner (03B).

    Se generan a partir del precio de cada simbolo para que los fixtures del
    bucle sigan midiendo lo que median antes del scanner.
    """
    return {s: {"lastPrice": str(p), "bidPrice": str(p * 0.9995),
                "askPrice": str(p * 1.0005), "quoteVolume": "1000000",
                "count": "5000", "highPrice": str(p * 1.05),
                "lowPrice": str(p), "priceChangePercent": "2.5"}
            for s, p in precios.items()}


def _simbolos(filtros):
    return [{"symbol": "XUSDT", "baseAsset": "X", "quoteAsset": "USDT",
             "status": "TRADING", "isSpotTradingAllowed": True,
             "filters": filtros}]


@pytest.fixture
def bucle(monkeypatch):
    """
    trading_loop instrumentado para observar el ORDEN de los efectos.

    `eventos` recoge, en secuencia, cada volcado y cada espera. Es lo unico que
    permite afirmar que la telemetria se persiste ANTES de dormir.
    """
    import backend.main as main
    from backend.config import settings
    from backend.risk import reloj
    from backend.risk.estado import EstadoRiesgo
    from backend.utils import asset_collector as ac
    from backend import telemetria_http

    eventos = []
    registro = {"llm": [], "iteraciones": 0, "ciclos_llm": []}
    escenario = {"filtros": FILTROS_OK, "usuario": True, "activos": True,
                 "evaluable": True, "fallo": None, "iteraciones": 1}

    monkeypatch.setattr(settings, "MODO_REAL", False)
    monkeypatch.setattr(ac.simulator, "positions", {}, raising=False)
    monkeypatch.setattr(main.time, "sleep",
                        lambda s: eventos.append(("sleep", s)))
    monkeypatch.setattr(telemetria_http.MedidorCicloHttp, "volcar",
                        lambda self, **kw: (eventos.append(("volcar", self.ciclo_id)), 0)[1])

    def contexto_falso():
        registro["iteraciones"] += 1
        eventos.append(("inicio", registro["iteraciones"]))
        if registro["iteraciones"] > escenario["iteraciones"]:
            raise _Parar()
        if escenario["fallo"] is not None:
            raise escenario["fallo"]
        return SimpleNamespace(
            usuario_id=1 if escenario["usuario"] else None,
            estado={}, ultimos_movimientos={}, ultimos_precios_venta={})

    monkeypatch.setattr(main, "cargar_contexto_usuario", contexto_falso)
    monkeypatch.setattr(main.binance, "init_client", lambda: None)
    monkeypatch.setattr(main.binance, "get_price_snapshot",
                        lambda medicion=None: {"XUSDT": 100.0})
    monkeypatch.setattr(main.binance, "get_market_metrics",
                        lambda medicion=None: _metricas_sanas({"XUSDT": 100.0}))
    monkeypatch.setattr(main.binance, "get_multiple_prices",
                        lambda symbols, snapshot=None, medicion=None: {
                            s: (snapshot or {}).get(s) for s in symbols
                            if (snapshot or {}).get(s)})
    monkeypatch.setattr(main.news_connector, "obtener_noticias_combinadas",
                        lambda total=6, medidor=None: ["n1"])
    monkeypatch.setattr(
        main, "get_available_assets",
        lambda medidor=None: (
            ([{"symbol": "XUSDT", "type": "crypto"}] if escenario["activos"] else []),
            [{"asset": "USDT", "free": "20.0", "locked": "0.0"}],
            _simbolos(escenario["filtros"])))
    monkeypatch.setattr(main, "get_market_pairs",
                        lambda symbols_info=None, snapshot=None, medidor=None: [])
    monkeypatch.setattr(main, "mercado_ny_abierto", lambda: False)
    monkeypatch.setattr(main, "precio_medio_de", lambda estado, symbol: None)
    monkeypatch.setattr(main, "construir_cartera",
                        lambda **k: SimpleNamespace(
                            modo="PAPER", capital_disponible=lambda: 20.0,
                            cantidad_disponible=lambda s: 0.0,
                            estado_riesgo=lambda: EstadoRiesgo(
                                dia=reloj.dia_de_riesgo())))

    def llm_falso(*a, **k):
        registro["llm"].append({"activos": a[0] if a else None} | k)
        registro["ciclos_llm"].append(k.get("ciclo"))
        return [], "sin json"

    monkeypatch.setattr(main.openai, "analyze_multiple_assets", llm_falso)

    def ejecutar(**cambios):
        escenario.update(cambios)
        with pytest.raises(_Parar):
            main.trading_loop()
        return eventos, registro

    ejecutar.WAIT = settings.WAIT_TIME
    return ejecutar


def _por_iteracion(eventos):
    """
    Parte los eventos en un bloque por iteracion del bucle.

    Se corta por el marcador `inicio`, no por `volcar`: el sleep pertenece a la
    MISMA iteracion que su volcado y va detras de el, asi que volcar no sirve
    como separador.
    """
    bloques, actual = [], None
    for ev in eventos:
        if ev[0] == "inicio":
            if actual is not None:
                bloques.append(actual)
            actual = []
            continue
        actual.append(ev)
    if actual is not None:
        bloques.append(actual)
    return bloques


def _primera_iteracion(eventos):
    bloques = _por_iteracion(eventos)
    return bloques[0] if bloques else []


# ═══════════════════════════════════════════════════════════════════════════
# 1-2 · CERO ELEGIBLES: VOLCAR ANTES DE ESPERAR, Y UNA SOLA ESPERA
# ═══════════════════════════════════════════════════════════════════════════
def test_1_cero_elegibles_vuelca_antes_de_esperar(bucle):
    """El caso exacto del benchmark de 03A."""
    eventos, registro = bucle(filtros=FILTROS_CAROS)
    primera = _primera_iteracion(eventos)

    tipos = [t for t, _ in primera]
    assert "volcar" in tipos, "el ciclo debe volcar su telemetria"
    assert tipos.index("volcar") < len(tipos), "volcar existe"
    if "sleep" in tipos:
        assert tipos.index("volcar") < tipos.index("sleep"), (
            f"la telemetria debe persistirse ANTES de esperar; orden={tipos}")
    assert registro["llm"] == [], "sin elegibles no se llama al LLM"


def test_2_sigue_existiendo_exactamente_una_espera_wait_time(bucle):
    eventos, _ = bucle(filtros=FILTROS_CAROS)
    primera = _primera_iteracion(eventos)
    esperas = [v for t, v in primera if t == "sleep"]

    assert esperas == [bucle.WAIT], (
        f"debe haber exactamente UNA espera de WAIT_TIME, hubo {esperas}")


def test_3_no_se_llama_al_llm_sin_elegibles(bucle):
    _, registro = bucle(filtros=FILTROS_CAROS)
    assert registro["llm"] == []
    assert registro["ciclos_llm"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 4 · `ciclo` CONSERVA SU SEMANTICA
# ═══════════════════════════════════════════════════════════════════════════
def test_4_ciclo_conserva_exactamente_la_semantica_anterior(bucle):
    """
    Con activos elegibles, el LLM sigue recibiendo impares: el `ciclo += 1`
    anterior a la llamada no se ha movido.
    """
    _, registro = bucle(iteraciones=4)
    assert registro["ciclos_llm"] == [1, 3], (
        f"la cadencia efectiva ha cambiado: {registro['ciclos_llm']}")


def test_4b_los_incrementos_de_ciclo_no_se_han_movido():
    fn = _trading_loop()
    incrementos = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.AugAssign)
                   and isinstance(n.target, ast.Name) and n.target.id == "ciclo"]
    assert len(incrementos) == 5, (
        f"02A congelo el numero de incrementos en 5, hay {len(incrementos)}")


def test_4c_evaluar_cada_n_ciclos_intacto():
    fn = _trading_loop()
    valores = [n.value.value for n in ast.walk(fn)
               if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "EVALUAR_CADA_N_CICLOS"
                       for t in n.targets)
               and isinstance(n.value, ast.Constant)]
    assert valores == [2]


# ═══════════════════════════════════════════════════════════════════════════
# 5-8 · TODAS LAS SALIDAS TEMPRANAS CONSERVAN LA CADENCIA
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("escenario,descripcion", [
    ({"usuario": False}, "sin usuario registrado"),
    ({"activos": False}, "sin activos disponibles"),
    ({"filtros": FILTROS_CAROS}, "sin activos elegibles"),
    ({"fallo": RuntimeError("fallo temprano")}, "error temprano"),
])
def test_5_a_8_cada_salida_temprana_vuelca_y_luego_espera_una_vez(
        bucle, escenario, descripcion):
    """
    Una espera de WAIT_TIME por iteracion, y el volcado SIEMPRE antes.
    Cubre: sin usuario, sin activos, sin elegibles y error temprano.
    """
    eventos, _ = bucle(**escenario)
    primera = _primera_iteracion(eventos)
    tipos = [t for t, _ in primera]
    esperas = [v for t, v in primera if t == "sleep"]

    assert "volcar" in tipos, descripcion
    assert esperas == [bucle.WAIT], f"{descripcion}: esperas={esperas}"
    assert tipos.index("volcar") < tipos.index("sleep"), (
        f"{descripcion}: se esperó antes de persistir; orden={tipos}")


def test_7b_ciclo_no_evaluable_conserva_la_cadencia(bucle):
    """
    La iteracion fuera de turno (`ciclo % EVALUAR_CADA_N_CICLOS != 0`) tambien
    vuelca antes de dormir.
    """
    eventos, registro = bucle(iteraciones=2)
    bloques = _por_iteracion(eventos)
    # Iteracion 1 evalua (ciclo 0); la 2 queda fuera de turno; la 3 lanza _Parar.
    assert len(bloques) == 3, f"un bloque por recorrido: {bloques}"

    tipos = [t for t, _ in bloques[1]]
    assert tipos.index("volcar") < tipos.index("sleep"), (
        f"la iteracion fuera de turno espero antes de persistir: {tipos}")
    assert [v for t, v in bloques[1] if t == "sleep"] == [bucle.WAIT]


def test_la_salida_normal_sigue_sin_esperar(bucle):
    """
    Un ciclo evaluado completo NO dormia antes y no debe dormir ahora: si lo
    hiciera, la cadencia real cambiaria.
    """
    eventos, _ = bucle(iteraciones=1)
    primera = _primera_iteracion(eventos)
    assert [t for t, _ in primera] == ["volcar"], (
        f"el ciclo evaluado no debe esperar; eventos={primera}")


# ═══════════════════════════════════════════════════════════════════════════
# 9 · SI EL PROCESO MUERE DURANTE EL SLEEP, LA TELEMETRIA YA ESTA
# ═══════════════════════════════════════════════════════════════════════════
def test_9_si_el_proceso_muere_en_el_sleep_la_telemetria_ya_esta_persistida(
        bucle, monkeypatch):
    """
    Se simula el apagado: el `sleep` lanza. La telemetria del ciclo ya tiene que
    estar escrita cuando eso ocurre.
    """
    import backend.main as main

    volcados = []
    from backend import telemetria_http
    monkeypatch.setattr(telemetria_http.MedidorCicloHttp, "volcar",
                        lambda self, **kw: (volcados.append(self.ciclo_id), 1)[1])

    def sleep_interrumpido(_s):
        raise KeyboardInterrupt("apagado durante la espera")

    monkeypatch.setattr(main.time, "sleep", sleep_interrumpido)

    with pytest.raises(KeyboardInterrupt):
        bucle(filtros=FILTROS_CAROS, iteraciones=99)

    assert len(volcados) == 1, (
        "la telemetria del ciclo debe estar persistida antes de la espera")


def test_9c_el_finally_no_duerme_cuando_propaga_una_base_exception(bucle):
    eventos, _ = bucle(iteraciones=0)       # primera llamada lanza _Parar
    assert [t for t, _ in eventos if t == "sleep"] == [], (
        "no se puede dormir mientras se propaga un apagado")


# ═══════════════════════════════════════════════════════════════════════════
# GUARDAS ESTRUCTURALES
# ═══════════════════════════════════════════════════════════════════════════
def _trading_loop():
    arbol = ast.parse(MAIN.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(arbol)
                if isinstance(n, ast.FunctionDef) and n.name == "trading_loop")


def _try_principal():
    fn = _trading_loop()
    bucle_while = next(n for n in ast.walk(fn) if isinstance(n, ast.While))
    return next(n for n in bucle_while.body if isinstance(n, ast.Try))


def test_no_queda_ningun_sleep_dentro_del_cuerpo_del_ciclo():
    """
    Guarda contra la regresion: un `sleep` en el cuerpo o en el `except` volveria
    a retrasar la telemetria WAIT_TIME.
    """
    principal = _try_principal()
    for zona, nodos in (("cuerpo", principal.body),
                        ("except", [n for h in principal.handlers for n in h.body])):
        for raiz in nodos:
            for nodo in ast.walk(raiz):
                if isinstance(nodo, ast.Call) and \
                        getattr(nodo.func, "attr", None) == "sleep":
                    pytest.fail(
                        f"main.py:{nodo.lineno}: hay un sleep en el {zona} del "
                        f"ciclo; debe marcar `esperar_ciclo` y dejar la espera "
                        f"en el finally, DESPUES de volcar()")


def test_el_finally_vuelca_antes_de_esperar():
    """Guarda estructural del orden volcar -> sleep."""
    principal = _try_principal()
    posiciones = {}
    for i, raiz in enumerate(principal.finalbody):
        for nodo in ast.walk(raiz):
            if not isinstance(nodo, ast.Call):
                continue
            attr = getattr(nodo.func, "attr", None)
            if attr == "volcar":
                posiciones.setdefault("volcar", nodo.lineno)
            elif attr == "sleep":
                posiciones.setdefault("sleep", nodo.lineno)

    assert "volcar" in posiciones, "el finally debe volcar la telemetria"
    assert "sleep" in posiciones, "el finally debe contener la unica espera"
    assert posiciones["volcar"] < posiciones["sleep"], (
        "volcar() tiene que ejecutarse ANTES de la espera")


def test_la_espera_del_finally_sigue_siendo_wait_time():
    principal = _try_principal()
    sleeps = [n for raiz in principal.finalbody for n in ast.walk(raiz)
              if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "sleep"]
    assert len(sleeps) == 1
    assert ast.dump(sleeps[0].args[0]) == ast.dump(
        ast.parse("settings.WAIT_TIME", mode="eval").body), \
        "el tiempo de espera no puede cambiar"


def test_la_espera_esta_condicionada_y_no_es_incondicional():
    """
    Si el finally durmiese siempre, el ciclo evaluado ganaria una espera que hoy
    no tiene y la cadencia cambiaria.
    """
    principal = _try_principal()
    condicionales = [n for raiz in principal.finalbody for n in ast.walk(raiz)
                     if isinstance(n, ast.If)]
    assert condicionales, "la espera del finally debe estar condicionada"
    volcado = " ".join(ast.dump(n.test) for n in condicionales)
    assert "esperar_ciclo" in volcado
    assert "exc_info" in volcado, (
        "debe evitarse dormir mientras se propaga un apagado")


def test_hay_seis_marcas_de_espera_una_por_salida_temprana():
    """
    Las seis ramas que esperaban siguen esperando: ni una mas, ni una menos.
    """
    fn = _trading_loop()
    marcas = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "esperar_ciclo"
                      for t in n.targets)
              and isinstance(n.value, ast.Constant) and n.value.value is True]
    assert len(marcas) == 6, (
        f"habia 6 salidas tempranas con espera; hay {len(marcas)} marcas")


# ═══════════════════════════════════════════════════════════════════════════
# 10 · PAPER / IMPORT SAFETY
# ═══════════════════════════════════════════════════════════════════════════
def test_10_paper_intacto():
    from backend.config import settings
    assert settings.TRADING_MODE == "PAPER"
    assert settings.MODO_REAL is False


def test_10b_import_safety_intacto(monkeypatch):
    conexiones, ddl = [], []
    original = sa.engine.Engine.connect
    monkeypatch.setattr(sa.engine.Engine, "connect",
                        lambda self, *a, **k: (conexiones.append(1),
                                               original(self, *a, **k))[1])
    monkeypatch.setattr(sa.MetaData, "create_all", lambda self, *a, **k: ddl.append(1))
    monkeypatch.setattr(sa.MetaData, "drop_all", lambda self, *a, **k: ddl.append(1))

    import importlib

    import backend.main
    importlib.reload(backend.main)

    assert conexiones == [] and ddl == []
    assert not [t for t in threading.enumerate() if t.name != "MainThread"]
