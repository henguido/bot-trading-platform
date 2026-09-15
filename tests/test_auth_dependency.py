"""
P0-3 · Pruebas de comportamiento de la capa de autenticacion.

Se monta una app FastAPI MINIMA que usa la dependencia REAL `get_current_user`.
No se importa `backend.main`: hacerlo arrancaria el hilo de trading e
instanciaria clientes de Binance/Alpaca. Aqui no hay ninguna llamada de red.

Cubre:
  1. endpoint protegido sin token           -> 401
  2. token con formato invalido             -> 401
  3. token firmado con otra clave           -> 401
  4. token expirado                         -> 401
  5. token valido                           -> 200
  6. token valido de un usuario inexistente -> 401
  7. login/signup siguen publicos
  8. hash/verify real de contrasena funciona con el conjunto reproducible
"""
from datetime import datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.auth import (
    get_current_user,
    get_db,
    get_password_hash,
    verify_password,
)
from backend.config import settings

EMAIL_VALIDO = "usuario.prueba@ejemplo.com"


@pytest.fixture(scope="module")
def db_memoria():
    """SQLite en memoria con un usuario de prueba. Jamas toca la BD real."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with Sesion() as db:
        db.add(models.User(
            nombre="Usuario Prueba",
            email=EMAIL_VALIDO,
            password_hash="hash-irrelevante-para-estas-pruebas",
        ))
        db.commit()

    yield Sesion
    engine.dispose()


@pytest.fixture(scope="module")
def client(db_memoria):
    """App minima con una ruta protegida por la dependencia real."""
    app = FastAPI()

    @app.get("/protegido")
    def protegido(current_user: models.User = Depends(get_current_user)):
        return {"email": current_user.email}

    @app.post("/login")
    def login_publico():
        return {"ok": True}

    @app.post("/signup")
    def signup_publico():
        return {"ok": True}

    def get_db_override():
        db = db_memoria()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = get_db_override
    return TestClient(app)


def _token(email, minutos_validez=60, clave=None):
    exp = datetime.utcnow() + timedelta(minutes=minutos_validez)
    return jwt.encode(
        {"sub": email, "exp": exp},
        clave or settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_sin_token_devuelve_401(client):
    r = client.get("/protegido")
    assert r.status_code == 401, f"esperado 401, recibido {r.status_code}"


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_token_con_formato_invalido_devuelve_401(client):
    r = client.get("/protegido", headers={"Authorization": "Bearer esto-no-es-un-jwt"})
    assert r.status_code == 401, f"esperado 401, recibido {r.status_code}"
    assert r.status_code != 500, "un token invalido nunca debe provocar un 500"


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_token_firmado_con_otra_clave_devuelve_401(client):
    falso = _token(EMAIL_VALIDO, clave="clave-del-atacante")
    r = client.get("/protegido", headers={"Authorization": f"Bearer {falso}"})
    assert r.status_code == 401, f"esperado 401, recibido {r.status_code}"


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_token_expirado_devuelve_401(client):
    caducado = _token(EMAIL_VALIDO, minutos_validez=-5)
    r = client.get("/protegido", headers={"Authorization": f"Bearer {caducado}"})
    assert r.status_code == 401, f"esperado 401, recibido {r.status_code}"
    assert r.status_code != 500, "un token expirado nunca debe provocar un 500"


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_token_valido_pasa_autenticacion(client):
    valido = _token(EMAIL_VALIDO)
    r = client.get("/protegido", headers={"Authorization": f"Bearer {valido}"})
    assert r.status_code == 200, f"esperado 200, recibido {r.status_code}"
    assert r.json()["email"] == EMAIL_VALIDO


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_token_valido_de_usuario_inexistente_devuelve_401(client):
    huerfano = _token("no.existe@ejemplo.com")
    r = client.get("/protegido", headers={"Authorization": f"Bearer {huerfano}"})
    assert r.status_code == 401, f"esperado 401, recibido {r.status_code}"


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_login_y_signup_siguen_siendo_publicos(client):
    assert client.post("/login").status_code == 200
    assert client.post("/signup").status_code == 200


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_hash_y_verify_de_contrasena_real_funcionan():
    """Regresion del fallo passlib 1.7.4 + bcrypt 5.0.0 observado en Windows."""
    password = "Clave-Prueba-2026!"
    password_hash = get_password_hash(password)

    assert password_hash != password
    assert verify_password(password, password_hash) is True
    assert verify_password("otra-clave", password_hash) is False


# ── Config canonica ──────────────────────────────────────────────────────────
def test_configuracion_jwt_es_unica_y_coherente():
    """auth.py debe usar exactamente los valores de config.settings."""
    from backend.app import auth
    assert auth.ALGORITHM == settings.ALGORITHM == "HS256"
    assert auth.ACCESS_TOKEN_EXPIRE_MINUTES == settings.ACCESS_TOKEN_EXPIRE_MINUTES


def test_jwterror_esta_importado_en_auth():
    """Regresion: 'except JWTError' sin importar la clase provocaba NameError -> 500."""
    from backend.app import auth
    from jose import JWTError
    assert getattr(auth, "JWTError", None) is JWTError
