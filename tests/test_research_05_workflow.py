from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "research-05-prospective.yml"


def _texto():
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_05_corre_cada_4h_y_en_orden_05i_05j_05k():
    texto = _texto()
    assert 'cron: "17 */4 * * *"' in texto
    i = texto.index("python scripts/shadow_scanner_unified_05i.py")
    j = texto.index("python scripts/analyze_scanner_challenger_05j.py")
    k = texto.index("python scripts/shadow_strategy_execution_05k.py")
    assert i < j < k


def test_workflow_05_es_fail_closed_en_paper_y_no_habilita_live():
    texto = _texto()
    assert "TRADING_MODE: PAPER" in texto
    assert 'ALLOW_LIVE_TRADING: ""' in texto
    assert 'INITIAL_CAPITAL_USD: "500"' in texto
    assert 'LIMITE_ASIGNACION_POR_OPERACION: "0.02"' in texto
    assert 'test -z "$ALLOW_LIVE_TRADING"' in texto
    assert "TRADING_MODE: LIVE" not in texto
    assert "yes-i-understand-the-risk" not in texto


def test_workflow_05_no_bloquea_alpha_publico_si_falta_fee_privada():
    texto = _texto()
    assert "Report fee source availability" in texto
    assert 'fee_source=NO_DISPONIBLE' in texto
    assert 'test -n "$BINANCE_API_KEY"' not in texto
    assert 'test -n "$BINANCE_API_SECRET"' not in texto
    assert "05I/05J continuaran con evidencia publica" in texto


def test_workflow_05_persiste_estado_y_publica_evidencia():
    texto = _texto()
    assert "actions/cache/restore@v4" in texto
    assert "actions/cache/save@v4" in texto
    assert "artifacts/scanner-unified-shadow-05i-state.json" in texto
    assert "artifacts/strategy-execution-shadow-05k-state.json" in texto
    assert "artifacts/scanner-challenger-05j.json" in texto
    assert "artifacts/research-05-status.txt" in texto
    assert "retention-days: 30" in texto
