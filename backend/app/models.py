from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

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

    portafolio = relationship("Portfolio", back_populates="transacciones")
