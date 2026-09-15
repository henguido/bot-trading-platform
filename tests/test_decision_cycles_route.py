from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.database import Base
from backend.observabilidad.ciclos import ResumenCicloDecision, persistir_resumen_ciclo
from backend.observabilidad.models import DecisionCycleAudit  # noqa: F401
from backend.routes.transacciones_routes import obtener_ciclos_decision


def _db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _usuario(db, nombre, email):
    u = models.User(nombre=nombre, email=email, password_hash="hash")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_endpoint_ciclos_devuelve_solo_ciclos_del_usuario_actual():
    db = _db()
    try:
        uno = _usuario(db, "Uno", "uno@e.com")
        dos = _usuario(db, "Dos", "dos@e.com")

        r1 = ResumenCicloDecision("ciclo-uno", uno.id, "PAPER", "GPT")
        r1.anotar_decision("ESPERAR")
        persistir_resumen_ciclo(db, r1)

        r2 = ResumenCicloDecision("ciclo-dos", dos.id, "PAPER", "GPT")
        r2.anotar_decision("COMPRAR")
        persistir_resumen_ciclo(db, r2)

        salida = obtener_ciclos_decision(limite=12, db=db, current_user=uno)
        assert [fila["ciclo_id"] for fila in salida] == ["ciclo-uno"]
        assert salida[0]["motivo_principal"] == "MOTOR_ESPERAR"
    finally:
        db.close()
