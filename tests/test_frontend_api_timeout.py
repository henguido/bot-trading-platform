from pathlib import Path


API_JS = Path("frontend/src/services/api.js")


def test_api_frontend_tiene_timeout_centralizado_y_abortcontroller():
    texto = API_JS.read_text(encoding="utf-8")

    assert "DEFAULT_TIMEOUT_MS = 15000" in texto
    assert "new AbortController()" in texto
    assert "controller.abort()" in texto
    assert 'error.code = "API_TIMEOUT"' in texto
    assert "clearTimeout(timer)" in texto


def test_api_fetch_y_journal_reutilizan_fetch_con_timeout():
    texto = API_JS.read_text(encoding="utf-8")

    assert "async function fetchConTimeout" in texto
    assert texto.count("fetchConTimeout(") >= 3
    assert "downloadPaperJournal" in texto


def test_frontend_no_deja_fetch_directo_fuera_del_wrapper():
    texto = API_JS.read_text(encoding="utf-8")
    lineas_fetch = [
        linea.strip()
        for linea in texto.splitlines()
        if "fetch(" in linea and not linea.lstrip().startswith("//")
    ]

    assert lineas_fetch == [
        "return await fetch(url, { ...options, signal: controller.signal });"
    ]
