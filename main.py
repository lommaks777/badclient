# main.py
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler
)

# Импорт конфигурации и данных
from config import TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, LLM_MODEL
from roles_data import ROLES, SYSTEM_PROMPT_TEMPLATE

# Импорт OpenAI (или другого LLM)
from openai import OpenAI 

# Настройка клиента OpenAI
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# --- КОНСТАНТЫ СОСТОЯНИЙ ДЛЯ ConversationHandler ---
SELECTING_ROLE, IN_DIALOG = range(2)
DB_FILE = 'leaderboard_db.json'

# --- ФУНКЦИИ ХРАНЕНИЯ ДАННЫХ ---
def load_db():
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_db(db):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

# --- LLM ИНТЕГРАЦИЯ ---
def get_llm_response(user_id, role_key, message_text):
    """
    Основная функция для запроса к LLM.
    Должна использовать историю диалога, хранящуюся в user_data.
    """
    # Загрузка данных роли
    role = ROLES[role_key]
    
    # Формирование системного промта
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(**role)
    
    # !!! Здесь будет логика для добавления ИСТОРИИ ДИАЛОГА !!!
    # Пока что заглушка:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message_text}
    ]
    
    try:
        # !!! Асинхронный вызов LLM (требует refactor на aiogram или async в python-telegram-bot)
        # Для простоты первого шага оставим синхронно:
        response = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка LLM: {e}")
        return "Извините, сейчас я немного занят... Кажется, у меня проблемы с памятью. Попробуйте еще раз."

# --- ОБРАБОТЧИКИ TELEGRAM ---
async def start(update: Update, context):
    """Отправляет приветственное сообщение и кнопки выбора роли."""
    keyboard = []
    for key, role in ROLES.items():
        # Кнопка для выбора роли
        keyboard.append([InlineKeyboardButton(f"{role['name']} ({role['level_description']})", callback_data=f"start_role_{key}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Привет! Я твой тренажер 'Вредный Клиент'.\n"
        "Выбери, с кем хочешь потренироваться сегодня:",
        reply_markup=reply_markup
    )
    return SELECTING_ROLE

async def select_role_callback(update: Update, context):
    """Обработка выбора роли и начало диалога."""
    query = update.callback_query
    await query.answer()
    
    role_key = query.data.split('_')[2]
    role = ROLES[role_key]
    
    # Сохраняем состояние диалога
    context.user_data['dialog'] = []
    context.user_data['role_key'] = role_key
    context.user_data['message_count'] = 0
    
    # Отправляем первый запрос в LLM, чтобы он начал диалог
    initial_message = f"Начинаем диалог с {role['name']}. Я сыграю роль клиента. Твоя очередь."
    
    # Используем get_llm_response для первого шага клиента
    # В идеале нужно сделать отдельный запрос для первого хода клиента
    # Но для старта можно и так:
    client_start_message = get_llm_response(query.from_user.id, role_key, initial_message)
    
    await query.edit_message_text(
        text=f"*** Вы выбрали: {role['name']} ***\n\n"
             f"Твоя цель: убедить клиента записаться.\n\n"
             f"💬 Клиент: {client_start_message}",
        reply_markup=None
    )
    
    # Сохраняем первый ход клиента в историю
    context.user_data['dialog'].append({"role": "client", "content": client_start_message})
    
    return IN_DIALOG

async def handle_message(update: Update, context):
    """Обработка сообщения во время диалога."""
    user_text = update.message.text
    user_id = update.message.from_user.id
    role_key = context.user_data.get('role_key')
    
    context.user_data['message_count'] += 1
    
    # Добавляем сообщение ученика в историю
    context.user_data['dialog'].append({"role": "user", "content": user_text})
    
    # Получаем ответ от LLM
    llm_response = get_llm_response(user_id, role_key, user_text) # Простая реализация
    
    # !!! Здесь должна быть логика ПРОВЕРКИ УСПЕХА по llm_response !!!
    # Пока что заглушка:
    if "Окей, договорились" in llm_response:
        # Успех!
        await update.message.reply_text(f"🥳 ПОБЕДА!\n\n{llm_response}\n\n[Здесь будет анализ и подсчет баллов]")
        return ConversationHandler.END # Завершаем диалог
    
    # Добавляем ответ клиента в историю
    context.user_data['dialog'].append({"role": "client", "content": llm_response})
    
    await update.message.reply_text(f"💬 Клиент: {llm_response}")
    return IN_DIALOG

async def fallback(update: Update, context):
    """Заглушка для неизвестных команд."""
    await update.message.reply_text("Извините, я вас не понял. Используйте /start для начала.")
    return ConversationHandler.END

# --- ОСНОВНАЯ ФУНКЦИЯ BOT RUNNER ---
def main():
    """Запуск бота."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Создание ConversationHandler для управления состояниями
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ROLE: [CallbackQueryHandler(select_role_callback, pattern='^start_role_')],
            IN_DIALOG: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.ALL, fallback)],
        allow_reentry=True
    )
    
    application.add_handler(conv_handler)
    
    # Добавить позже: CommandHandler('top', show_leaderboard)
    
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

