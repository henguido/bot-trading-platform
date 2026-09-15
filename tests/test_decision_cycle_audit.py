from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.database import Base
from backend.observabilidad.ciclos import (
    ResumenCicloDecision,
    persistir_resumen_ciclo,
    ultimos_resumenes,
)
from backend.observabilidad.models import DecisionCycleAudit


def _db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _usuario(db, email):
    u = models.User(nombre=email.split("@")[0], email=email, password_hash="hash")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_resumen_ciclo_explica_embudo_y_motivo_principal():
    r = ResumenCicloDecision(
        ciclo_id="ciclo-1",
        usuario_id=7,
        modo="PAPER",
        decision_engine="GPT",
    )
    r.anotar_elegibilidad(SimpleNamespace(
        universo=100,
        elegibles_compra=20,
        preservados_venta=1,
        descartados=79,
        por_motivo={"ELEGIBLE": 20, "MIN_NOTIONAL_INALCANZABLE": 50},
    ))
    r.anotar_scanner(SimpleNamespace(
        entrada=20,
        puntuados=18,
        seleccionados=5,
        preservados=1,
        descartados=2,
        por_motivo={"SPREAD_EXCESIVO": 2, "FUERA_DEL_TOP": 13},
    ))
    r.anotar_rentabilidad_pre(
        antes=6,
        despues=6,
        aplicado=False,
        motivo="DESACTIVADO_PENDIENTE_EVIDENCIA_OOS",
    )
    r.anotar_decision("COMPRAR")
    r.anotar_riesgo(SimpleNamespace(
        aprobado=False,
        limite_violado="MAX_EXPOSICION_TOTAL_USDT",
        motivo="exposicion total",
    ))

    salida = r.como_dict()

    assert salida["motivo_principal"] == "RIESGO_BLOQUEO"
    assert salida["hubo_ejecucion"] is False
    assert salida["contadores"]["universo"] == 100
    assert salida["contadores"]["scanner_seleccionados"] == 5
    assert salida["contadores"]["riesgo_rechazadas"] == 1
    assert salida["motivos"]["ELEGIBILIDAD:MIN_NOTIONAL_INALCANZABLE"] == 50
    assert salida["motivos"]["SCANNER:FUERA_DEL_TOP"] == 13
    assert salida["motivos"]["RIESGO:MAX_EXPOSICION_TOTAL_USDT"] == 1


def test_persistencia_es_idempotente_y_lectura_aisla_por_usuario():
    db = _db()
    try:
        u1 = _usuario(db, "uno@example.com")
        u2 = _usuario(db, "dos@example.com")

        r1 = ResumenCicloDecision("ciclo-u1", u1.id, "PAPER", "GPT")
        r1.anotar_decision("ESPERAR")
        fila1 = persistir_resumen_ciclo(db, r1)
        fila1_repetida = persistir_resumen_ciclo(db, r1)
        assert fila1.id == fila1_repetida.id

        r2 = ResumenCicloDecision("ciclo-u2", u2.id, "PAPER", "SAFE_NO_TRADE")
        persistir_resumen_ciclo(db, r2)

        filas_u1 = ultimos_resumenes(db, usuario_id=u1.id)
        assert len(filas_u1) == 1
        assert filas_u1[0]["ciclo_id"] == "ciclo-u1"
        assert filas_u1[0]["usuario_id"] == u1.id
        assert filas_u1[0]["motivo_principal"] == "MOTOR_ESPERAR"
        assert db.query(DecisionCycleAudit).count() == 2
    finally:
        db.close()


def test_ejecucion_exitosa_domina_el_motivo_principal():
    r = ResumenCicloDecision("ciclo-ok", 1, "PAPER", "GPT")
    r.anotar_decision("COMPRAR")
    r.anotar_riesgo(SimpleNamespace(aprobado=True))
    r.anotar_ejecucion(success=True)
    assert r.como_dict()["motivo_principal"] == "OPERACION_EJECUTADA"
    assert r.como_dict()["hubo_ejecucion"] is True
