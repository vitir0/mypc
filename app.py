import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get('8004274832:AAG2gDVDp_dQLllcVBIYVB-0WTJ1Ts4CtCU')
PORT = int(os.environ.get('PORT', 5000))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(f"Привет, {user.mention_html()}! 👋\nЯ успешно запущен на Render.com!")

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    
    # Запуск веб-сервера для Render
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=os.environ.get('WEBHOOK_URL'),
        secret_token='RANDOM_SECRET'
    )

if __name__ == "__main__":
    main()
