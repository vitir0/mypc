import os
import json
import uuid
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

app = Flask(__name__)

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.environ.get('TOKEN')  # Токен из переменных окружения Render
SECRET_KEY = os.environ.get('SECRET_KEY')  # Секретный ключ из переменных окружения
PORT = int(os.environ.get('PORT', 5000))
# ========================

bot = Bot(token=TOKEN)
clients = {}
pending_commands = {}

# Меню управления (упрощенное)
KEYBOARD_LAYOUT = [
    [InlineKeyboardButton("📸 Скриншот", callback_data='screenshot')],
    [InlineKeyboardButton("🖼 Фото на экран", callback_data='play_photo'),
     InlineKeyboardButton("🎥 Видео на экран", callback_data='play_video')],
    [InlineKeyboardButton("❌ Alt+F4", callback_data='altf4')],
    [InlineKeyboardButton("🔄 Перезагрузить", callback_data='reboot'),
     InlineKeyboardButton("⏹ Выключить", callback_data='shutdown')]
]

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
    
    client_ip = request.remote_addr
    commands = pending_commands.get(client_ip, [])
    pending_commands[client_ip] = []
    return jsonify(commands)

@app.route('/complete', methods=['POST'])
def complete_command():
    """Подтверждение выполнения команды"""
    data = request.json
    if data.get('key') != SECRET_KEY:
        return jsonify({'status': 'unauthorized'}), 401
    
    client_ip = request.remote_addr
    command_id = data.get('command_id')
    
    if client_ip in pending_commands:
        pending_commands[client_ip] = [
            cmd for cmd in pending_commands[client_ip] 
            if cmd.get('id') != command_id
        ]
    
    return jsonify({'status': 'ok'})

def send_menu(chat_id):
    """Отправка меню с кнопками"""
    bot.send_message(
        chat_id=chat_id,
        text="🔒 Управление ноутбуком\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(KEYBOARD_LAYOUT)
    )

def button_handler(update: Update, context):
    """Обработчик нажатий кнопок"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    chat_id = query.message.chat_id
    
    try:
        client_id = next(iter(clients.keys()), None)
        
        if not client_id:
            bot.send_message(chat_id, "⚠️ Нет подключенных устройств")
            return
        
        if data == 'screenshot':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'screenshot',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            bot.send_message(chat_id, "📸 Запрошен скриншот...")
        
        elif data in ('play_video', 'play_photo'):
            media_type = 'video' if data == 'play_video' else 'image'
            bot.send_message(chat_id, f"📹 Отправьте {'видео' if media_type == 'video' else 'фото'} файл...")
            context.user_data['awaiting_media'] = {'type': media_type, 'client': client_id}
        
        elif data == 'altf4':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'altf4',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            bot.send_message(chat_id, "✅ Команда Alt+F4 отправлена")
        
        elif data == 'reboot':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'reboot',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            bot.send_message(chat_id, "🔄 Команда перезагрузки отправлена")
        
        elif data == 'shutdown':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'shutdown',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            bot.send_message(chat_id, "⏹ Команда выключения отправлена")
        
        bot.answer_callback_query(query.id)
    
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка: {str(e)}")

def media_handler(update: Update, context):
    """Обработчик медиафайлов"""
    media_info = context.user_data.get('awaiting_media')
    if not media_info:
        return
    
    chat_id = update.message.chat_id
    client_id = media_info.get('client')
    media_type = media_info.get('type')
    
    try:
        file_id = None
        
        if media_type == 'image' and update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif media_type == 'video' and update.message.video:
            file_id = update.message.video.file_id
        
        if file_id:
            file = bot.get_file(file_id)
            command = {
                'id': str(uuid.uuid4()),
                'type': 'media',
                'media_type': media_type,
                'url': file.file_path,
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            bot.send_message(chat_id, f"✅ {'Фото' if media_type == 'image' else 'Видео'} отправлено на устройство")
        
        del context.user_data['awaiting_media']
        send_menu(chat_id)
    
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка обработки медиа: {str(e)}")

def start(update: Update, context):
    """Обработчик команды /start"""
    send_menu(update.message.chat_id)

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

def run_bot():
    """Запуск Telegram бота"""
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.photo | Filters.video, media_handler))
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    # Запускаем очистку клиентов в фоне
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Запускаем бота в отдельном потоке
    threading.Thread(target=run_bot, daemon=True).start()
    
    # Запускаем Flask сервер
    app.run(host='0.0.0.0', port=PORT)
