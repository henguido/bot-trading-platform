from pathlib import Path


API_JS = Path("frontend/src/services/api.js")
CARD = Path("frontend/src/components/EconomicReadinessCard.jsx")


def test_frontend_consulta_readiness_por_wrapper_autenticado():
    api = API_JS.read_text(encoding="utf-8")

    assert "export function getPaperReadiness()" in api
    assert 'return apiFetch("/api/readiness")' in api


def test_tarjeta_muestra_fee_vigencia_y_resultado_del_gate():
    card = CARD.read_text(encoding="utf-8")

    assert "Readiness económico" in card
    assert "bps/lado" in card
    assert "fee.age_seconds" in card
    assert "fee.max_age_seconds" in card
    assert "fee.age_seconds !== null" in card
    assert "Vigencia restante" in card
    assert "readiness.blockers" in card
    assert "readiness.warnings" in card


def test_tarjeta_falla_cerrado_si_readiness_no_es_consultable():
    card = CARD.read_text(encoding="utf-8")

    assert "Este estado no se interpreta como listo" in card
    assert 'ready ? "READY" : "BLOQUEADO"' in card
    assert 'value={hasBps ? `${bps.toFixed(1)} bps/lado` : "No verificable"}' in card
