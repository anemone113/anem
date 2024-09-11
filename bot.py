from telegram import Update, InputMediaPhoto, ReplyKeyboardRemove, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
from PIL import Image
from telegram.constants import ParseMode
from tenacity import retry, wait_fixed, stop_after_attempt
import asyncio
import requests
import logging
import os
import shutil
import io
import aiohttp
from tenacity import retry, wait_fixed, stop_after_attempt, RetryError
import tempfile
import re

# Укажите ваши токены и ключ для imgbb
TELEGRAM_BOT_TOKEN = '7538468672:AAGRzsQVHQ1mzXgQuBbZjSA4FezIirJxjRA'
TELEGRAPH_TOKEN = 'c244b32be4b76eb082d690914944da14238249bbdd55f6ffd349b9e000c1'
IMGBB_API_KEY = 'fdd4c4ac12a927568f6bd0704d2553fa'
GROUP_CHAT_ID = -1002233281756

# Состояния
ASKING_FOR_ARTIST_LINK, ASKING_FOR_AUTHOR_NAME, ASKING_FOR_IMAGE = range(3)

# Сохранение данных состояния пользователя
user_data = {}
publish_data = {}

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id not in user_data:
        logger.info(f"User {user_id} started the process.")
        await update.message.reply_text('Пожалуйста, отправьте ссылку на автора. Если у вас её нет то отправьте любой текст\n \n В боте есть команда /restart которая перезапускает процесс на любом этапе')
        user_data[user_id] = {'status': 'awaiting_artist_link'}  # Инициализация данных для пользователя
        return ASKING_FOR_ARTIST_LINK
    else:
        if user_data[user_id]['status'] == 'awaiting_artist_link':
            return await handle_artist_link(update, context)
        elif user_data[user_id]['status'] == 'awaiting_author_name':
            return await handle_author_name(update, context)
        elif user_data[user_id]['status'] == 'awaiting_image':
            return await handle_image(update, context)

async def restart(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    logger.info(f"User {user_id} restarted the process.")
    await update.message.reply_text('Процесс сброшен. Пожалуйста, начните заново. \n Отправьте ссылку на автора.')
    user_data[user_id] = {'status': 'awaiting_artist_link'}
    return ASKING_FOR_ARTIST_LINK

HELP_TEXT = """
Статья в Telegraph формируется в порядке отправки изображений и текста боту\.\n\n Поддерживаемые тэги\:\(без кавычек\)\n \- \"\*\*\*\" — горизонтальная линия\-разделитель \(отправьте три звёздочки отдельным сообщением\, в этом месте в статье телеграф появится разделитель\)\.\n\- \"\_текст\_\" \— курсив\.\n\- \"\*текст\*\" \— жирный текст\.\n\- \"\[текст ссылки\]\(ссылка\)\" \— гиперссылка\.\n\- \"видео\: \" \— вставка видео с Vimeo или YouTube\.\n\- \"цитата\:\" \— цитата\.\n\- \"цитата по центру\:\" \— центрированная цитата\.\n\- "заголовок:" — заголовок\\.\n\\- "подзаголовок:" — подзаголовок\\.\n\n Последние 5 тэгов пишутся в начале сообщения и применяются ко всему сообщению целиком\. Каждое новое сообщение \— это новый абзац\. Сообщения без тэгов \— обычный текст\.\n\n Пример\: \(без кавычек\)\n\- \"цитата\: \*Волк\* никогда не будет жить в загоне\, но загоны всегда будут жить в \*волке\*\" \— в статье телеграф будет выглядеть как цитата\, в которой слово \"волк\" выделено жирным\.\n\- \"видео\: ссылка\_на\_видео\" \— вставка видео YouTube или Vimeo\.\n\n
"""

async def help_command(update: Update, context: CallbackContext) -> None: await update.message.reply_text( HELP_TEXT, parse_mode=ParseMode.MARKDOWN_V2 )

async def handle_artist_link(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in user_data and user_data[user_id]['status'] == 'awaiting_artist_link':
        user_data[user_id]['artist_link'] = update.message.text
        logger.info(f"User {user_id} provided author link: {update.message.text}")
        await update.message.reply_text('Теперь отправьте имя автора. \n\n Для скрытия слова "Автор:" используйте тэг "^" при вводе автора. Например: ^Любой_текст^. \n Чтобы добавить текст перед "Автор:", оформите его как "^текст^Имя". В возвращённом ботом сообщении это будет выглядеть следующим образом:\n "текст\n Автор: Имя"')
        user_data[user_id]['status'] = 'awaiting_author_name'
        return ASKING_FOR_AUTHOR_NAME
    else:
        await update.message.reply_text('Ошибка: данные не найдены.')
        return ConversationHandler.END

# Ввод имени художника
async def handle_author_name(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in user_data and user_data[user_id]['status'] == 'awaiting_author_name':
        author_input = update.message.text.strip()

        # Проверка на то, заключен ли весь текст в "^...^"
        if re.match(r'^\^.*\^$', author_input):
            # Извлекаем текст без символов "^"
            title = author_input[1:-1].strip()  
            user_data[user_id]['title'] = title
            user_data[user_id]['author_name'] = ""  # Убираем имя автора
            user_data[user_id]['extra_phrase'] = ""  # Пустая фраза, если ничего не найдено
        else:
            # Проверка на наличие фразы в "^...^" в начале текста
            match = re.match(r'^\^(.*?)\^\s*(.*)', author_input)
            if match:
                phrase = match.group(1)  # Извлекаем фразу из "^...^"
                author_name = match.group(2).strip()  # Извлекаем остальное имя автора
                user_data[user_id]['extra_phrase'] = phrase  # Сохраняем фразу отдельно
            else:
                author_name = author_input.strip()  # Если нет фразы в "^...^", сохраняем как есть
                user_data[user_id]['extra_phrase'] = ""  # Пустая фраза, если ничего не найдено

            # Сохраняем имя автора как заголовок статьи
            user_data[user_id]['author_name'] = author_name
            user_data[user_id]['title'] = author_name  # Используем только имя автора для заголовка

        logger.info(f"User {user_id} provided author name or title: {author_input}")
        
        await update.message.reply_text('Теперь отправьте изображения файлом или текст. \n \n Текст поддерживает различное форматирование. Для получения списка тэгов и помощи введите /help  \n \n Так же вы можете начажать /restart для сброса')
        user_data[user_id]['status'] = 'awaiting_image'
        return ASKING_FOR_IMAGE
    else:
        await update.message.reply_text('Ошибка: данные не найдены. Попробуйте снова или нажмите /restart')
        return ConversationHandler.END

def compress_image(file_path: str, output_path: str) -> None:
    # Определяем максимальный размер файла в байтах (5 МБ)
    max_size = 5 * 1024 * 1024

    # Открываем изображение
    with Image.open(file_path) as img:
        # Проверяем формат и размер изображения
        if img.format == 'PNG' and os.path.getsize(file_path) > max_size:
            # Если PNG и размер больше 5 МБ, конвертируем в JPG
            img = img.convert('RGB')
            temp_path = file_path.rsplit('.', 1)[0] + '.jpg'
            img.save(temp_path, format='JPEG', quality=90)
            file_path = temp_path
            img = Image.open(file_path)
        
        # Если изображение имеет альфа-канал, преобразуем его в RGB
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGB')

        # Сохраняем изображение в формате JPG с начальным качеством
        quality = 90
        img.save(output_path, format='JPEG', quality=quality)

        # Проверяем размер файла и сжимаем при необходимости
        while os.path.getsize(output_path) > max_size:
            quality -= 10
            if quality < 10:
                break
            img.save(output_path, format='JPEG', quality=quality)

        # Если изображение всё ещё больше 5 МБ, уменьшаем разрешение
        while os.path.getsize(output_path) > max_size:
            width, height = img.size
            img = img.resize((width // 2, height // 2), Image.ANTIALIAS)
            img.save(output_path, format='JPEG', quality=quality)

        # Удаляем временный JPG файл, если он был создан
        if file_path.endswith('.jpg'):
            os.remove(file_path)

# Асинхронная функция для загрузки изображения на imgbb
async def upload_image_to_imgbb(file_path: str) -> str:
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            form = aiohttp.FormData()
            form.add_field('key', IMGBB_API_KEY)
            form.add_field('image', f)

            async with session.post('https://api.imgbb.com/1/upload', data=form) as response:
                if response.status == 200:
                    response_json = await response.json()
                    return response_json['data']['url']
                else:
                    raise Exception(f"Ошибка загрузки на imgbb: {response.status}")

import re

# Определяем разметку тегов
markup_tags = {
    '*': 'strong',  # Жирный текст
    '_': 'em',      # Курсив
}

import re

def apply_markup(text: str) -> dict:
    """Применяет разметку к тексту на основе команд и возвращает узел контента в формате Telegra.ph."""
    
    text = text.strip()  # Убираем пробелы в начале и в конце текста
    text_lower = text.lower()

    # Обработка команд
    if text_lower.startswith("подзаголовок: "):
        content = text[len("Подзаголовок: "):].strip()
        content = apply_markup_to_content(content)
        return {"tag": "h4", "children": content}
    elif text_lower.startswith("цитата:"):
        content = text[len("Цитата:"):].strip()
        content = apply_markup_to_content(content)
        return {"tag": "blockquote", "children": content}
    elif text_lower.startswith("заголовок: "):
        content = text[len("Заголовок: "):].strip()
        content = apply_markup_to_content(content)
        return {"tag": "h3", "children": content}
    elif text_lower.startswith("цитата по центру:"):
        content = text[len("Цитата по центру:"):].strip()
        content = apply_markup_to_content(content)
        return {"tag": "aside", "children": content}
    elif text_lower.startswith("***"):
        return {"tag": "hr"}
    elif text_lower.startswith("видео: "):
        video_url = text[len("Видео: "):].strip()
        # Кодируем URL, чтобы он подходил для использования в src
        encoded_url = re.sub(r'https://', 'https%3A%2F%2F', video_url)
        
        # Проверяем, это YouTube или Vimeo
        if "youtube.com" in video_url or "youtu.be" in video_url:
            return {
                "tag": "figure",
                "children": [
                    {
                        "tag": "iframe",
                        "attrs": {
                            "src": f"/embed/youtube?url={encoded_url}",
                            "width": 640,
                            "height": 360,
                            "frameborder": 0,
                            "allowtransparency": "true",
                            "allowfullscreen": "true",
                            "scrolling": "no"
                        }
                    }
                ]
            }
        elif "vimeo.com" in video_url:
            return {
                "tag": "figure",
                "children": [
                    {
                        "tag": "iframe",
                        "attrs": {
                            "src": f"/embed/vimeo?url={encoded_url}",
                            "width": 640,
                            "height": 360,
                            "frameborder": 0,
                            "allowtransparency": "true",
                            "allowfullscreen": "true",
                            "scrolling": "no"
                        }
                    }
                ]
            }

    # Если команда не распознана, обрабатываем текст с разметкой
    content = apply_markup_to_content(text)
    return {"tag": "div", "children": content}

def apply_markup_to_content(content: str) -> list:
    """Обрабатывает разметку в тексте и возвращает список узлов для Telegra.ph."""
    nodes = []

    # Регулярные выражения для разметки
    regex_markup = re.compile(r'(\*|_)(.*?)\1', re.DOTALL)
    link_regex = re.compile(r'\[(.*?)\]\((.*?)\)', re.DOTALL)

    # Сначала обрабатываем гиперссылки
    pos = 0
    temp_nodes = []
    for match in link_regex.finditer(content):
        # Добавляем текст до текущего совпадения
        if pos < match.start():
            temp_nodes.append(content[pos:match.start()])

        # Добавляем узел ссылки
        link_text, url = match.groups()
        temp_nodes.append({"tag": "a", "attrs": {"href": url}, "children": [{"tag": "text", "children": [link_text]}]})

        # Обновляем позицию
        pos = match.end()

    # Добавляем оставшийся текст после обработки гиперссылок
    if pos < len(content):
        temp_nodes.append(content[pos:])

    # Теперь обрабатываем остальную разметку
    nodes = []
    pos = 0
    for node in temp_nodes:
        if isinstance(node, str):
            # Обрабатываем текст с разметкой
            text = node
            while True:
                match = regex_markup.search(text)
                if not match:
                    nodes.append({"tag": "text", "children": [text]})
                    break
                # Добавляем текст до текущего совпадения
                if pos < match.start():
                    nodes.append({"tag": "text", "children": [text[:match.start()]]})
                    text = text[match.start():]
                # Определяем тег и добавляем узел
                tag = markup_tags.get(match.group(1))
                if tag:
                    text = text[match.end():]
                    nodes.append({"tag": tag, "children": [match.group(2)]})
                    pos = 0
                else:
                    nodes.append({"tag": "text", "children": [text]})
                    break
        else:
            nodes.append(node)

    return nodes

# Обновленная функция handle_image для обработки изображений
async def handle_image(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in user_data and user_data[user_id]['status'] == 'awaiting_image':
        if update.message.photo:
            await update.message.reply_text('Пожалуйста, отправьте изображение как файл (формат JPG, PNG или RAR для  GIF), без сжатия.')
            return ASKING_FOR_IMAGE
        elif update.message.document:
            file_name = update.message.document.file_name
            file_ext = file_name.lower().split('.')[-1]
            file = await context.bot.get_file(update.message.document.file_id)

            # Создаём временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
                file_path = tmp_file.name
                await file.download_to_drive(file_path)

            # Если файл .rar, переименовываем его в .gif
            if file_ext == 'rar':
                new_file_path = f'{os.path.splitext(file_path)[0]}.gif'
                shutil.move(file_path, new_file_path)
                file_path = new_file_path
                file_name = os.path.basename(file_path)
                file_ext = 'gif'

            if file_ext in ('jpg', 'jpeg', 'png', 'gif'):
                # Если изображение больше 5 МБ, сжимаем его
                if os.path.getsize(file_path) > 5 * 1024 * 1024:
                    compressed_path = f'{os.path.splitext(file_path)[0]}_compressed.jpg'
                    compress_image(file_path, compressed_path)
                    file_path = compressed_path

                try:
                    # Запускаем асинхронную загрузку изображений
                    image_url = await upload_image_to_imgbb(file_path)
                    if 'media' not in user_data[user_id]:
                        user_data[user_id]['media'] = []
                    user_data[user_id]['media'].append({'type': 'image', 'url': image_url})
                    os.remove(file_path)  # Удаляем временный файл
                    await update.message.reply_text('Одно изображение добавлено.\n\n Дождитесь загрузки остальных изображений если их более чем одно. Затем вы можете продолжить присылать изображения или текст \n\n Если желаете завершить публикацию введите /publish')
                    return ASKING_FOR_IMAGE
                except Exception as e:
                    await update.message.reply_text(f'Ошибка при загрузке изображения на imgbb: {str(e)} Можете попробовать прислать файл ещё раз или нажать /restart')
                    return ConversationHandler.END
            else:
                await update.message.reply_text('Пожалуйста, отправьте изображение в формате JPG, PNG или RAR для GIF файлом, без сжатия.\n\n для помощи введите /help')
                return ASKING_FOR_IMAGE
        elif update.message.text:
            # Обработка текстовых сообщений с разметкой
            formatted_text = apply_markup(update.message.text)
            if 'media' not in user_data[user_id]:
                user_data[user_id]['media'] = []
            user_data[user_id]['media'].append({'type': 'text', 'content': formatted_text})
            await update.message.reply_text('Текст успешно добавлен. Вы можете отправить ещё текст или изображения. \n\n Либо завершить публикацию с помощью команды /publish.')
            return ASKING_FOR_IMAGE
        else:
            await update.message.reply_text('Пожалуйста, отправьте изображение как файл (формат JPG, PNG или GIF), без сжатия, или текст.\n\n для помощи введите /help')
            return ASKING_FOR_IMAGE
    else:
        await update.message.reply_text('Ошибка: данные не найдены. Попробуйте отправить снова. Или нажмите /restart')
        return ConversationHandler.END

@retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
def make_request(url, data):
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()

# Функция для отправки медиа-сообщений с повторными попытками
@retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
async def send_media_with_retries(update, media_group, caption):
    try:
        await update.message.reply_text(caption, parse_mode='HTML')
        await update.message.reply_media_group(media=media_group)
    except Exception as e:
        logger.error(f"Failed to send media group: {e}")
        raise  # Перекидываем исключение для повторных попыток

async def send_media_group(update, media_group, caption):
    if not media_group:
        logger.error("Media group is empty")
        return
    try:
        await update.message.reply_text(caption, parse_mode='HTML')
        await update.message.reply_media_group(media=media_group)
    except Exception as e:
        logger.error(f"Failed to send media group: {e}")
        raise

async def send_media_group_with_retries(update, media_group, max_retries=3, delay=2):
    retries = 0
    while retries < max_retries:
        try:
            await update.message.reply_media_group(media_group)
            return True  # Успешная отправка
        except Exception as e:
            logger.error(f"Failed to send media group: {e}")
            retries += 1
            if retries < max_retries:
                logger.info(f"Retrying in {delay} seconds... (Attempt {retries}/{max_retries})")
                await asyncio.sleep(delay)
    return False  # Если все попытки не удались

# Метод для отправки одного изображения с повторными попытками и задержкой
async def send_photo_with_retries(update, photo_url, caption, parse_mode, max_retries=3, delay=2):
    retries = 0
    while retries < max_retries:
        try:
            await update.message.reply_photo(
                photo=photo_url,
                caption=caption,
                parse_mode=parse_mode
            )
            return True  # Успешная отправка
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")
            retries += 1
            if retries < max_retries:
                logger.info(f"Retrying in {delay} seconds... (Attempt {retries}/{max_retries})")
                await asyncio.sleep(delay)
    return False  # Если все попытки не удались

# Основная функция публикации
async def publish(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id in user_data:
        try:
            author_name = "Anemone"
            author_link = "https://t.me/anemonn"
            artist_link = user_data[user_id]['artist_link']
            media = user_data[user_id].get('media', [])
            title = user_data[user_id].get('title', 'test')

            # Извлекаем фразу перед "Автор", если она есть
            extra_phrase = user_data[user_id].get('extra_phrase', "")
            author_name_final = user_data[user_id].get('author_name', '')

            # Формируем строку с фразой перед "Автор", если она есть
            if extra_phrase:
                author_line = f"{extra_phrase}\nАвтор: {author_name_final}"
            else:
                author_line = f"Автор: {author_name_final}"

            # Проверяем, есть ли авторское имя
            if not author_name_final:
                author_line = title  # Если это заголовок из "^...^", то используем только заголовок
            else:
                # Формируем строку с фразой перед "Автор", если она есть
                if extra_phrase:
                    author_line = f"{extra_phrase}\nАвтор: {author_name_final}"
                else:
                    author_line = f"Автор: {author_name_final}"


            # Создание статьи в Telegra.ph
            content = [
                {
                    'tag': 'p',
                    'children': [
                        {
                            'tag': 'a',
                            'attrs': {'href': artist_link},
                            'children': [artist_link]
                        }
                    ]
                }
            ]

            # Добавление изображений с разделителями
            for index, item in enumerate(media):
                if item['type'] == 'text':
                    content.append({'tag': 'p', 'children': [item['content']]})
                elif item['type'] == 'image':
                    content.append({'tag': 'img', 'attrs': {'src': item['url']}})
                    if index < len(media) - 1:
                        content.append({'tag': 'hr'})

            # Добавление надписи в конце статьи
            content.append({'tag': 'hr'})
            content.append({
                'tag': 'i',
                'children': [f'Оригиналы доступны в браузере через меню (⋮)']
            })

            response = requests.post('https://api.telegra.ph/createPage', json={
                'access_token': TELEGRAPH_TOKEN,
                'title': title,
                'author_name': author_name,
                'author_url': author_link,
                'content': content
            })
            response.raise_for_status()
            response_json = response.json()

            if response_json.get('ok'):
                article_url = f"https://telegra.ph/{response_json['result']['path']}"

                # Получение данных статьи
                article_response = requests.get(f'https://api.telegra.ph/getPage?access_token={TELEGRAPH_TOKEN}&path={response_json["result"]["path"]}&return_content=true')
                article_response.raise_for_status()
                article_data = article_response.json()

                # Подсчет количества изображений
                image_count = sum(1 for item in article_data.get('result', {}).get('content', []) if item.get('tag') == 'img')

                # Отправка изображений, если они есть
                if image_count > 1:
                    message_with_link = f'{author_line}\n<a href="{article_url}">Оригинал</a>'
                    await update.message.reply_text(message_with_link, parse_mode='HTML')
                    media_groups = [media[i:i + 10] for i in range(0, len(media), 10)]
                    for group in media_groups:
                        media_group = [InputMediaPhoto(media=item['url']) for item in group if item['type'] == 'image']

                        # Попытка отправить медиа группу с задержкой и повторными попытками
                        success = await send_media_group_with_retries(update, media_group)
                        if not success:
                            await update.message.reply_text('Ошибка при отправке медиа. /restart')
                            return

                elif image_count == 1:
                    # Если одно изображение, отправляем одно сообщение с изображением
                    single_image = next((item for item in media if item['type'] == 'image'), None)
                    if single_image:
                        caption = f'{author_line}\n<a href="{article_url}">Оригинал</a>'
                        success = await send_photo_with_retries(
                            update,
                            photo_url=single_image['url'],
                            caption=caption,
                            parse_mode='HTML'
                        )
                        if not success:
                            await update.message.reply_text('Ошибка при отправке изображения. /restart')
                            return

                elif image_count == 0:
                    # Если нет изображений
                    message_with_link = f'{author_line}\n<a href="{article_url}">Оригинал</a>'
                    await update.message.reply_text(message_with_link, parse_mode='HTML')

# Отправка сообщения с количеством изображений
                await update.message.reply_text(f'В статье {image_count} изображений.')

                # Сохранение данных
                publish_data[user_id] = {
                    'title': title,
                    'article_url': article_url,
                    'image_count': image_count,
                    'author_line': author_line
                }

                del user_data[user_id]
                await update.message.reply_text(
                    'Публикация успешно создана. Чтобы поделиться ей с администрацией нажмите /suggest \n\n *Бот перезапущен успешно.*',
                    reply_markup=ReplyKeyboardRemove()
                )
                logger.info(f"User {user_id}'s data cleared and process completed.")
                await start(update, context)
                return ConversationHandler.END
            else:
                await update.message.reply_text('Ошибка при создании статьи. /restart')
        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            await update.message.reply_text('Ошибка при создании статьи. /restart')
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            await update.message.reply_text('Произошла непредвиденная ошибка. /restart')

        del user_data[user_id]
        logger.info(f"Error occurred. User {user_id}'s data cleared.")
        return ConversationHandler.END
    else:
        await update.message.reply_text('Ошибка: данные не найдены. /restart')
        return ConversationHandler.END

async def unknown_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text('Неизвестное сообщение. Пожалуйста, отправьте ссылку на автора, имя автора или изображение. В случае если это сообщение повторяется нажмите /restart')
    else:
        # Обработка сообщений в процессе
        if user_data[user_id]['status'] == 'awaiting_artist_link':
            await handle_artist_link(update, context)
        elif user_data[user_id]['status'] == 'awaiting_author_name':
            await handle_author_name(update, context)
        elif user_data[user_id]['status'] == 'awaiting_image':
            await handle_image(update, context)
            
async def suggest(update: Update, context: CallbackContext) -> None:
    global publish_data
    user_id = update.message.from_user.id
    if user_id in publish_data:
        data = publish_data[user_id]
        title = data['title']
        article_url = data['article_url']
        author_line = data['author_line']

        try:
            # Получаем содержимое статьи
            article_response = requests.get(f'https://api.telegra.ph/getPage?path={article_url.split("/")[-1]}&return_content=true')
            article_response.raise_for_status()
            article_data = article_response.json()

            # Ищем все изображения в контенте
            images = []
            for node in article_data['result']['content']:
                if node['tag'] == 'img' and 'attrs' in node and 'src' in node['attrs']:
                    images.append(node['attrs']['src'])
            
            # Отправляем первое сообщение с текстом в группу
            message_with_link = f'Пользователь {update.message.from_user.username} предложил:\n {author_line}\n<a href="{article_url}">Оригинал</a>'
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_with_link, parse_mode='HTML')
            
            # Если есть изображения, отправляем их как медиагруппу в группу
            if images:
                media_group = [InputMediaPhoto(image) for image in images]
                await context.bot.send_media_group(chat_id=GROUP_CHAT_ID, media=media_group)
            else:
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text='Изображений в статье нет.')

            # Сообщение об успешной отправке предложения в личный диалог с пользователем
            await update.message.reply_text('Ваше предложение отправлено администрации')
        except Exception as e:
            logger.error(f"Failed to process article: {e}")
            await update.message.reply_text('Ошибка при обработке статьи. /restart')
    else:
        await update.message.reply_text('Нет данных для предложения.')

def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Настройка ConversationHandler
    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, start)
        ],
        states={
            ASKING_FOR_ARTIST_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_artist_link)],
            ASKING_FOR_AUTHOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_author_name)],
            ASKING_FOR_IMAGE: [MessageHandler(filters.PHOTO | filters.Document.ALL, handle_image)]
        },
        fallbacks=[MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message)],
        per_user=True
    )

    application.add_handler(CommandHandler('restart', restart))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('publish', publish))
    application.add_handler(CommandHandler('suggest', suggest))  # Добавляем обработчик для /suggest
    application.add_handler(conversation_handler)
    logger.info("Bot started and polling...")
    application.run_polling()

if __name__ == '__main__':
    main()

