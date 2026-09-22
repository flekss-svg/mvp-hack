"""Общие настройки MVP."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
MODELS = ROOT / "models"
REPORTS = ROOT / "reports"
DASH = ROOT / "dashboard"

# Файлы data.mos.ru (имена выгрузок могут отличаться датой — ищем по номеру набора)
DATASETS = {
    "routes": "60664",      # маршруты
    "stops": "60662",       # остановки с координатами
    "trips": "60665",       # рейсы
    "stop_times": "60661",  # плановое время на остановках
    "calendar": "60666",    # перечни дат (дни недели)
}

# Сколько маршрутов брать в MVP (самые насыщенные по будням). None = все.
N_ROUTES = 40

# Постановка задачи
LATE_THRESHOLD_MIN = 3.0     # опоздание, которое считаем задержкой
HORIZON_MIN = (10, 15)       # прогнозируем состояние через 10–15 минут

# Синтетический «факт» (заменяется реальной телематикой)
SIM_START = "2026-08-10"     # понедельник
SIM_DAYS = 28
RANDOM_SEED = 42

# Праздники РФ в окне симуляции (для реальных данных — брать из производственного календаря)
HOLIDAYS = set()
