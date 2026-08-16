"""
Fase BOT 2.0-01 · Instrumentacion del consumo de IA.

Mide, no optimiza. Ninguna prueba llama a OpenAI de verdad: se sustituye
requests.post por un doble.

Se comprueba ademas que la instrumentacion NO cambia el comportamiento de
trading y que no filtra secretos.
"""
import json
import threading
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.telemetria_llm import (
    DISPONIBLE,
    NO_DISPONIBLE,
    MetricasLlamadaLLM,
    calcular_costo_usd,
    registrar_llamada,
)

API_KEY_FALSA = "sk-CLAVE-SINTETICA-DE-PRUEBA-NO-REAL-000000"


class RespuestaFalsa:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload) if isinstance(payload, dict) else str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def payload_ok(contenido='[{"symbol":"BTCUSDT","decision":"ESPERAR","quantity":0,"risk_score":0.1}]',
               usage=True, modelo="gpt-4o-2024-08-06"):
    d = {"model": modelo, "choices": [{"message": {"content": contenido}}]}
    if usage:
        d["usage"] = {"prompt_tokens": 1200, "completion_tokens": 300,
                      "total_tokens": 1500}
    return d


@pytest.fixture
def conector(monkeypatch):
    """Conector con API key sintetica y telemetria capturada en memoria."""
    from backend.config import settings
    from backend.connectors.apis import openai_connector as mod

    monkeypatch.setattr(settings, "OPENAI_API_KEY", API_KEY_FALSA)
    capturadas = []
    c = mod.OpenAIConnector(registrar_telemetria=capturadas.append)
    c.api_key = API_KEY_FALSA
    return c, capturadas, mod


ACTIVOS = [{"symbol": "BTCUSDT", "price": 100000.0, "position_quantity": 0.0,
            "average_price": None}]
PARES = [{"pair": "ETHBTC", "price": 0.05}, {"pair": "SOLBTC", "price": 0.001}]
NOTICIAS = "titular uno\ntitular dos\ntitular tres"


def llamar(conector_tuple, monkeypatch, respuesta=None, excepcion=None):
    c, capturadas, mod = conector_tuple

    def post_falso(url, headers=None, json=None, timeout=None):
        post_falso.timeout = timeout
        post_falso.headers = headers
        if excepcion:
            raise excepcion
        return respuesta

    monkeypatch.setattr(mod.requests, "post", post_falso)
    r = c.analyze_multiple_assets(ACTIVOS, 1000.0, "NEUTRO", NOTICIAS,
                                  market_pairs=PARES, ciclo=7)
    return r, capturadas[0] if capturadas else None, post_falso


# ── 1-6 · Uso normal ────────────────────────────────────────────────────────
def test_1_uso_normal_registra_metricas(conector, monkeypatch):
    (parsed, _), m, _ = llamar(conector, monkeypatch, RespuestaFalsa(payload_ok()))
    assert parsed and parsed[0]["symbol"] == "BTCUSDT"
    assert m is not None and m.exito is True
    assert m.http_status == 200
    assert m.operacion == "analyze_multiple_assets"
    assert m.proveedor == "openai"
    assert m.call_id.startswith("llm-") and len(m.call_id) > 10
    assert m.ciclo == 7


def test_2_3_4_tokens_capturados(conector, monkeypatch):
    _, m, _ = llamar(conector, monkeypatch, RespuestaFalsa(payload_ok()))
    assert m.prompt_tokens == 1200
    assert m.completion_tokens == 300
    assert m.total_tokens == 1500


def test_5_latencia_capturada(conector, monkeypatch):
    _, m, _ = llamar(conector, monkeypatch, RespuestaFalsa(payload_ok()))
    assert m.latencia_ms is not None and m.latencia_ms >= 0


def test_6_modelo_solicitado_y_real(conector, monkeypatch):
    _, m, _ = llamar(conector, monkeypatch,
                     RespuestaFalsa(payload_ok(modelo="gpt-4o-2024-11-20")))
    assert m.modelo_solicitado == conector[0].model
    assert m.modelo_respuesta == "gpt-4o-2024-11-20"


def test_magnitudes_de_entrada(conector, monkeypatch):
    _, m, _ = llamar(conector, monkeypatch, RespuestaFalsa(payload_ok()))
    assert m.n_activos == 1
    assert m.n_market_pairs == 2
    assert m.n_noticias == 3
    assert m.prompt_chars and m.prompt_chars > 0
    assert m.respuesta_chars and m.respuesta_chars > 0


# ── 7-10 · Fallos ───────────────────────────────────────────────────────────
def test_7_http_no_200(conector, monkeypatch):
    _, m, _ = llamar(conector, monkeypatch,
                     RespuestaFalsa({"error": {"message": "rate limit"}}, status=429))
    assert m.http_status == 429
    assert m.exito is False
    assert m.tipo_error == "respuesta_sin_choices"


def test_8_excepcion_de_red(conector, monkeypatch):
    (parsed, expl), m, _ = llamar(conector, monkeypatch,
                                  excepcion=ConnectionError("sin red"))
    assert parsed == [] and expl == "Error de conexión"
    assert m.exito is False and m.tipo_error == "ConnectionError"
    assert m.latencia_ms is not None


def test_9_respuesta_sin_usage(conector, monkeypatch):
    _, m, _ = llamar(conector, monkeypatch, RespuestaFalsa(payload_ok(usage=False)))
    assert m.exito is True, "la llamada si tuvo exito"
    assert m.prompt_tokens is None and m.total_tokens is None, \
        "sin usage, los tokens son desconocidos, no cero"


def test_10_json_de_decision_invalido(conector, monkeypatch):
    _, m, _ = llamar(conector, monkeypatch,
                     RespuestaFalsa(payload_ok(contenido="esto no es json")))
    assert m.exito is False
    assert m.tipo_error == "json_invalido", \
        "un fallo de formato no debe confundirse con uno de red"
    assert m.http_status == 200, "la peticion HTTP si funciono"
    assert m.prompt_tokens == 1200, "los tokens se cobran igualmente"


# ── 11 · Fallo de persistencia de telemetria ────────────────────────────────
def test_11_fallo_de_telemetria_no_afecta_al_trading(monkeypatch):
    """Una telemetria rota no puede cambiar el resultado de la llamada."""
    from backend.config import settings
    from backend.connectors.apis import openai_connector as mod

    monkeypatch.setattr(settings, "OPENAI_API_KEY", API_KEY_FALSA)

    def telemetria_rota(_):
        raise RuntimeError("base de datos caida")

    c = mod.OpenAIConnector(registrar_telemetria=telemetria_rota)
    monkeypatch.setattr(mod.requests, "post",
                        lambda *a, **k: RespuestaFalsa(payload_ok()))

    parsed, contenido = c.analyze_multiple_assets(
        ACTIVOS, 1000.0, "NEUTRO", NOTICIAS, market_pairs=PARES)

    assert parsed and parsed[0]["decision"] == "ESPERAR", \
        "la decision debe ser la misma aunque la telemetria falle"


def test_11b_registrar_llamada_nunca_lanza():
    def fabrica_rota():
        raise RuntimeError("sin base de datos")
    assert registrar_llamada(MetricasLlamadaLLM(operacion="x"),
                             session_factory=fabrica_rota) is False


# ── 12 · Ninguna API key persistida ─────────────────────────────────────────
def test_12_no_se_persiste_ninguna_api_key(conector, monkeypatch, tmp_path):
    _, m, post = llamar(conector, monkeypatch, RespuestaFalsa(payload_ok()))

    # La cabecera SI lleva la clave (es necesario), pero no debe acabar en las metricas.
    assert API_KEY_FALSA in post.headers["Authorization"]
    serializado = repr(vars(m))
    assert API_KEY_FALSA not in serializado
    assert "Authorization" not in serializado
    assert "Bearer" not in serializado

    # Y tampoco en la fila persistida.
    engine = sa.create_engine("sqlite://", connect_args={"check_same_thread": False},
                              poolclass=StaticPool)
    models.Base.metadata.create_all(bind=engine)
    Sesion = sessionmaker(bind=engine)
    assert registrar_llamada(m, session_factory=Sesion,
                             config=SimpleNamespace()) is True
    with Sesion() as db:
        fila = db.query(models.LlmCallAudit).first()
        texto = " ".join(str(getattr(fila, c.name)) for c in fila.__table__.columns)
    assert API_KEY_FALSA not in texto and "sk-" not in texto


def test_12b_no_se_persiste_el_prompt_ni_la_respuesta():
    """Solo magnitudes: la tabla no tiene columnas de contenido."""
    columnas = {c.name for c in models.LlmCallAudit.__table__.columns}
    for prohibida in ("prompt", "respuesta", "contenido", "mensaje", "headers"):
        assert prohibida not in columnas, f"la tabla no debe guardar {prohibida}"
    assert "prompt_chars" in columnas and "respuesta_chars" in columnas


def test_12c_el_prompt_completo_ya_no_se_vuelca_por_consola():
    import ast
    import pathlib
    ruta = pathlib.Path(__file__).resolve().parents[1] / \
        "backend/connectors/apis/openai_connector.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, ast.Call) and getattr(nodo.func, "id", None) == "print"
                and len(nodo.args) == 1
                and isinstance(nodo.args[0], ast.Name)
                and nodo.args[0].id in ("prompt", "content")):
            pytest.fail(f"linea {nodo.lineno}: se vuelca el prompt/respuesta completo")


# ── COSTO ───────────────────────────────────────────────────────────────────
def test_costo_sin_tarifas_es_no_disponible():
    costo, estado, detalle = calcular_costo_usd(1000, 500)
    assert costo is None, "jamas 0.0 por desconocimiento"
    assert estado == NO_DISPONIBLE
    assert "tarifas" in detalle


def test_costo_sin_usage_es_no_disponible():
    costo, estado, _ = calcular_costo_usd(None, None,
                                          precio_input_por_1m=2.5,
                                          precio_output_por_1m=10.0)
    assert costo is None and estado == NO_DISPONIBLE


def test_costo_con_tarifas_se_calcula_y_queda_auditable():
    costo, estado, detalle = calcular_costo_usd(
        1_000_000, 1_000_000, precio_input_por_1m=2.5, precio_output_por_1m=10.0)
    assert costo == pytest.approx(12.5)
    assert estado == DISPONIBLE
    assert "2.5" in detalle and "10.0" in detalle, \
        "debe quedar registrada la tarifa aplicada"


def test_no_hay_tarifas_hardcodeadas_en_el_codigo():
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parents[1]
    fuente = (raiz / "backend/telemetria_llm.py").read_text(encoding="utf-8")
    import ast
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.arguments):
            for d in nodo.defaults + nodo.kw_defaults:
                if isinstance(d, ast.Constant) and isinstance(d.value, float):
                    pytest.fail(f"tarifa hardcodeada como default: {d.value}")


# ── TIMEOUT (robustez) ──────────────────────────────────────────────────────
def test_la_llamada_al_llm_lleva_timeout_explicito(conector, monkeypatch):
    _, _, post = llamar(conector, monkeypatch, RespuestaFalsa(payload_ok()))
    assert post.timeout is not None, "sin timeout una peticion colgada bloquea el bot"
    assert post.timeout > 0


# ── 13-17 · La instrumentacion no cambia nada del entorno ───────────────────
def test_13_14_15_import_sigue_siendo_inocuo(monkeypatch):
    con, ddl = [], []
    original = sa.engine.Engine.connect
    monkeypatch.setattr(sa.engine.Engine, "connect",
                        lambda self, *a, **k: (con.append(1), original(self, *a, **k))[1])
    monkeypatch.setattr(sa.MetaData, "create_all", lambda self, *a, **k: ddl.append(1))
    monkeypatch.setattr(sa.MetaData, "drop_all", lambda self, *a, **k: ddl.append(1))

    import importlib
    import backend.main
    importlib.reload(backend.main)

    assert con == [], "13. importar no debe abrir conexiones"
    assert ddl == [], "14. importar no debe ejecutar DDL"
    assert not [t for t in threading.enumerate() if t.name != "MainThread"], \
        "15. importar no debe arrancar trading loops"


def test_16_17_paper_sigue_activo():
    from backend.config import settings
    assert settings.TRADING_MODE == "PAPER"
    assert settings.MODO_REAL is False


def test_la_telemetria_no_toca_el_flujo_de_ordenes():
    """AST: telemetria_llm no importa nada del ciclo de ordenes ni del riesgo."""
    import ast
    import pathlib
    ruta = pathlib.Path(__file__).resolve().parents[1] / "backend/telemetria_llm.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    prohibidos = ("real_trading_connector", "ordenes_repo", "motor", "reconciliacion")
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            texto = ast.dump(nodo)
            for p in prohibidos:
                assert p not in texto, f"la telemetria no debe acoplarse a {p}"
