from backend.app.database import engine
from sqlalchemy import inspect

inspector = inspect(engine)
columns = inspector.get_columns('usuarios')

for col in columns:
    print(col['name'])