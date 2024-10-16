from telegram import Update, InputMediaPhoto, ReplyKeyboardRemove, InputMediaDocument, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
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

# Укажите ваши токены и ключ для imgbb
TELEGRAM_BOT_TOKEN = '7538468672:AAEOEFS7V0z0uDzZkeGNQKYsDGlzdOziAZI'
TELEGRAPH_TOKEN = 'c244b32be4b76eb082d690914944da14238249bbdd55f6ffd349b9e000c1'
IMGBB_API_KEY = '2467db337d47e9f9cc85af27dc7ea1d3'
GROUP_CHAT_ID = -1002233281756

# Состояния
ASKING_FOR_ARTIST_LINK, ASKING_FOR_AUTHOR_NAME, ASKING_FOR_IMAGE = range(3)

# Сохранение данных состояния пользователя
user_data = {}
publish_data = {}
users_in_send_mode = set()
media_group_storage = {}

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id not in user_data:
        logger.info(f"User {user_id} started the process.")
        await update.message.reply_text('🌠Этот бот поможет вам создать пост для группы Anemone. Изначально пост будет виден исключительно вам, так что не бойтесь экспериментировать и смотреть что получится\n \nДля начала, пожалуйста, отправьте ссылку на автора. Если у вас её нет то отправьте любой текст\n \n <i>В боте есть команда /restart которая перезапускает процесс на любом этапе</i>\n',
    parse_mode='HTML')
        user_data[user_id] = {'status': 'awaiting_artist_link'}  # Инициализация данных для пользователя
        return ASKING_FOR_ARTIST_LINK
    else:
        status = user_data[user_id].get('status')
        if status == 'awaiting_artist_link':
            return await handle_artist_link(update, context)
        elif status == 'awaiting_author_name':
            return await handle_author_name(update, context)
        elif status == 'awaiting_image':
            return await handle_image(update, context)
        else:
            await update.message.reply_text('🚫Ошибка: некорректное состояние.')
            return ConversationHandler.END

async def restart(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in user_data:
        del user_data[user_id]  # Удаляем старые данные пользователя  
    logger.info(f"User {user_id} restarted the process.") 
    # Инициализируем новое состояние пользователя
    user_data[user_id] = {'status': 'awaiting_artist_link'}
    await update.message.reply_text('✅Процесс сброшен. Пожалуйста, начните заново. \n Отправьте ссылку на автора.')
    return ASKING_FOR_ARTIST_LINK

HELP_TEXT = """
▶️Пост в Анемоне формируется из двух частей \- непосредственно сам пост видимый в телеграме \, плюс статья Telagraph доступная по ссылке\(для примера посмотрите любой из последних постов в группе\) Бот позволяет сделать обе части\. \n\n  Изначально статья и всё её содержание видны только вам\, администрации она станет доступна только после того как вы нажмёте сначала кнопку \/publish \(опубликовать\) и затем \(по желанию\) кнопку \/share \(поделиться\)\. Если после публикации вы не захотите вводить команду share то публикация останется видна только вам\n\n ▶️Статья в Telegraph формируется в порядке отправки вами изображений и текста боту\.\n\n Во время создания статьи вы можете открыть её предпросмотр с помощью команды \/preview \n Либо удалить последний добавленный элемент командой \/delete \(работает неограниченное количество раз\, пока статья не станет пустой\) \n\n▶️Поддерживаемые тэги текста при создании статьи telegraph\:\(без кавычек\)\n \- \"\*\*\*\" — горизонтальная линия\-разделитель \(отправьте три звёздочки отдельным сообщением\, в этом месте в статье телеграф появится разделитель\)\.\n\- \"\_текст\_\" — курсив\.\n\- \"\*текст\*\" — жирный текст\.\n\- \"\[текст ссылки\]\(ссылка\)\" — гиперссылка\.\n\- \"видео\: \" — вставка видео с Vimeo или YouTube\.\n\- \"цитата\:\" — цитата\.\n\- \"цитата по центру\:\" — центрированная цитата\.\n\- "заголовок:" — заголовок\\.\n\\- "подзаголовок:" — подзаголовок\\.\n\n Последние 5 тэгов пишутся в начале сообщения и применяются ко всему сообщению целиком\. Каждое новое сообщение — это новый абзац\. Сообщения без тэгов — обычный текст\.\n\n Пример\: \(без кавычек\)\n\- \"цитата\: \*Волк\* никогда не будет жить в загоне\, но загоны всегда будут жить в \*волке\*\" — в статье телеграф примет вид цитата\, в которой слово \"волк\" выделено жирным\.\n\- \"видео\: ссылка\_на\_видео\" — вставка интерактивного видео YouTube или Vimeo\.\n\n▶️Кроме того бот поддерживает загрузку GIF файлов\. Для этого переименуйте \.GIF в \.RAR \, затем отправьте файл боту во время оформления поста\. Это нужно для того чтобы телеграм не пережимал GIF файлы\, бот автоматически переименует файл обратно в GIF перед размещением в Телеграф\n\n▶️Так же вы можете отправить что\-то администрации напрямую\, в режиме прямой связи\. Для этого введите команду \/send и после неё все ваши сообщения отправленные боту тут же будут пересылаться администрации\. Это могут быть какие\-то пояснения\, дополнительные изображения или их правильное размещение в посте телеграм\, вопросы\, предложения\, ссылка на самостоятельно созданную статью телеграф\, пойманные в боте ошибки и что угодно ещё\. Для завершения этого режима просто введите \/fin и бот вернётся в свой обычный режим\. Просьба не спамить через этот режим\, писать или отправлять только нужную информацию  \n
"""

async def help_command(update: Update, context: CallbackContext) -> None: await update.message.reply_text( HELP_TEXT, parse_mode=ParseMode.MARKDOWN_V2 )

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

        await update.message.reply_text('Отлично \n🌌Теперь приступим к наполнению публикации контентом, для этого отправьте изображения файлом (без сжатия) или текст. Если вы отправите изображение с подписью, то в статье телеграф текст тоже будет отображаться как подпись под изображением \n\n Текст поддерживает различное форматирование. Для получения списка тэгов и помощи введите /help. \n\n <i>Так же вы можете нажать /restart для сброса</i>',
    parse_mode='HTML')
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

# Асинхронная функция для загрузки изображения на imgbb
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



# Обновленная функция handle_image для обработки изображений
async def handle_image(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    caption = update.message.caption  # Сохраняем подпись, если она есть
    if user_id in user_data and user_data[user_id]['status'] == 'awaiting_image':
        if update.message.photo:
            await update.message.reply_text('Пожалуйста, отправьте изображение как файл (формат JPG, PNG или .RAR для .GIF), без сжатия. Для подробностей введите /help')
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
                # Если формат GIF, не трогаем его, даже если размер больше 5 МБ
                if file_ext == 'gif':
                    try:
                        # Запускаем асинхронную загрузку изображения через универсальную функцию
                        image_url = await upload_image(file_path)
                        if 'media' not in user_data[user_id]:
                            user_data[user_id]['media'] = []
                        # Добавляем изображение и его подпись (если есть) в user_data
                        user_data[user_id]['media'].append({
                            'type': 'image',
                            'url': image_url,
                            'caption': caption if caption else ""  # Добавляем подпись
                        })
                        await update.message.reply_text('✅ Одно изображение добавлено.\n\n Дождитесь загрузки остальных изображений, если их больше чем одно. Затем вы можете продолжить присылать изображения или текст.\n\n Так же вы можете использовать следующие команды:\n /preview - для предпросмотра статьи \n /delete - Для удаления последнего элемента в статье(команду можно повторять)\n /help - для вызова помощи и списка всех функций разметки \n\n 🟩 /publish - для перехода к окну финальной версии и завершению публикации \n 🟥 /restart - полный сброс и перезапуск бота')
                        return ASKING_FOR_IMAGE
                    except Exception as e:
                        await update.message.reply_text(f'🚫Ошибка при загрузке изображения: {str(e)}. Можете попробовать прислать файл ещё раз через некоторое время или нажать /restart')
                        return ConversationHandler.END
                else:
                    # Если изображение больше 5 МБ (но не GIF), сжимаем его
                    if os.path.getsize(file_path) > 5 * 1024 * 1024:
                        compressed_path = f'{os.path.splitext(file_path)[0]}_compressed.jpg'
                        compress_image(file_path, compressed_path)
                        file_path = compressed_path
            
                    try:
                        # Запускаем асинхронную загрузку изображения через универсальную функцию
                        image_url = await upload_image(file_path)
                        if 'media' not in user_data[user_id]:
                            user_data[user_id]['media'] = []
                        user_data[user_id]['media'].append({
                            'type': 'image',
                            'url': image_url,
                            'caption': caption if caption else ""  # Добавляем подпись
                        })
                        os.remove(file_path)  # Удаляем временный файл
                        await update.message.reply_text('✅ Одно изображение добавлено.\n\n Дождитесь загрузки остальных изображений, если их больше чем одно. Затем вы можете продолжить присылать изображения или текст.\n\n Так же вы можете использовать следующие команды:\n /preview - для предпросмотра статьи \n /delete - Для удаления последнего элемента в статье(команду можно повторять)\n /help - для вызова помощи и списка всех функций разметки \n\n 🟩 /publish - для перехода к окну финальной версии и завершению публикации \n 🟥 /restart - полный сброс и перезапуск бота')
                        return ASKING_FOR_IMAGE
                    except Exception as e:
                        await update.message.reply_text(f'🚫Ошибка при загрузке изображения: {str(e)}. Можете попробовать прислать файл ещё раз через некоторое время или нажать /restart')
                        return ConversationHandler.END
            else:
                await update.message.reply_text('Пожалуйста, отправьте изображение в формате JPG, PNG или .RAR для .GIF файлом, без сжатия.\n\n для помощи введите /help')
                return ASKING_FOR_IMAGE
            
        elif update.message.text:
            # Обработка текстовых сообщений с помощью новой функции
            return await handle_text(update, context)
        else:
            await update.message.reply_text('Пожалуйста, отправьте изображение как файл (формат JPG, PNG или .RAR для .GIF), без сжатия, или текст.\n\n для помощи введите /help')
            return ASKING_FOR_IMAGE
    else:
        await update.message.reply_text('🚫Ошибка: данные не найдены. Попробуйте отправить снова. Или нажмите /restart')
        return ConversationHandler.END

        
# Функция для обработки текстовых сообщений
async def handle_text(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in user_data and user_data[user_id]['status'] == 'awaiting_image':
        # Обработка текстовых сообщений с разметкой
        formatted_text = apply_markup(update.message.text)
        if 'media' not in user_data[user_id]:
            user_data[user_id]['media'] = []
        user_data[user_id]['media'].append({'type': 'text', 'content': formatted_text})
        await update.message.reply_text('✅ Текст успешно добавлен. Вы можете отправить ещё текст или изображения. \n\nТак же вы можете использовать следующие команды:\n /preview - для предпросмотра статьи \n /delete - Для удаления последнего элемента в статье(команду можно повторять) \n /help - для вызова помощи и списка всех функций разметки \n\n 🟩 /publish - для перехода к окну финальной версии и завершению публикации \n 🟥 /restart - полный сброс и перезапуск бота')
        return ASKING_FOR_IMAGE
    else:
        await update.message.reply_text('🚫Ошибка: данные не найдены. Попробуйте отправить снова. Или нажмите /restart')
        return ConversationHandler.END

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
    user_id = update.message.from_user.id
    if user_id in user_data and 'media' in user_data[user_id]:
        if user_data[user_id]['media']:
            last_item = user_data[user_id]['media'].pop()  # Удаляем последний элемент
            item_type = last_item['type']
            await update.message.reply_text(f"Удалён последний элемент типа: {item_type}\n\nДля предпросмотра изменений введите команду /preview")
        else:
            await update.message.reply_text("Ваша статья пуста. Нет элементов для удаления.")
    else:
        await update.message.reply_text("У вас нет активной статьи для редактирования. Используйте /start для начала.")    


async def preview_article(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id in user_data:
        try:
            author_name = "Anemone"
            author_link = "https://t.me/anemonn"
            artist_link = user_data[user_id].get('artist_link', '')
            media = user_data[user_id].get('media', [])
            title = user_data[user_id].get('title', 'Предпросмотр статьи')

            # Создаём контент для страницы
            content = [{'tag': 'p', 'children': [{'tag': 'a', 'attrs': {'href': artist_link}, 'children': [artist_link]}]}]

            for item in media:
                if item['type'] == 'text':
                    content.append({'tag': 'p', 'children': [item['content']]})
                elif item['type'] == 'image':
                    figure_content = [{'tag': 'img', 'attrs': {'src': item['url']}}]
                    if item.get('caption'):
                        figure_content.append({'tag': 'figcaption', 'children': [item['caption']]})
                    content.append({'tag': 'figure', 'children': figure_content})

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
                await update.message.reply_text(f'Предпросмотр статьи: {preview_url}')
            else:
                await update.message.reply_text('Ошибка при создании предпросмотра статьи.')

        except requests.RequestException as e:
            await update.message.reply_text(f'Ошибка при создании предпросмотра: {e}')
    else:
        await update.message.reply_text('Нет данных для предпросмотра. Начните с отправки текста или изображений.')



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
                    # Создаем фигуру с изображением и подписью
                    figure_content = [
                        {'tag': 'img', 'attrs': {'src': item['url']}},
                    ]
                    # Если есть подпись, добавляем её в figcaption
                    if item.get('caption'):
                        figure_content.append({'tag': 'figcaption', 'children': [item['caption']]})

                    content.append({'tag': 'figure', 'children': figure_content})

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

                # Подсчет количества изображений в контенте статьи
                image_count = count_images_in_content(content)

                # Логируем количество изображений для проверки
                logger.info(f"Number of images detected: {image_count}")

                # Отправка изображений, если они есть
                if image_count > 1:
                    message_with_link = f'{author_line}\n<a href="{article_url}">Оригинал</a>'
                    await update.message.reply_text(message_with_link, parse_mode='HTML', disable_web_page_preview=True)
                    media_groups = [media[i:i + 10] for i in range(0, len(media), 10)]
                    for group in media_groups:
                        media_group = []

                        for idx, item in enumerate(group):
                            if item['type'] == 'image':
                                if idx == 0:  # Добавляем заголовок только для первого изображения
                                    media_group.append(InputMediaPhoto(
                                        media=item['url'],
                                        caption=f'{author_line}\n<a href="{article_url}">Оригинал</a>',
                                        parse_mode='HTML'
                        ))
                                else:
                                    media_group.append(InputMediaPhoto(media=item['url']))

            # Попытка отправить медиа группу с задержкой и повторными попытками
                    success = await send_media_group_with_retries(update, media_group)
                    if not success:
                        await update.message.reply_text('🚫Ошибка при отправке медиа. /restart')
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
                            await update.message.reply_text('🚫Ошибка при отправке изображения. /restart')
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
                    '✅Все данные для публикации успешно созданы.\n Но сейчас они видны только вам, чтобы поделиться ими с администрацией просто нажмите /share (эта кнопка будет работать только до вашего следующего нажатия команды publish) \n\n Либо создайте другую публикацию если что-то пошло не так. \n\nВы так же можете ввести команду /send чтобы перейти в режим прямой связи с администрацией. Просто нажмите на эту команду и после этого любые ваши сообщения отправленные боту будут сразу дублироваться администрации. Таким образом вы можете задать вопросы, отправить дополнительные файлы, изображения и пояснения касательно вашей публикации, сообщить об обнаруженных багах или что-то ещё. \n\n  ✅*Бот перезапущен успешно.*\n\n(=^・ェ・^=)',
                    reply_markup=ReplyKeyboardRemove()
                )
                logger.info(f"User {user_id}'s data cleared and process completed.")
                await update.message.reply_text('********************************************************')
                await start(update, context)
                return ConversationHandler.END
            else:
                await update.message.reply_text('🚫Ошибка при создании статьи. /restart')
        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            await update.message.reply_text('🚫Ошибка при создании статьи. /restart')
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            await update.message.reply_text('🚫Произошла непредвиденная ошибка. /restart')

        del user_data[user_id]
        logger.info(f"Error occurred. User {user_id}'s data cleared.")
        return ConversationHandler.END
    else:
        await update.message.reply_text('🚫Ошибка: данные не найдены. /restart')
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
            
async def share(update: Update, context: CallbackContext) -> None:
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
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_with_link, parse_mode='HTML', disable_web_page_preview=True)
            
            # Если есть изображения, отправляем их как медиагруппу в группу
            if images:
                media_group = [InputMediaPhoto(image) for image in images]
                await context.bot.send_media_group(chat_id=GROUP_CHAT_ID, media=media_group)
            else:
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text='Изображений в статье нет.')

            # Сообщение об успешной отправке предложения в личный диалог с пользователем
            await update.message.reply_text('✅Ваше предложение отправлено администрации. Спасибо.')
        except Exception as e:
            logger.error(f"Failed to process article: {e}")
            await update.message.reply_text('🚫Ошибка при обработке статьи. /restart')
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
            MessageHandler(filters.TEXT & ~filters.COMMAND, start)
        ],
        states={
            ASKING_FOR_ARTIST_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_artist_link)],
            ASKING_FOR_AUTHOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_author_name)],
            ASKING_FOR_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, handle_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)  # Добавляем обработку текста
            ]
        },
        fallbacks=[MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message)],
        per_user=True
    )

    # Добавляем обработчики команд
    application.add_handler(CommandHandler('send', send_mode))
    application.add_handler(CommandHandler('fin', fin_mode))
    application.add_handler(CommandHandler('restart', restart))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('publish', publish))
    application.add_handler(CommandHandler('preview', preview_article))  # Добавляем обработчик для /preview
    application.add_handler(CommandHandler('delete', delete_last))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, duplicate_message))  # Обработчик дублирования сообщений
    
    application.add_handler(conversation_handler)
    
    logger.info("Bot started and polling...")  
    keep_alive()#запускаем flask-сервер в отдельном потоке. Подробнее ниже...
    application.run_polling() #запуск бота
    
if __name__ == '__main__':
    main()
