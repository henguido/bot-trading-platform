from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app import models, schemas, database
from backend.app.database import SessionLocal
from backend.config.settings import (
    DATABASE_URL,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from passlib.context import CryptContext
# JWTError es la clase base de todos los errores de python-jose (firma invalida,
# token malformado, ExpiredSignatureError...). Antes se usaba en el 'except' sin
# importarla, lo que convertia cualquier token invalido en un 500 por NameError.
from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer

# Configuración para hasheo de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ALGORITHM y ACCESS_TOKEN_EXPIRE_MINUTES se importan de config.settings, que es
# la unica fuente de verdad. Antes se redefinian aqui (24 h) contradiciendo el
# valor declarado en settings (60 min).

# Obtener instancia de base de datos (para usar con Depends)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Hashear una contraseña
def get_password_hash(password):
    return pwd_context.hash(password)

# Verificar si una contraseña es válida
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# Crear token de acceso (JWT)
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="No se pudo validar el token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception

    return user