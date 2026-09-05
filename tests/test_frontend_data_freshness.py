from pathlib import Path


ALERT = Path("frontend/src/components/DataFreshnessAlert.jsx")
OBSERVABILITY = Path("frontend/src/pages/ObservabilityPage.jsx")


def test_alerta_visual_distingue_timeout_backend_y_snapshot_stale():
    texto = ALERT.read_text(encoding="utf-8")

    assert 'error?.code === "API_TIMEOUT"' in texto
    assert "Tiempo de espera agotado" in texto
    assert "Backend no accesible" in texto
    assert "pueden estar desactualizados" in texto
    assert 'role="alert"' in texto


def test_observabilidad_no_presenta_datos_no_confirmados_como_validos():
    texto = OBSERVABILITY.read_text(encoding="utf-8")

    assert "<DataFreshnessAlert" in texto
    assert "const hasSnapshot = Boolean(updatedAt)" in texto
    assert "const dataStale = Boolean(error && hasSnapshot)" in texto
    assert "Sin datos operativos confirmados" in texto
    assert "Datos desactualizados" in texto
    assert "setError(err)" in texto
