import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import yt_dlp

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Замените на ваш токен от BotFather
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

def get_video_formats(url):
    """Получает доступные форматы видео с YouTube"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return None, "Не удалось получить информацию о видео"
            
            # Фильтруем только видео с аудио
            formats = []
            seen_quality = set()
            
            for fmt in info.get('formats', []):
                if fmt.get('vcodec') != 'none' and fmt.get('acodest') != 'none':
                    quality = fmt.get('format_note', '')
                    if not quality:
                        quality = f"{fmt.get('height', 'unknown')}p"
                    
                    if quality and quality not in seen_quality:
                        seen_quality.add(quality)
                        formats.append({
                            'format_id': fmt.get('format_id'),
                            'quality': quality,
                            'ext': fmt.get('ext', 'mp4'),
                            'filesize': fmt.get('filesize', 0)
                        })
            
            # Сортируем по качеству (по высоте)
            formats.sort(key=lambda x: int(x['quality'].replace('p', '').replace('k', '000')) if x['quality'][:-1].isdigit() else 0, reverse=True)
            
            return info, formats[:10]  # Возвращаем топ-10 форматов
            
    except Exception as e:
        return None, f"Ошибка: {str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Привет! Я бот для скачивания видео с YouTube.\n\n"
        "📌 Просто отправьте мне ссылку на YouTube видео,\n"
        "и я предложу выбрать качество для скачивания."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ссылок на YouTube"""
    text = update.message.text
    
    # Простая проверка на YouTube ссылку
    if not ('youtube.com' in text or 'youtu.be' in text):
        await update.message.reply_text(
            "❌ Это не похоже на ссылку YouTube. Пожалуйста, отправьте корректную ссылку."
        )
        return
    
    await update.message.reply_text("⏳ Обрабатываю видео, пожалуйста подождите...")
    
    info, formats = get_video_formats(text)
    
    if not formats:
        await update.message.reply_text(f"❌ Ошибка: {formats if isinstance(formats, str) else 'Не удалось получить форматы'}")
        return
    
    # Создаем клавиатуру с вариантами качества
    keyboard = []
    for fmt in formats:
        size_mb = round(fmt['filesize'] / (1024 * 1024), 1) if fmt['filesize'] else '?'
        btn_text = f"{fmt['quality']} ({fmt['ext']}) - {size_mb} MB"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"download_{fmt['format_id']}_{text}")])
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    video_title = info.get('title', 'Без названия') if info else 'Неизвестно'
    
    await update.message.reply_text(
        f"🎬 **{video_title}**\n\nВыберите качество для скачивания:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки выбора качества"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Скачивание отменено.")
        return
    
    if query.data.startswith("download_"):
        parts = query.data.split('_', 2)
        if len(parts) < 3:
            await query.edit_message_text("❌ Ошибка формата запроса.")
            return
        
        format_id = parts[1]
        url = parts[2]
        
        await query.edit_message_text("⏳ Скачиваю видео, пожалуйста подождите...")
        
        try:
            # Создаем временную директорию
            temp_dir = f"downloads_{query.message.chat_id}"
            os.makedirs(temp_dir, exist_ok=True)
            
            ydl_opts = {
                'format': f"{format_id}+bestaudio[ext=m4a]/best",
                'outtmpl': f'{temp_dir}/%(title)s.%(ext)s',
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Если файл был сконвертирован/объединен, имя может измениться
                if not os.path.exists(filename):
                    base = os.path.splitext(filename)[0]
                    for ext in ['mp4', 'mkv', 'webm']:
                        if os.path.exists(f"{base}.{ext}"):
                            filename = f"{base}.{ext}"
                            break
                
                if os.path.exists(filename):
                    await query.message.reply_text("📤 Отправляю видео...")
                    
                    # Отправляем файл
                    with open(filename, 'rb') as video:
                        await query.message.reply_video(
                            video=video,
                            caption=f"🎬 {info.get('title', 'Video')}",
                            timeout=600
                        )
                    
                    # Удаляем файл после отправки
                    os.remove(filename)
                    await query.edit_message_text("✅ Видео отправлено!")
                else:
                    await query.edit_message_text("❌ Ошибка: файл не найден после скачивания.")
                    
        except Exception as e:
            logging.error(f"Error downloading video: {e}")
            await query.edit_message_text(f"❌ Ошибка при скачивании: {str(e)}")
        finally:
            # Очищаем временную директорию
            try:
                if os.path.exists(temp_dir):
                    for f in os.listdir(temp_dir):
                        os.remove(os.path.join(temp_dir, f))
                    os.rmdir(temp_dir)
            except:
                pass


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неизвестных команд"""
    await update.message.reply_text(
        "❓ Не понимаю эту команду. Отправьте ссылку на YouTube видео или используйте /start"
    )


if __name__ == '__main__':
    # Создание приложения
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'), handle_link))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    print("🤖 Бот запущен...")
    application.run_polling()
