"""Клиент ML-модуля (ml_service/server.py), когда он работает отдельным сервисом.

Интерфейс тот же, что у LiveForecaster: ingest(fix) и forecasts(). Отметки не отправляются по одной:
ingest только кладет их в очередь, фоновый поток отправляет пачкой раз в FLUSH_S секунд. Если ML-модуль
недоступен, отметки копятся в ограниченной очереди, а forecasts() возвращает None: live-срез показывает
машины без прогнозов вместо того, чтобы падать.
"""
import json
import logging
import threading
import urllib.request
from collections import deque
from dataclasses import asdict

log = logging.getLogger("uvicorn.error")

FLUSH_S = 0.5
TIMEOUT_S = 5.0
QUEUE_MAX = 200_000        # ~несколько часов потока десятков машин; старые отметки вытесняются


class RemoteForecaster:
    def __init__(self, url: str, flush_s: float = FLUSH_S, timeout_s: float = TIMEOUT_S):
        self._url, self._flush_s, self._timeout = url.rstrip("/"), flush_s, timeout_s
        self._queue: deque = deque(maxlen=QUEUE_MAX)
        self._lock = threading.Lock()
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ml-client", daemon=True)
        self._thread.start()

    def ingest(self, fix) -> bool:
        with self._lock:
            self._queue.append(asdict(fix))
        return True

    def forecasts(self) -> dict | None:
        try:
            data = self._request("GET", "/forecasts")
        except Exception as e:  # noqa: BLE001 — нет прогнозов, но live-срез продолжает работать
            self._fail(e)
            return None
        self.error = None
        return {int(unit): fc for unit, fc in data.items()}

    @property
    def ready(self) -> bool:
        try:
            ok = bool(self._request("GET", "/health").get("ready"))
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            return False
        return ok

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(self._flush_s):
            self.flush()

    def flush(self) -> None:
        with self._lock:
            batch = list(self._queue)
            self._queue.clear()
        if not batch:
            return
        try:
            self._request("POST", "/fixes", batch)
        except Exception as e:  # noqa: BLE001 — вернуть в очередь и попробовать в следующий раз
            with self._lock:
                self._queue.extendleft(reversed(batch))
            self._fail(e)

    def _request(self, method: str, path: str, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self._url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return json.loads(resp.read())

    def _fail(self, e: Exception) -> None:
        msg = f"ML-модуль {self._url} недоступен: {type(e).__name__}: {e}"
        if msg != self.error:
            log.warning(msg)
        self.error = msg
