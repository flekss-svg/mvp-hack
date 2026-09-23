"""Контракт источников данных.

Сервис, движок признаков (engine/) и модель (model/) знают только каноническую схему из
domain/schema.py — не то, откуда данные пришли.

* Плановое расписание: любой источник (data.mos.ru, GTFS другого города, ...) реализует
  протокол ScheduleSource — метод load(), возвращающий ScheduleTables. Сейчас единственная
  реализация — data_sources/mos_ru_schedule.py.

* Фактическое движение: источник (симулятор simulation/synthetic_telemetry.py или адаптер
  реальной телематики data_sources/gps_telemetry.py) обязан отдавать pandas.DataFrame с
  колонками domain.schema.STOP_EVENT_COLUMNS. Это не формализовано отдельным протоколом,
  потому что у источников разная форма вызова (симулятор генерирует день целиком, GPS-адаптер
  разбирает поток отметок) — общий для них контракт именно в форме выходных данных.

Добавление нового источника — это всегда новый файл в data_sources/ или simulation/,
реализующий один из этих контрактов. Остальной код (engine, model, service, api) менять
не нужно.
"""
from typing import Protocol, runtime_checkable

from app.domain.schema import ScheduleTables


@runtime_checkable
class ScheduleSource(Protocol):
    def load(self) -> ScheduleTables:
        """Построить плановое расписание в канонической схеме ScheduleTables."""
        ...
