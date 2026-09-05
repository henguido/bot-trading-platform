from scripts.verify_paper_v1_rc import construir_veredicto


def test_rc_ready_operativo_no_equivale_a_estrategia_validada():
    readiness = {"ready": True, "status": "READY"}
    runtime = {"ready": True, "status": "READY"}
    research = {
        "status": "INSUFFICIENT_EVIDENCE",
        "blockers": ["05I_BUCKETS_8_DE_30", "05K_BUCKETS_NETOS_1_DE_30"],
    }

    r = construir_veredicto(readiness, runtime, research)

    assert r["operational_ready"] is True
    assert r["operational_status"] == "READY"
    assert r["strategy_validation_status"] == "INSUFFICIENT_EVIDENCE"
    assert r["strategy_validation_blockers"] == [
        "05I_BUCKETS_8_DE_30",
        "05K_BUCKETS_NETOS_1_DE_30",
    ]
    assert r["live_authorized"] is False
    assert r["profitability_gate_05e_enabled"] is False


def test_rc_bloquea_si_falla_readiness_estatico():
    r = construir_veredicto(
        {"ready": False, "status": "NOT_READY"},
        {"ready": True, "status": "READY"},
        None,
    )
    assert r["operational_ready"] is False
    assert r["operational_status"] == "NOT_READY"
    assert r["strategy_validation_status"] == "NO_DISPONIBLE"


def test_rc_bloquea_si_falla_smoke_runtime():
    r = construir_veredicto(
        {"ready": True, "status": "READY"},
        {"ready": False, "status": "NOT_READY"},
        {"status": "INSUFFICIENT_EVIDENCE", "blockers": []},
    )
    assert r["operational_ready"] is False
    assert r["operational_status"] == "NOT_READY"


def test_rc_reporta_research_invalido_sin_convertirlo_en_permiso_live():
    r = construir_veredicto(
        {"ready": True},
        {"ready": True},
        {"_invalid": True},
    )
    assert r["operational_ready"] is True
    assert r["strategy_validation_status"] == "INVALIDO"
    assert r["live_authorized"] is False
