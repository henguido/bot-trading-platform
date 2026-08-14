from sqlalchemy import (Column, Integer, String, Float, ForeignKey, DateTime,
                        UniqueConstraint)
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base
from sqlalchemy import Text

class User(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    tipo_cuenta = Column(String, default="free")

    portafolios = relationship("Portfolio", back_populates="usuario")

class Portfolio(Base):
    __tablename__ = "portafolios"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    nombre = Column(String, nullable=False)
    tipo_activo = Column(String, nullable=False)
    balance_inicial = Column(Float, default=0.0)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("User", back_populates="portafolios")
    transacciones = relationship("Transaction", back_populates="portafolio")

class Asset(Base):
    __tablename__ = "activos"
    id = Column(Integer, primary_key=True, index=True)
    simbolo = Column(String, unique=True, index=True)
    nombre = Column(String)
    tipo = Column(String)

class Transaction(Base):
    __tablename__ = "transacciones"
    id = Column(Integer, primary_key=True, index=True)
    portafolio_id = Column(Integer, ForeignKey("portafolios.id"))
    activo_id = Column(Integer, ForeignKey("activos.id"))
    tipo_operacion = Column(String)  # Compra o Venta
    cantidad = Column(Float)
    precio = Column(Float)
    fecha_operacion = Column(DateTime, default=datetime.utcnow)
    # Origen economico de la transaccion. UNIQUE para que un mismo fill no
    # pueda generar dos apuntes. NULL en las transacciones legacy, anteriores
    # al sistema de ordenes; UNIQUE admite multiples NULL.
    fill_id = Column(Integer, ForeignKey("fills.id"), unique=True, nullable=True)

    portafolio = relationship("Portfolio", back_populates="transacciones")
    activo = relationship("Asset")  # ✅ Añadir esta línea

class Orden(Base):
    """
    Intencion de operar. Se persiste ANTES de enviar nada al broker (P0-11).

    Es la unica forma de poder preguntar despues "que paso con ESTA orden"
    cuando se pierde la respuesta. `client_order_id` es UNIQUE: dos procesos no
    pueden registrar la misma orden, y reintentar no crea una segunda.
    """
    __tablename__ = "ordenes"

    id = Column(Integer, primary_key=True, index=True)
    client_order_id = Column(String(64), unique=True, nullable=False, index=True)
    broker = Column(String(32), nullable=False, default="binance")
    broker_order_id = Column(String(64), nullable=True, index=True)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    decision_audit_id = Column(Integer, ForeignKey("decision_audit.id"), nullable=True)

    symbol = Column(String(32), nullable=False, index=True)
    side = Column(String(8), nullable=False)          # BUY | SELL

    requested_base_quantity = Column(Float, nullable=True)
    requested_quote_amount = Column(Float, nullable=True)
    executed_base_quantity = Column(Float, nullable=False, default=0.0)
    executed_quote_amount = Column(Float, nullable=False, default=0.0)

    estado = Column(String(32), nullable=False, index=True)
    error = Column(Text, nullable=True)

    creada_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    actualizada_en = Column(DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow, nullable=False)

    fills = relationship("Fill", back_populates="orden")


class Fill(Base):
    """
    Ejecucion parcial o total confirmada por el broker.

    La identidad externa (broker, symbol, trade_id) es UNIQUE: procesar el mismo
    fill cien veces deja una sola fila. Es lo que hace idempotente al
    reconciliador a nivel de BASE DE DATOS, no solo de codigo Python.
    """
    __tablename__ = "fills"
    __table_args__ = (
        UniqueConstraint("broker", "symbol", "trade_id", name="uq_fill_externo"),
    )

    id = Column(Integer, primary_key=True, index=True)
    orden_id = Column(Integer, ForeignKey("ordenes.id"), nullable=False, index=True)

    broker = Column(String(32), nullable=False, default="binance")
    symbol = Column(String(32), nullable=False)
    trade_id = Column(String(64), nullable=False)

    price = Column(Float, nullable=False)
    qty = Column(Float, nullable=False)
    # Tal cual lo informa el broker. Nunca se deduce una tasa.
    commission = Column(Float, nullable=True)
    commission_asset = Column(String(16), nullable=True)

    registrado_en = Column(DateTime, default=datetime.utcnow, nullable=False)

    orden = relationship("Orden", back_populates="fills")


class DecisionAudit(Base):
    __tablename__ = "decision_audit"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)
    quantity = Column(Float)
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    sentimiento = Column(String)
    noticias = Column(Text)
    risk_score = Column(Float)
    decision_gpt = Column(Text)  # JSON como texto por simplicidad
