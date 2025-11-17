# db.py
"""
Модуль для работы с PostgreSQL базой данных.
"""
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager

# Глобальный пул соединений
_pool = None

def init_db():
    """Инициализация пула соединений с базой данных."""
    global _pool
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        raise ValueError("DATABASE_URL не установлен. Установите переменную окружения.")
    
    # Парсим DATABASE_URL для совместимости с Railway
    # Railway предоставляет DATABASE_URL в формате: postgresql://user:password@host:port/dbname
    try:
        _pool = SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url
        )
        print("База данных инициализирована успешно")
    except Exception as e:
        print(f"Ошибка при инициализации базы данных: {e}")
        raise

@contextmanager
def get_db_connection():
    """Контекстный менеджер для получения соединения с БД."""
    global _pool
    if _pool is None:
        init_db()
    
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)

def create_tables():
    """Создание таблиц в базе данных."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(255) PRIMARY KEY,
                    completed_roles JSONB DEFAULT '[]'::jsonb,
                    current_level_index INTEGER DEFAULT 0,
                    total_score NUMERIC(10, 2) DEFAULT 0,
                    best_scores JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Создаем индекс для быстрого поиска по total_score (для лидерборда)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_total_score 
                ON users(total_score DESC);
            """)
            
            print("Таблицы созданы успешно")

def get_user_progress(user_id):
    """
    Получение или инициализация данных пользователя.
    Возвращает словарь с ключами:
    - completed_roles: список пройденных ролей
    - current_level_index: индекс следующей роли для прохождения
    - total_score: общий счет пользователя
    - best_scores: лучшие счета по каждой роли
    """
    user_id_str = str(user_id)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Проверяем, существует ли пользователь
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id_str,))
            user_data = cur.fetchone()
            
            if user_data is None:
                # Создаем нового пользователя
                cur.execute("""
                    INSERT INTO users (user_id, completed_roles, current_level_index, total_score, best_scores)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *;
                """, (
                    user_id_str,
                    json.dumps([]),
                    0,
                    0,
                    json.dumps({})
                ))
                user_data = cur.fetchone()
            
            # Преобразуем JSONB в Python объекты
            result = {
                "user_id": user_id_str,
                "completed_roles": user_data["completed_roles"] if isinstance(user_data["completed_roles"], list) else json.loads(user_data["completed_roles"]),
                "current_level_index": user_data["current_level_index"],
                "total_score": float(user_data["total_score"]),
                "best_scores": user_data["best_scores"] if isinstance(user_data["best_scores"], dict) else json.loads(user_data["best_scores"])
            }
            
            # Проверяем и выполняем миграцию данных если нужно
            migrate_user_data(result)
            
            return result

def update_user_progress(user_id, role_key, score):
    """Обновление прогресса пользователя после победы."""
    # Импортируем здесь, чтобы избежать циклических импортов
    ROLE_ORDER = ["dmitry", "irina", "max", "oleg", "victoria"]
    
    user_id_str = str(user_id)
    user_data = get_user_progress(user_id)
    
    # Добавляем роль в список пройденных, если еще не пройдена
    completed_roles = user_data["completed_roles"].copy()
    if role_key not in completed_roles:
        completed_roles.append(role_key)
    
    # Обновляем индекс следующего уровня
    current_level_index = user_data["current_level_index"]
    if role_key not in user_data["completed_roles"]:
        if current_level_index < len(ROLE_ORDER) - 1:
            current_level_index += 1
    
    # Обновляем лучший счет для роли
    best_scores = user_data["best_scores"].copy()
    if role_key not in best_scores or score > best_scores[role_key]:
        best_scores[role_key] = score
    
    # Обновляем общий счет
    total_score = sum(best_scores.values())
    
    # Сохраняем в БД
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET completed_roles = %s,
                    current_level_index = %s,
                    total_score = %s,
                    best_scores = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s;
            """, (
                json.dumps(completed_roles),
                current_level_index,
                total_score,
                json.dumps(best_scores),
                user_id_str
            ))
    
    # Возвращаем обновленные данные
    return {
        "completed_roles": completed_roles,
        "current_level_index": current_level_index,
        "total_score": total_score,
        "best_scores": best_scores
    }

def get_leaderboard(limit=10):
    """
    Получение лидерборда пользователей.
    Возвращает список пользователей, отсортированных по total_score.
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT user_id, total_score, completed_roles, best_scores
                FROM users
                WHERE total_score > 0
                ORDER BY total_score DESC
                LIMIT %s;
            """, (limit,))
            
            results = cur.fetchall()
            
            leaderboard = []
            for row in results:
                leaderboard.append({
                    "user_id": row["user_id"],
                    "total_score": float(row["total_score"]),
                    "completed_roles": row["completed_roles"] if isinstance(row["completed_roles"], list) else json.loads(row["completed_roles"]),
                    "best_scores": row["best_scores"] if isinstance(row["best_scores"], dict) else json.loads(row["best_scores"])
                })
            
            return leaderboard

def migrate_user_data(user_data):
    """
    Миграция старых ключей ролей на новые.
    Эта функция вызывается при первом обращении к данным пользователя.
    """
    # Импортируем здесь, чтобы избежать циклических импортов
    ROLE_ORDER = ["dmitry", "irina", "max", "oleg", "victoria"]
    
    # Маппинг старых ключей на новые
    old_to_new = {
        "svetlana": "dmitry",
        "marina": "irina",
    }
    
    old_roles = ["svetlana", "marina", "irina", "oleg", "victoria"]
    
    migrated = False
    completed_roles = user_data.get("completed_roles", []).copy()
    best_scores = user_data.get("best_scores", {}).copy()
    
    # Мигрируем completed_roles
    if completed_roles:
        # Проверяем, были ли пройдены все старые 5 уровней
        had_all_old = all(role in completed_roles for role in old_roles)
        
        if had_all_old:
            # Если были пройдены все старые уровни, считаем все новые уровни пройденными
            completed_roles = ROLE_ORDER.copy()
            migrated = True
        else:
            # Иначе мигрируем по одному
            new_completed = []
            for role_key in completed_roles:
                if role_key in old_to_new:
                    new_key = old_to_new[role_key]
                    if new_key not in new_completed:
                        new_completed.append(new_key)
                    migrated = True
                elif role_key in ROLE_ORDER:
                    if role_key not in new_completed:
                        new_completed.append(role_key)
            completed_roles = new_completed
    
    # Мигрируем best_scores
    if best_scores:
        new_best_scores = {}
        for role_key, score in best_scores.items():
            if role_key in old_to_new:
                new_key = old_to_new[role_key]
                if new_key not in new_best_scores or score > new_best_scores[new_key]:
                    new_best_scores[new_key] = score
                migrated = True
            elif role_key in ROLE_ORDER:
                if role_key not in new_best_scores or score > new_best_scores[role_key]:
                    new_best_scores[role_key] = score
        best_scores = new_best_scores
    
    # Пересчитываем total_score
    if best_scores:
        total_score = sum(best_scores.values())
    else:
        total_score = 0
    
    # Обновляем current_level_index если нужно
    completed_count = len(completed_roles)
    if completed_count >= len(ROLE_ORDER):
        current_level_index = len(ROLE_ORDER)
    else:
        current_level_index = completed_count
    
    if migrated:
        # Сохраняем мигрированные данные
        user_id_str = user_data.get("user_id")
        if user_id_str:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE users 
                        SET completed_roles = %s,
                            current_level_index = %s,
                            total_score = %s,
                            best_scores = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = %s;
                    """, (
                        json.dumps(completed_roles),
                        current_level_index,
                        total_score,
                        json.dumps(best_scores),
                        user_id_str
                    ))
    
    return migrated

