from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from backend.app.database import Base


class DecisionCycleAudit(Base):
    """Una fila agregada por ciclo operativo y usuario.

    No sustituye `DecisionAudit`: aquella conserva decisiones concretas; esta
    responde una pregunta distinta y de cardinalidad mucho menor: por que el
    ciclo termino con o sin ejecuciones.
    """

    __tablename__ = "decision_cycle_audit"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    ciclo_id = Column(String(64), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    modo = Column(String(16), nullable=False)
    decision_engine = Column(String(32), nullable=False)
    resumen_json = Column(Text, nullable=False)
