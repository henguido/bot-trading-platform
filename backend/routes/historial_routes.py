from fastapi import APIRouter
from backend.simulation.simulator import simulator  # Asegúrate que sea accesible o pásalo por inyección

router = APIRouter()

@router.get("/api/historial", tags=["Historial"])
def get_historial():
    return simulator.history + simulator.audit_log
