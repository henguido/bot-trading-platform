import os
from dotenv import load_dotenv

load_dotenv()

# MODULO LEGADO — no lo importa nadie. La configuracion canonica vive en
# backend/config/settings.py. Se mantiene solo por compatibilidad historica.
# El fallback "supersecret" se elimino: una clave de firma conocida anularia
# la autenticacion de toda la API.
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
