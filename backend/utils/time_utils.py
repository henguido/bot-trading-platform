# backend/utils/time_utils.py

from datetime import datetime, time
import pytz

def mercado_ny_abierto():
    """
    Verifica si el mercado de acciones de Nueva York está abierto (NYSE/NASDAQ).
    Horario regular: Lunes a Viernes, de 9:30 AM a 4:00 PM (hora Nueva York).
    """
    zona_ny = pytz.timezone("America/New_York")
    ahora_ny = datetime.now(zona_ny)
    hora_actual = ahora_ny.time()
    dia_semana = ahora_ny.weekday()  # Lunes = 0, Domingo = 6

    apertura = time(9, 30)
    cierre = time(16, 0)

    return dia_semana < 5 and apertura <= hora_actual <= cierre
