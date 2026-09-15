from pathlib import Path


START_SH = Path(__file__).resolve().parents[1] / "start.sh"


def _texto():
    return START_SH.read_text(encoding="utf-8")


def test_start_sh_ejecuta_readiness_si_no_hay_live_doblemente_autorizado():
    texto = _texto()
    assert 'MODE_UPPER="${MODE^^}"' in texto
    assert 'LIVE_OPT_IN_LOWER="${LIVE_OPT_IN,,}"' in texto
    assert '[ "$MODE_UPPER" != "LIVE" ] || [ "$LIVE_OPT_IN_LOWER" != "yes-i-understand-the-risk" ]' in texto
    assert "python scripts/check_paper_release.py" in texto


def test_start_sh_no_puede_tratar_live_sin_opt_in_como_exento_del_preflight():
    texto = _texto()
    assert 'if [ "${MODE^^}" = "PAPER" ]; then' not in texto
    assert "TRADING_MODE=LIVE + ALLOW_LIVE_TRADING=yes-i-understand-the-risk" in texto


def test_start_sh_mantiene_un_solo_worker_y_sin_migracion_automatica():
    texto = _texto()
    assert "--workers 1" in texto
    assert "alembic upgrade head" in texto
    assert "python -m uvicorn backend.main:app" in texto
