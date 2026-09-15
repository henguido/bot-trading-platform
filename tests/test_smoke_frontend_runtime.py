from scripts.smoke_frontend_runtime import consultar_frontend, evaluar_respuesta


class FakeResponse:
    def __init__(self, status_code=200, content_type="text/html; charset=utf-8", text="<!doctype html><html></html>"):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.text = text


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, timeout):
        self.calls.append((url, timeout))
        return self.response


def test_frontend_ready_requiere_200_html_y_documento():
    r = evaluar_respuesta(200, "text/html; charset=utf-8", "<!doctype html><html><body>BOT</body></html>")
    assert r["ready"] is True
    assert r["blockers"] == 0


def test_frontend_bloquea_respuesta_json_aunque_sea_200():
    r = evaluar_respuesta(200, "application/json", '{"ok": true}')
    assert r["ready"] is False
    assert r["blockers"] == 2


def test_frontend_bloquea_status_no_exitoso():
    r = evaluar_respuesta(503, "text/html", "<html></html>")
    assert r["ready"] is False
    assert any(c["codigo"] == "FRONTEND_HTTP_200" and c["nivel"] == "BLOCKER" for c in r["checks"])


def test_consulta_frontend_es_get_acotado_y_solo_lectura():
    session = FakeSession(FakeResponse())
    r = consultar_frontend("http://localhost:5173/", timeout=3.5, session=session)
    assert r["ready"] is True
    assert session.calls == [("http://localhost:5173", 3.5)]
