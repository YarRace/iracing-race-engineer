"""Разовая авторизация Telegram для Дмитрия (только отправка сообщений).

Что нужно заранее: зайти на https://my.telegram.org → API development tools →
создать приложение → скопировать api_id (число) и api_hash (строка).

Запуск: python tg_setup.py
Скрипт спросит api_id, api_hash, номер телефона и код из Telegram, создаст
сессию (dmitry_tg.session) и сохранит api-данные в tg_config.json (локально).
"""
import json
import os

from telethon.sync import TelegramClient

_ROOT = os.path.abspath(os.path.dirname(__file__))
CONFIG = os.path.join(_ROOT, "tg_config.json")
SESSION = os.path.join(_ROOT, "dmitry_tg")

print("=== Настройка Telegram для Дмитрия ===")
print("Сначала получи api_id и api_hash на https://my.telegram.org (API development tools).\n")

api_id = input("api_id (число): ").strip()
api_hash = input("api_hash (строка): ").strip()

with open(CONFIG, "w", encoding="utf-8") as f:
    json.dump({"api_id": int(api_id), "api_hash": api_hash}, f)

print("\nПодключаюсь… введи номер телефона и код, который придёт в Telegram.")
with TelegramClient(SESSION, int(api_id), api_hash) as client:
    me = client.get_me()
    print(f"\nГотово! Авторизован как: {me.first_name} (@{me.username})")
    print("Несколько твоих чатов (для проверки):")
    for d in client.get_dialogs(limit=10):
        print("  -", d.name)
print("\nСессия сохранена. Теперь Дмитрий может писать в чаты.")
