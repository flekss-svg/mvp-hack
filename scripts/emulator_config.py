"""Отправить конфиг эмулятору терминалов организаторов (ndtp-telemetry-emulator).

Эмулятор хранит конфиг только в памяти: после каждого старта его нужно прислать заново
(POST /api/config), иначе он ничего не шлет. В compose это делает сервис emulator-config.

Эмулятор с autoGenerate шлет случайное блуждание около Москвы и текущее время — это машины без
расписания («контекстные»): на карте они видны, прогноза по ним нет. Цель — показать, что сервис
принимает NDTP от родного инструмента организаторов.

    python scripts/emulator_config.py --url http://emulator:18080 --target backend:9201 --units 5
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def wait_ready(url: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    while True:
        try:
            urllib.request.urlopen(f"{url}/api/cells", timeout=3).read()
            return
        except (urllib.error.URLError, OSError):
            if time.time() > deadline:
                sys.exit(f"эмулятор {url} не ответил за {timeout_s:.0f} с")
            time.sleep(2)


def config(target_host: str, target_port: int, units: int, interval_ms: int, first_unit: int) -> dict:
    # Стартовая точка autoGenerate зависит от unitId % 1000 (спецификация эмулятора):
    # шаг 200 разносит машины по городу, а не кладет их в одну точку.
    ids = [first_unit + 200 * i for i in range(units)]
    return {"targetHost": target_host, "targetPort": target_port,
            "units": [{"unitId": u, "intervalMs": interval_ms, "autoGenerate": True, "cells": []} for u in ids]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:18080", help="REST API эмулятора")
    ap.add_argument("--target", default="backend:9201", help="куда слать NDTP, хост:порт")
    ap.add_argument("--units", type=int, default=5)
    ap.add_argument("--interval-ms", type=int, default=5000)
    ap.add_argument("--first-unit", type=int, default=1000100)
    ap.add_argument("--wait", type=float, default=120, help="сколько секунд ждать запуска эмулятора")
    args = ap.parse_args()

    host, port = args.target.rsplit(":", 1)
    wait_ready(args.url, args.wait)
    body = json.dumps(config(host, int(port), args.units, args.interval_ms, args.first_unit)).encode()
    req = urllib.request.Request(f"{args.url}/api/config", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.HTTPError as e:
        sys.exit(f"эмулятор отклонил конфиг: HTTP {e.code} {e.read().decode(errors='replace')}")
    print(f"эмулятор {args.url}: {args.units} машин, каждые {args.interval_ms} мс -> {args.target}")


if __name__ == "__main__":
    main()
