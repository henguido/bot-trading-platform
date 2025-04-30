# bot_api.py

from fastapi import APIRouter
from simulation.simulator import Simulator

router = APIRouter()
simulator = Simulator()

@router.get("/api/saldo")
def get_saldo():
    return {"capital_actual": simulator.capital}

@router.get("/api/historial")
def get_historial():
    return simulator.history

@router.get("/api/estado")
def get_estado():
    return simulator.latest_decisions if hasattr(simulator, "latest_decisions") else {}
