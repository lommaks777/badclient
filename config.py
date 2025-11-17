# config.py
import os

# Получаем переменные окружения, с fallback на значения по умолчанию для локальной разработки
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "ft:gpt-3.5-turbo-0125:personal:massage-client-v1:CciCxlPm")

# Проверка наличия обязательных переменных
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен. Установите переменную окружения.")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не установлен. Установите переменную окружения.")

