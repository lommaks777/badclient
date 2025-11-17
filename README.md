# Bad Client - Telegram Bot

Telegram бот для тренировки навыков продаж массажа.

## Локальная разработка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Установите PostgreSQL локально или используйте облачную БД (например, Railway PostgreSQL)

3. Создайте файл `.env` или установите переменные окружения:
```bash
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
export OPENAI_API_KEY="your_openai_api_key"
export DATABASE_URL="postgresql://user:password@localhost:5432/dbname"
export LLM_MODEL="ft:gpt-3.5-turbo-0125:personal:massage-client-v1:CciCxlPm"  # опционально
```

4. Запустите бота:
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

### Шаг 3: Добавление PostgreSQL базы данных

1. В вашем проекте Railway нажмите **"+ New"** → **"Database"** → **"Add PostgreSQL"**
2. Railway автоматически создаст PostgreSQL базу данных и добавит переменную окружения `DATABASE_URL`
3. База данных будет автоматически подключена к вашему сервису

### Шаг 4: Настройка переменных окружения

В настройках проекта Railway добавьте следующие переменные окружения:

- `TELEGRAM_BOT_TOKEN` - токен вашего Telegram бота (получите у @BotFather)
- `OPENAI_API_KEY` - ваш API ключ OpenAI
- `DATABASE_URL` - автоматически добавляется при создании PostgreSQL (не нужно настраивать вручную)
- `LLM_MODEL` - модель OpenAI (опционально, по умолчанию используется fine-tuned модель)

### Шаг 5: Деплой

Railway автоматически определит проект как Python и запустит деплой. Процесс займет несколько минут.

**Важно:** При первом запуске бот автоматически создаст необходимые таблицы в базе данных. Убедитесь, что `DATABASE_URL` правильно настроен.

### Шаг 6: Проверка

После успешного деплоя бот должен автоматически запуститься. Проверьте логи в Railway Dashboard, чтобы убедиться, что:
- База данных подключена успешно
- Таблицы созданы (вы увидите сообщение "Таблицы созданы успешно")
- Бот работает корректно

## Важные замечания

- **База данных**: Проект использует PostgreSQL для хранения данных лидерборда. Данные сохраняются надежно и не теряются при перезапуске сервиса.

- **Автоматическая миграция**: При первом запуске бот автоматически создает необходимые таблицы в базе данных. Если нужно выполнить миграцию вручную, используйте файл `schema.sql`.

- **Логи**: Все логи доступны в Railway Dashboard в разделе "Deployments" → "View Logs"

- **Перезапуск**: Бот автоматически перезапустится при сбое благодаря настройке `restartPolicyType: "ON_FAILURE"` в `railway.json`

- **Подключение к БД**: Railway автоматически предоставляет переменную `DATABASE_URL` при добавлении PostgreSQL. Убедитесь, что она доступна в вашем сервисе.

## Структура проекта

- `main.py` - основной файл бота
- `config.py` - конфигурация (использует переменные окружения)
- `db.py` - модуль для работы с PostgreSQL базой данных
- `roles_data.py` - данные о ролях клиентов
- `schema.sql` - SQL схема для базы данных (создается автоматически)
- `requirements.txt` - зависимости Python
- `Procfile` - команда запуска для Railway
- `railway.json` - конфигурация Railway

## Миграция данных из JSON в PostgreSQL

Если у вас есть старые данные в `leaderboard_db.json`, вы можете мигрировать их в PostgreSQL:

1. Убедитесь, что PostgreSQL запущен и `DATABASE_URL` настроен
2. Запустите скрипт миграции (можно создать отдельный скрипт `migrate_from_json.py`):
```python
import json
from db import init_db, create_tables, get_db_connection

init_db()
create_tables()

with open('leaderboard_db.json', 'r') as f:
    data = json.load(f)

with get_db_connection() as conn:
    with conn.cursor() as cur:
        for user_id, user_data in data.items():
            cur.execute("""
                INSERT INTO users (user_id, completed_roles, current_level_index, total_score, best_scores)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    completed_roles = EXCLUDED.completed_roles,
                    current_level_index = EXCLUDED.current_level_index,
                    total_score = EXCLUDED.total_score,
                    best_scores = EXCLUDED.best_scores;
            """, (
                user_id,
                json.dumps(user_data.get('completed_roles', [])),
                user_data.get('current_level_index', 0),
                user_data.get('total_score', 0),
                json.dumps(user_data.get('best_scores', {}))
            ))
```

