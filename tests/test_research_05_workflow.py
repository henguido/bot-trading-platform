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
    v = texto.index("python scripts/verdict_research_05.py")
    assert i < j < k < v


def test_workflow_05_no_abre_un_segundo_linaje_acumulativo_por_pr():
    texto = _texto()
    assert "pull_request:" not in texto
    assert "github.head_ref" not in texto
    assert "workflow_call:" in texto
    assert "workflow_dispatch:" in texto


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


def test_workflow_05_declara_fee_manual_verificada_y_sus_disparadores():
    texto = _texto()
    assert 'RESEARCH_TAKER_FEE_BPS: "10.0"' in texto
    assert (
        'RESEARCH_TAKER_FEE_SOURCE: '
        '"manual:binance_account.commissionRates.taker"'
    ) in texto
    assert 'RESEARCH_TAKER_FEE_VERIFIED_AT: "2026-09-04T18:47:00Z"' in texto
    assert "La validez temporal se verifica fail-closed dentro de Python." in texto


def test_workflow_05_persiste_estado_y_publica_evidencia():
    texto = _texto()
    assert "actions/cache/restore@v4" in texto
    assert "actions/cache/save@v4" in texto
    assert "research-05-state-${{ github.run_id }}-${{ github.run_attempt }}" in texto
    assert "artifacts/scanner-unified-shadow-05i-state.json" in texto
    assert "artifacts/strategy-execution-shadow-05k-state.json" in texto
    assert "artifacts/scanner-challenger-05j.json" in texto
    assert "artifacts/research-05-status.txt" in texto
    assert "artifacts/research-05-verdict.json" in texto
    assert "retention-days: 30" in texto


def test_workflow_05_no_pisa_cache_restaurado_con_seed_antigua():
    texto = _texto()
    assert "Detect restored shadow state" in texto
    assert "id: shadow-state" in texto
    assert "[ -s artifacts/scanner-unified-shadow-05i-state.json ]" in texto
    assert "[ -s artifacts/strategy-execution-shadow-05k-state.json ]" in texto
    assert "steps.shadow-state.outputs.available != 'true'" in texto
    assert "steps.restore-shadow.outputs.cache-hit != 'true'" not in texto
