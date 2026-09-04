from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "launch_paper_stack.ps1"
STOPPER = ROOT / "scripts" / "stop_paper_stack.ps1"
START_CMD = ROOT / "INICIAR_BOT_PAPER.cmd"
STOP_CMD = ROOT / "DETENER_BOT_PAPER.cmd"


def test_lanzador_ejecuta_readiness_y_smoke_antes_de_exponer_frontend():
    texto = LAUNCHER.read_text(encoding="utf-8")
    readiness = texto.index('scripts\\check_paper_release.py')
    backend = texto.index('"uvicorn"')
    smoke = texto.index('"scripts.smoke_paper_runtime"')
    frontend = texto.index('"--strictPort"')
    assert readiness < backend < smoke < frontend


def test_lanzador_ejecuta_smoke_como_modulo_desde_raiz_repo():
    texto = LAUNCHER.read_text(encoding="utf-8")
    assert '& $Python "-m" "scripts.smoke_paper_runtime"' in texto
    assert '& $Python "scripts\\smoke_paper_runtime.py"' not in texto
    assert "Set-Location $Root" in texto


def test_lanzador_local_usa_localhost_compatible_con_cors_y_api_frontend():
    texto = LAUNCHER.read_text(encoding="utf-8")
    assert '[string]$HostAddress = "localhost"' in texto
    assert '[string]$HostAddress = "127.0.0.1"' not in texto


def test_lanzador_fija_vite_api_al_backend_que_acaba_de_validar():
    texto = LAUNCHER.read_text(encoding="utf-8")
    asignacion = '$env:VITE_API_URL = $BackendUrl'
    assert asignacion in texto
    assert texto.index(asignacion) < texto.index('"--strictPort"')


def test_lanzador_fuerza_utf8_para_python_en_windows():
    texto = LAUNCHER.read_text(encoding="utf-8")
    assert '$env:PYTHONUTF8 = "1"' in texto
    assert '$env:PYTHONIOENCODING = "utf-8"' in texto
    assert texto.index('$env:PYTHONUTF8 = "1"') < texto.index('scripts\\check_paper_release.py')
    assert texto.index('$env:PYTHONUTF8 = "1"') < texto.index('"uvicorn"')


def test_lanzador_no_migra_no_instala_dependencias_y_no_habilita_live():
    texto = LAUNCHER.read_text(encoding="utf-8")
    lineas_ejecutables = [
        linea.strip()
        for linea in texto.splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]
    texto_ejecutable = "\n".join(lineas_ejecutables)

    assert "alembic upgrade" not in texto_ejecutable
    assert "ALLOW_LIVE_TRADING=yes-i-understand-the-risk" not in texto_ejecutable
    assert "TRADING_MODE=LIVE" not in texto_ejecutable

    # Los mensajes informativos pueden mencionar comandos manuales. Lo que se
    # protege es que el launcher no invoque instaladores por si mismo.
    assert not any(
        linea.startswith(("pip ", "pip.exe ", "python -m pip ", "npm ", "npm.cmd "))
        for linea in lineas_ejecutables
    )


def test_lanzador_usa_un_worker_y_pids_propios_para_apagado():
    launcher = LAUNCHER.read_text(encoding="utf-8")
    stopper = STOPPER.read_text(encoding="utf-8")
    assert '"--workers", "1"' in launcher
    assert 'paper-backend.pid' in launcher
    assert 'paper-frontend.pid' in launcher
    assert 'paper-backend.pid' in stopper
    assert 'paper-frontend.pid' in stopper
    assert 'Stop-Process -Id $savedPid' in stopper


def test_accesos_cmd_de_doble_clic_apuntan_a_scripts_controlados():
    start = START_CMD.read_text(encoding="utf-8")
    stop = STOP_CMD.read_text(encoding="utf-8")
    assert "launch_paper_stack.ps1" in start
    assert "stop_paper_stack.ps1" in stop
    assert "ExecutionPolicy Bypass" in start
    assert "ExecutionPolicy Bypass" in stop
