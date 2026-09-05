from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config.settings import DATABASE_URL

# Motor y sesión
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Función para obtener la sesión DB con FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
