-- SQL схема для базы данных лидерборда
-- Этот файл создается автоматически при первом запуске через db.py
-- Но можно использовать для ручной миграции или проверки

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    completed_roles JSONB DEFAULT '[]'::jsonb,
    current_level_index INTEGER DEFAULT 0,
    total_score NUMERIC(10, 2) DEFAULT 0,
    best_scores JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индекс для быстрого поиска по total_score (для лидерборда)
CREATE INDEX IF NOT EXISTS idx_users_total_score 
ON users(total_score DESC);

