from backend.esquema import ALINEADO
from scripts.smoke_paper_runtime import consultar_health, evaluar_health, main


def _health(**overrides):
    base = {
        "trading_mode": "PAPER",
        "modo_real": False,
        "bucle_activo": True,
        "es_lider": True,
        "motivo_inactivo": None,
        "esquema": {
            "estado": ALINEADO,
            "revision_actual": "0007_decision_cycle_audit",
            "revision_esperada": "0007_decision_cycle_audit",
            "detalle": None,
        },
    }
    base.update(overrides)
    return base


def test_smoke_runtime_ready_solo_con_paper_alineado_activo_y_lider():
    resultado = evaluar_health(_health())

    assert resultado["ready"] is True
    assert resultado["status"] == "READY"
    assert resultado["blockers"] == 0
    assert {c["codigo"] for c in resultado["checks"]} == {
        "MODO_PAPER", "ALEMBIC", "BUCLE", "LIDERAZGO"
    }


def test_smoke_runtime_usa_estado_canonico_del_modulo_esquema():
    assert ALINEADO == "OK"
    resultado = evaluar_health(_health())
    alembic = next(c for c in resultado["checks"] if c["codigo"] == "ALEMBIC")
    assert alembic["nivel"] == "OK"


def test_smoke_runtime_bloquea_live_aunque_el_resto_este_sano():
    resultado = evaluar_health(_health(trading_mode="LIVE", modo_real=True))

    assert resultado["ready"] is False
    modo = next(c for c in resultado["checks"] if c["codigo"] == "MODO_PAPER")
    assert modo["nivel"] == "BLOCKER"


def test_smoke_runtime_bloquea_esquema_desalineado_bucle_inactivo_y_no_lider():
    resultado = evaluar_health(_health(
        bucle_activo=False,
        es_lider=False,
        motivo_inactivo="schema migration required",
        esquema={
            "estado": "SCHEMA_MIGRATION_REQUIRED",
            "revision_actual": "0006_paper_ledger",
            "revision_esperada": "0007_decision_cycle_audit",
            "detalle": "pendiente",
        },
    ))

    blockers = {c["codigo"] for c in resultado["checks"] if c["nivel"] == "BLOCKER"}
    assert blockers == {"ALEMBIC", "BUCLE", "LIDERAZGO"}


def test_consultar_health_solo_hace_get_al_endpoint_publico():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return _health()

    class Session:
        def __init__(self):
            self.calls = []

        def get(self, url, timeout):
            self.calls.append((url, timeout))
            return Response()

    session = Session()
    payload = consultar_health("http://127.0.0.1:8000/", timeout=3.5, session=session)

    assert payload["trading_mode"] == "PAPER"
    assert session.calls == [("http://127.0.0.1:8000/health", 3.5)]


def test_main_falla_cerrado_si_health_no_es_consultable(monkeypatch, capsys):
    def falla(*_args, **_kwargs):
        raise RuntimeError("backend no disponible")

    monkeypatch.setattr("scripts.smoke_paper_runtime.consultar_health", falla)
    codigo = main(["--base-url", "http://127.0.0.1:9999"])
    salida = capsys.readouterr().out

    assert codigo == 2
    assert '"status": "NOT_READY"' in salida
    assert '"codigo": "HEALTH_HTTP"' in salida
