from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
START = RAIZ / "start.sh"


def test_start_paper_ejecuta_readiness_antes_de_uvicorn():
    fuente = START.read_text(encoding="utf-8")
    readiness = fuente.index("python scripts/check_paper_release.py")
    uvicorn = fuente.index("exec python -m uvicorn backend.main:app")
    assert readiness < uvicorn


def test_start_no_automigra_y_conserva_un_worker():
    fuente = START.read_text(encoding="utf-8")
    assert "alembic upgrade head" in fuente  # solo documentado como paso explicito
    assert "--workers 1" in fuente
    lineas_ejecutables = [
        linea.strip() for linea in fuente.splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]
    assert all(not linea.startswith("alembic ") for linea in lineas_ejecutables)


def test_preflight_se_aplica_a_paper_y_live_sin_opt_in():
    fuente = START.read_text(encoding="utf-8")
    assert 'MODE_UPPER="${MODE^^}"' in fuente
    assert 'LIVE_OPT_IN_LOWER="${LIVE_OPT_IN,,}"' in fuente
    assert 'if [ "$MODE_UPPER" != "LIVE" ] || [ "$LIVE_OPT_IN_LOWER" != "yes-i-understand-the-risk" ]; then' in fuente
    assert "python scripts/check_paper_release.py" in fuente


def test_preflight_solo_se_omite_para_live_doblemente_autorizado():
    fuente = START.read_text(encoding="utf-8")
    assert 'LIVE_OPT_IN="${ALLOW_LIVE_TRADING:-}"' in fuente
    assert '"yes-i-understand-the-risk"' in fuente
    assert 'if [ "$MODE_UPPER" != "LIVE" ] || [ "$LIVE_OPT_IN_LOWER" != "yes-i-understand-the-risk" ]; then' in fuente
