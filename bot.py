from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, InlineQueryHandler, CallbackContext, ConversationHandler, filters
from telegraph import Telegraph
from PIL import Image
from io import BytesIO
import logging
import os
import requests

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
def check_image_size(image_url: str) -> bool:
    response = requests.get(image_url)
    file_size = len(response.content)
    return file_size < 1_000_000  # 1 МБ

# Начало разговора
async def start(update: Update, context: CallbackContext) -> int:
    logger.info("Started conversation with user: %s", update.effective_user.username)
    context.user_data.clear()  # Очистка данных пользователя при начале нового разговора
    await update.message.reply_text('Введите ссылку на автора. Либо введите /restart если желаете начать сначала')
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
        # Если получено текстовое сообщение, сбрасываем процесс
        await update.message.reply_text('Получен текст, процесс создания статьи сброшен. Начинаем заново.')
        return await restart(update, context)  # Сбрасываем процесс в начало
    
    elif update.message.photo:  # Проверка на сжатые изображения
        await update.message.reply_text('Пожалуйста, отправьте изображение как файл без сжатия, чтобы сохранить его качество.')
        return CONTENT

    elif update.message.document and update.message.document.mime_type in ['image/jpeg', 'image/png', 'image/webp']:
        file_id = update.message.document.file_id
        logger.info(f"Received file_id: {file_id}")

        file = await context.bot.get_file(file_id)
        image_url = file.file_path
        logger.info(f"Image URL: {image_url}")

        local_filename = 'temp_image.jpg'
        download_file(image_url, local_filename)

        try:
            with open(local_filename, 'rb') as f:
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
                else:
                    await update.message.reply_text('Не удалось загрузить изображение на Telegraph. Попробуйте снова отправить изображение командой /retry. или сбросте к началу командой /restart')
                    context.user_data['state'] = RETRY
                    return RETRY
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            await update.message.reply_text('Произошла ошибка при загрузке изображения. Попробуйте снова отправить изображение командой /retry. или сбросте к началу командой /restart')
            context.user_data['state'] = RETRY
            return RETRY
        finally:
            if os.path.exists(local_filename):
                os.remove(local_filename)
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

    # Создание HTML-контента
    html_content = f"<p><a href='{link}'>{link}</a></p>"  # Текст ссылки
    html_content += ''.join(images)  # Сначала добавляем изображения
    html_content += f"<p>{content}</p>"  # Затем текст

    try:
        # Создание страницы на Telegraph
        response = telegraph.create_page(
            title=author,  # Используем имя автора как заголовок
            author_name=author,
            html_content=html_content
        )

        # Получение URL статьи
        article_url = f"https://telegra.ph/{response['path']}"
        logger.info(f"Article URL: {article_url}")

        # Форматирование гиперссылки с текстом ссылки
        message_text = f'by <a href="{article_url}">{author}</a>'
        
        # Подготовка медиа-группы для отправки изображений
        media_group = []
        if len(images) == 1:
            # Если одно изображение, отправляем его вместе с ссылкой в одном сообщении
            image_html = images[0]
            # Получение URL изображения
            start_index = image_html.find('src="') + 5
            end_index = image_html.find('"', start_index)
            image_url = image_html[start_index:end_index]
            
            # Проверка и корректировка URL, если необходимо
            if image_url.startswith('/'):
                image_url = f'https://telegra.ph{image_url}'

            logger.info(f"Adding single image to message: {image_url}")

            # Отправка сообщения с изображением и ссылкой
            try:
                await update.message.reply_photo(photo=image_url, caption=message_text, parse_mode='HTML')
            except Exception as e:
                logger.error(f"Error sending image with link: {e}")
                await update.message.reply_text('Произошла ошибка при отправке изображения с ссылкой.')
        else:
            # Если несколько изображений, отправляем сообщения отдельно
            await update.message.reply_text(message_text, parse_mode='HTML')

            for image_html in images:
                # Получение URL изображения
                start_index = image_html.find('src="') + 5
                end_index = image_html.find('"', start_index)
                image_url = image_html[start_index:end_index]

                # Проверка и корректировка URL, если необходимо
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

            # Отправка медиагруппы
            if media_group:
                try:
                    await update.message.reply_media_group(media=media_group)
                except Exception as e:
                    logger.error(f"Error sending media group: {e}")
                    await update.message.reply_text('Произошла ошибка при отправке изображений. Попробуйте снова командой /retry или сбросте к началу командой /restart')

    except Exception as e:
        logger.error(f"Error creating or sending article: {e}")
        await update.message.reply_text('Произошла ошибка при создании или отправке статьи. Попробуйте снова командой /retry.')
        return RETRY

    # Очистка данных пользователя после публикации
    context.user_data.clear()

    # Завершение разговора
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
    
    if state == IMAGE:
        await update.message.reply_text('Пожалуйста, отправьте изображение снова.')
    elif state == RETRY:
        await update.message.reply_text('Пожалуйста, попробуйте снова отправить статью.')
    
    return state
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
