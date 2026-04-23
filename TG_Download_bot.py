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
        'nocheckcertificate': True,
        'extract_flat': False,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'ignoreerrors': True,
        'prefer_free_formats': False,
        'socket_timeout': 30,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return None, "Не удалось получить информацию о видео"
            
            # Проверяем что info это словарь
            if not isinstance(info, dict):
                return None, "Некорректный ответ от YouTube"
            
            # Фильтруем только видео с аудио (комбинированные форматы)
            formats = []
            seen_quality = set()
            
            all_formats = info.get('formats', [])
            if not isinstance(all_formats, list):
                return None, "Не удалось получить список форматов"
            
            for fmt in all_formats:
                # Пропускаем если fmt не словарь
                if not isinstance(fmt, dict):
                    continue
                    
                # Ищем форматы где есть и видео и аудио
                has_video = fmt.get('vcodec') and fmt.get('vcodec') != 'none'
                has_audio = fmt.get('acodec') and fmt.get('acodec') != 'none'
                
                if has_video and has_audio:
                    quality = fmt.get('format_note', '')
                    if not quality or quality == 'tiny':
                        height = fmt.get('height')
                        if height:
                            quality = f"{height}p"
                        else:
                            quality = f"{fmt.get('width', '?')}x{fmt.get('height', '?')}"
                    
                    if quality and quality not in seen_quality:
                        seen_quality.add(quality)
                        filesize = fmt.get('filesize') or fmt.get('filesize_approx', 0)
                        formats.append({
                            'format_id': fmt.get('format_id'),
                            'quality': quality,
                            'ext': fmt.get('ext', 'mp4'),
                            'filesize': filesize,
                            'type': 'combined'
                        })
            
            if not formats:
                video_formats = []
                audio_formats = []
                
                for fmt in all_formats:
                    if not isinstance(fmt, dict):
                        continue
                    if fmt.get('vcodec') != 'none' and fmt.get('acodec') == 'none':
                        height = fmt.get('height')
                        if height:
                            quality = f"{height}p"
                            video_formats.append({
                                'format_id': fmt.get('format_id'),
                                'quality': quality,
                                'ext': fmt.get('ext', 'mp4'),
                                'filesize': fmt.get('filesize') or fmt.get('filesize_approx', 0),
                                'type': 'video_only'
                            })
                    elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                        audio_formats.append(fmt)
                
                # Берем лучший аудио
                best_audio = None
                for aud in sorted(audio_formats, key=lambda x: x.get('abr', 0) or x.get('tbr', 0), reverse=True):
                    best_audio = aud
                    break
                
                if best_audio and video_formats:
                    for vid in video_formats[:10]:
                        formats.append({
                            'format_id': f"{vid['format_id']}+{best_audio.get('format_id')}",
                            'quality': vid['quality'],
                            'ext': 'mp4',
                            'filesize': vid['filesize'],
                            'type': 'separate'
                        })
            
            # Сортируем по качеству
            def sort_key(x):
                q = x['quality']
                if q.endswith('p'):
                    try:
                        return int(q[:-1])
                    except:
                        return 0
                return 0
            
            formats.sort(key=sort_key, reverse=True)
            
            return info, formats[:10] if formats else []
            
    except Exception as e:
        logging.error(f"Error getting formats: {e}")
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
        # Дополнительная защита: проверяем что fmt это словарь
        if not isinstance(fmt, dict):
            logging.warning(f"Пропущен некорректный формат: {fmt}")
            continue
        size_mb = round(fmt['filesize'] / (1024 * 1024), 1) if fmt.get('filesize') else '?'
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
