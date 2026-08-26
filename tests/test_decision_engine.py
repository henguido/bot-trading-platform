from backend import decision_engine as de


class OpenAIEspia:
    def __init__(self):
        self.calls = []

    def analyze_multiple_assets(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return [{"symbol": "BTCUSDT", "decision": "ESPERAR", "quantity": 0}], "ok"


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
