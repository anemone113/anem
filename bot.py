from telegram import Update, InputMediaPhoto, ReplyKeyboardRemove, InputMediaDocument, InputMediaVideo, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, CallbackQueryHandler
from PIL import Image
from background import keep_alive
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
from requests.exceptions import Timeout

# Укажите ваши токены и ключ для imgbb
TELEGRAM_BOT_TOKEN = '7538468672:AAEOEFS7V0z0uDzZkeGNQKYsDGlzdOziAZI'
TELEGRAPH_TOKEN = 'c244b32be4b76eb082d690914944da14238249bbdd55f6ffd349b9e000c1'
IMGBB_API_KEY = '25c8af109577638da9ba88a667be22b1'
GROUP_CHAT_ID = -1002233281756

# Состояния
ASKING_FOR_ARTIST_LINK, ASKING_FOR_AUTHOR_NAME, ASKING_FOR_IMAGE, EDITING_FRAGMENT = range(4)
# Сохранение данных состояния пользователя
user_data = {}
publish_data = {}
users_in_send_mode = set()
media_group_storage = {}

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: CallbackContext) -> int:
    # Проверка, если событие пришло от текстового сообщения
    if update.message:
        user_id = update.message.from_user.id
        message_to_reply = update.message
    # Проверка, если событие пришло от callback_query
    elif update.callback_query:
        user_id = update.callback_query.from_user.id
        message_to_reply = update.callback_query.message
    else:
        # Если нет ни сообщения, ни callback_query
        return ConversationHandler.END

    # Если пользователя еще нет в данных, инициализируем процесс
    if user_id not in user_data:
        logger.info(f"User {user_id} started the process.")
        await message_to_reply.reply_text(
            '🌠Этот бот поможет вам создать пост для группы Anemone. Изначально пост будет виден исключительно вам, так что не бойтесь экспериментировать и смотреть что получится\n\n'
            'Для начала, пожалуйста, отправьте ссылку на автора. Если у вас её нет, то отправьте любой текст\n\n'
            '<i>В боте есть команда /restart, которая перезапускает процесс на любом этапе</i>\n',
            parse_mode='HTML'
        )
        user_data[user_id] = {'status': 'awaiting_artist_link'}  # Инициализация данных для пользователя
        return ASKING_FOR_ARTIST_LINK
    else:
        # Обработка состояний пользователя
        status = user_data[user_id].get('status')
        if status == 'awaiting_artist_link':
            return await handle_artist_link(update, context)
        elif status == 'awaiting_author_name':
            return await handle_author_name(update, context)
        elif status == 'awaiting_image':
            return await handle_image(update, context)
        else:
            await message_to_reply.reply_text('🚫Ошибка: некорректное состояние.')
            return ConversationHandler.END

async def restart(update: Update, context: CallbackContext) -> int:
    # Проверка типа события
    if update.message:
        user_id = update.message.from_user.id
        message_to_reply = update.message
    elif update.callback_query:
        user_id = update.callback_query.from_user.id
        message_to_reply = update.callback_query.message
    else:
        return ConversationHandler.END

    if user_id in user_data:
        del user_data[user_id]  # Удаляем старые данные пользователя  
    logger.info(f"User {user_id} restarted the process.") 
    
    # Инициализируем новое состояние пользователя
    user_data[user_id] = {'status': 'awaiting_artist_link'}
    await message_to_reply.reply_text('✅Процесс сброшен. Пожалуйста, начните заново. \nОтправьте ссылку на автора.')
    
    return ASKING_FOR_ARTIST_LINK


HELP_TEXT = """
▶️Пост в Анемоне формируется из двух частей \- непосредственно сам пост видимый в телеграме \, плюс статья Telagraph доступная по ссылке\(для примера посмотрите любой из последних постов в группе\) Бот позволяет сделать обе части\. \n\n  Изначально статья и всё её содержание видны только вам\, администрации она станет доступна только после того как вы нажмёте сначала кнопку \" К Завершению Публикации \" и затем \(по желанию\) кнопку \/share \(поделиться\)\. Если после публикации вы не захотите вводить команду share то публикация останется видна только вам\n\n ▶️Статья в Telegraph формируется в порядке отправки вами изображений и текста боту\.\n\n Во время создания статьи\, с помощью соответствующих кнопок вы можете\: \n\-открыть предросмотр\n \-удалить последний добавленный элемент \(работает неограниченное количество раз\, пока статья не станет пустой\)\n \-редактировать всё содержимое вашей статьи через список добавленных изображений и текста\. С любым фрагментом можно делать что угодно\, менять текст на изображение и наоборот\, удалять\,  исправлять\, однако только до тех пор пока вы не используете кнопку \" К Завершению Публикации \", послее её нажатия редактировать статью уже будет больше нельзя\, только наполнить новую\. \n\n▶️Поддерживаемые тэги разметки статьибез кавычек\)\n \- \"\*\*\*\" — горизонтальная линия\-разделитель \(отправьте три звёздочки отдельным сообщением\, в этом месте в статье телеграф появится разделитель\)\.\n\- \"\_текст\_\" — курсив\.\n\- \"\*текст\*\" — жирный текст\.\n\- \"\[текст ссылки\]\(ссылка\)\" — гиперссылка\.\n\- \"видео\: \" — вставка видео с Vimeo или YouTube\.\n\- \"цитата\:\" — цитата\.\n\- \"цитата по центру\:\" — центрированная цитата\.\n\- "заголовок:" — заголовок\\.\n\\- "подзаголовок:" — подзаголовок\\.\n\n Последние 5 тэгов пишутся в начале сообщения и применяются ко всему сообщению целиком\. Каждое новое сообщение — это новый абзац\. Сообщения без тэгов — обычный текст\.\n\n Пример\: \(без кавычек\)\n\- \"цитата\: \*Волк\* никогда не будет жить в загоне\, но загоны всегда будут жить в \*волке\*\" — в статье телеграф примет вид цитата\, в которой слово \"волк\" выделено жирным\.\n\- \"видео\: ссылка\_на\_видео\" — вставка интерактивного видео YouTube или Vimeo\.\n\n▶️Кроме того бот поддерживает загрузку GIF файлов\. Для этого переименуйте \.GIF в \.RAR \, затем отправьте файл боту во время оформления поста\. Это нужно для того чтобы телеграм не пережимал GIF файлы\, бот автоматически переименует файл обратно в GIF перед размещением в Телеграф\n\n▶️Так же вы можете отправить что\-то администрации напрямую\, в режиме прямой связи\. Для этого введите команду \/send и после неё все ваши сообщения отправленные боту тут же будут пересылаться администрации\. Это могут быть какие\-то пояснения\, дополнительные изображения или их правильное размещение в посте телеграм\, вопросы\, предложения\, ссылка на самостоятельно созданную статью телеграф\, пойманные в боте ошибки и что угодно ещё\. Для завершения этого режима просто введите \/fin и бот вернётся в свой обычный режим\. Просьба не спамить через этот режим\, писать или отправлять только нужную информацию  \n
"""

async def help_command(update: Update, context: CallbackContext) -> None:
    if update.message:  # Если команда пришла через сообщение
        await update.message.reply_text(HELP_TEXT, parse_mode='MarkdownV2')
    elif update.callback_query:  # Если команда пришла через инлайн-кнопку
        await update.callback_query.message.reply_text(HELP_TEXT, parse_mode='MarkdownV2')
        await update.callback_query.answer()  # Подтверждаем нажатие кнопки

async def handle_artist_link(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in user_data and user_data[user_id]['status'] == 'awaiting_artist_link':
        user_data[user_id]['artist_link'] = update.message.text
        logger.info(f"User {user_id} provided author link: {update.message.text}")
        await update.message.reply_text('Теперь отправьте имя автора. \n\n <i>Чтобы скрыть слово "Автор:", используйте символ "^" в начале и конце сообщения. Например: ^Имя^</i>',
    parse_mode='HTML')
        user_data[user_id]['status'] = 'awaiting_author_name'
        return ASKING_FOR_AUTHOR_NAME
    else:
        await update.message.reply_text('🚫Ошибка: данные не найдены.')
        return ConversationHandler.END

# Ввод имени художника
async def handle_author_name(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in user_data and user_data[user_id].get('status') == 'awaiting_author_name':
        author_input = update.message.text.strip()

        # Проверка на то, заключен ли весь текст в "^...^" с учётом переносов строк
        if re.match(r'^\^(.*)\^$', author_input, re.S):
            # Извлекаем текст без символов "^", сохраняя переносы строк
            title = author_input[1:-1].strip()
            user_data[user_id]['title'] = title
            user_data[user_id]['author_name'] = ""  # Убираем имя автора
            user_data[user_id]['extra_phrase'] = ""  # Пустая фраза, если ничего не найдено
        else:
            # Проверка на наличие фразы в "^...^" в начале текста с учётом переносов строк
            match = re.match(r'^\^(.*?)\^\s*(.*)', author_input, re.S)
            if match:
                phrase = match.group(1).strip()  # Извлекаем фразу из "^...^", сохраняя переносы строк
                author_name = match.group(2).strip()  # Извлекаем остальное имя автора
                user_data[user_id]['extra_phrase'] = phrase  # Сохраняем фразу отдельно
            else:
                author_name = author_input.strip()  # Если нет фразы в "^...^", сохраняем как есть
                user_data[user_id]['extra_phrase'] = ""  # Пустая фраза, если ничего не найдено

            # Сохраняем имя автора как заголовок статьи
            user_data[user_id]['author_name'] = author_name
            user_data[user_id]['title'] = author_name  # Используем только имя автора для заголовка

        logger.info(f"User {user_id} provided author name or title: {author_input}")

        await update.message.reply_text('Отлично \n🌌Теперь приступим к наполнению публикации контентом, для этого отправьте изображения файлом (без сжатия) или текст. Если вы отправите изображение с подписью, то в статье телеграф текст тоже будет отображаться как подпись под изображением \n\n Текст поддерживает различное форматирование. Для получения списка тэгов и помощи введите /help. \n\n <i>Так же вы можете отправить содержание путем пересылки сообщений. Просто перешлите в бот сообщения содержащие текст и/или изображения в виде файлов и бот автоматически перенесёт всё это в статью в той же очерёдности</i>',    parse_mode='HTML')
        user_data[user_id]['status'] = 'awaiting_image'
        return ASKING_FOR_IMAGE
    else:
        await update.message.reply_text('🚫Ошибка: данные не найдены. Попробуйте снова или нажмите /restart')
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

# Функция для загрузки изображения на сloudinary
async def upload_image_to_cloudinary(file_path: str) -> str:
    CLOUDINARY_URL = 'https://api.cloudinary.com/v1_1/dmacjjaho/image/upload'
    UPLOAD_PRESET = 'ml_default'
    
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            form = aiohttp.FormData()
            form.add_field('file', f)
            form.add_field('upload_preset', UPLOAD_PRESET)

            async with session.post(CLOUDINARY_URL, data=form) as response:
                if response.status == 200:
                    response_json = await response.json()
                    return response_json['secure_url']
                else:
                    response_text = await response.text()  # Логируем текст ошибки
                    raise Exception(f"Ошибка загрузки на Cloudinary: {response.status}, ответ: {response_text}")


# Функция для загрузки изображения на imgbb
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

# Функция для загрузки изображения на Imgur
async def upload_image_to_imgur(file_path: str) -> str:
    IMGUR_CLIENT_ID = '5932e0bc7fdb523'  # Укажите свой ID клиента Imgur
    headers = {'Authorization': f'Client-ID {IMGUR_CLIENT_ID}'}
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            form = aiohttp.FormData()
            form.add_field('image', f)

            async with session.post('https://api.imgur.com/3/image', headers=headers, data=form) as response:
                if response.status == 200:
                    response_json = await response.json()
                    return response_json['data']['link']
                else:
                    raise Exception(f"Ошибка загрузки на Imgur: {response.status}")

# Функция для загрузки изображения на Catbox
async def upload_image_to_catbox(file_path: str) -> str:
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            form = aiohttp.FormData()
            form.add_field('reqtype', 'fileupload')
            form.add_field('fileToUpload', f)
            
            # Добавляем ваш userhash
            form.add_field('userhash', '1f68d2a125c66f6ab79a4f89c')

            async with session.post('https://catbox.moe/user/api.php', data=form) as response:
                if response.status == 200:
                    return await response.text()  # возвращает URL загруженного файла
                else:
                    raise Exception(f"Ошибка загрузки на Catbox: {response.status}")

async def upload_image_to_freeimage(file_path: str) -> str:
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            form = aiohttp.FormData()
            form.add_field('key', '6d207e02198a847aa98d0a2a901485a5')  # Ваш API ключ для freeimage.host
            form.add_field('action', 'upload')
            form.add_field('source', f)  # Используем файл для загрузки

            async with session.post('https://freeimage.host/api/1/upload', data=form) as response:
                if response.status == 200:
                    response_json = await response.json()
                    return response_json['image']['url']  # Проверьте правильность пути к URL в ответе
                elif response.status == 400:
                    response_text = await response.text()
                    raise Exception(f"Ошибка загрузки на Free Image Hosting: {response_text}")
                else:
                    raise Exception(f"Ошибка загрузки на Free Image Hosting: {response.status}")

# Основная функция загрузки изображения с проверкой доступности сервисов
async def upload_image(file_path: str) -> str:
    try:
        # Попытка загрузки на imgbb
        return await upload_image_to_imgbb(file_path)
    except Exception as e:
        logging.error(f"Ошибка загрузки на imgbb: {e}")
        try:
            # Попытка загрузки на Cloudinary
            return await upload_image_to_cloudinary(file_path)
        except Exception as e:
            logging.error(f"Ошибка загрузки на Cloudinary: {e}")
            try:
                # Попытка загрузки на Free Image Hosting
                return await upload_image_to_freeimage(file_path)
            except Exception as e:
                logging.error(f"Ошибка загрузки на Free Image Hosting: {e}")
                try:
                    # Попытка загрузки на Catbox
                    return await upload_image_to_catbox(file_path)
                except Exception as e:
                    logging.error(f"Ошибка загрузки на Catbox: {e}")
                    try:
                        # Попытка загрузки на Imgur
                        return await upload_image_to_imgur(file_path)
                    except Exception as e:
                        logging.error(f"Ошибка загрузки на Imgur: {e}")
                        raise Exception("Не удалось загрузить изображение на все сервисы.")


import re

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
    for node in temp_nodes:
        if isinstance(node, str):
            # Обрабатываем текст с разметкой
            while True:
                match = regex_markup.search(node)
                if not match:
                    # Если больше нет совпадений, добавляем оставшийся текст
                    nodes.append({"tag": "text", "children": [node]})
                    break
                # Добавляем текст до текущего совпадения
                if match.start() > 0:
                    nodes.append({"tag": "text", "children": [node[:match.start()]]})

                # Определяем тег и добавляем узел
                tag = markup_tags.get(match.group(1))
                if tag:
                    nodes.append({"tag": tag, "children": [match.group(2)]})

                # Обновляем строку: обрезаем её до конца текущего совпадения
                node = node[match.end():]
        else:
            nodes.append(node)

    return nodes
    

async def edit_article(update: Update, context: CallbackContext) -> None:
    # Проверяем, является ли обновление запросом обратного вызова (нажатие кнопки)
    if update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
    else:
        user_id = update.message.from_user.id  # Если это сообщение, получаем ID пользователя

    media = user_data[user_id].get('media', [])
    
    if not media:
        await update.message.reply_text("🚫 Ошибка: нет фрагментов для редактирования.")
        return

    # Удаляем предыдущее сообщение с кнопками содержания статьи
    if 'last_content_message_id' in user_data[user_id]:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,  # Используем effective_chat
                message_id=user_data[user_id]['last_content_message_id']
            )
        except Exception as e:
            print(f"Ошибка при удалении сообщения с содержанием: {e}")

    # Настройки пагинации
    items_per_page = 30  # Количество кнопок на странице
    total_pages = (len(media) + items_per_page - 1) // items_per_page  # Общее количество страниц
    current_page = user_data[user_id].get('current_page', 0)  # Текущая страница

    # Ограничиваем текущую страницу
    current_page = max(0, min(current_page, total_pages - 1))
    
    # Создаем новый список кнопок для текущей страницы
    keyboard = []
    image_counter = 1  # Счётчик для изображений
    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(media))

    for idx in range(start_idx, end_idx):
        item = media[idx]
        if item['type'] == 'text':
            text = item['content']
            if isinstance(text, dict) and 'children' in text:
                text = ''.join(child['children'][0] for child in text['children'] if isinstance(child, dict) and 'children' in child)
            preview_text = (text[:12] + '...') if len(text) > 12 else text
        else:
            preview_text = f"{image_counter} изображение"
            image_counter += 1
        
        keyboard.append([
            InlineKeyboardButton(text=str(preview_text), callback_data=f"preview_{idx}"),
            InlineKeyboardButton(text="Редактировать", callback_data=f"edit_{idx}"),
            InlineKeyboardButton(text="Удалить", callback_data=f"delete_{idx}"),
        ])

    # Добавляем кнопки навигации, если это не первая страница
    if current_page > 0:
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='page_down')])
    
    # Добавляем кнопки навигации, если это не последняя страница
    if current_page < total_pages - 1:
        keyboard.append([InlineKeyboardButton("Вперёд ➡️", callback_data='page_up')])
    
    keyboard.append([
        InlineKeyboardButton("🌌 Предпросмотр 🌌 ", callback_data='preview_article')
    ])    

    # Отправляем новое сообщение и сохраняем его ID
    sent_message = await (query.message if update.callback_query else update.message).reply_text(
        "Выберите фрагмент для редактирования или удаления:", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # Сохраняем ID нового сообщения с кнопками
    user_data[user_id]['last_content_message_id'] = sent_message.message_id
    user_data[user_id]['current_page'] = current_page  # Сохраняем текущую страницу




async def handle_edit_delete(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action, index = query.data.split('_')
    index = int(index)

    media = user_data[user_id].get('media', [])

    # Проверяем, существует ли фрагмент с таким индексом
    if index >= len(media):
        await query.message.reply_text("🚫 Ошибка: указанный индекс недействителен.")
        return

    if action == 'edit':
        # Если тип контента — изображение, предлагаем отправить новое изображение
        if media[index]['type'] == 'image':
            context.user_data['editing_index'] = index
            await query.message.reply_text("Пожалуйста, отправьте новое изображение или текст:")
            return ASKING_FOR_IMAGE  # Переход к ожиданию нового изображения
        # Если тип контента — текст, предлагаем ввести новый текст
        elif media[index]['type'] == 'text':
            context.user_data['editing_index'] = index
            await query.message.reply_text("Пожалуйста, отправьте новое изображение или текст:")
            return EDITING_FRAGMENT  # Переходим в состояние редактирования текста

    elif action == 'delete':
        if index < len(media):
            media.pop(index)
            user_data[user_id]['media'] = media  # Сохраняем изменения

            # Обновляем кнопки
# Количество кнопок на одной странице
            PAGE_SIZE = 30

            # Получаем текущую страницу из user_data (по умолчанию 1)
            if 'page' not in user_data[user_id]:
                user_data[user_id]['page'] = 1
            current_page = user_data[user_id]['page']

            # Обновляем кнопки
            keyboard = []
            image_counter = 1  # Счётчик для изображений

            # Подсчёт общего количества элементов
            total_items = len(media)
            total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE  # Рассчитываем количество страниц

            # Показ элементов только для текущей страницы
            start_idx = (current_page - 1) * PAGE_SIZE
            end_idx = start_idx + PAGE_SIZE

            for idx, item in enumerate(media[start_idx:end_idx], start=start_idx):
                if item['type'] == 'text':
                    text = item['content']
                    
                    # Извлечение текста, если нужно
                    if isinstance(text, dict) and 'children' in text:
                        text = ''.join(child['children'][0] for child in text['children'] if isinstance(child, dict) and 'children' in child)
                    
                    preview_text = (text[:12] + '...') if len(text) > 12 else text
                else:  # Если элемент — это изображение
                    preview_text = f"{image_counter} изображение"  # Нумерация только для изображений
                    image_counter += 1  # Увеличиваем счётчик только для изображений
                
                # Добавляем кнопки для текущей страницы
                keyboard.append([
                    InlineKeyboardButton(text=str(preview_text), callback_data=f"preview_{idx}"),
                    InlineKeyboardButton(text="Редактировать", callback_data=f"edit_{idx}"),
                    InlineKeyboardButton(text="Удалить", callback_data=f"delete_{idx}"),
                ])

            # Добавляем кнопки для переключения страниц
            navigation_buttons = []
            if current_page > 1:
                navigation_buttons.append(InlineKeyboardButton("⬆️ Предыдущая страница", callback_data=f"prev_page_{current_page - 1}"))
            if current_page < total_pages:
                navigation_buttons.append(InlineKeyboardButton("⬇️ Следующая страница", callback_data=f"next_page_{current_page + 1}"))

            if navigation_buttons:
                keyboard.append(navigation_buttons)

            # Добавляем кнопку предпросмотра
            keyboard.append([InlineKeyboardButton("🌌 Предпросмотр 🌌 ", callback_data='preview_article')])

            # Отправляем новое сообщение с обновлённым списком кнопок
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.edit_reply_markup(reply_markup=reply_markup)  # Обновляем клавиатуру

            await query.message.reply_text("✅ Фрагмент удалён.")
        return


async def handle_new_text(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    index = context.user_data['editing_index']
    media = user_data[user_id].get('media', [])

    # Убедимся, что индекс действителен
    if index >= 0 and index < len(media):
        # Если редактируемый элемент — это текст
        if media[index]['type'] == 'text':
            # Обновляем текст
            formatted_text = apply_markup(update.message.text)
            media[index] = {  # Обновляем существующий текст
                'type': 'text',
                'content': formatted_text
            }
            user_data[user_id]['media'] = media  # Сохраняем изменения

            # Удаляем предыдущее сообщение с кнопками содержания статьи
            if 'last_content_message_id' in user_data[user_id]:
                try:
                    await context.bot.delete_message(
                        chat_id=update.message.chat_id, 
                        message_id=user_data[user_id]['last_content_message_id']
                    )
                except Exception as e:
                    print(f"Ошибка при удалении сообщения с содержанием: {e}")

            # Настройки пагинации
            items_per_page = 30  # Количество кнопок на странице
            total_pages = (len(media) + items_per_page - 1) // items_per_page  # Общее количество страниц
            current_page = user_data[user_id].get('current_page', 0)  # Текущая страница

            # Ограничиваем текущую страницу
            current_page = max(0, min(current_page, total_pages - 1))


            # Создаём новый список кнопок для содержания статьи
    # Создаем новый список кнопок для текущей страницы
            keyboard = []
            image_counter = 1  # Счётчик для изображений
            start_idx = current_page * items_per_page
            end_idx = min(start_idx + items_per_page, len(media))

            for idx, item in enumerate(media):
                item = media[idx]
                if item['type'] == 'text':
                    text = item['content']
                    
                    # Извлечение текста, если нужно
                    if isinstance(text, dict) and 'children' in text:
                        text = ''.join(child['children'][0] for child in text['children'] if isinstance(child, dict) and 'children' in child)
                    
                    preview_text = (text[:12] + '...') if len(text) > 12 else text
                else:  # Если элемент — это изображение
                    preview_text = f"{image_counter} изображение"  # Нумерация только для изображений
                    image_counter += 1  # Увеличиваем счётчик только для изображений
                
                # Добавляем кнопки для предпросмотра, редактирования и удаления
                keyboard.append([
                    InlineKeyboardButton(text=str(preview_text), callback_data=f"preview_{idx}"),
                    InlineKeyboardButton(text="Редактировать", callback_data=f"edit_{idx}"),
                    InlineKeyboardButton(text="Удалить", callback_data=f"delete_{idx}"),
                ])

            if current_page > 0:
                keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='page_down')])
            
            # Добавляем кнопки навигации, если это не последняя страница
            if current_page < total_pages - 1:
                keyboard.append([InlineKeyboardButton("Вперёд ➡️", callback_data='page_up')])
            

            keyboard.append([
                InlineKeyboardButton("🌌 Предпросмотр 🌌 ", callback_data='preview_article')
            ])    

            # Отправляем новое сообщение с обновлённым списком кнопок
            reply_markup = InlineKeyboardMarkup(keyboard)
            sent_message = await context.bot.send_message(
                chat_id=update.message.chat_id,
                text='📝 Текущее содержание статьи2:',
                reply_markup=reply_markup
            )

            # Сохраняем ID нового сообщения с кнопками
            user_data[user_id]['last_content_message_id'] = sent_message.message_id
            user_data[user_id]['current_page'] = current_page  
            # Сообщаем пользователю об успешном обновлении текста
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text='✅ Текст обновлён.',
                reply_to_message_id=update.message.message_id
            )

            # Удаляем индекс редактирования после завершения
            del context.user_data['editing_index']

            return ASKING_FOR_IMAGE
        else:
            # Ошибка, если тип редактируемого элемента не текст
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text='🚫 Ошибка: указанный элемент не является текстом.',
                reply_to_message_id=update.message.message_id
            )
            del context.user_data['editing_index']  # Удаляем индекс, если он недействителен
            return ConversationHandler.END
    else:
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text='🚫 Ошибка: указанный индекс недействителен.',
            reply_to_message_id=update.message.message_id
        )
        del context.user_data['editing_index']  # Удаляем индекс, если он недействителен
        return ConversationHandler.END


async def handle_new_image(update: Update, context: CallbackContext, index: int, media: list) -> int:
    user_id = update.message.from_user.id
    message_id = update.message.message_id

    if update.message.photo or update.message.document:
        if update.message.photo:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text='🚫 Ошибка: пожалуйста, отправьте изображение как файл (формат JPG, PNG или .RAR для .GIF), без сжатия. Для подробностей введите /help',
                reply_to_message_id=message_id
            )
            return ASKING_FOR_IMAGE 

        elif update.message.document:
            file_name = update.message.document.file_name
            file_ext = file_name.lower().split('.')[-1]
            file = await context.bot.get_file(update.message.document.file_id)

        # Создаем временный файл для сохранения изображения
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
            file_path = tmp_file.name
            await file.download_to_drive(file_path)

        if file_ext == 'rar':
            new_file_path = f'{os.path.splitext(file_path)[0]}.gif'
            shutil.move(file_path, new_file_path)
            file_path = new_file_path
            file_name = os.path.basename(file_path)
            file_ext = 'gif'

        if file_ext in ('jpg', 'jpeg', 'png', 'gif'):
            if file_ext == 'gif':
                try:
                    image_url = await upload_image(file_path)
                    media[index] = {  # Обновляем существующее изображение
                        'type': 'image',
                        'url': image_url,
                        'caption': update.message.caption if update.message.caption else ""
                    }
                    user_data[user_id]['media'] = media  # Сохраняем изменения

                    # Удаляем предыдущее сообщение, если оно есть
                    if 'last_image_message_id' in user_data[user_id]:
                        try:
                            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=user_data[user_id]['last_image_message_id'])
                        except Exception as e:
                            print(f"Ошибка при удалении сообщения: {e}")

                    # Отправляем новое сообщение
                    sent_message = await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text='✅ Изображение очень обновлено.',
                        reply_to_message_id=message_id
                    )

                    # Сохраняем ID нового сообщения
                    user_data[user_id]['last_image_message_id'] = sent_message.message_id

                    # Удаляем индекс редактирования после завершения
                    del context.user_data['editing_index']

                    return ASKING_FOR_IMAGE
                except Exception as e:
                    await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text=f'🚫 Ошибка при загрузке изображения: {str(e)}. Попробуйте снова.',
                        reply_to_message_id=message_id
                    )
                    return ConversationHandler.END

            else:
                if os.path.getsize(file_path) > 5 * 1024 * 1024:
                    compressed_path = f'{os.path.splitext(file_path)[0]}_compressed.jpg'
                    compress_image(file_path, compressed_path)
                    file_path = compressed_path

                try:
                    image_url = await upload_image(file_path)
                    media[index] = {  # Обновляем существующее изображение
                        'type': 'image',
                        'url': image_url,
                        'caption': update.message.caption if update.message.caption else ""
                    }
                    user_data[user_id]['media'] = media  # Сохраняем изменения
                    os.remove(file_path)

                    # Удаляем предыдущее сообщение, если оно есть
                    if 'last_image_message_id' in user_data[user_id]:
                        try:
                            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=user_data[user_id]['last_image_message_id'])
                        except Exception as e:
                            print(f"Ошибка при удалении сообщения: {e}")

                    # Отправляем новое сообщение
                    sent_message = await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text='✅ Изображение добавлено.',
                        reply_to_message_id=message_id
                    )

                    # Удаляем предыдущее сообщение с кнопками содержания статьи, если оно существует
                    if 'last_content_message_id' in user_data[user_id]:
                        try:
                            await context.bot.delete_message(
                                chat_id=update.message.chat_id, 
                                message_id=user_data[user_id]['last_content_message_id']
                            )
                        except Exception as e:
                            print(f"Ошибка при удалении сообщения с содержанием: {e}")


                    # Настройки пагинации
                    items_per_page = 30  # Количество кнопок на странице
                    total_pages = (len(media) + items_per_page - 1) // items_per_page  # Общее количество страниц
                    current_page = user_data[user_id].get('current_page', 0)  # Текущая страница

                    # Ограничиваем текущую страницу
                    current_page = max(0, min(current_page, total_pages - 1))

                    # Создаём новый список кнопок для содержания статьи
                    keyboard = []
                    image_counter = 1  # Счётчик для изображений
                    start_idx = current_page * items_per_page
                    end_idx = min(start_idx + items_per_page, len(media))
                    for idx in range(start_idx, end_idx):
                        item = media[idx]
                        if item['type'] == 'text':
                            text = item['content']
                            
                            # Извлечение текста, если нужно
                            if isinstance(text, dict) and 'children' in text:
                                text = ''.join(child['children'][0] for child in text['children'] if isinstance(child, dict) and 'children' in child)
                            
                            preview_text = (text[:12] + '...') if len(text) > 12 else text
                        else:  # Если элемент — это изображение
                            preview_text = f"Обн изображение"  # Нумерация только для изображений
                            image_counter += 1  # Увеличиваем счётчик только для изображений
                        
                        # Добавляем кнопки для предпросмотра, редактирования и удаления
                        keyboard.append([
                            InlineKeyboardButton(text=str(preview_text), callback_data=f"preview_{idx}"),
                            InlineKeyboardButton(text="Редактировать", callback_data=f"edit_{idx}"),
                            InlineKeyboardButton(text="Удалить", callback_data=f"delete_{idx}"),
                        ])

                    if current_page > 0:
                        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='page_down')])
                    
                    # Добавляем кнопки навигации, если это не последняя страница
                    if current_page < total_pages - 1:
                        keyboard.append([InlineKeyboardButton("Вперёд ➡️", callback_data='page_up')])
                    
                    keyboard.append([
                        InlineKeyboardButton("🌌 Предпросмотр 🌌 ", callback_data='preview_article')
                    ])    

                    # Отправляем новое сообщение с обновлённым списком кнопок
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    sent_message = await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text='📝 Текущее содержание статьи1:',
                        reply_markup=reply_markup
                    )

                    # Сохраняем ID нового сообщения с кнопками
                    user_data[user_id]['last_content_message_id'] = sent_message.message_id
                    user_data[user_id]['current_page'] = current_page  

                    # Удаляем индекс редактирования после завершения
                    del context.user_data['editing_index']

                    return ASKING_FOR_IMAGE
                except Exception as e:
                    await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text=f'🚫 Ошибка при загрузке изображения: {str(e)}. Попробуйте снова.',
                        reply_to_message_id=message_id
                    )
                    return ConversationHandler.END

        else:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text='Пожалуйста, отправьте изображение в формате JPG, PNG или .RAR для .GIF.',
                reply_to_message_id=message_id
            )
            return ASKING_FOR_IMAGE
    else:
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text='🚫 Ошибка: ожидается изображение или файл.',
            reply_to_message_id=message_id
        )
        return ConversationHandler.END



# Обновленная функция handle_image для обработки изображений
async def handle_image(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    caption = update.message.caption
    message_id = update.message.message_id

    # Проверяем, редактирует ли пользователь что-либо
    if 'editing_index' in context.user_data:
        index = context.user_data['editing_index']
        media = user_data[user_id].get('media', [])

        # Проверяем, если индекс действителен
        if 0 <= index < len(media):
            # Проверяем, если редактируем текст, и если получен текст
            if media[index]['type'] == 'text':
                # Если пользователь прислал текст, обрабатываем его как текст
                if update.message.text:
                    return await handle_new_text_from_image(update, context, index, media)

                # Если вместо текста пришло изображение
                if update.message.photo or update.message.document:
                    return await handle_new_image(update, context, index, media)

            # Проверяем, если редактируем изображение
            if media[index]['type'] == 'image':
                # Проверяем, если пользователь отправил текст вместо изображения
                if update.message.text:
                    return await handle_new_text_from_image(update, context, index, media)

                # Проверка фото
                if update.message.photo:
                    await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text='Пожалуйста, отправьте изображение как файл (формат JPG, PNG или .RAR для .GIF), без сжатия. Для подробностей введите /help',
                        reply_to_message_id=message_id
                    )
                    return ASKING_FOR_IMAGE

                elif update.message.document:
                    file_name = update.message.document.file_name
                    if file_name:  # Проверка, что файл имеет имя
                        file_ext = file_name.lower().split('.')[-1]

                        # Если не удается определить расширение, выходим
                        if not file_ext:
                            await context.bot.send_message(
                                chat_id=update.message.chat_id,
                                text='🚫 Ошибка: не удалось определить расширение файла. Пожалуйста, отправьте файл с правильным расширением.',
                                reply_to_message_id=message_id
                            )
                            return ConversationHandler.END

                        file = await context.bot.get_file(update.message.document.file_id)
                        # Скачивание и создание временного файла
                        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
                            file_path = tmp_file.name
                            await file.download_to_drive(file_path)                    

                # Обработка документа

                        if file_ext == 'rar':
                            new_file_path = f'{os.path.splitext(file_path)[0]}.gif'
                            shutil.move(file_path, new_file_path)
                            file_path = new_file_path
                            file_name = os.path.basename(file_path)
                            file_ext = 'gif'

                        if file_ext in ('jpg', 'jpeg', 'png', 'gif'):
                            if file_ext == 'gif':
                                try:
                                    image_url = await upload_image(file_path)
                                    media[index] = {  # Обновляем существующее изображение
                                        'type': 'image',
                                        'url': image_url,
                                        'caption': caption if caption else ""
                                    }
                                    user_data[user_id]['media'] = media  # Сохраняем изменения

                                    # Удаляем предыдущее сообщение, если оно есть
                                    if 'last_image_message_id' in user_data[user_id]:
                                        try:
                                            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=user_data[user_id]['last_image_message_id'])
                                        except Exception as e:
                                            print(f"Ошибка при удалении сообщения: {e}")

                                    # Отправляем новое сообщение
                                    sent_message = await context.bot.send_message(
                                        chat_id=update.message.chat_id,
                                        text='✅ Изображение замечательно обновлено.',
                                        reply_to_message_id=message_id
                                    )

                                    # Сохраняем ID нового сообщения
                                    user_data[user_id]['last_image_message_id'] = sent_message.message_id

                                    # Удаляем индекс редактирования после завершения
                                    del context.user_data['editing_index']

                                    return ASKING_FOR_IMAGE
                                except Exception as e:
                                    await context.bot.send_message(
                                        chat_id=update.message.chat_id,
                                        text=f'🚫 Ошибка при загрузке изображения: {str(e)}. Попробуйте снова.',
                                        reply_to_message_id=message_id
                                    )
                                    return ConversationHandler.END
                            else:
                                if os.path.getsize(file_path) > 5 * 1024 * 1024:
                                    compressed_path = f'{os.path.splitext(file_path)[0]}_compressed.jpg'
                                    compress_image(file_path, compressed_path)
                                    file_path = compressed_path

                                try:




                                    image_url = await upload_image(file_path)
                                    media[index] = {  # Обновляем существующее изображение
                                        'type': 'image',
                                        'url': image_url,
                                        'caption': caption if caption else ""
                                    }
                                    user_data[user_id]['media'] = media # Сохраняем изменения
                                    os.remove(file_path)

                                    # Удаляем предыдущее сообщение, если оно есть
                                    if 'last_image_message_id' in user_data[user_id]:
                                        try:
                                            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=user_data[user_id]['last_image_message_id'])
                                        except Exception as e:
                                            print(f"Ошибка при удалении сообщения: {e}")

                                    # Отправляем новое сообщение
                                    sent_message = await context.bot.send_message(
                                        chat_id=update.message.chat_id,
                                        text='✅ Изображение Заменено.',
                                        reply_to_message_id=message_id
                                    )

                                    # Сохраняем ID нового сообщения
                                    user_data[user_id]['last_image_message_id'] = sent_message.message_id

                                    # Удаляем индекс редактирования после завершения
                                    del context.user_data['editing_index']

                                    return ASKING_FOR_IMAGE
                                except Exception as e:
                                    await context.bot.send_message(
                                        chat_id=update.message.chat_id,
                                        text=f'🚫 Ошибка при загрузке изображения: {str(e)}. Попробуйте снова.',
                                        reply_to_message_id=message_id
                                    )
                                    return ConversationHandler.END

                        else:
                            await context.bot.send_message(
                                chat_id=update.message.chat_id,
                                text='Пожалуйста, отправьте изображение в формате JPG, PNG или .RAR для .GIF.',
                                reply_to_message_id=message_id
                            )
                            return ASKING_FOR_IMAGE

                    elif media[index]['type'] == 'text':
                        # Если редактируем текст, вызываем обработчик текста
                        return await handle_new_text(update, context)
                    else:
                        await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text='🚫 Ошибка: указанный элемент имеет недопустимый тип.',
                            reply_to_message_id=message_id
                        )
                        del context.user_data['editing_index']
                        return ConversationHandler.END
                else:
                    await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text='🚫 Ошибка: указанный индекс изображения недействителен.',
                        reply_to_message_id=message_id
                    )
                    del context.user_data['editing_index']  # Удаляем индекс, если он недействителен
                    return ConversationHandler.END

    # Если не в состоянии редактирования, продолжаем обычную обработку изображений
    if user_id in user_data and user_data[user_id]['status'] == 'awaiting_image':
        if update.message.photo:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text='Пожалуйста, отправьте изображение как файл (формат JPG, PNG или .RAR для .GIF), без сжатия. Для подробностей введите /help',
                reply_to_message_id=message_id
            )
            return ASKING_FOR_IMAGE

        elif update.message.document:
            file_name = update.message.document.file_name
            file_ext = file_name.lower().split('.')[-1]
            file = await context.bot.get_file(update.message.document.file_id)

            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
                file_path = tmp_file.name
                await file.download_to_drive(file_path)

            if file_ext == 'rar':
                new_file_path = f'{os.path.splitext(file_path)[0]}.gif'
                shutil.move(file_path, new_file_path)
                file_path = new_file_path
                file_name = os.path.basename(file_path)
                file_ext = 'gif'

            if file_ext in ('jpg', 'jpeg', 'png', 'gif'):
                if file_ext == 'gif':
                    try:
                        image_url = await upload_image(file_path)
                        if 'media' not in user_data[user_id]:
                            user_data[user_id]['media'] = []
                        user_data[user_id]['media'].append({
                            'type': 'image',
                            'url': image_url,
                            'caption': caption if caption else ""
                        })

                        # Удаляем предыдущее сообщение, если оно есть
                        if 'last_image_message_id' in user_data[user_id]:
                            try:
                                await context.bot.delete_message(chat_id=update.message.chat_id, message_id=user_data[user_id]['last_image_message_id'])
                            except Exception as e:
                                print(f"Ошибка при удалении сообщения: {e}")

                        keyboard = [
                            [InlineKeyboardButton("‼️Сброс Публикации и Возврат к Началу‼️", callback_data='restart')],
                            [InlineKeyboardButton("Удалить последний элемент", callback_data='delete_last')],
                            [InlineKeyboardButton("Предпросмотр", callback_data='preview_article')],
                            [InlineKeyboardButton("Редактировать", callback_data='edit_article')],
                            [InlineKeyboardButton("Помощь и разметка", callback_data='help_command')],
                            [InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')]
                        ]

                        reply_markup = InlineKeyboardMarkup(keyboard)                                

                        if 'image_counter' not in user_data[user_id]:
                            user_data[user_id]['image_counter'] = 0

                        # Когда бот получает изображение, увеличиваем счётчик
                        user_data[user_id]['image_counter'] += 1
                        image_counter = user_data[user_id]['image_counter']

                        # Используем счётчик в сообщении
                        image_text = "изображение" if image_counter == 1 else "изображения"
                        sent_message = await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text=f'✅ {image_counter} {image_text} добавлено.\n\n Дождитесь загрузки остальных изображений, если их больше чем одно. Затем вы можете продолжить присылать изображения или текст.\n\n Так же вы можете использовать следующие команды:',
                            reply_to_message_id=message_id,
                            reply_markup=reply_markup
                        )

                        # Сохраняем ID нового сообщения
                        user_data[user_id]['last_image_message_id'] = sent_message.message_id

                        return ASKING_FOR_IMAGE
                    except Exception as e:
                        await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text=f'🚫Ошибка при загрузке изображения: {str(e)}. Можете попробовать прислать файл ещё раз через некоторое время или нажать /restart',
                            reply_to_message_id=message_id
                        )
                        return ConversationHandler.END
                else:
                    if os.path.getsize(file_path) > 5 * 1024 * 1024:
                        compressed_path = f'{os.path.splitext(file_path)[0]}_compressed.jpg'
                        compress_image(file_path, compressed_path)
                        file_path = compressed_path

                    try:
                        image_url = await upload_image(file_path)
                        if 'media' not in user_data[user_id]:
                            user_data[user_id]['media'] = []
                        user_data[user_id]['media'].append({
                            'type': 'image',
                            'url': image_url,
                            'caption': caption if caption else ""
                        })
                        os.remove(file_path)

                        # Удаляем предыдущее сообщение, если оно есть
                        if 'last_image_message_id' in user_data[user_id]:
                            try:
                                await context.bot.delete_message(chat_id=update.message.chat_id, message_id=user_data[user_id]['last_image_message_id'])
                            except Exception as e:
                                print(f"Ошибка при удалении сообщения: {e}")

                        keyboard = [
                            [InlineKeyboardButton("‼️Сброс Публикации и Возврат к Началу‼️", callback_data='restart')],
                            [InlineKeyboardButton("Удалить последний элемент", callback_data='delete_last')],
                            [InlineKeyboardButton("Предпросмотр", callback_data='preview_article')],
                            [InlineKeyboardButton("Редактировать", callback_data='edit_article')],
                            [InlineKeyboardButton("Помощь и разметка", callback_data='help_command')],
                            [InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')]
                        ]

                        reply_markup = InlineKeyboardMarkup(keyboard) 


                        if 'image_counter' not in user_data[user_id]:
                            user_data[user_id]['image_counter'] = 0

                        # Когда бот получает изображение, увеличиваем счётчик
                        user_data[user_id]['image_counter'] += 1
                        image_counter = user_data[user_id]['image_counter']

                        # Используем счётчик в сообщении
                        image_text = "изображение" if image_counter == 1 else "изображения"
                        sent_message = await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text=f'✅ {image_counter} {image_text} добавлено.\n\n Дождитесь загрузки остальных изображений, если их больше чем одно. Затем вы можете продолжить присылать изображения или текст.\n\n Так же вы можете использовать следующие команды:',
                            reply_to_message_id=message_id,
                            reply_markup=reply_markup
                        )

                        # Сохраняем ID нового сообщения
                        user_data[user_id]['last_image_message_id'] = sent_message.message_id

                        return ASKING_FOR_IMAGE
                    except Exception as e:
                        await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text=f'🚫Ошибка при загрузке изображения: {str(e)}. Можете попробовать прислать файл ещё раз через некоторое время или нажать /restart',
                            reply_to_message_id=message_id
                        )
                        return ConversationHandler.END

            else:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text='Пожалуйста, отправьте изображение в формате JPG, PNG или .RAR для .GIF.',
                    reply_to_message_id=message_id
                )
                return ASKING_FOR_IMAGE

        elif update.message.text:
            return await handle_text(update, context)

        else:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text='Пожалуйста, отправьте изображение как файл (формат JPG, PNG или .RAR для .GIF), без сжатия, или текст.',
                reply_to_message_id=message_id
            )
            return ASKING_FOR_IMAGE

    else:
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text='🚫Ошибка: данные не найдены. Попробуйте отправить снова. Или нажмите /restart',
            reply_to_message_id=message_id
        )
        return ConversationHandler.END

# Функция для обработки текстовых сообщений
async def handle_text(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    message_text = update.message.text

    # Если не в режиме редактирования, продолжаем обычную обработку текстовых сообщений
    user_data_entry = user_data.get(user_id, {})

    # Проверяем статус пользователя
    if user_data_entry.get('status') == 'awaiting_image':
        # Обработка текстовых сообщений с разметкой
        formatted_text = apply_markup(message_text)

        # Проверка наличия раздела 'media' и добавление текста
        if 'media' not in user_data_entry:
            user_data_entry['media'] = []

        user_data_entry['media'].append({'type': 'text', 'content': formatted_text})

        # Сохраняем обновлённые данные
        user_data[user_id] = user_data_entry

        # Удаление предыдущего сообщения, если оно существует
        if 'last_message_id' in user_data_entry:
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, 
                    message_id=user_data_entry['last_message_id']
                )
            except Exception as e:
                print(f"Ошибка при удалении сообщения: {e}")

        # Отправляем новое сообщение


        keyboard = [
            [InlineKeyboardButton("‼️Сброс Публикации и Возврат к Началу‼️", callback_data='restart')],
            [InlineKeyboardButton("Удалить последний элемент", callback_data='delete_last')],
            [InlineKeyboardButton("Предпросмотр", callback_data='preview_article')],
            [InlineKeyboardButton("Редактировать", callback_data='edit_article')],
            [InlineKeyboardButton("Помощь и разметка", callback_data='help_command')],
            [InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')]
 # Новая кнопка
        ]

        reply_markup = InlineKeyboardMarkup(keyboard) 

        if 'text_counter' not in user_data[user_id]:
            user_data[user_id]['text_counter'] = 0

        # Когда бот получает текст, увеличиваем счётчик
        user_data[user_id]['text_counter'] += 1
        text_counter = user_data[user_id]['text_counter']

        # Используем счётчик текста в сообщении
        text_message = "текст" if text_counter == 1 else "текста"
        sent_message = await update.message.reply_text(
            f'✅ {text_counter} {text_message} успешно добавлено. Вы можете отправить ещё текст или изображения.\n\n'
            'Либо воспользоваться одной из команд ниже:\n',
            reply_to_message_id=update.message.message_id,
            reply_markup=reply_markup  # Добавляем клавиатуру с кнопкой
        )
        # Сохраняем ID нового сообщения
        user_data_entry['last_message_id'] = sent_message.message_id
        user_data[user_id] = user_data_entry

        return ASKING_FOR_IMAGE
    else:
        await update.message.reply_text('🚫 Ошибка: данные не найдены. Попробуйте отправить снова. Или нажмите /restart')
        return ConversationHandler.END
        

async def handle_new_text_from_image(update: Update, context: CallbackContext, index, media) -> int:
    user_id = update.message.from_user.id
    message_text = update.message.text

    # Проверка наличия данных пользователя и медиа
    if user_id not in user_data or 'media' not in user_data[user_id]:
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text='🚫 Ошибка: данные пользователя не найдены. Попробуйте снова.',
            reply_to_message_id=update.message.message_id
        )
        return ConversationHandler.END

    # Проверка корректности индекса
    if not (0 <= index < len(media)):
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text='🚫 Ошибка: недопустимый индекс редактируемого элемента.',
            reply_to_message_id=update.message.message_id
        )
        return ConversationHandler.END

    # Применение разметки к тексту
    formatted_text = apply_markup(message_text)

    # Замена изображения на текст в media
    media[index] = {
        'type': 'text',
        'content': formatted_text
    }
    user_data[user_id]['media'] = media  # Обновляем данные пользователя

    # Уведомление пользователя
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text='✅ Содержание изменено.',
        reply_to_message_id=update.message.message_id
    )

    # Удаляем индекс редактирования только после успешной замены
    del context.user_data['editing_index']

    # Удаляем предыдущее сообщение с кнопками содержания статьи, если оно существует
    if 'last_content_message_id' in user_data[user_id]:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, 
                message_id=user_data[user_id]['last_content_message_id']
            )
        except Exception as e:
            print(f"Ошибка при удалении сообщения с содержанием: {e}")

        # Настройки пагинации
    items_per_page = 30  # Количество кнопок на странице
    total_pages = (len(media) + items_per_page - 1) // items_per_page  # Общее количество страниц
    current_page = user_data[user_id].get('current_page', 0)  # Текущая страница

    # Ограничиваем текущую страницу
    current_page = max(0, min(current_page, total_pages - 1))        

    # Создаём новый список кнопок для содержания статьи
    keyboard = []
    image_counter = 1  # Счётчик для изображений
    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(media))
    for idx in range(start_idx, end_idx):
        item = media[idx]
        if item['type'] == 'text':
            text = item['content']
            
            # Извлечение текста, если нужно
            if isinstance(text, dict) and 'children' in text:
                text = ''.join(child['children'][0] for child in text['children'] if isinstance(child, dict) and 'children' in child)
            
            preview_text = (text[:12] + '...') if len(text) > 12 else text
        else:  # Если элемент — это изображение
            preview_text = f"{image_counter} изображение"  # Нумерация только для изображений
            image_counter += 1  # Увеличиваем счётчик только для изображений
        
        # Добавляем кнопки для предпросмотра, редактирования и удаления
        keyboard.append([
            InlineKeyboardButton(text=str(preview_text), callback_data=f"preview_{idx}"),
            InlineKeyboardButton(text="Редактировать", callback_data=f"edit_{idx}"),
            InlineKeyboardButton(text="Удалить", callback_data=f"delete_{idx}"),
        ])
    # Добавляем кнопки навигации, если это не первая страница
    if current_page > 0:
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='page_down')])
    
    # Добавляем кнопки навигации, если это не последняя страница
    if current_page < total_pages - 1:
        keyboard.append([InlineKeyboardButton("Вперёд ➡️", callback_data='page_up')])
    
    keyboard.append([
        InlineKeyboardButton("🌌 Предпросмотр 🌌 ", callback_data='preview_article')
    ])       

    # Отправляем новое сообщение с обновлённым списком кнопок
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent_message = await context.bot.send_message(
        chat_id=update.message.chat_id,
        text='📝 Текущее содержание статьи3:',
        reply_markup=reply_markup
    )

    # Сохраняем ID нового сообщения с кнопками
    user_data[user_id]['last_content_message_id'] = sent_message.message_id
    user_data[user_id]['current_page'] = current_page 

    del context.user_data['editing_index']

    return ASKING_FOR_IMAGE
    

@retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
def make_request(url, data):
    response = requests.post(url, json=data, timeout=30)
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
    # Определяем, является ли событие сообщением или callback-запросом
    if update.message:
        message_to_reply = update.message
    elif update.callback_query:
        message_to_reply = update.callback_query.message
    else:
        return False  # Не удалось определить источник

    while retries < max_retries:
        try:
            await message_to_reply.reply_media_group(media_group)
            return True  # Успешная отправка
        except Exception as e:
            logger.error(f"Failed to send media group: {e}")
            retries += 1
            if retries < max_retries:
                logger.info(f"Retrying in {delay} seconds... (Attempt {retries}/{max_retries})")
                await asyncio.sleep(delay)
    return False  # Если все попытки не удались

# Метод для отправки одного изображения с повторными попытками и задержкой
async def send_photo_with_retries(update, photo_url, caption, parse_mode, reply_markup=None, max_retries=3, delay=2):
    retries = 0
    # Определяем, является ли событие сообщением или callback-запросом
    if update.message:
        message_to_reply = update.message
    elif update.callback_query:
        message_to_reply = update.callback_query.message
    else:
        return False  # Не удалось определить источник

    while retries < max_retries:
        try:
            await message_to_reply.reply_photo(
                photo=photo_url,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup  # Добавляем возможность передать клавиатуру с кнопками
            )
            return True  # Успешная отправка
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")
            retries += 1
            if retries < max_retries:
                logger.info(f"Retrying in {delay} seconds... (Attempt {retries}/{max_retries})")
                await asyncio.sleep(delay)
    return False  # Если все попытки не удались

# Функция для рекурсивного поиска изображений
def count_images_in_content(content):
    image_count = 0
    for item in content:
        if isinstance(item, dict):
            if item.get('tag') == 'img':
                image_count += 1
            elif item.get('tag') == 'figure' and 'children' in item:
                # Если есть тег figure, проверяем его содержимое
                image_count += count_images_in_content(item['children'])
    return image_count


async def delete_last(update: Update, context: CallbackContext) -> None:
    # Определяем, откуда пришёл запрос - через команду или через кнопку
    if update.message:  # Если это сообщение
        user_id = update.message.from_user.id
        chat_id = update.message.chat_id
        message_id = update.message.message_id
    elif update.callback_query:  # Если это callback через кнопку
        user_id = update.callback_query.from_user.id
        chat_id = update.callback_query.message.chat_id
        message_id = update.callback_query.message.message_id
    else:
        return  # Если это что-то другое, то ничего не делаем

    if user_id in user_data and 'media' in user_data[user_id]:
        if user_data[user_id]['media']:
            last_item = user_data[user_id]['media'].pop()  # Удаляем последний элемент
            item_type = last_item['type']
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Удалён последний элемент типа: {item_type}\n\nДля предпросмотра введите команду /preview",
                reply_to_message_id=message_id
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Ваша статья пуста. Нет элементов для удаления.",
                reply_to_message_id=message_id
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="У вас нет активной статьи для редактирования. Используйте /start для начала.",
            reply_to_message_id=message_id
        )   


async def preview_article(update: Update, context: CallbackContext) -> None:
    # Проверяем, вызвано ли через сообщение или инлайн-кнопку
    if update.message:
        user_id = update.message.from_user.id
    elif update.callback_query:
        user_id = update.callback_query.from_user.id
    else:
        return

    if user_id in user_data:
        try:
            author_name = "Anemone"
            author_link = "https://t.me/anemonn"
            artist_link = user_data[user_id].get('artist_link', '')
            media = user_data[user_id].get('media', [])
            title = user_data[user_id].get('title', 'Предпросмотр статьи')

            # Создаём контент для страницы
            content = [{'tag': 'p', 'children': [{'tag': 'a', 'attrs': {'href': artist_link}, 'children': [artist_link]}]}]

            # Добавление изображений с разделителями
            for index, item in enumerate(media):
                if item['type'] == 'text':
                    content.append({'tag': 'p', 'children': [item['content']]})
                elif item['type'] == 'image':
                    # Создаем фигуру с изображением и подписью
                    figure_content = [{'tag': 'img', 'attrs': {'src': item['url']}}]
                    if item.get('caption'):
                        figure_content.append({'tag': 'figcaption', 'children': [item['caption']]})

                    content.append({'tag': 'figure', 'children': figure_content})

                    # Добавление разделителя после изображения, если это не последнее изображение
                    if index < len(media) - 1:
                        content.append({'tag': 'hr'})

            # Создание статьи в Telegra.ph
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
                preview_url = f"https://telegra.ph/{response_json['result']['path']}"

                # Создание кнопки
                keyboard = [[InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Отправляем предпросмотр пользователю
                if update.message:
                    await update.message.reply_text(f'Предпросмотр статьи: {preview_url}', reply_markup=reply_markup)
                elif update.callback_query:
                    await update.callback_query.message.reply_text(f'Предпросмотр статьи: {preview_url}', reply_markup=reply_markup)
            else:
                if update.message:
                    await update.message.reply_text('Ошибка при создании предпросмотра статьи.')
                elif update.callback_query:
                    await update.callback_query.message.reply_text('Ошибка при создании предпросмотра статьи.')

        except requests.RequestException as e:
            if update.message:
                await update.message.reply_text(f'Ошибка при создании предпросмотра: {e}')
            elif update.callback_query:
                await update.callback_query.message.reply_text(f'Ошибка при создании предпросмотра: {e}')
    else:
        if update.message:
            await update.message.reply_text('Нет данных для предпросмотра. Начните с отправки текста или изображений.')
        elif update.callback_query:
            await update.callback_query.message.reply_text('Нет данных для предпросмотра. Начните с отправки текста или изображений.')


async def handle_preview_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    if query.data == 'preview_article':
        await preview_article(update, context)

async def handle_delete_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    if query.data == 'delete_last':
        await delete_last(update, context)


async def handle_help_text_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    if query.data == 'help_command':
        await help_command(update, context)


async def handle_create_article_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Ответ на нажатие

    # Вызываем функцию publish, которая создаёт статью
    await publish(update, context)


async def handle_restart_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    if query.data == 'restart':
        await restart(update, context)

async def handle_edit_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    if query.data == 'edit_article':
        await edit_article(update, context)  

# Добавьте обработчик для переключения страниц
async def handle_page_change(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    
    if query.data == 'page_down':
        user_data[user_id]['current_page'] -= 1
    elif query.data == 'page_up':
        user_data[user_id]['current_page'] += 1

    await edit_article(update, context)  # Повторно вызываем функцию редактирования




# Функция для рекурсивного поиска изображений
def count_images_in_content(content):
    image_count = 0
    for item in content:
        if isinstance(item, dict):
            if item.get('tag') == 'img':
                image_count += 1
            elif item.get('tag') == 'figure' and 'children' in item:
                # Если есть тег figure, проверяем его содержимое
                image_count += count_images_in_content(item['children'])
    return image_count

# Основная функция публикации
async def publish(update: Update, context: CallbackContext) -> None:
    # Проверяем, пришло ли событие от сообщения или от callback_query
    if update.message:
        user_id = update.message.from_user.id
        message_to_reply = update.message
    elif update.callback_query:
        user_id = update.callback_query.from_user.id
        message_to_reply = update.callback_query.message
    else:
        return  # Если ни того, ни другого нет, просто выйдем

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
                    # Создаем фигуру с изображением и подписью
                    figure_content = [
                        {'tag': 'img', 'attrs': {'src': item['url']}},
                    ]
                    if item.get('caption'):
                        figure_content.append({'tag': 'figcaption', 'children': [item['caption']]})

                    content.append({'tag': 'figure', 'children': figure_content})

                    if index < len(media) - 1:
                        content.append({'tag': 'hr'})

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

                article_response = requests.get(f'https://api.telegra.ph/getPage?access_token={TELEGRAPH_TOKEN}&path={response_json["result"]["path"]}&return_content=true')
                article_response.raise_for_status()
                article_data = article_response.json()

                image_count = count_images_in_content(content)
                logger.info(f"Number of images detected: {image_count}")

                if image_count > 1:
                    # Фильтруем только изображения, чтобы избежать смешивания с текстом
                    image_media = [item for item in media if item['type'] == 'image']
                    
                    # Разделение только изображений на группы по 10
                    media_groups = [image_media[i:i + 10] for i in range(0, len(image_media), 10)]
                    media_group_data = []
                    
                    # Для хранения информации о том, был ли добавлен текст
                    text_added = False

                    for group in media_groups:
                        media_group = []

                        for idx, item in enumerate(group):
                            caption = None
                            
                            # Если текст ещё не добавлен, добавляем подпись к первому изображению
                            if not text_added:
                                caption = f'{author_line}\n<a href="{article_url}">Оригинал</a>'
                                text_added = True

                            # Добавляем только изображения в медиа-группу
                            media_group.append(InputMediaPhoto(media=item['url'], caption=caption, parse_mode='HTML' if caption else None))
                            
                            # Запоминаем данные для последующего использования
                            media_group_data.append({
                                "file_id": item['url'],
                                "caption": caption,
                                "parse_mode": 'HTML' if caption else None
                            })

                        # Используем функцию для повторных попыток отправки медиа-группы
                        success = await send_media_group_with_retries(update, media_group)
                        if not success:
                            await message_to_reply.reply_text(f'🚫Ошибка при отправке медиа-группы.')
                            return

                    media_group_storage[user_id] = media_group_data



                if image_count == 1:
                    single_image = next((item for item in media if item['type'] == 'image'), None)
                    if single_image:
                        caption = f'{author_line}\n<a href="{article_url}">Оригинал</a>'
                        
                        media_group_storage[user_id] = [{
                            "file_id": single_image['url'],
                            "caption": caption,
                            "parse_mode": 'HTML'
                        }]
                        
                        # Проверяем, откуда пришел вызов - из команды или инлайн-кнопки
                        success = await send_photo_with_retries(
                            update=update,
                            photo_url=single_image['url'],
                            caption=caption,
                            parse_mode='HTML',
                            reply_markup=create_publish_button(user_id)
                        )
                        if not success:
                            await message_to_reply.reply_text('🚫Ошибка при отправке изображения. /restart')
                            return

                elif image_count == 0:
                    message_with_link = f'{author_line}\n<a href="{article_url}">Оригинал</a>'
                    await message_to_reply.reply_text(message_with_link, parse_mode='HTML', reply_markup=create_publish_button(user_id))

                image_text = (
                    "изображение" if image_count % 10 == 1 and image_count % 100 != 11
                    else "изображения" if 2 <= image_count % 10 <= 4 and (image_count % 100 < 10 or image_count % 100 >= 20)
                    else "изображений"
                )

                await message_to_reply.reply_text(
                    f'====--- В статье {image_count} {image_text} ---====',
                )

                publish_data[user_id] = {
                    'title': title,
                    'article_url': article_url,
                    'image_count': image_count,
                    'author_line': author_line
                }

                del user_data[user_id]
                await message_to_reply.reply_text(
                    '✅Все данные для публикации успешно созданы.\n Но сейчас они видны только вам, чтобы поделиться ими с администрацией просто нажмите /share (эта кнопка будет работать только до вашего следующего нажатия команды publish) \n\n Либо создайте другую публикацию если что-то пошло не так. \n\nВы так же можете ввести команду /send чтобы перейти в режим прямой связи с администрацией. Просто нажмите на эту команду и после этого любые ваши сообщения отправленные боту будут сразу дублироваться администрации. Таким образом вы можете задать вопросы, отправить дополнительные файлы, изображения и пояснения касательно вашей публикации, сообщить об обнаруженных багах или что-то ещё. \n\n  ✅*Бот перезапущен успешно.*\n\n(=^・ェ・^=)',
                    reply_markup=ReplyKeyboardRemove()
                )
                logger.info(f"User {user_id}'s data cleared and process completed.")
                await message_to_reply.reply_text('********************************************************')
                await start(update, context)
                return ConversationHandler.END
            else:
                await message_to_reply.reply_text('🚫Ошибка при создании статьи. /restart')
        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            await message_to_reply.reply_text('🚫Ошибка при создании статьи. /restart')
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            await message_to_reply.reply_text(f'🚫Произошла непредвиденная ошибка: {e}')

        del user_data[user_id]
        logger.info(f"Error occurred. User {user_id}'s data cleared.")
        return ConversationHandler.END
    else:
        await message_to_reply.reply_text('🚫Ошибка: данные не найдены. /restart')
        return ConversationHandler.END



async def unknown_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text('🚫Неизвестное сообщение. Пожалуйста, отправьте ссылку на автора, имя автора или изображение. В случае если это сообщение повторяется нажмите /restart')
    else:
        # Обработка сообщений в процессе
        if user_data[user_id]['status'] == 'awaiting_artist_link':
            await handle_artist_link(update, context)
        elif user_data[user_id]['status'] == 'awaiting_author_name':
            await handle_author_name(update, context)
        elif user_data[user_id]['status'] == 'awaiting_image':
            await handle_image(update, context)
            
def chunk_images(images, chunk_size=10):
    for i in range(0, len(images), chunk_size):
        yield images[i:i + chunk_size]

TELEGRAM_API_TIMEOUT = 20  # Увеличьте время ожидания        

async def share(update: Update, context: CallbackContext) -> None:
    global publish_data
    user_id = update.message.from_user.id
    if user_id in publish_data:
        data = publish_data[user_id]
        title = data['title']
        article_url = data['article_url']
        author_line = data['author_line']

        try:
            # Увеличиваем таймаут для запроса к Telegra.ph
            article_response = requests.get(f'https://api.telegra.ph/getPage?path={article_url.split("/")[-1]}&return_content=true', timeout=10)
            article_response.raise_for_status()
            article_data = article_response.json()

            # Ищем изображения в контенте, включая теги figure
            images = []
            for node in article_data['result']['content']:
                if node.get('tag') == 'img' and 'attrs' in node and 'src' in node['attrs']:
                    images.append(node['attrs']['src'])
                elif node.get('tag') == 'figure' and 'children' in node:
                    images_in_figure = count_images_in_content(node['children'])
                    images.extend([img['attrs']['src'] for img in node['children'] if img.get('tag') == 'img' and 'attrs' in img and 'src' in img['attrs']])

            # Отправляем сообщение с текстом
            message_with_link = f'Пользователь {update.message.from_user.username} предложил:\n {author_line}\n<a href="{article_url}">Оригинал</a>'
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_with_link, parse_mode='HTML', disable_web_page_preview=True)

            # Отправляем изображения группами по 10
            if images:
                for image_group in chunk_images(images):
                    media_group = [InputMediaPhoto(image) for image in image_group]
                    await context.bot.send_media_group(chat_id=GROUP_CHAT_ID, media=media_group)
                    await asyncio.sleep(1)  # Задержка в 1 секунду между отправками медиа-групп
            else:
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text='Изображений в статье нет.')

            # Сообщение об успешной отправке
            await update.message.reply_text('✅Ваше предложение отправлено администрации. Спасибо.')

        except Timeout:
            logger.warning("Request to Telegram timed out, but message sent successfully.")
            await update.message.reply_text('✅Ваше предложение отправлено, но обработка статьи заняла больше времени. Вероятно это произошло из-за большого объёма статьи, на всякий случай сообщите об этом через команду /send и прикрепите там ссылку на вашу статью /restart для перезапуска')
        except Exception as e:
            logger.error(f"Failed to process article: {e}")
            await update.message.reply_text('✅Ваше предложение отправлено, но обработка статьи заняла больше времени. Вероятно это произошло из-за большого объёма статьи, на всякий случай сообщите об этом через команду /send и прикрепите там ссылку на вашу статью /restart для перезапуска')
    else:
        await update.message.reply_text('🚫Нет данных для предложения.')

async def send_mode(update: Update, context: CallbackContext) -> None:
    """Включение режима дублирования сообщений."""
    user_id = update.message.from_user.id
    users_in_send_mode.add(user_id)
    await update.message.reply_text('🔄 Режим прямой связи включен. Все последующие сообщения будут дублироваться администрации. Для завершения режима введите /fin')
    
async def fin_mode(update: Update, context: CallbackContext) -> None:
    """Выключение режима дублирования сообщений и возврат к изначальной логике."""
    user_id = update.message.from_user.id
    if user_id in users_in_send_mode:
        users_in_send_mode.remove(user_id)
        await update.message.reply_text('✅ Режим пересылки сообщений администрации отключен. Бот вернулся к своему основному режиму работы.')
    else:
        await update.message.reply_text('❗ Вы не активировали режим дублирования.')

from telegram import InputMediaPhoto, InputMediaVideo



from telegram import InputMediaPhoto, InputMediaVideo, InputMediaDocument

async def duplicate_message(update: Update, context: CallbackContext) -> None:
    """Дублирование сообщений пользователя в группу, включая медиа-группы, одиночные сообщения и документы."""
    user = update.message.from_user
    user_name = user.username if user.username else user.full_name
    message_prefix = f"{user_name} отправил сообщение:"

    if user.id in users_in_send_mode:
        # Если сообщение является частью медиа-группы
        if update.message.media_group_id:
            media_group = []
            messages = await context.bot.get_updates(offset=update.update_id - 10)  # Получаем несколько предыдущих сообщений для сборки медиа-группы

            # Фильтрация сообщений с тем же media_group_id
            for message in messages:
                if message.message.media_group_id == update.message.media_group_id:
                    if message.message.photo:
                        media_group.append(InputMediaPhoto(message.message.photo[-1].file_id, caption=message.message.caption if message.message.caption else ""))
                    elif message.message.video:
                        media_group.append(InputMediaVideo(message.message.video.file_id, caption=message.message.caption if message.message.caption else ""))
                    elif message.message.document:
                        media_group.append(InputMediaDocument(message.message.document.file_id, caption=message.message.caption if message.message.caption else ""))

            # Отправляем медиа-группу, если она есть
            if media_group:
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_prefix)
                await context.bot.send_media_group(chat_id=GROUP_CHAT_ID, media=media_group)
                await update.message.reply_text("Сообщение успешно отправлено администрации. Для завершения режима дублирования введите /fin")

        # Обработка одиночных текстовых сообщений
        elif update.message.text:
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"{message_prefix}\n{update.message.text}")
            await update.message.reply_text("Сообщение успешно отправлено администрации. Для завершения режима дублирования введите /fin")

        # Обработка одиночных фото
        elif update.message.photo:
            photo = update.message.photo[-1].file_id  # Получаем последнюю фотографию с наибольшим разрешением
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_prefix)
            await context.bot.send_photo(chat_id=GROUP_CHAT_ID, photo=photo, caption=update.message.caption)
            await update.message.reply_text("Сообщение успешно отправлено администрации. Для завершения режима дублирования введите /fin")

        # Обработка одиночных документов (включая изображения, отправленные как файл)
        elif update.message.document:
            doc = update.message.document.file_id
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_prefix)
            await context.bot.send_document(chat_id=GROUP_CHAT_ID, document=doc, caption=update.message.caption)
            await update.message.reply_text("Сообщение успешно отправлено администрации. Для завершения режима дублирования введите /fin")

        # Обработка одиночных видео
        elif update.message.video:
            video = update.message.video.file_id
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_prefix)
            await context.bot.send_video(chat_id=GROUP_CHAT_ID, video=video, caption=update.message.caption)
            await update.message.reply_text("Сообщение успешно отправлено администрации. Для завершения режима дублирования введите /fin")

        # Обработка стикеров
        elif update.message.sticker:
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_prefix)
            await context.bot.send_sticker(chat_id=GROUP_CHAT_ID, sticker=update.message.sticker.file_id)
            await update.message.reply_text("Сообщение успешно отправлено администрации. Для завершения режима дублирования введите /fin")

        # Обработка аудио
        elif update.message.audio:
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_prefix)
            await context.bot.send_audio(chat_id=GROUP_CHAT_ID, audio=update.message.audio.file_id, caption=update.message.caption)
            await update.message.reply_text("Сообщение успешно отправлено администрации. Для завершения режима дублирования введите /fin")

        # Добавьте обработку других типов сообщений по мере необходимости
    else:
        # Если пользователь не в режиме дублирования, продолжаем с основной логикой
        await start(update, context)




def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Настройка ConversationHandler
    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('edit', edit_article),  # Обработчик для команды /edit
            MessageHandler(filters.TEXT & ~filters.COMMAND, start)
        ],
        states={
            ASKING_FOR_ARTIST_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_artist_link)],
            ASKING_FOR_AUTHOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_author_name)],
            EDITING_FRAGMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_text)],  # Обрабатываем новый текст
            ASKING_FOR_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, handle_new_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)  # Добавляем обработку текста
            ],
        },
        fallbacks=[MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message)],
        per_user=True
    )

    # Добавляем обработчики команд
    application.add_handler(CallbackQueryHandler(handle_edit_button, pattern='edit_article'))
    application.add_handler(CallbackQueryHandler(handle_delete_button, pattern='delete_last'))
    application.add_handler(CallbackQueryHandler(handle_edit_delete, pattern='^edit_|^delete_'))
    application.add_handler(CallbackQueryHandler(handle_preview_button, pattern='preview_article'))
    application.add_handler(CallbackQueryHandler(handle_create_article_button, pattern='create_article'))
    application.add_handler(CallbackQueryHandler(handle_help_text_button, pattern='help_command'))
    application.add_handler(CallbackQueryHandler(handle_restart_button, pattern='restart'))
    application.add_handler(CallbackQueryHandler(handle_page_change, pattern='^page_')) 
    application.add_handler(CommandHandler('send', send_mode))
    application.add_handler(CommandHandler('fin', fin_mode))
    application.add_handler(CommandHandler('restart', restart))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('publish', publish))
    application.add_handler(CommandHandler('preview', preview_article))  # Добавляем обработчик для /preview
    application.add_handler(CommandHandler('delete', delete_last))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, duplicate_message))  # Обработчик дублирования сообщений
    application.add_handler(CommandHandler('share', share))  # Добавляем обработчик для /share
    application.add_handler(conversation_handler)

    

    logger.info("Bot started and polling...")
    application.run_polling()  # Запуск бота

if __name__ == '__main__':
    main()
