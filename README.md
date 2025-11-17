# Bad Client - Telegram Bot

Telegram бот для тренировки навыков продаж массажа.

## Локальная разработка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` или установите переменные окружения:
```bash
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
export OPENAI_API_KEY="your_openai_api_key"
export LLM_MODEL="ft:gpt-3.5-turbo-0125:personal:massage-client-v1:CciCxlPm"  # опционально
```

3. Запустите бота:
```bash
python main.py
```

## Деплой на Railway

### Шаг 1: Подготовка репозитория

1. Убедитесь, что все изменения закоммичены:
```bash
git add .
git commit -m "Prepare for Railway deployment"
```

2. Запушьте изменения в GitHub:
```bash
git push origin main
```

### Шаг 2: Создание проекта на Railway

1. Зайдите на [railway.app](https://railway.app) и войдите через GitHub
2. Нажмите "New Project"
3. Выберите "Deploy from GitHub repo"
4. Выберите ваш репозиторий `badclient`

### Шаг 3: Настройка переменных окружения

В настройках проекта Railway добавьте следующие переменные окружения:

- `TELEGRAM_BOT_TOKEN` - токен вашего Telegram бота (получите у @BotFather)
- `OPENAI_API_KEY` - ваш API ключ OpenAI
- `LLM_MODEL` - модель OpenAI (опционально, по умолчанию используется fine-tuned модель)

### Шаг 4: Деплой

Railway автоматически определит проект как Python и запустит деплой. Процесс займет несколько минут.

### Шаг 5: Проверка

После успешного деплоя бот должен автоматически запуститься. Проверьте логи в Railway Dashboard, чтобы убедиться, что бот работает корректно.

## Важные замечания

- **База данных**: Файл `leaderboard_db.json` хранится в ephemeral storage Railway. Данные могут быть потеряны при перезапуске сервиса. Для продакшена рекомендуется использовать внешнюю БД (PostgreSQL, MongoDB и т.д.).

- **Логи**: Все логи доступны в Railway Dashboard в разделе "Deployments" → "View Logs"

- **Перезапуск**: Бот автоматически перезапустится при сбое благодаря настройке `restartPolicyType: "ON_FAILURE"` в `railway.json`

## Структура проекта

- `main.py` - основной файл бота
- `config.py` - конфигурация (использует переменные окружения)
- `roles_data.py` - данные о ролях клиентов
- `requirements.txt` - зависимости Python
- `Procfile` - команда запуска для Railway
- `railway.json` - конфигурация Railway

