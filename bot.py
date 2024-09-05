from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, InlineQueryHandler, CallbackContext, ConversationHandler, filters
from telegraph import Telegraph
from PIL import Image
from io import BytesIO
import logging
import os
import requests
import asyncio

# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ваши токены
TELEGRAPH_TOKEN = 'c244b32be4b76eb082d690914944da14238249bbdd55f6ffd349b9e000c1'
TELEGRAM_BOT_TOKEN = '7538468672:AAGRzsQVHQ1mzXgQuBbZjSA4FezIirJxjRA'

# Инициализация Telegraph и Telegram бота
telegraph = Telegraph()
telegraph.create_account(short_name='bot')

# Определение состояний
AUTHOR, LINK, CONTENT, IMAGE, RETRY = range(5)

# Загрузка файла по URL
def download_file(url: str, local_filename: str):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

# Проверка размера файла
def check_image_size(file_path: str) -> bool:
    return os.path.getsize(file_path) < 5_000_000  # 5 МБ

# Уменьшение разрешения изображения
def resize_image(input_path: str, output_path: str, max_size: int = 4000):
    with Image.open(input_path) as img:
        width, height = img.size
        if width > max_size or height > max_size:
            new_width = min(width, max_size)
            new_height = int((new_width / width) * height)
            img = img.resize((new_width, new_height), Image.LANCZOS)
        img.save(output_path)

# Функция сжатия изображений
def compress_image(input_path: str, output_path: str, format: str):
    # Если размер файла меньше 5 МБ, не конвертируем и не изменяем формат
    if check_image_size(input_path):
        os.rename(input_path, output_path)
        return

    if format == 'PNG':
        img = Image.open(input_path)
        img = img.convert('RGB')  # Конвертируем PNG в RGB
        temp_jpg_path = 'temp.jpg'
        img.save(temp_jpg_path, format='JPEG', quality=100)
        
        while not check_image_size(temp_jpg_path):
            with Image.open(temp_jpg_path) as temp_img:
                quality = 90
                temp_img.save(temp_jpg_path, format='JPEG', quality=quality)
                while not check_image_size(temp_jpg_path):
                    quality -= 5
                    temp_img.save(temp_jpg_path, format='JPEG', quality=quality)
                    if quality < 90:
                        break
            resize_image(temp_jpg_path, temp_jpg_path)
        
        os.rename(temp_jpg_path, output_path)

    elif format == 'JPEG':
        quality = 90
        with Image.open(input_path) as img:
            img.save(output_path, format='JPEG', quality=quality)
            while not check_image_size(output_path):
                quality -= 5
                img.save(output_path, format='JPEG', quality=quality)
                if quality < 90:
                    break
            resize_image(output_path, output_path)

# Начало разговора
async def start(update: Update, context: CallbackContext) -> int:
    logger.info("Started conversation with user: %s", update.effective_user.username)
    context.user_data.clear()  # Очистка данных пользователя при начале нового разговора
    await update.message.reply_text('Введите ссылку на автора. Обратите внимание что у бота есть команда /cancel которая в любой момент полностью отменяет диалог и сбрасывает процесс')
    return LINK

# Получение ссылки
async def receive_link(update: Update, context: CallbackContext) -> int:
    context.user_data['link'] = update.message.text
    await update.message.reply_text('Введите имя автора:')
    return AUTHOR

# Получение имени автора
async def receive_author(update: Update, context: CallbackContext) -> int:
    context.user_data['author'] = update.message.text
    await update.message.reply_text('Отправьте изображения, не забудьте снять галочку с сжатия и отправить их файлами. Затем вы получите сообщения об успешной загрузке равное количеству отправленных изображений, нажмите /publish когда вы получите все уведомления. Либо введите /restart если желаете начать сначала')
    return CONTENT

# Получение содержания статьи и изображений
async def receive_content(update: Update, context: CallbackContext) -> int:
    if update.message.text:
        await update.message.reply_text('Получен текст, процесс создания статьи сброшен. Начинаем заново.')
        return await restart(update, context)  # Сбрасываем процесс в начало
    
    elif update.message.photo:
        await update.message.reply_text('Пожалуйста, отправьте изображение как файл без сжатия, чтобы сохранить его качество.')
        return CONTENT

    elif update.message.document and update.message.document.mime_type in ['image/jpeg', 'image/png', 'image/webp']:
        file_id = update.message.document.file_id
        logger.info(f"Received file_id: {file_id}")

        file = await context.bot.get_file(file_id)
        image_url = file.file_path
        logger.info(f"Image URL: {image_url}")

        local_filename = 'temp_image.jpg'
        download_file(url=image_url, local_filename=local_filename)

        format = 'PNG' if update.message.document.mime_type == 'image/png' else 'JPEG'
        compressed_filename = 'compressed_image.jpg'
        
        # Повторные попытки с задержкой
        for attempt in range(3):  # Попробовать 3 раза
            try:
                compress_image(input_path=local_filename, output_path=compressed_filename, format=format)
                with open(compressed_filename, 'rb') as f:
                    response = telegraph.upload_file(f)
                    if response:
                        image_url_telegraph = response[0]['src']
                        logger.info(f"Uploaded Image URL: {image_url_telegraph}")
                        if 'images' not in context.user_data:
                            context.user_data['images'] = []
                        if context.user_data['images']:
                            context.user_data['images'].append('<hr/>')
                        context.user_data['images'].append(f'<img src="{image_url_telegraph}" width="600" alt="Image"/>')
                        await update.message.reply_text('Одно изображение добавлено. Дождитесь загрузки остальных если их более одного. Затем вы можете либо продолжать отправлять изображения, либо отправьте команду /publish для завершения.')
                        break
                    else:
                        raise ValueError("Не удалось загрузить изображение на Telegraph.")
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Error uploading file: {e}")
                if attempt < 2:  # Если не последний попытка
                    await asyncio.sleep(5)  # Подождать 5 секунд
                    continue
                await update.message.reply_text('Не удалось загрузить изображение после нескольких попыток. Попробуйте снова отправить изображение командой /retry.')
                context.user_data['state'] = RETRY
                return RETRY
            finally:
                if os.path.exists(local_filename):
                    os.remove(local_filename)
                if os.path.exists(compressed_filename):
                    os.remove(compressed_filename)
        context.user_data['state'] = IMAGE
        return IMAGE
    else:
        await update.message.reply_text('Пожалуйста, отправьте текст или изображение.')
        context.user_data['state'] = CONTENT
        return CONTENT

# Публикация статьи
async def publish_article(update: Update, context: CallbackContext) -> int:
    author = context.user_data.get('author', 'Автор не указан')
    link = context.user_data.get('link', 'Ссылка не указана')
    content = context.user_data.get('content', '')
    images = context.user_data.get('images', [])

    if not content and not images:
        await update.message.reply_text('Не предоставлено содержания или изображений для публикации.')
        return CONTENT

    html_content = f"<p><a href='{link}'>{link}</a></p>"
    html_content += ''.join(images)
    html_content += f"<p>{content}</p>"

    # Повторные попытки с задержкой
    for attempt in range(3):  # Попробовать 3 раза
        try:
            response = telegraph.create_page(
                title=author,
                author_name=author,
                html_content=html_content
            )
            article_url = f"https://telegra.ph/{response['path']}"
            logger.info(f"Article URL: {article_url}")

            message_text = f'by <a href="{article_url}">{author}</a>'
            
            media_group = []
            if len(images) == 1:
                image_html = images[0]
                start_index = image_html.find('src="') + 5
                end_index = image_html.find('"', start_index)
                image_url = image_html[start_index:end_index]
                if image_url.startswith('/'):
                    image_url = f'https://telegra.ph{image_url}'

                logger.info(f"Adding single image to message: {image_url}")

                try:
                    await update.message.reply_photo(photo=image_url, caption=message_text, parse_mode='HTML')
                except Exception as e:
                    logger.error(f"Error sending image with link: {e}")
                    await update.message.reply_text('Произошла ошибка при отправке изображения с ссылкой.')
            else:
                await update.message.reply_text(message_text, parse_mode='HTML')

                for image_html in images:
                    start_index = image_html.find('src="') + 5
                    end_index = image_html.find('"', start_index)
                    image_url = image_html[start_index:end_index]
                    if image_url.startswith('/'):
                        image_url = f'https://telegra.ph{image_url}'

                    logger.info(f"Adding image to media group: {image_url}")

                    try:
                        response = requests.head(image_url)
                        if response.status_code != 200:
                            logger.error(f"Image URL {image_url} is not accessible.")
                            continue
                    except requests.RequestException as e:
                        logger.error(f"Error checking image URL {image_url}: {e}")
                        continue

                    media_group.append(InputMediaPhoto(media=image_url))

                if media_group:
                    try:
                        await update.message.reply_media_group(media=media_group)
                    except Exception as e:
                        logger.error(f"Error sending media group: {e}")
                        await update.message.reply_text('Произошла ошибка при отправке изображений. Попробуйте снова отправить изображение командой /retry.')
            break
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: Error creating or sending article: {e}")
            if attempt < 2:  # Если не последний попытка
                await asyncio.sleep(5)  # Подождать 5 секунд
                continue
            await update.message.reply_text('Произошла ошибка при создании или отправке статьи после нескольких попыток. Попробуйте снова командой /retry.')
            return RETRY

    context.user_data.clear()
    return ConversationHandler.END


# Обработка отмены
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Разговор отменен.')
    # Очистка данных пользователя при отмене
    context.user_data.clear()
    return ConversationHandler.END

# Обработка сброса (рестарта)
async def restart(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Процесс создания публикации был сброшен. Начинаем заново.')
    context.user_data.clear()
    return await start(update, context)

# Обработка повторной попытки
async def retry(update: Update, context: CallbackContext) -> int:
    state = context.user_data.get('state', None)
    
    if state == IMAGE or state == RETRY:
        await update.message.reply_text('Повторная загрузка изображений и создание новой статьи. Пожалуйста, подождите.')
        
        images = context.user_data.get('images', [])
        if not images:
            await update.message.reply_text('Нет изображений для повторной загрузки. Попробуйте отправить изображения снова. Или начните процесс заново командой /restart.')
            return CONTENT
        
        author = context.user_data.get('author', 'Автор не указан')
        link = context.user_data.get('link', 'Ссылка не указана')
        content = context.user_data.get('content', '')

        html_content = f"<p><a href='{link}'>{link}</a></p>"
        html_content += ''.join(images)
        html_content += f"<p>{content}</p>"

        # Повторные попытки с задержкой
        for attempt in range(3):  # Попробовать 3 раза
            try:
                context.user_data['draft'] = {
                    'author': author,
                    'link': link,
                    'content': html_content
                }
                await update.message.reply_text('Новая статья со старыми данными успешно создана. Вы можете продолжить добавлять изображения или опубликовать статью командой /publish.')
                return IMAGE
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Error creating draft: {e}")
                if attempt < 2:
                    await asyncio.sleep(5)  # Подождать 5 секунд
                    continue
                await update.message.reply_text('Произошла повторная ошибка. Попробуйте снова командой /retry или начните заново с помощью /restart.')
                return RETRY

    elif state == CONTENT:
        await update.message.reply_text('Произошла ошибка до загрузки изображений. Пожалуйста, начните процесс заново командой /restart.')
        return ConversationHandler.END
    
    await update.message.reply_text('Неизвестное состояние. Попробуйте начать заново командой /restart.')
    return ConversationHandler.END

# Обработка InlineQuery
async def inline_query(update: Update, context: CallbackContext) -> None:
    query = update.inline_query.query
    if not query:
        return

    # Поиск и отображение статьи по запросу
    articles = find_articles(query)
    results = []
    for article in articles:
        results.append(
            InlineQueryResultArticle(
                id=article['id'],
                title=article['title'],
                input_message_content=InputTextMessageContent(
                    message_text=f"{article['title']}\n\n{article['content']}\n\n[Читать далее]({article['url']})"
                ),
                url=article['url'],
                thumb_url=article['thumb_url']  # Если у вас есть изображение-миниатюра
            )
        )
    await update.inline_query.answer(results, cache_time=1)

# Функция для поиска статей (пример)
def find_articles(query: str):
    # В этой функции вы должны реализовать логику поиска статей
    # Здесь просто возвращаем пример данных
    return [
        {
            'id': '1',
            'title': 'Пример статьи',
            'content': 'Это пример содержания статьи.',
            'url': 'https://telegra.ph/example',
            'thumb_url': 'https://example.com/thumbnail.jpg'
        }
    ]

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Определение обработчиков
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, start)],
        states={
            LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_link)],
            AUTHOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_author)],
            CONTENT: [MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, receive_content)],
            IMAGE: [MessageHandler(filters.PHOTO | filters.Document.ALL, receive_content)],
            RETRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, retry)],
        },
        fallbacks=[CommandHandler('publish', publish_article), CommandHandler('cancel', cancel), CommandHandler('restart', restart), CommandHandler('retry', retry)],
    )

    application.add_handler(conv_handler)
    application.add_handler(InlineQueryHandler(inline_query))

    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
