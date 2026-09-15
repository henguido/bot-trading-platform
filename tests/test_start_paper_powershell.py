from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "start_paper.ps1"


def test_powershell_usa_venv_oficial_y_readiness_antes_de_uvicorn():
    fuente = SCRIPT.read_text(encoding="utf-8")
    assert '.venv\\Scripts\\python.exe' in fuente
    readiness = fuente.index('scripts\\check_paper_release.py')
    uvicorn = fuente.index('-m uvicorn backend.main:app')
    assert readiness < uvicorn


def test_powershell_no_automigra_y_usa_un_worker():
    fuente = SCRIPT.read_text(encoding="utf-8")
    assert '--workers 1' in fuente
    assert 'alembic upgrade head' not in fuente.lower()


def test_powershell_no_arranca_si_readiness_falla():
    fuente = SCRIPT.read_text(encoding="utf-8")
    assert 'if ($LASTEXITCODE -ne 0)' in fuente
    assert 'No se arranca uvicorn' in fuente
