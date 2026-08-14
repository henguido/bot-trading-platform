from fastapi import APIRouter, Depends
from backend.simulation.simulator import simulator  # Asegúrate que sea accesible o pásalo por inyección
from backend.app.auth import get_current_user
from backend.app import models

router = APIRouter()

@router.get("/api/historial", tags=["Historial"])
def get_historial(current_user: models.User = Depends(get_current_user)):
    return simulator.history + simulator.audit_log
