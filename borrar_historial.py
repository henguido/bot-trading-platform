from backend.app.database import SessionLocal, engine
from backend.app import models

# Borrar todas las tablas y recrearlas
print("⚠️ Eliminando todas las tablas...")
models.Base.metadata.drop_all(bind=engine)
print("✅ Tablas eliminadas.")

print("🛠️ Creando tablas nuevas...")
models.Base.metadata.create_all(bind=engine)
print("✅ Base de datos reiniciada.")
