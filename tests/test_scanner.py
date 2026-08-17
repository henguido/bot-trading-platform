"""
Fase BOT 2.0-03B · Scanner deterministico de candidatos.

El scanner solo ORDENA y RECORTA candidatos de compra nueva. No decide, no
dimensiona, no autoriza y no pregunta nada a un LLM.

Todo aqui es aritmetica pura sobre metricas ya obtenidas: sin red, sin IA, sin
BD, sin aleatoriedad.
"""
import ast
import pathlib
import threading
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from backend import scanner as sc

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SCANNER = RAIZ / "backend" / "scanner.py"
MAIN = RAIZ / "backend" / "main.py"


def fila(*, precio="100", bid="99.95", ask="100.05", qv="1000000",
         trades="5000", hi="105", lo="100", cambio="2.5"):
    """Fila de ticker/24hr a medida."""
    return {"lastPrice": precio, "bidPrice": bid, "askPrice": ask,
            "quoteVolume": qv, "count": trades, "highPrice": hi,
            "lowPrice": lo, "priceChangePercent": cambio}


def activo(symbol, *, posicion=0.0):
    return {"symbol": symbol, "price": 100.0, "position_quantity": posicion,
            "average_price": None, "_position_detected": posicion > 0,
            "_balance_detected": posicion > 0}


def universo(n, *, base_qv=1_000_000, base_trades=5_000):
    """n activos sanos y distinguibles, con features escalonadas."""
    activos, metricas = [], {}
    for i in range(n):
        sym = f"A{i:03d}USDT"
        activos.append(activo(sym))
        metricas[sym] = fila(qv=str(base_qv * (i + 1)),
                             trades=str(base_trades + i * 10),
                             hi=str(100 + 5 + i * 0.1), lo="100",
                             cambio=str(1.0 + i * 0.05))
    return activos, metricas


# ═══════════════════════════════════════════════════════════════════════════
# 1-2 · DETERMINISMO Y ORDEN ESTABLE
# ═══════════════════════════════════════════════════════════════════════════
def test_1_mismo_snapshot_mismo_resultado():
    activos, metricas = universo(60)
    primera = sc.aplicar(activos, metricas, top_n=20)
    for _ in range(6):
        assert [a["symbol"] for a in sc.aplicar(activos, metricas, top_n=20)] \
            == [a["symbol"] for a in primera]


def test_1b_los_scores_son_identicos_entre_ejecuciones():
    _, metricas = universo(40)
    ms = [sc.leer_metricas(s, f) for s, f in metricas.items()]
    a = [(c.symbol, c.score) for c in sc.puntuar(ms)]
    b = [(c.symbol, c.score) for c in sc.puntuar(ms)]
    assert a == b


def test_2_el_orden_no_depende_del_orden_de_llegada():
    """El scanner ordena por symbol antes de calcular nada."""
    activos, metricas = universo(50)
    normal = sc.aplicar(activos, metricas, top_n=15)
    invertido = sc.aplicar(list(reversed(activos)), metricas, top_n=15)
    mezclado = sc.aplicar(activos[25:] + activos[:25], metricas, top_n=15)

    assert [a["symbol"] for a in normal] == [a["symbol"] for a in invertido]
    assert [a["symbol"] for a in normal] == [a["symbol"] for a in mezclado]


def test_2b_no_hay_azar_ni_reloj_en_el_scanner():
    arbol = ast.parse(SCANNER.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            volcado = ast.dump(nodo)
            for prohibido in ("random", "time", "datetime", "uuid", "secrets"):
                assert prohibido not in volcado, \
                    f"el scanner debe ser deterministico; importa {prohibido}"


# ═══════════════════════════════════════════════════════════════════════════
# 3 · DATOS FALTANTES
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("campo", ["lastPrice", "bidPrice", "askPrice",
                                   "quoteVolume", "count", "highPrice",
                                   "lowPrice"])
def test_3_un_campo_imprescindible_ausente_descarta(campo):
    f = fila()
    del f[campo]
    assert sc.leer_metricas("XUSDT", f) is None
    assert sc.evaluar_filtros(sc.leer_metricas("XUSDT", f)) == sc.DATOS_INCOMPLETOS


@pytest.mark.parametrize("valor", [None, "", "no-es-numero", "NaN", "inf"])
def test_3b_un_valor_ilegible_descarta(valor):
    assert sc.leer_metricas("XUSDT", fila(qv=valor)) is None


def test_3c_metricas_ausentes_para_el_symbol_descartan():
    activos, _ = universo(5)
    salida = sc.aplicar(activos, {}, top_n=20)
    assert salida == [], "sin metricas no se puntua nada"


def test_3d_priceChangePercent_ausente_no_invalida_el_activo():
    """El momentum es la senal mas debil: su ausencia no descarta."""
    f = fila()
    del f["priceChangePercent"]
    m = sc.leer_metricas("XUSDT", f)
    assert m is not None and m.cambio_pct == 0.0
    assert sc.evaluar_filtros(m) == sc.CANDIDATO


@pytest.mark.parametrize("f,caso", [
    (fila(precio="0"), "precio cero"),
    (fila(bid="0"), "bid cero"),
    (fila(lo="0"), "low cero"),
    (fila(bid="101", ask="100"), "ask < bid"),
    (fila(hi="90", lo="100"), "high < low"),
    (fila(qv="-1"), "volumen negativo"),
    ("no soy un dict", "fila no dict"),
    (None, "fila None"),
])
def test_3e_datos_incoherentes_se_descartan(f, caso):
    assert sc.leer_metricas("XUSDT", f) is None, caso


# ═══════════════════════════════════════════════════════════════════════════
# 4-5 · SPREAD Y VOLUMEN
# ═══════════════════════════════════════════════════════════════════════════
def test_4_spread_excesivo_se_descarta():
    # p95 medido del universo = 42,5 bps; el corte esta en 50.
    assert sc.SPREAD_MAXIMO_BPS == 50.0
    ancho = sc.leer_metricas("XUSDT", fila(bid="98", ask="102"))   # ~400 bps
    assert sc.evaluar_filtros(ancho) == sc.SPREAD_EXCESIVO


def test_4b_el_spread_se_calcula_sobre_el_punto_medio():
    m = sc.leer_metricas("XUSDT", fila(bid="99.95", ask="100.05"))
    assert m.spread_bps == pytest.approx(10.0, abs=0.01)


def test_4c_justo_en_el_umbral_de_spread_sigue_siendo_candidato():
    # spread exactamente 50 bps: bid=99.75 ask=100.25 -> mid=100 -> 50 bps
    m = sc.leer_metricas("XUSDT", fila(bid="99.75", ask="100.25"))
    assert m.spread_bps == pytest.approx(50.0, abs=0.01)
    assert sc.evaluar_filtros(m) == sc.CANDIDATO, "el limite es inclusivo"


def test_5_volumen_insuficiente_se_descarta():
    assert sc.QUOTE_VOLUME_MINIMO_USDT == 100_000.0
    pobre = sc.leer_metricas("XUSDT", fila(qv="50000"))
    assert sc.evaluar_filtros(pobre) == sc.LIQUIDEZ_INSUFICIENTE


def test_5b_mercado_inactivo_se_descarta():
    assert sc.TRADES_MINIMOS_24H == 1000
    muerto = sc.leer_metricas("XUSDT", fila(trades="150"))
    assert sc.evaluar_filtros(muerto) == sc.MERCADO_INACTIVO


def test_5c_sin_recorrido_se_descarta():
    """Las stablecoins caen aqui: sin rango no hay nada que capturar."""
    assert sc.RANGO_MINIMO_24H == 0.01
    plano = sc.leer_metricas("USDPUSDT", fila(precio="1", bid="0.9999",
                                             ask="1.0001", hi="1.0002",
                                             lo="1.0", cambio="0.0"))
    assert sc.evaluar_filtros(plano) == sc.SIN_RECORRIDO


def test_5d_un_activo_sano_pasa_todos_los_filtros():
    assert sc.evaluar_filtros(sc.leer_metricas("XUSDT", fila())) == sc.CANDIDATO


def test_5e_los_umbrales_estan_anclados_a_percentiles_documentados():
    """Guarda: los cortes no pueden cambiarse sin actualizar su justificacion."""
    fuente = SCANNER.read_text(encoding="utf-8")
    assert "DISTRIBUCION MEDIDA" in fuente
    for ancla in ("p95", "p5", "p25", "p50"):
        assert ancla in fuente, f"falta el anclaje {ancla} en la documentacion"


# ═══════════════════════════════════════════════════════════════════════════
# 6 · SCORE
# ═══════════════════════════════════════════════════════════════════════════
def test_6_el_score_esta_acotado_entre_0_y_1():
    _, metricas = universo(80)
    ms = [sc.leer_metricas(s, f) for s, f in metricas.items()]
    for c in sc.puntuar(ms):
        assert 0.0 <= c.score <= 1.0


def test_6b_los_pesos_suman_uno():
    assert sum(sc.PESOS.values()) == pytest.approx(1.0)


def test_6c_mas_liquidez_puntua_mas_si_lo_demas_es_igual():
    metricas = {
        "AUSDT": fila(qv="100000"),
        "BUSDT": fila(qv="100000000"),
    }
    ms = [sc.leer_metricas(s, f) for s, f in metricas.items()]
    orden = [c.symbol for c in sc.puntuar(ms)]
    assert orden[0] == "BUSDT", "el de mas volumen debe ir primero"


def test_6d_menos_spread_puntua_mas_si_lo_demas_es_igual():
    metricas = {
        "AUSDT": fila(bid="99.80", ask="100.20"),   # 40 bps
        "BUSDT": fila(bid="99.99", ask="100.01"),   # 2 bps
    }
    ms = [sc.leer_metricas(s, f) for s, f in metricas.items()]
    assert [c.symbol for c in sc.puntuar(ms)][0] == "BUSDT"


def test_6e_mas_recorrido_puntua_mas_si_lo_demas_es_igual():
    metricas = {
        "AUSDT": fila(hi="101", lo="100"),      # 1%
        "BUSDT": fila(hi="120", lo="100"),      # 20%
    }
    ms = [sc.leer_metricas(s, f) for s, f in metricas.items()]
    assert [c.symbol for c in sc.puntuar(ms)][0] == "BUSDT"


def test_6f_el_score_expone_su_desglose():
    ms = [sc.leer_metricas("XUSDT", fila()), sc.leer_metricas("YUSDT", fila())]
    c = sc.puntuar(ms)[0]
    assert set(c.features) == set(sc.PESOS), "cada peso debe tener su feature"
    assert all(0.0 <= v <= 1.0 for v in c.features.values())
    assert c.symbol in str(c) and "score=" in str(c)


def test_6g_un_solo_candidato_recibe_score_neutro():
    """Con n=1 no hay distribucion: el percentil es 0,5 por convencion."""
    c = sc.puntuar([sc.leer_metricas("XUSDT", fila())])
    assert len(c) == 1
    assert c[0].score == pytest.approx(0.5)


def test_6h_los_percentiles_no_dependen_de_la_escala_absoluta():
    """Rango percentil: robusto a colas brutales como un spread de 377 bps."""
    p = sc._percentiles([1.0, 2.0, 3.0])
    assert p == [0.0, 0.5, 1.0]
    p2 = sc._percentiles([1.0, 2.0, 100000.0])
    assert p2 == [0.0, 0.5, 1.0], "el outlier no aplasta al resto"


# ═══════════════════════════════════════════════════════════════════════════
# 7 · HARD FILTERS EN CONJUNTO
# ═══════════════════════════════════════════════════════════════════════════
def test_7_los_descartados_no_llegan_al_score():
    activos = [activo("BUENOUSDT"), activo("ANCHOUSDT"), activo("MUERTOUSDT")]
    metricas = {
        "BUENOUSDT": fila(),
        "ANCHOUSDT": fila(bid="95", ask="105"),
        "MUERTOUSDT": fila(trades="10"),
    }
    r = sc.ResumenScanner()
    salida = sc.aplicar(activos, metricas, top_n=20, resumen=r)

    assert [a["symbol"] for a in salida] == ["BUENOUSDT"]
    assert r.descartados == 2
    assert r.puntuados == 1
    assert r.por_motivo[sc.SPREAD_EXCESIVO] == 1
    assert r.por_motivo[sc.MERCADO_INACTIVO] == 1


def test_7b_si_ninguno_pasa_los_filtros_no_se_envia_nada():
    """No se fuerza el Top N con activos que no cumplen."""
    activos = [activo(f"MALO{i}USDT") for i in range(30)]
    metricas = {a["symbol"]: fila(qv="1000", trades="5") for a in activos}
    r = sc.ResumenScanner()
    assert sc.aplicar(activos, metricas, top_n=20, resumen=r) == []
    assert r.seleccionados == 0 and r.enviados == 0


def test_7c_el_motivo_es_el_primer_corte_que_falla():
    """Un activo que incumple varios reporta uno solo, de forma estable."""
    m = sc.leer_metricas("XUSDT", fila(bid="90", ask="110", trades="1",
                                       qv="10"))
    assert sc.evaluar_filtros(m) == sc.SPREAD_EXCESIVO


# ═══════════════════════════════════════════════════════════════════════════
# 8 · POSICIONES PRESERVADAS
# ═══════════════════════════════════════════════════════════════════════════
def test_8_una_posicion_abierta_no_se_filtra_nunca():
    """
    Aunque su mercado sea horrible y aunque quede fuera de cualquier Top: el bot
    no puede quedarse sin poder analizar la salida de lo que ya tiene.
    """
    activos = [activo("HORRIBLEUSDT", posicion=5.0)] + \
              [activo(f"B{i:03d}USDT") for i in range(40)]
    metricas = {"HORRIBLEUSDT": fila(bid="50", ask="150", qv="1", trades="1",
                                     hi="100", lo="100")}
    for a in activos[1:]:
        metricas[a["symbol"]] = fila()

    r = sc.ResumenScanner()
    salida = sc.aplicar(activos, metricas, top_n=5, resumen=r)
    simbolos = [a["symbol"] for a in salida]

    assert "HORRIBLEUSDT" in simbolos
    assert r.preservados == 1
    assert r.por_motivo[sc.POSICION_ABIERTA] == 1
    assert len(salida) == 6, "5 del Top + 1 preservado"


def test_8b_una_posicion_sin_metricas_tambien_se_preserva():
    activos = [activo("SINDATOSUSDT", posicion=1.0)]
    salida = sc.aplicar(activos, {}, top_n=20)
    assert [a["symbol"] for a in salida] == ["SINDATOSUSDT"]


def test_8c_las_preservadas_no_cuentan_como_entrada_del_scanner():
    activos = [activo("CONPOSUSDT", posicion=2.0), activo("NUEVOUSDT")]
    metricas = {"CONPOSUSDT": fila(), "NUEVOUSDT": fila()}
    r = sc.ResumenScanner()
    sc.aplicar(activos, metricas, top_n=20, resumen=r)
    assert r.entrada == 1, "solo los aspirantes a compra nueva"
    assert r.preservados == 1


def test_8d_las_preservadas_van_primero_en_la_salida():
    activos = [activo("NUEVOUSDT"), activo("CONPOSUSDT", posicion=1.0)]
    metricas = {"CONPOSUSDT": fila(), "NUEVOUSDT": fila()}
    salida = sc.aplicar(activos, metricas, top_n=20)
    assert salida[0]["symbol"] == "CONPOSUSDT"


def test_8e_el_scanner_solo_puntua_a_quien_no_tiene_posicion():
    """Guarda AST: la rama de preservacion precede a los filtros."""
    fn = next(n for n in ast.walk(ast.parse(SCANNER.read_text(encoding="utf-8")))
              if isinstance(n, ast.FunctionDef) and n.name == "aplicar")
    for nodo in ast.walk(fn):
        if isinstance(nodo, ast.If) and "_position_detected" in ast.dump(nodo.test):
            cuerpo = "\n".join(ast.dump(n) for n in nodo.body)
            assert "evaluar_filtros" not in cuerpo, \
                "una posicion abierta no pasa por los filtros de compra"
            return
    pytest.fail("no se encontro la rama que preserva las posiciones")


# ═══════════════════════════════════════════════════════════════════════════
# 9-11 · TOP N, UNIVERSO PEQUENO Y EMPATES
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("n", [1, 3, 5, 10, 20, 30])
def test_9_el_top_n_devuelve_exactamente_n(n):
    activos, metricas = universo(100)
    r = sc.ResumenScanner()
    salida = sc.aplicar(activos, metricas, top_n=n, resumen=r)
    assert len(salida) == n
    assert r.seleccionados == n
    assert r.top_n == n


def test_9b_el_top_n_es_el_prefijo_del_ranking_completo():
    activos, metricas = universo(60)
    completo = [a["symbol"] for a in sc.aplicar(activos, metricas, top_n=60)]
    top10 = [a["symbol"] for a in sc.aplicar(activos, metricas, top_n=10)]
    assert top10 == completo[:10]


def test_9c_el_valor_por_defecto_esta_documentado():
    assert sc.TOP_N_POR_DEFECTO == 20
    fuente = SCANNER.read_text(encoding="utf-8")
    assert "p95" in fuente and "14.521" in fuente, \
        "el Top N debe citar la medicion que lo justifica"


def test_10_si_el_universo_es_menor_que_n_se_envian_los_que_hay():
    activos, metricas = universo(3)
    r = sc.ResumenScanner()
    salida = sc.aplicar(activos, metricas, top_n=20, resumen=r)
    assert len(salida) == 3, "no se rellena el Top con nada"
    assert r.seleccionados == 3


def test_10b_top_n_cero_no_envia_candidatos_pero_conserva_posiciones():
    activos = [activo("NUEVOUSDT"), activo("CONPOSUSDT", posicion=1.0)]
    metricas = {"NUEVOUSDT": fila(), "CONPOSUSDT": fila()}
    salida = sc.aplicar(activos, metricas, top_n=0)
    assert [a["symbol"] for a in salida] == ["CONPOSUSDT"]


def test_10c_entrada_vacia_no_lanza():
    assert sc.aplicar([], {}, top_n=20) == []
    assert sc.aplicar(None, None, top_n=20) == []


def test_11_los_empates_se_rompen_por_symbol():
    """Activos identicos: mismo score y orden alfabetico estable."""
    simbolos = ["ZUSDT", "MUSDT", "AUSDT", "QUSDT"]
    metricas = {s: fila() for s in simbolos}
    ms = [sc.leer_metricas(s, f) for s, f in metricas.items()]
    candidatos = sc.puntuar(ms)

    assert len({round(c.score, 12) for c in candidatos}) == 1, "todos empatan"
    assert [c.symbol for c in candidatos] == sorted(simbolos)


def test_11b_un_empate_no_cambia_con_el_orden_de_entrada():
    simbolos = ["ZUSDT", "MUSDT", "AUSDT", "QUSDT"]
    metricas = {s: fila() for s in simbolos}
    a = [c.symbol for c in sc.puntuar([sc.leer_metricas(s, metricas[s])
                                       for s in simbolos])]
    b = [c.symbol for c in sc.puntuar([sc.leer_metricas(s, metricas[s])
                                       for s in reversed(simbolos)])]
    assert a == b == sorted(simbolos)


def test_11c_el_top_n_con_empate_total_es_reproducible():
    activos = [activo(s) for s in ("ZUSDT", "MUSDT", "AUSDT", "QUSDT")]
    metricas = {a["symbol"]: fila() for a in activos}
    for _ in range(5):
        salida = sc.aplicar(activos, metricas, top_n=2)
        assert [a["symbol"] for a in salida] == ["AUSDT", "MUSDT"]


# ═══════════════════════════════════════════════════════════════════════════
# 12 · NI UNA PETICION HTTP EN EL SCANNER
# ═══════════════════════════════════════════════════════════════════════════
def test_12_el_scanner_no_hace_ninguna_peticion():
    """Guarda AST: el modulo no puede tocar la red ni el conector."""
    arbol = ast.parse(SCANNER.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            volcado = ast.dump(nodo)
            for prohibido in ("requests", "binance", "urllib", "http",
                              "socket", "connectors"):
                assert prohibido not in volcado, \
                    f"el scanner no puede hacer red; importa {prohibido}"


def test_12b_el_scanner_recibe_las_metricas_ya_obtenidas():
    """
    Firma: `aplicar(activos, metricas_por_symbol, ...)`. Las metricas entran
    como dato, nunca se piden dentro.
    """
    import inspect
    params = list(inspect.signature(sc.aplicar).parameters)
    assert params[:2] == ["activos", "metricas_por_symbol"]


def test_12c_una_sola_peticion_alimenta_a_los_484(monkeypatch):
    """El ciclo pide ticker/24hr UNA vez y el scanner no vuelve a la red."""
    from backend.connectors.crypto import binance_connector as bc

    llamadas = {"n": 0}

    class Cliente:
        response = None

        def get_ticker(self, **kw):
            llamadas["n"] += 1
            self.response = SimpleNamespace(status_code=200)
            return [dict(symbol=f"A{i:03d}USDT", **fila()) for i in range(484)]

    c = bc.BinanceConnector()
    monkeypatch.setattr(c, "init_client", lambda: None)
    monkeypatch.setattr(c, "client", Cliente(), raising=False)

    metricas = c.get_market_metrics()
    assert llamadas["n"] == 1
    assert len(metricas) == 484

    activos = [activo(f"A{i:03d}USDT") for i in range(484)]
    sc.aplicar(activos, metricas, top_n=20)
    assert llamadas["n"] == 1, "el scanner no vuelve a pedir nada"


def test_12d_no_hay_bucles_con_peticiones_en_el_conector_de_metricas():
    fn = next(n for n in ast.walk(ast.parse(
        (RAIZ / "backend/connectors/crypto/binance_connector.py")
        .read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "get_market_metrics")
    for nodo in ast.walk(fn):
        if isinstance(nodo, (ast.For, ast.While)):
            for hijo in nodo.body:
                for interno in ast.walk(hijo):
                    if isinstance(interno, ast.Call) and \
                            getattr(interno.func, "attr", None) == "peticion":
                        pytest.fail("peticion HTTP dentro de un bucle: N+1")


# ═══════════════════════════════════════════════════════════════════════════
# 13 · TELEMETRIA FAIL-OPEN
# ═══════════════════════════════════════════════════════════════════════════
def test_13_un_resumen_corrupto_no_altera_la_salida():
    activos, metricas = universo(30)
    esperada = [a["symbol"] for a in sc.aplicar(activos, metricas, top_n=10)]

    class Corrupto(sc.ResumenScanner):
        def __init__(self):
            super().__init__()
            self.por_motivo = "corrompido"      # dejara de ser contable

    r = Corrupto()
    salida = sc.aplicar(activos, metricas, top_n=10, resumen=r)
    assert [a["symbol"] for a in salida] == esperada
    assert isinstance(r.linea(), str)


def test_13b_la_linea_de_resumen_nunca_lanza():
    r = sc.ResumenScanner()
    assert isinstance(r.linea(), str)
    assert isinstance(r.linea(12, requests=1), str)
    r.scores = "no es una lista"
    assert isinstance(r.linea(), str)
    r.anotar(None)


def test_13c_los_contadores_cuadran():
    activos = [activo("BUENOUSDT"), activo("MALOUSDT"),
               activo("CONPOSUSDT", posicion=1.0)]
    metricas = {"BUENOUSDT": fila(), "MALOUSDT": fila(qv="10"),
                "CONPOSUSDT": fila()}
    r = sc.ResumenScanner()
    sc.aplicar(activos, metricas, top_n=20, resumen=r)

    assert r.entrada == 2
    assert r.descartados == 1
    assert r.puntuados == 1
    assert r.seleccionados == 1
    assert r.preservados == 1
    assert r.enviados == 2


def test_13d_la_linea_incluye_la_distribucion_de_scores():
    activos, metricas = universo(30)
    r = sc.ResumenScanner()
    sc.aplicar(activos, metricas, top_n=10, resumen=r)
    linea = r.linea(7, requests=0)
    for trozo in ("entrada=30", "topN=10", "seleccionados=10", "a_GPT=10",
                  "scores[", "requests=0"):
        assert trozo in linea, trozo


# ═══════════════════════════════════════════════════════════════════════════
# 14-16 · LIMITES DE RESPONSABILIDAD
# ═══════════════════════════════════════════════════════════════════════════
def test_14_el_scanner_no_puede_ejecutar_ordenes():
    arbol = ast.parse(SCANNER.read_text(encoding="utf-8"))
    identificadores = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            identificadores.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            identificadores.add(nodo.attr)
    for prohibido in ("comprar", "vender", "ejecutar", "order_market_buy",
                      "order_market_sell", "cartera", "real_trader",
                      "guardar_transaccion_real", "SessionLocal"):
        assert prohibido not in identificadores, \
            f"el scanner no puede operar; usa {prohibido}"


def test_15_el_scanner_no_importa_openai():
    fuente = SCANNER.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            volcado = ast.dump(nodo).lower()
            for prohibido in ("openai", "gpt", "llm", "telemetria_llm"):
                assert prohibido not in volcado, \
                    f"el scanner no puede saber nada del LLM; importa {prohibido}"


def test_15b_el_scanner_no_pide_al_llm_que_rankee():
    """El ranking es nuestro y deterministico."""
    fuente = SCANNER.read_text(encoding="utf-8").lower()
    for prohibido in ("analyze_multiple_assets", "chat/completions", "prompt ="):
        assert prohibido not in fuente


def test_16_el_riskengine_sigue_intacto():
    """El scanner no toca riesgo, sizing ni limites."""
    arbol = ast.parse(SCANNER.read_text(encoding="utf-8"))
    identificadores = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            identificadores.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            identificadores.add(nodo.attr)
    for prohibido in ("MotorRiesgo", "limite_compra", "MONTO_MAXIMO_USDT",
                      "LIMITE_ASIGNACION_POR_OPERACION", "evaluar",
                      "settings", "min_notional"):
        assert prohibido not in identificadores, \
            f"el scanner no puede tocar el riesgo; usa {prohibido}"


def test_16b_el_gate_y_el_scanner_son_etapas_separadas():
    """El scanner no reimplementa la elegibilidad, y viceversa."""
    fuente = SCANNER.read_text(encoding="utf-8")
    assert "elegibilidad" not in fuente
    gate = (RAIZ / "backend/risk/elegibilidad.py").read_text(encoding="utf-8")
    assert "scanner" not in gate


def test_16c_el_orden_en_el_bucle_es_gate_y_luego_scanner():
    fuente = MAIN.read_text(encoding="utf-8")
    pos_gate = fuente.index("gate.linea(")
    pos_scanner = fuente.index("scanner.aplicar(")
    pos_llm = fuente.index("openai.analyze_multiple_assets(")
    assert pos_gate < pos_scanner < pos_llm, (
        "la cadena debe ser Eligibility Gate -> scanner -> LLM")


# ═══════════════════════════════════════════════════════════════════════════
# 17-18 · EL ENTORNO NO CAMBIA
# ═══════════════════════════════════════════════════════════════════════════
def test_17_paper_intacto():
    from backend.config import settings
    assert settings.TRADING_MODE == "PAPER"
    assert settings.MODO_REAL is False


def test_18_import_safety_intacto(monkeypatch):
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


def test_18b_el_scanner_no_necesita_migracion():
    from backend.esquema import revision_esperada
    assert revision_esperada() == "0005_telemetria_http"
    assert not list((RAIZ / "migrations" / "versions").glob("0006*"))


def test_18c_el_scheduling_no_cambia():
    fn = next(n for n in ast.walk(ast.parse(MAIN.read_text(encoding="utf-8")))
              if isinstance(n, ast.FunctionDef) and n.name == "trading_loop")
    incrementos = [n for n in ast.walk(fn) if isinstance(n, ast.AugAssign)
                   and isinstance(n.target, ast.Name) and n.target.id == "ciclo"]
    assert len(incrementos) == 5
    valores = [n.value.value for n in ast.walk(fn)
               if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "EVALUAR_CADA_N_CICLOS"
                       for t in n.targets)
               and isinstance(n.value, ast.Constant)]
    assert valores == [2]
