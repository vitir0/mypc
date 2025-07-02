import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ['8004274832:AAG2gDVDp_dQLllcVBIYVB-0WTJ1Ts4CtCU']
PORT = int(os.environ.get('PORT', 5000))
WEBHOOK_URL = os.environ['WEBHOOK_URL'] + '/'  # Важно: добавить слэш в конце

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(f"Привет, {user.mention_html()}! 👋\nБот работает на Render!")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    # Установка вебхука
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
        secret_token=os.environ.get('SECRET_TOKEN', 'DEFAULT_SECRET')
    )

if __name__ == "__main__":
    main()
