from pathlib import Path


def test_launcher_no_declara_paper_listo_sin_smoke_http_del_frontend():
    texto = Path("scripts/launch_paper_stack.ps1").read_text(encoding="utf-8")

    assert 'scripts.smoke_frontend_runtime' in texto
    assert '5/5 Validando frontend HTTP' in texto
    assert 'El smoke HTTP del frontend PAPER no quedo READY.' in texto
    assert texto.index('scripts.smoke_frontend_runtime') < texto.index('BOT Trading PAPER iniciado correctamente')
