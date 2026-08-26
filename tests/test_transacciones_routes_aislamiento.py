from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.database import Base
from backend.routes.transacciones_routes import obtener_transacciones_reales


def _db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _usuario(db, nombre, email):
    usuario = models.User(
        nombre=nombre,
        email=email,
        password_hash="hash-solo-prueba",
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def _transaccion(db, usuario, *, symbol, precio):
    activo = models.Asset(simbolo=symbol, nombre=symbol, tipo="crypto")
    db.add(activo)
    db.commit()
    db.refresh(activo)

    portafolio = models.Portfolio(
        usuario_id=usuario.id,
        nombre=f"Portfolio {usuario.id}",
        tipo_activo="crypto",
        balance_inicial=0.0,
    )
    db.add(portafolio)
    db.commit()
    db.refresh(portafolio)

    tx = models.Transaction(
        portafolio_id=portafolio.id,
        activo_id=activo.id,
        tipo_operacion="Compra",
        cantidad=1.0,
        precio=precio,
        fecha_operacion=datetime(2026, 8, 26, 12, 0, 0),
    )
    db.add(tx)
    db.commit()
    return tx


def test_transacciones_reales_aisla_por_usuario_autenticado():
    db = _db()
    try:
        usuario_a = _usuario(db, "A", "a@example.com")
        usuario_b = _usuario(db, "B", "b@example.com")
        _transaccion(db, usuario_a, symbol="BTCUSDT", precio=100.0)
        _transaccion(db, usuario_b, symbol="ETHUSDT", precio=200.0)

        resultado = obtener_transacciones_reales(db=db, current_user=usuario_a)

        assert len(resultado) == 1
        assert resultado[0]["usuario_id"] == usuario_a.id
        assert resultado[0]["simbolo"] == "BTCUSDT"
    finally:
        db.close()


def test_transacciones_reales_sin_filas_devuelve_lista_vacia():
    db = _db()
    try:
        usuario = _usuario(db, "Sin operaciones", "empty@example.com")
        assert obtener_transacciones_reales(db=db, current_user=usuario) == []
    finally:
        db.close()
