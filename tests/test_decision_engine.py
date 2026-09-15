from pathlib import Path

import pytest

from backend import decision_engine as de
from backend.config import settings


RAIZ = Path(__file__).resolve().parents[1]


class OpenAIEspia:
    def __init__(self, resultado=None):
        self.calls = []
        self.resultado = resultado or {
            "symbol": "BTCUSDT",
            "decision": "ESPERAR",
            "quantity": 0,
        }

    def analyze_multiple_assets(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return [dict(self.resultado)], "ok"


class OpenAIQueNoDebeUsarse:
    def __getattr__(self, nombre):
        raise AssertionError(f"SAFE_NO_TRADE no debe tocar OpenAI: {nombre}")


def _kwargs(openai):
    return dict(
        openai=openai,
        activos=[{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
        usdt_disponible=500.0,
        sentimiento="NO DISPONIBLE",
        noticias_str="sin noticias",
        portafolio_contexto={},
        market_pairs_filtrados=[],
        ciclo=7,
        ciclo_id="ciclo-test",
    )


def test_gpt_conserva_contrato_legacy_y_delega_una_vez():
    espia = OpenAIEspia()
    resultados, explicacion = de.decidir(de.ENGINE_GPT, **_kwargs(espia))

    assert explicacion == "ok"
    assert resultados[0]["symbol"] == "BTCUSDT"
    assert len(espia.calls) == 1
    args, kwargs = espia.calls[0]
    assert args[0] == [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
    assert args[1] == 500.0
    assert kwargs == {"ciclo": 7, "ciclo_id": "ciclo-test"}


def test_gpt_no_puede_inventar_edge_coste_neto_ni_estrategia():
    espia = OpenAIEspia({
        "symbol": "BTCUSDT",
        "decision": "COMPRAR",
        "quantity": 999.0,
        "strategy": "INVENTADA_POR_LLM",
        "expected_edge_bps": 9999.0,
        "expected_cost_bps": 0.0,
        "expected_net_bps": 9999.0,
    })

    resultados, _ = de.decidir(de.ENGINE_GPT, **_kwargs(espia))

    assert resultados[0]["decision"] == "COMPRAR"
    assert resultados[0]["quantity"] == 999.0
    for campo in de.CAMPOS_ECONOMICOS:
        assert campo not in resultados[0]


def test_contexto_economico_determinista_preserva_desconocido_como_ausente():
    contexto = de.contexto_economico_de({
        "strategy": "  SCANNER_05I  ",
        "expected_edge_bps": "42.5",
        "expected_cost_bps": 18,
        "expected_net_bps": None,
    })

    assert contexto == {
        "strategy": "SCANNER_05I",
        "expected_edge_bps": 42.5,
        "expected_cost_bps": 18.0,
    }
    assert "expected_net_bps" not in contexto


@pytest.mark.parametrize("campo,valor", [
    ("expected_edge_bps", float("nan")),
    ("expected_cost_bps", float("inf")),
    ("expected_net_bps", True),
])
def test_contexto_economico_rechaza_numeros_invalidos(campo, valor):
    with pytest.raises(ValueError):
        de.contexto_economico_de({"strategy": "TEST", campo: valor})


def test_contexto_para_ejecucion_gpt_es_vacio_aunque_intenten_reinyectar_economia():
    contexto, diagnostico = de.contexto_economico_para_ejecucion(
        de.ENGINE_GPT,
        {
            "strategy": "NO_CONFIABLE",
            "expected_edge_bps": 9000,
            "expected_cost_bps": 0,
            "expected_net_bps": 9000,
        },
    )

    assert contexto == {}
    assert diagnostico is None


def test_contexto_para_ejecucion_motor_no_registrado_no_es_confiable():
    contexto, diagnostico = de.contexto_economico_para_ejecucion(
        "MOTOR_FUTURO_NO_REGISTRADO",
        {"strategy": "X", "expected_net_bps": 12.0},
    )

    assert contexto == {}
    assert diagnostico == "MOTOR_ECONOMICO_NO_CONFIABLE"


def test_contexto_para_ejecucion_telemetria_invalida_no_lanza():
    # Simula un motor determinista futuro ya registrado sin tener que cambiar
    # la configuracion productiva de motores en este bloque.
    original = de.ENGINES_VALIDOS
    try:
        de.ENGINES_VALIDOS = original + ("DETERMINISTA_TEST",)
        contexto, diagnostico = de.contexto_economico_para_ejecucion(
            "DETERMINISTA_TEST",
            {"strategy": "TEST", "expected_net_bps": float("nan")},
        )
    finally:
        de.ENGINES_VALIDOS = original

    assert contexto == {}
    assert diagnostico == "ECONOMIA_INVALIDA"


def test_contexto_para_ejecucion_motor_determinista_registrado_normaliza():
    original = de.ENGINES_VALIDOS
    try:
        de.ENGINES_VALIDOS = original + ("DETERMINISTA_TEST",)
        contexto, diagnostico = de.contexto_economico_para_ejecucion(
            "DETERMINISTA_TEST",
            {
                "strategy": "  MOMENTUM_OOS  ",
                "expected_edge_bps": "44.5",
                "expected_cost_bps": 17,
                "expected_net_bps": 27.5,
            },
        )
    finally:
        de.ENGINES_VALIDOS = original

    assert diagnostico is None
    assert contexto == {
        "strategy": "MOMENTUM_OOS",
        "expected_edge_bps": 44.5,
        "expected_cost_bps": 17.0,
        "expected_net_bps": 27.5,
    }


def test_safe_no_trade_no_llama_ia_y_solo_devuelve_esperar():
    resultados, explicacion = de.decidir(
        de.ENGINE_SAFE_NO_TRADE,
        **_kwargs(OpenAIQueNoDebeUsarse()),
    )

    assert [r["symbol"] for r in resultados] == ["BTCUSDT", "ETHUSDT"]
    assert {r["decision"] for r in resultados} == {"ESPERAR"}
    assert {r["quantity"] for r in resultados} == {0.0}
    assert {r["risk_score"] for r in resultados} == {0.0}
    assert "IA omitida" in explicacion


def test_motor_desconocido_falla_cerrado():
    try:
        de.decidir("INVENTADO", **_kwargs(OpenAIQueNoDebeUsarse()))
    except ValueError as exc:
        assert "DECISION_ENGINE" in str(exc)
    else:
        raise AssertionError("un motor desconocido no puede degradarse a GPT")


def test_config_default_conserva_gpt_y_declara_safe_no_trade():
    assert settings.DECISION_ENGINE == de.ENGINE_GPT
    assert de.ENGINE_GPT in settings.DECISION_ENGINES_VALIDOS
    assert de.ENGINE_SAFE_NO_TRADE in settings.DECISION_ENGINES_VALIDOS


def test_main_delega_en_decision_engine_y_no_llama_openai_directamente():
    main = (RAIZ / "backend" / "main.py").read_text(encoding="utf-8")
    assert "decision_engine.decidir(" in main
    assert "openai.analyze_multiple_assets(" not in main
    assert "settings.DECISION_ENGINE" in main