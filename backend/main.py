from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app import models, schemas, auth
from app.database import engine, SessionLocal
from app.auth import get_password_hash, verify_password, create_access_token, get_db

# Inicializar la base de datos
models.Base.metadata.create_all(bind=engine)

# Crear instancia FastAPI
app = FastAPI(
    title="BOT Trading Platform",
    description="API de trading con login/signup",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)



# Middleware de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción podrías usar ["https://tu-frontend.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ruta de prueba
@app.get("/")
def read_root():
    return {"message": "Bienvenido a BOT Trading Platform"}

# Ruta para registrarse
@app.post("/signup", response_model=schemas.Token)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El correo ya está registrado.")
    hashed_pw = get_password_hash(user.password)
    new_user = models.User(nombre=user.nombre, email=user.email, password_hash=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    token = create_access_token(data={"sub": new_user.email})
    return {"access_token": token, "token_type": "bearer"}

# Ruta para iniciar sesión
@app.post("/login", response_model=schemas.Token)
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = create_access_token(data={"sub": db_user.email})
    return {"access_token": token, "token_type": "bearer"}
