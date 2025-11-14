# main.py
import json
import re
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
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

# Порядок прохождения уровней
ROLE_ORDER = ["dmitry", "irina", "max", "oleg", "victoria"]

# --- ФУНКЦИИ ХРАНЕНИЯ ДАННЫХ ---
def load_db():
    """Загрузка базы данных пользователей."""
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_db(db):
    """Сохранение базы данных пользователей."""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

def get_user_progress(user_id):
    """
    Получение или инициализация данных пользователя.
    Возвращает словарь с ключами:
    - completed_roles: список пройденных ролей
    - current_level_index: индекс следующей роли для прохождения
    - total_score: общий счет пользователя
    - best_scores: лучшие счета по каждой роли
    """
    db = load_db()
    user_id_str = str(user_id)
    
    if user_id_str not in db:
        db[user_id_str] = {
            "completed_roles": [],
            "current_level_index": 0,
            "total_score": 0,
            "best_scores": {}
        }
        save_db(db)
    
    return db[user_id_str]

def update_user_progress(user_id, role_key, score):
    """Обновление прогресса пользователя после победы."""
    db = load_db()
    user_id_str = str(user_id)
    user_data = get_user_progress(user_id)
    
    # Добавляем роль в список пройденных, если еще не пройдена
    if role_key not in user_data["completed_roles"]:
        user_data["completed_roles"].append(role_key)
        # Обновляем индекс следующего уровня
        if user_data["current_level_index"] < len(ROLE_ORDER) - 1:
            user_data["current_level_index"] += 1
    
    # Обновляем лучший счет для роли
    if role_key not in user_data["best_scores"] or score > user_data["best_scores"][role_key]:
        user_data["best_scores"][role_key] = score
    
    # Обновляем общий счет
    user_data["total_score"] = sum(user_data["best_scores"].values())
    
    db[user_id_str] = user_data
    save_db(db)
    
    return user_data

# --- LLM ИНТЕГРАЦИЯ ---
# Executor для синхронных вызовов OpenAI в асинхронном контексте
executor = ThreadPoolExecutor(max_workers=2)

def get_llm_response(role_key, dialog_history):
    """
    Основная функция для запроса к LLM с полной историей диалога.
    
    Args:
        role_key: ключ роли из ROLES
        dialog_history: список сообщений в формате [{"role": "user"/"client", "content": "..."}, ...]
    
    Returns:
        Ответ от LLM
    """
    # Загрузка данных роли
    role = ROLES[role_key]
    
    # Формирование системного промта
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(**role)
    
    # Формирование списка сообщений для API
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    
    # Преобразование истории диалога
    for message in dialog_history:
        # 'client' в user_data соответствует 'assistant' в API OpenAI
        api_role = 'assistant' if message['role'] == 'client' else 'user'
        messages.append({
            "role": api_role,
            "content": message['content']
        })
    
    try:
        response = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка LLM: {e}")
        return "Извините, сейчас я немного занят... Кажется, у меня проблемы с памятью. Попробуйте еще раз."

async def send_typing_periodically(chat_id, bot, duration=60):
    """Периодически отправляет индикатор печати пока идет обработка."""
    start_time = time.time()
    while (time.time() - start_time) < duration:
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(3)  # Telegram требует обновлять каждые 3-5 секунд
        except Exception as e:
            print(f"Ошибка при отправке typing indicator: {e}")
            break

async def get_llm_response_async(role_key, dialog_history, chat_id=None, bot=None):
    """Асинхронная обертка для get_llm_response с индикатором печати."""
    # Запускаем задачу для периодической отправки typing indicator
    typing_task = None
    if chat_id and bot:
        typing_task = asyncio.create_task(send_typing_periodically(chat_id, bot))
    
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(executor, get_llm_response, role_key, dialog_history)
        return result
    finally:
        # Отменяем задачу typing indicator после получения ответа
        if typing_task:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

def split_long_message(text, max_length=4000):
    """Разбивает длинное сообщение на части для Telegram (лимит 4096 символов)."""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current_part = ""
    
    # Разбиваем по абзацам
    paragraphs = text.split('\n\n')
    
    for para in paragraphs:
        if len(current_part) + len(para) + 2 <= max_length:
            current_part += para + '\n\n'
        else:
            if current_part:
                parts.append(current_part.strip())
            # Если параграф сам по себе длиннее лимита, разбиваем по предложениям
            if len(para) > max_length:
                sentences = para.split('. ')
                for sent in sentences:
                    if len(current_part) + len(sent) + 2 <= max_length:
                        current_part += sent + '. '
                    else:
                        if current_part:
                            parts.append(current_part.strip())
                        current_part = sent + '. '
            else:
                current_part = para + '\n\n'
    
    if current_part:
        parts.append(current_part.strip())
    
    return parts if parts else [text[:max_length]]

def calculate_score(role_key, message_count, llm_response):
    """
    Расчет очков на основе формулы:
    Счет = Множитель Уровня × (Базовый балл от LLM / Количество Сообщений Ученика)
    
    Args:
        role_key: ключ роли
        message_count: количество сообщений ученика
        llm_response: ответ от LLM (может содержать анализ и оценку)
    
    Returns:
        dict с ключами: base_score, final_score, achievement
    """
    role = ROLES[role_key]
    multiplier = role['multiplier']
    
    # Парсинг базовой оценки из ответа LLM (0-20 баллов)
    base_score = 10  # Значение по умолчанию
    
    # Ищем оценку в ответе LLM
    score_patterns = [
        r'(\d+)\s*балл',
        r'оценк[аиуе]\s*[:\-]?\s*(\d+)',
        r'(\d+)\s*из\s*20',
        r'(\d+)/20',
        r'оцен[аиуе]\s*(\d+)',
    ]
    
    for pattern in score_patterns:
        match = re.search(pattern, llm_response, re.IGNORECASE)
        if match:
            try:
                parsed_score = int(match.group(1))
                if 0 <= parsed_score <= 20:
                    base_score = parsed_score
                    break
            except ValueError:
                continue
    
    # Расчет финального счета
    if message_count == 0:
        message_count = 1  # Избегаем деления на ноль
    
    final_score = multiplier * (base_score / message_count)
    
    # Определение достижения
    achievement = None
    if base_score >= 18:
        achievement = "🌟 Мастер переговоров"
    elif base_score >= 15:
        achievement = "💎 Профессионал"
    elif base_score >= 12:
        achievement = "⭐ Хорошая работа"
    elif base_score >= 8:
        achievement = "👍 Неплохо"
    
    return {
        "base_score": base_score,
        "final_score": round(final_score, 2),
        "achievement": achievement
    }

# --- ОБРАБОТЧИКИ TELEGRAM ---
async def start(update: Update, context):
    """Отправляет приветственное сообщение и кнопки выбора роли с учетом прогресса."""
    try:
        user_id = update.message.from_user.id
        user_progress = get_user_progress(user_id)
        
        keyboard = []
        
        # Функция для создания короткого названия кнопки
        def get_short_button_text(role, is_next=False):
            """Создает короткий текст для кнопки, чтобы избежать обрезания."""
            icon = "▶️" if is_next else "🔄"
            # Извлекаем номер уровня и короткое описание
            level_desc = role['level_description']
            # Ищем номер уровня (например, "Уровень 1", "Уровень 2")
            level_match = re.search(r'Уровень\s+(\d+)', level_desc)
            level_num = level_match.group(1) if level_match else ""
            
            # Извлекаем короткое описание (до первой точки или кавычки)
            short_desc = level_desc.split('.')[0].split("'")[0].strip()
            if len(short_desc) > 25:
                short_desc = short_desc[:22] + "..."
            
            if level_num:
                return f"{icon} {role['name']} (Ур.{level_num})"
            else:
                return f"{icon} {role['name']}"
        
        # Показываем текущий (следующий) уровень для прохождения
        current_index = user_progress["current_level_index"]
        if current_index < len(ROLE_ORDER):
            role_key = ROLE_ORDER[current_index]
            if role_key in ROLES:
                role = ROLES[role_key]
                keyboard.append([
                    InlineKeyboardButton(
                        get_short_button_text(role, is_next=True),
                        callback_data=f"start_role_{role_key}"
                    )
                ])
        
        # Показываем кнопки "Повторить" для пройденных уровней
        completed_roles = user_progress.get("completed_roles", [])
        if completed_roles:
            keyboard.append([InlineKeyboardButton("━━━ Повторить уровень ━━━", callback_data="separator")])
            # Показываем все пройденные уровни в порядке прохождения
            for role_key in ROLE_ORDER:
                if role_key in completed_roles and role_key in ROLES:
                    role = ROLES[role_key]
                    keyboard.append([
                        InlineKeyboardButton(
                            get_short_button_text(role, is_next=False),
                            callback_data=f"start_role_{role_key}"
                        )
                    ])
        
        # Если нет кнопок, создаем хотя бы одну для первого уровня
        if not keyboard:
            if ROLE_ORDER and ROLE_ORDER[0] in ROLES:
                role = ROLES[ROLE_ORDER[0]]
                keyboard.append([
                    InlineKeyboardButton(
                        get_short_button_text(role, is_next=True),
                        callback_data=f"start_role_{ROLE_ORDER[0]}"
                    )
                ])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Формируем сообщение с прогрессом
        progress_text = f"👋 Привет! Я твой тренажер 'Вредный Клиент'.\n\n"
        
        if user_progress["total_score"] > 0:
            progress_text += f"📊 Твой общий счет: {user_progress['total_score']:.2f} баллов\n"
            progress_text += f"✅ Пройдено уровней: {len(completed_roles)}/{len(ROLE_ORDER)}\n\n"
        
        if current_index < len(ROLE_ORDER):
            progress_text += f"🎯 Следующий уровень:\n"
        else:
            progress_text += f"🎉 Поздравляю! Ты прошел все уровни!\n"
        
        progress_text += "\nВыбери уровень для тренировки:"
        
        await update.message.reply_text(
            progress_text,
            reply_markup=reply_markup
        )
        return SELECTING_ROLE
    except Exception as e:
        print(f"Ошибка в функции start: {e}")
        import traceback
        traceback.print_exc()
        try:
            await update.message.reply_text(
                f"Произошла ошибка: {str(e)}\n\nПопробуйте еще раз или используйте /start"
            )
        except:
            pass
        return ConversationHandler.END

async def select_role_callback(update: Update, context):
    """Обработка выбора роли и начало диалога."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "separator":
        return SELECTING_ROLE
    
    role_key = query.data.split('_')[2]
    role = ROLES[role_key]
    
    # Сохраняем состояние диалога
    context.user_data['dialog'] = []
    context.user_data['role_key'] = role_key
    context.user_data['message_count'] = 0
    
    # Формируем начальное сообщение для первого хода клиента
    initial_prompt = "Начинаем диалог. Ты играешь роль клиента. Начни диалог с первого сообщения, как будто ты только что увидел предложение о массаже или тебе написали."
    
    # Показываем индикатор печати
    await query.message.chat.send_action(ChatAction.TYPING)
    
    # Первый запрос к LLM для начала диалога
    initial_dialog = [{"role": "user", "content": initial_prompt}]
    client_start_message = await get_llm_response_async(
        role_key, 
        initial_dialog,
        chat_id=query.message.chat_id,
        bot=context.bot
    )
    
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
    
    if not role_key:
        await update.message.reply_text("Ошибка: роль не выбрана. Используйте /start")
        return ConversationHandler.END
    
    context.user_data['message_count'] += 1
    
    # Добавляем сообщение ученика в историю
    context.user_data['dialog'].append({"role": "user", "content": user_text})
    
    # Показываем индикатор печати
    await update.message.chat.send_action(ChatAction.TYPING)
    
    # Получаем ответ от LLM с полной историей диалога (асинхронно)
    try:
        llm_response = await get_llm_response_async(
            role_key, 
            context.user_data['dialog'],
            chat_id=update.message.chat_id,
            bot=context.bot
        )
    except Exception as e:
        print(f"Ошибка при получении ответа LLM: {e}")
        await update.message.reply_text("Извините, произошла ошибка при обработке запроса. Попробуйте еще раз.")
        return IN_DIALOG
    
    # Проверка на победу
    victory_phrases = [
        "Окей, договорились",
        "окей, договорились",
        "Хорошо, договорились",
        "хорошо, договорились",
        "Договорились",
        "договорились",
        "Согласен",
        "согласен",
        "Согласна",
        "согласна"
    ]
    
    is_victory = any(phrase in llm_response for phrase in victory_phrases)
    
    if is_victory:
        # Победа! Рассчитываем очки и обновляем прогресс
        message_count = context.user_data.get('message_count', 1)
        score_data = calculate_score(role_key, message_count, llm_response)
        
        # Обновляем прогресс пользователя
        user_progress = update_user_progress(user_id, role_key, score_data['final_score'])
        
        # Формируем сообщение о победе
        victory_message = f"🥳 ПОБЕДА!\n\n"
        victory_message += f"{llm_response}\n\n"
        victory_message += f"━━━━━━━━━━━━━━━━━━━━\n"
        victory_message += f"📊 Результаты:\n"
        victory_message += f"• Базовая оценка: {score_data['base_score']}/20\n"
        victory_message += f"• Финальный счет: {score_data['final_score']:.2f} баллов\n"
        victory_message += f"• Сообщений отправлено: {message_count}\n"
        
        if score_data['achievement']:
            victory_message += f"• Достижение: {score_data['achievement']}\n"
        
        victory_message += f"\n📈 Прогресс:\n"
        victory_message += f"• Пройдено уровней: {len(user_progress['completed_roles'])}/{len(ROLE_ORDER)}\n"
        victory_message += f"• Общий счет: {user_progress['total_score']:.2f} баллов\n"
        
        # Проверяем, есть ли следующий уровень
        if user_progress['current_level_index'] < len(ROLE_ORDER):
            next_role_key = ROLE_ORDER[user_progress['current_level_index']]
            next_role = ROLES[next_role_key]
            victory_message += f"\n🎯 Следующий уровень: {next_role['name']}\n"
        else:
            victory_message += f"\n🎉 Поздравляю! Ты прошел все уровни!\n"
        
        victory_message += f"\nИспользуй /start для продолжения."
        
        # Разбиваем длинное сообщение на части если нужно
        message_parts = split_long_message(victory_message)
        
        try:
            # Отправляем первую часть
            await update.message.reply_text(message_parts[0])
            
            # Отправляем остальные части если есть
            for part in message_parts[1:]:
                await update.message.reply_text(part)
        except Exception as e:
            print(f"Ошибка при отправке сообщения о победе: {e}")
            # Отправляем упрощенное сообщение
            try:
                await update.message.reply_text(
                    f"🥳 ПОБЕДА!\n\n"
                    f"📊 Результаты:\n"
                    f"• Базовая оценка: {score_data['base_score']}/20\n"
                    f"• Финальный счет: {score_data['final_score']:.2f} баллов\n"
                    f"• Пройдено уровней: {len(user_progress['completed_roles'])}/{len(ROLE_ORDER)}\n\n"
                    f"Используй /start для продолжения."
                )
            except Exception as e2:
                print(f"Критическая ошибка при отправке сообщения: {e2}")
        
        # Очищаем состояние диалога
        context.user_data.clear()
        
        return ConversationHandler.END
    
    # Добавляем ответ клиента в историю
    context.user_data['dialog'].append({"role": "client", "content": llm_response})
    
    # Разбиваем длинный ответ на части если нужно
    client_message = f"💬 Клиент: {llm_response}"
    message_parts = split_long_message(client_message)
    
    try:
        await update.message.reply_text(message_parts[0])
        # Отправляем остальные части если есть
        for part in message_parts[1:]:
            await update.message.reply_text(part)
    except Exception as e:
        print(f"Ошибка при отправке ответа клиента: {e}")
        await update.message.reply_text("💬 Клиент: [Сообщение слишком длинное, попробуйте продолжить диалог]")
    
    return IN_DIALOG

async def fallback(update: Update, context):
    """Заглушка для неизвестных команд."""
    await update.message.reply_text("Извините, я вас не понял. Используйте /start для начала.")
    return ConversationHandler.END

# --- ОБРАБОТЧИК ОШИБОК ---
async def error_handler(update: object, context):
    """Обработчик ошибок."""
    print(f"Ошибка при обработке update: {update}")
    import traceback
    traceback.print_exc()

# --- ОСНОВНАЯ ФУНКЦИЯ BOT RUNNER ---
def main():
    """Запуск бота."""
    try:
        print("Инициализация бота...")
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Добавляем обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Создание ConversationHandler для управления состояниями
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                SELECTING_ROLE: [CallbackQueryHandler(select_role_callback, pattern='^start_role_|^separator$')],
                IN_DIALOG: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            },
            fallbacks=[CommandHandler("start", start), MessageHandler(filters.ALL, fallback)],
            allow_reentry=True
        )
        
        application.add_handler(conv_handler)
        
        print("Бот запущен и готов к работе...")
        print(f"Проверка: ROLE_ORDER = {ROLE_ORDER}")
        print(f"Проверка: ROLES keys = {list(ROLES.keys())}")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as e:
        print(f"Критическая ошибка при запуске бота: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
