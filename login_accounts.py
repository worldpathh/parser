"""
Скрипт для первичной авторизации аккаунтов.
Запустите один раз перед использованием парсера.
"""
import asyncio
import sys

from clients import create_client

import config as _cfg

API_ID = _cfg.API_ID
API_HASH = _cfg.API_HASH
ACCOUNTS = _cfg.ACCOUNTS
SESSIONS_DIR = _cfg.SESSIONS_DIR



async def login_all():
    for name in ACCOUNTS:
        print(f"\n=== Логин аккаунта: {name} ===")
        print("Введите номер телефона (с кодом страны, например +79001234567)")
        print("Или Enter чтобы пропустить, если сессия уже есть")
        phone = input("Phone: ").strip()
        if not phone:
            continue
        try:
            await create_client(name, API_ID, API_HASH, SESSIONS_DIR, phone=phone, force_sms=False)
            print(f"✓ {name} успешно авторизован")
        except Exception as e:
            print(f"✗ Ошибка: {e}")


if __name__ == "__main__":
    # Проверяем, нужно ли логинить один аккаунт
    if len(sys.argv) > 1:
        name = sys.argv[1]
        print(f"Логин: {name}")
        phone = input("Phone: ").strip()
        asyncio.run(create_client(name, API_ID, API_HASH, SESSIONS_DIR, phone=phone, force_sms=False))
    else:
        asyncio.run(login_all())
