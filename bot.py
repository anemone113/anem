from telegram import Update, InputMediaPhoto, ReplyKeyboardRemove, InputMediaDocument, InputMediaVideo, InlineKeyboardButton, InlineKeyboardMarkup, Message, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, CallbackQueryHandler, ContextTypes
from PIL import Image
from telegram.constants import ParseMode
from tenacity import retry, wait_fixed, stop_after_attempt
from background import keep_alive
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
from bs4 import BeautifulSoup
import wikipediaapi
import wikipedia
import gpt_helper
from gpt_helper import (
    add_to_context,
    generate_gemini_response,
    generate_image_description,
    set_user_role,
    limit_response_length,
    user_contexts,
    save_context_to_firebase,
    load_context_from_firebase,
    generate_audio_response,
    load_publications_from_firebase,
    save_publications_to_firebase,
    delete_from_firebase,
    save_channel_to_firebase,
    save_vk_keys_to_firebase,
    generate_plant_issue_response,
    generate_text_rec_response,
    generate_plant_help_response,
    reset_firebase_dialog,
    generate_video_response,
    generate_animation_response,
    generate_mushrooms_response,
    translate_promt_with_gemini,
    get_user_model,
    set_user_model,
    generate_document_response,
    load_shared_publications,
    save_to_shared_publications,
    add_to_favorites,
    copy_to_shared_publications
)
from collections import deque
from aiohttp import ClientSession, ClientTimeout, FormData
import chardet
import json
import os
from gpt_helper import user_roles, DEFAULT_ROLES
import base64
import random
from langdetect import detect
import firebase_admin
from firebase_admin import credentials, db
import re
import logging
import re
from bs4 import BeautifulSoup
import aiohttp
import wikipediaapi  # Импортируем библиотеку
import wikipedia
import ast
from telegram.error import Forbidden
from telegram.helpers import escape, mention_html
from huggingface_hub import AsyncInferenceClient
import time
import itertools
import os
from dotenv import load_dotenv
# Укажите ваши токены и ключ для imgbb
TELEGRAM_BOT_TOKEN = '7538468672:AAEOEFS7V0z0uDzZkeGNQKYsDGlzdOziAZI'
TELEGRAPH_TOKEN = 'c244b32be4b76eb082d690914944da14238249bbdd55f6ffd349b9e000c1'
IMGBB_API_KEY = '9edd5bc20f700e3e1a8a0d833a423133'
GROUP_CHAT_ID = -1002233281756

# Состояния
ASKING_FOR_ARTIST_LINK, ASKING_FOR_AUTHOR_NAME, ASKING_FOR_IMAGE, EDITING_FRAGMENT, ASKING_FOR_FILE, ASKING_FOR_OCR, RUNNING_GPT_MODE, ASKING_FOR_ROLE, ASKING_FOR_FOLLOWUP,AWAITING_FOR_FORWARD, WAITING_FOR_NEW_CAPTION = range(11)
# Сохранение данных состояния пользователя
user_data = {}
publish_data = {}
users_in_send_mode = {}
media_group_storage = {}
is_search_mode = {}
is_ocr_mode = {}
is_gpt_mode = {}
is_role_mode = {}
is_asking_mode = {}
user_presets = {} 
user_models = {}
waiting_for_forward = {}
waiting_for_vk = {}
waiting_for_caption = {}
# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# Загружаем данные при запуске бота
media_group_storage = load_publications_from_firebase()

# Функция для сохранения данных в JSON файл
def save_media_group_data(media_group_storage, user_id):
    """Сохраняет данные публикаций для указанного пользователя в Firebase."""
    try:
        logger.info(f"Пользователь {user_id} сохраняет публикацию")

        
        # Приведение типа ключей
        user_publications = media_group_storage.get(
            user_id if user_id in media_group_storage else str(user_id), {}
        )
        
        # Проверка данных
        if not user_publications:
            logger.warning(f"Нет публикаций для user_id={user_id}")
            return
        
        # Сохраняем данные текущего пользователя
        for message_id, data in user_publications.items():
            save_publications_to_firebase(user_id, message_id, data)
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных пользователя ")



async def sendall(update: Update, context: CallbackContext) -> None:
    """Отправляет сообщение указанным пользователям с HTML-разметкой."""
    if not update.message or not update.message.text:
        await update.message.reply_text("Использование: /sendall [id1, id2, ...] текст сообщения")
        return

    # Получаем полный текст сообщения без команды
    message_text = update.message.text[len("/sendall") :].strip()

    if not message_text.startswith("["):
        await update.message.reply_text("Некорректный формат. Используйте: /sendall [id1, id2] текст сообщения")
        return

    try:
        # Извлекаем список user_id из квадратных скобок
        ids_part, message_text = message_text.split("]", 1)
        user_ids = ast.literal_eval(ids_part + "]")  # Преобразуем строку в список
        message_text = message_text.strip()

        if not isinstance(user_ids, list) or not all(isinstance(i, int) for i in user_ids):
            raise ValueError
    except Exception:
        await update.message.reply_text("Ошибка в формате ID. Используйте: /sendall [id1, id2] текст сообщения")
        return

    if not message_text:
        await update.message.reply_text("Вы не ввели текст для рассылки.")
        return

    success_count, fail_count = 0, 0

    for user_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=user_id, 
                text=message_text, 
                parse_mode="HTML"  # Используем HTML-разметку
            )
            success_count += 1
        except Exception as e:
            fail_count += 1
            print(f"Ошибка при отправке пользователю {user_id}: {e}")

    await update.message.reply_text(f"Сообщение отправлено {success_count} пользователям, не удалось {fail_count}.")



async def mainhelp_callback(update: Update, context: CallbackContext):
    """Обработчик нажатия на кнопку для вызова mainhelp."""
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    # Заранее заготовленный текст с HTML-разметкой
    help_text = """
    В боте есть множество функций, разделённых по кнопкам:

    <b>===Кнопка "Найти автора"===</b>
    Позволяет попытаться найти автора изображения, его ник и страницы в соцсетях. Также может распознать скрин из аниме или мультфильмов с точностью до указания серии и минуты, откуда он сделан. 
    Кроме того может проверить вероятность того, сгенерировано ли изображение нейросетью или же нарисовано вручную.

    <b>===Кнопка "Распознать"===</b>  
    Позволяет распознать текст или растение по их фотографии. Также с помощью встроенной в функцию нейросети можно сделать различные манипуляции с распознанным текстом или узнать, что с растением (болезни, вредители). Кроме того почитать информацию о распознанном растении или получить советы по уходу за ним.  

    <b>===Кнопка "Поговорить с ботом"===</b>  
    Переключает в режим диалога с ботом. У этого режима также есть много интересных особенностей вроде распознавания видео или анализа содержимого веб-страниц. У этого режима есть отдельная кнопка помощи, если необходимо.

    <b>===Основной режим бота==="</b>
    Основной режим бота позволяет создавать, сохранять и публиковать посты. По умолчанию, если загружать вручную, изображения в телеграм загружаются и отображаются в разрешении 1280 пикселей. Если же загружать их через бота (через API telegram), то в таком случае изображение загружается и отображается с разрешением 2560 пикселей, что более чем в 2 раза превышает ручную загрузку и потому даёт лучшее качество отображения.
    Бот принимает сначала текст, который будет служить подписью к посту, затем сами изображения, отправленные как файлы, без сжатия, после чего возвращает готовый пост с изображениями в исходном качестве. Также при вводе подписи доступно указание и оформление ссылок, например на соцсети.

    ▶️Кроме того, бот поддерживает загрузку GIF-файлов. Для этого переименуйте .GIF в .RAR, затем отправьте файл боту во время оформления поста. Это нужно для того, чтобы телеграм не пережимал GIF-файлы. Бот автоматически переименует файл обратно в GIF перед размещением в Telegraph.  

    ▶️Также вы можете отправить что-то администрации напрямую, в режиме прямой связи. Для этого введите команду /send, и после неё все ваши сообщения, отправленные боту, тут же будут пересылаться администрации. Это могут быть какие-то пояснения, дополнительные изображения или их правильное размещение в посте телеграм, вопросы, предложения, ссылка на самостоятельно созданную статью Telegraph, пойманные в боте ошибки и что угодно ещё. Для завершения этого режима просто введите /fin, и бот вернётся в свой обычный режим. Просьба не спамить через этот режим, писать или отправлять только нужную информацию.

    ▶️Создаваемые посты видны только вам, до тех пор пока вы их сами не выложите или не поделитесь ими через нажатие кнопок публикации в ТГ, ВК или предложки в Анемон. Так что не бойтесь экспериментировать с ботом.

    Пример:
<pre>https://ссылка_1

https://ссылка_2

рисунок акварелью</pre>
    Даст такой результат:
<pre>рисунок акварелью

ссылка_1 • ссылка_2</pre>
    """

    # Определяем кнопки
    keyboard = [
        [InlineKeyboardButton("📚 Архив ваших постов 📚", callback_data="scheduled_by_tag")],
        [InlineKeyboardButton("🎨 Найти автора или проверить на ИИ 🎨", callback_data='start_search')],
        [InlineKeyboardButton("🌱 Распознать(растение, грибы, текст) 🌱", callback_data='start_ocr')],            
        [InlineKeyboardButton("🦊 Поговорить с ботом 🦊", callback_data='run_gpt')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем или обновляем сообщение
    await query.edit_message_text(help_text, parse_mode="HTML", reply_markup=reply_markup)



def format_text_to_html(message):
    # Выбираем текст или подпись, если они есть
    raw_text = message.text or message.caption
    logger.info(f"raw_text: {raw_text}")     
    if not raw_text:
        return ""  # Возвращаем пустую строку, если текст и подпись отсутствуют

    entities = message.entities if message.text else message.caption_entities
    logger.info(f"entities: {entities}")    
    if not entities:
        escaped_text = escape(raw_text.strip())
        return add_plain_links(escaped_text)  # Добавляем ссылки в чистом тексте

    formatted_text = ""
    offset = 0

    for entity in entities:
        start, end = entity.offset, entity.offset + entity.length
        plain_text = escape(raw_text[offset:start])  # Текст до текущей сущности
        formatted_text += add_plain_links(plain_text)  # Обрабатываем ссылки в обычном тексте
        logger.info(f"formatted_text: {formatted_text}")  
        logger.info(f"plain_text: {plain_text}")          
        entity_text = escape(raw_text[start:end])
        if entity.type == "bold":
            formatted_text += f"<b>{entity_text}</b>"
        elif entity.type == "italic":
            formatted_text += f"<i>{entity_text}</i>"
        elif entity.type == "underline":
            formatted_text += f"<u>{entity_text}</u>"
        elif entity.type == "strikethrough":
            formatted_text += f"<s>{entity_text}</s>"
        elif entity.type == "code":
            formatted_text += f"<code>{entity_text}</code>"
        elif entity.type == "pre":
            formatted_text += f"<pre>{entity_text}</pre>"
        elif entity.type == "text_link":
            formatted_text += f'<a href="{entity.url}">{entity_text}</a>'
        elif entity.type == "mention":
            formatted_text += mention_html(entity.user.id, entity_text)
        elif entity.type == "spoiler":
            formatted_text += f'<span class="tg-spoiler">{entity_text}</span>'
        elif entity.type == "url":  # Обработка обычных ссылок
            formatted_text += f'{entity_text}'

        offset = end

    formatted_text += add_plain_links(escape(raw_text[offset:]))  # Обрабатываем оставшийся текст
    return formatted_text

def add_plain_links(text):
    # Регулярное выражение для поиска обычных ссылок
    url_pattern = re.compile(r"(https?://[^\s]+)")
    return url_pattern.sub(r'<a href="\1">\1</a>', text)

def log_user_state(user_id: int):
    logger.info(f"--- User {user_id} Current State ---")
    logger.info(f"user_data: {user_data.get(user_id, 'Not Found')}")
    logger.info(f"is_search_mode: {is_search_mode.get(user_id, False)}")
    logger.info(f"is_ocr_mode: {is_ocr_mode.get(user_id, False)}")
    logger.info(f"is_gpt_mode: {is_gpt_mode.get(user_id, False)}")
    logger.info(f"is_role_mode: {is_role_mode.get(user_id, False)}")
    logger.info(f"is_asking_mode: {is_asking_mode.get(user_id, False)}")
    logger.info(f"waiting_for_vk: {waiting_for_vk.get(user_id, False)}")
    logger.info(f"waiting_for_forward: {waiting_for_forward.get(user_id, False)}")
    logger.info(f"waiting_for_caption: {waiting_for_caption.get(user_id, False)}")
    logger.info("---------------------------------")

async def start(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id if update.message else update.callback_query.from_user.id

    # Проверяем, есть ли пользователь в данных
    if update.message:
        message_to_reply = update.message
        user_id = update.message.from_user.id
    elif update.callback_query:
        message_to_reply = update.callback_query.message
        user_id = update.callback_query.from_user.id
    else:
        return ConversationHandler.END  # На случай, если ни одно условие не выполнится

    # Проверяем, есть ли пользователь в данных
    if user_id not in user_data:
        logger.info(f"User {user_id} started the process.")
        
        # Создаем кнопку "Начать поиск"
        # Создаем кнопку "Начать поиск"
        keyboard = [
            [InlineKeyboardButton("🗂 Папки с сохранёнными постами 🗂", callback_data="scheduled_by_tag")],
            [InlineKeyboardButton("🎨 Найти автора или проверить на ИИ 🎨", callback_data='start_search')],
            [InlineKeyboardButton("🌱 Распознать(растение, грибы, текст) 🌱", callback_data='start_ocr')],            
            [InlineKeyboardButton("🦊 Поговорить с ботом 🦊", callback_data='run_gpt')],
            [InlineKeyboardButton("📖 Посмотреть помощь", callback_data="osnhelp")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем сообщение с кнопкой
        await message_to_reply.reply_text(
            '🌠Привет ⸜(⸝⸝⸝´꒳`⸝⸝⸝)⸝\n\n'
            'Этот бот поможет вам создать публикацию для телеграм канала или вк группы с изображениями высокого разрешения.\n\n'
            'Для начала, пожалуйста, отправьте мне текст, который будет служить подписью к вашей будущей записи в телеграм посте. Текст перенесётся в пост в том форматировании в котором вы его отправите \n\nЕсли текста нет, то напишите "нет".\n\nЛибо воспользуйтесь одной из кнопок(в кнопке 🦊 доступна генерация изображений и много чего ещё):\n\n',                       

            reply_markup=reply_markup,
            parse_mode='HTML'
        )

        user_data[user_id] = {'status': 'awaiting_artist_link'}
        return ASKING_FOR_ARTIST_LINK
    # Проверяем, если бот в режиме поиска
    if users_in_send_mode.get(user_id, False):
        await duplicate_message(update, context) 
    # Проверяем, если бот в режиме поиска
    if is_search_mode.get(user_id, False):
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            image_path = 'temp_image.jpg'
        elif update.message.document and update.message.document.mime_type.startswith('image/'):
            file = await update.message.document.get_file()
            image_path = 'temp_image.jpg'
        else:
            await update.message.reply_text("Пожалуйста, отправьте изображение для поиска.")
            return ASKING_FOR_FILE

        await file.download_to_drive(image_path)

        # Отправляем первоначальное сообщение о загрузке файла
        loading_message = await update.message.reply_text("Загрузка файла на хостинг...")

        # Загружаем изображение на Catbox
        img_url = await upload_catbox(image_path)
        context.user_data['img_url'] = img_url 

        # Обновляем сообщение о статусе загрузки
        await loading_message.edit_text("Файл успешно загружен! Ожидание ответа от SauceNAO... обычно это занимает до 5 секунд")

        # Создаем URL для поиска
        search_url = f"https://saucenao.com/search.php?db=999&url={img_url}"
        yandex_search_url = f"https://yandex.ru/images/search?source=collections&rpt=imageview&url={img_url}"
        google_search_url = f"https://lens.google.com/uploadbyurl?url={img_url}"
        bing_search_url = f"https://www.bing.com/images/search?view=detailv2&iss=sbi&form=SBIVSP&sbisrc=UrlPaste&q=imgurl:{img_url}"

        keyboard = [
            [InlineKeyboardButton("АИ или нет?", callback_data='ai_or_not')],
            [InlineKeyboardButton("Все результаты на SauceNAO", url=search_url)],
            [InlineKeyboardButton("Поиск через Yandex Images", url=yandex_search_url)],
            [InlineKeyboardButton("Поиск через Google Images", url=google_search_url)],
            [InlineKeyboardButton("Поиск через Bing Images", url=bing_search_url)],
            [InlineKeyboardButton("Завершить поиск", callback_data='finish_search')],
            [InlineKeyboardButton("‼️Полный Сброс Бота‼️", callback_data='restart')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)        

        try:
            # Получаем авторов и ссылки через SauceNAO
            authors_text, external_links, jp_name, details_text, ep_name, ep_time, dA_id, full_author_text, pixiv_id, twitter_id = await search_image_saucenao(image_path)
        except Exception as e:
            # Обработка ошибок, например, превышение лимита запросов
            if str(e) == "Лимит превышен":
                await loading_message.edit_text("Лимит запросов к SauceNAO у бота на сегодня исчерпан. Всего их 100 запросов на всех пользователей бота в сутки. Попробуйте через пару часов, либо воспользуйтесь одной из кнопок ниже чтобы поискать источники самостоятельно.", reply_markup=reply_markup)
            else:
                await loading_message.edit_text(f"Произошла ошибка при обращении к SauceNAO: {str(e)}", reply_markup=reply_markup)
            os.remove(image_path)
            return ASKING_FOR_FILE

        os.remove(image_path)

        # Подготовка ссылок в удобном для чтения формате
        links_text = "\n".join(f"{i + 1}. {link}" for i, link in enumerate(external_links)) if isinstance(external_links, list) else None
        
        # Формируем сообщение
        reply_text = "Результаты поиска:\n"
        if authors_text:
            reply_text += f"Название: {authors_text}\n"
        if details_text:
            reply_text += f"Детали: {details_text}\n\n"
        if jp_name:
            reply_text += f"JP Название: {jp_name}\n"
        if ep_name:
            reply_text += f"{ep_name}\n"
        if dA_id:
            reply_text += f"dA ID: {dA_id}\n"
        if twitter_id:
            reply_text += f"Твиттер:\n{twitter_id}"               
        if pixiv_id:
            reply_text += f"Pixiv: {pixiv_id}\n"
        if full_author_text:
            reply_text += f"Автор: {full_author_text}\n"
        if ep_time:
            reply_text += f"{ep_time}\n\n"
        if links_text:
            reply_text += f"Ссылки:\n{links_text}"



        # Если нет данных, отправляем сообщение о том, что ничего не найдено
        if not authors_text and not links_text:
            reply_text = (
                "К сожалению, ничего не найдено. "
                "Возможно, изображение сгенерировано, возможно автор малоизвестен или изображение слишком свежее. Отправьте другое изображение или завершите поиск"
            )

        # Обновляем сообщение результатами поиска с кнопками
        await loading_message.edit_text(reply_text.strip(), reply_markup=reply_markup)

        return ASKING_FOR_FILE



    # Проверяем, если бот в режиме ocr
    if is_ocr_mode.get(user_id, False):
        # Проверяем, отправил ли пользователь фото или документ
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            image_path = 'temp_image.jpg'
        elif update.message.document and update.message.document.mime_type.startswith('image/'):
            file = await update.message.document.get_file()
            image_path = 'temp_image.jpg'
        else:
            keyboard = [
                [InlineKeyboardButton("Отменить режим распознавания", callback_data='finish_ocr')],
                [InlineKeyboardButton("‼️Полный Сброс Бота‼️", callback_data='restart')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Пожалуйста, отправьте изображение для распознавания",
                reply_markup=reply_markup
            )
            return ASKING_FOR_OCR

        # Загружаем файл и отправляем сообщение о процессе
        loading_message = await update.message.reply_text("Загрузка изображения...")

        await file.download_to_drive(image_path)

        # Загружаем изображение на Catbox и обновляем сообщение
        await loading_message.edit_text("Изображение загружается на Catbox...")
        img_url = await second_upload_image(image_path)
        inat_url = "https://www.inaturalist.org/computer_vision_demo"

        context.user_data['img_url'] = img_url

        # Формируем клавиатуру с кнопками для распознавания
        keyboard = [
            [InlineKeyboardButton("📃Распознать текст📃", callback_data='recognize_text')],
            [InlineKeyboardButton("🖼️Распознать текст через GPT🖼️", callback_data='text_rec_with_gpt')],  # Новая кнопка            
            [InlineKeyboardButton("🌸Распознать растение🌸", callback_data='recognize_plant')],
            [InlineKeyboardButton("🍄‍🟫Распознать гриб 🍄‍🟫", callback_data='mushrooms_gpt')],            
            [InlineKeyboardButton("🍂Что не так с растением?🍂", callback_data='text_plant_help_with_gpt')],
            [InlineKeyboardButton("Распознать на iNaturalist", url=inat_url)],
            [InlineKeyboardButton("❌Отменить режим распознавания❌", callback_data='finish_ocr')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Обновляем сообщение с кнопками после успешной загрузки
        await loading_message.edit_text(
            "Изображение успешно загружено! Что именно вы желаете распознать? Обычно обработка запроса занимает до 10-15 секунд. Распознавание через GPT поддерживает текст, написанный от руки, но читаемым почерком",
            reply_markup=reply_markup
        )

        return ASKING_FOR_OCR

    status = user_data[user_id].get('status')
    logger.info(f"status {status}")
    if waiting_for_vk.get(user_id, False):

        return await handle_vk_keys_input(update, context)    
    if waiting_for_forward.get(user_id, False):

        return await handle_forwarded_message(update, context)
    if waiting_for_caption.get(user_id, False):
        key = waiting_for_caption[user_id]
        return await handle_new_caption(update, context, key)



    # Проверяем, если бот в режиме GPT
    if is_gpt_mode.get(user_id, False):
        return await gpt_running(update, context)  # Вызываем функцию gpt_running

    if is_role_mode.get(user_id, False):
        return await receive_role_input(update, context)

    if is_asking_mode.get(user_id, False):
        return await receive_followup_question(update, context)





    if update.message:
        message_to_reply = update.message

        # Проверяем состояние пользователя
        if user_data.get(user_id, {}).get('status') == 'awaiting_artist_link':
            if update.message.media_group_id:
                await message_to_reply.reply_text(
                    "Пожалуйста, отправьте сначала текстовую подпись для будущего поста либо \"нет\", если она не нужна"
                )
                return ConversationHandler.END
  
              
            # Получаем текст сообщения
            if update.message.text:

                text = format_text_to_html(update.message)  

                # Проверка на наличие HTML-ссылок
                html_link_pattern = r'<a\s+href="(https?://[^\s]+)"[^>]*>.*?</a>'
                html_links = re.findall(html_link_pattern, text)

                if html_links:  # Если найдены HTML-ссылки
                    # Считываем весь текст как title
                    title = text.strip()  # Весь текст считывается как заголовок
                    user_data[user_id] = {
                        'status': 'awaiting_image',
                        'artist_link': "",
                        'extra_links': [],
                        'author_name': "",
                        'title': title,  # Сохраняем весь текст как title
                        'media': [],
                        'image_counter': 0,
                    }
                    await update.message.reply_text(
                        "✅ Отлично! ( ´ ω  ) Принято. Теперь отправьте изображения без сжатия, как документы.\n\n Либо если вам нужен текстовый пост, то отправьте \"нет\""
                    )
                    return 'awaiting_image'
                
                # Если нет HTML-ссылок, продолжаем искать обычные ссылки
                link_pattern = r'https?://[^\s]+'
                links = re.findall(link_pattern, text)

                if not links:  # Если ссылки не найдены
                    # Удаляем пробелы и лишние символы из текста
                    author_input = re.sub(r'^\s+|\s+$', '', text)
                    title = author_input            
                    # Проверяем, весь ли текст внутри "^...^"


                    artist_link = ""
                    extra_links = []

                    # Сохраняем данные в user_data
                    user_data[user_id] = {
                        'status': 'awaiting_image',
                        'artist_link': artist_link,
                        'extra_links': extra_links,
                        'author_name': "",
                        'title': title,  # Если нет заголовка, используем имя автора
                        'media': [],
                        'image_counter': 0,
                    }

                    await update.message.reply_text(
                        "✅ Отлично! ( ´ ω ` ) Принято. Теперь отправьте изображения без сжатия, как документы.\n\n Либо если вам нужен текстовый пост, то отправьте \"нет\""
                    )
                    return 'awaiting_image'               
                # Если сообщение не содержит ссылок или не является только ссылкой, выполняем дальнейший код
                if ' ' in text:
                    parts = text.split(maxsplit=1)

                    if len(parts) > 0:
                        # Проверка на формат с "*"
                        if parts[0].startswith('*'):
                            artist_link = ""  # Если начинается с "*", то ссылка пустая
                            author_input = parts[1] if len(parts) > 1 else ''  # Остальная часть - это текст
                        else:
                            artist_link_match = re.match(r'(https?://[^\s]+)', parts[0])
                            artist_link = artist_link_match.group(1) if artist_link_match else ""
                            author_input = parts[1] if len(parts) > 1 else ''  # Остальная часть - это текст

                        # Извлечение дополнительных ссылок
                        all_links = re.findall(r'https?://[^\s,]+', author_input)
                        extra_links = [artist_link] + all_links if artist_link else all_links
                        logger.info(f"extra_links: {extra_links}") 
                        logger.info(f"all_links: {all_links}")                        
                        # Убираем ссылки из текста, чтобы оставить только имя автора
                        author_input = re.sub(r'https?://[^\s,]+', '', author_input).strip()

                        # Удаляем лишние разделители (например, начальные и конечные запятые)
                        author_input = re.sub(r'^[,]+|[,]+$', '', author_input).strip()
                        author_input = author_input.strip()  # На всякий случай окончательно удаляем пробелы
                        # Проверяем, если авторское имя обернуто в "^...^"

                       
                        match_full = re.match(r'^\^(.*)\^$', author_input, re.S)
                        if match_full:
                            # Если весь текст внутри "^...^", используем его как заголовок и убираем авторское имя
                            title = match_full.group(1).strip()
                            user_data[user_id] = {
                                'status': 'awaiting_image',
                                'artist_link': artist_link,
                                'extra_links': extra_links,
                                'author_name': "",
                                'title': title,  # Используем как заголовок
                                'media': [],
                                'image_counter': 0,
                            }

                        else:
                            # Проверка на наличие фразы в начале текста "^...^"
                            match_partial = re.match(r'^\^(.*?)\^\s*(.*)', author_input, re.S)
                            if match_partial:
                                # Извлекаем фразу и имя автора
                                phrase = match_partial.group(1).strip()  # Фраза из "^...^"
                                author_name = match_partial.group(2).strip()  # Остаток текста как автор
                                user_data[user_id] = {
                                    'status': 'awaiting_image',
                                    'artist_link': artist_link,
                                    'extra_links': extra_links,
                                    'author_name': author_name,  # Имя автора
                                    'title': author_name,  # Используем как заголовок
                                    'extra_phrase': phrase,  # Сохраняем фразу
                                    'media': [],
                                    'image_counter': 0,
                                }
                            else:
                                # Если нет фразы в "^...^", сохраняем всё как имя автора
                                author_name = author_input
                                user_data[user_id] = {
                                    'status': 'awaiting_image',
                                    'artist_link': artist_link,
                                    'extra_links': extra_links,
                                    'author_name': author_name,
                                    'title': author_name,  # Заголовок статьи
                                    'media': [],
                                    'image_counter': 0,
                                }

                        # Ответ, что теперь ожидается изображение в виде документа
                        await update.message.reply_text(
                            "Теперь отправьте изображение в формате документа."
                        )

                        return 'awaiting_image'

            # Если ожидаемое изображение пришло как документ
            elif update.message.document and update.message.document.mime_type.startswith('image/'):
                # Обрабатываем caption с разметкой
                caption = (
                    format_text_to_html(update.message)
                    if update.message.caption
                    else ''
                )
                
                # Разделяем текст по запятой, чтобы извлечь все ссылки
                parts = caption.split(',', maxsplit=1)
                if len(parts) > 0:
                    # Первая часть - это либо первая ссылка, либо текст
                    # Ищем все ссылки в тексте
                    links = re.findall(r'https?://[^\s,]+', caption)
                    
                    # Первая ссылка — это artist_link, если она есть
                    artist_link = links[0] if links else ''
                    
                    # Все ссылки добавляются в extra_links
                    extra_links = links
                    
                    # Убираем все ссылки из текста, чтобы оставить только имя автора
                    author_input = re.sub(r'https?://[^\s,]+', '', caption).strip()

                    # Удаляем лишние запятые, пробелы и любые разделители, оставшиеся после удаления ссылок
                    author_input = author_input.strip()  # На всякий случай окончательно удаляем пробелы



                    # Проверяем, если авторское имя обернуто в "^...^"
                    match_full = re.match(r'^\^(.*)\^$', author_input, re.S)
                    if match_full:
                        # Если весь текст внутри "^...^", используем его как заголовок и убираем авторское имя
                        title = match_full.group(1).strip()
                        # Проверяем, есть ли автор в базе

                        user_data[user_id] = {
                            'status': 'awaiting_image',
                            'artist_link': artist_link,
                            'extra_links': extra_links,
                            'author_name': "",
                            'title': title,  # Используем как заголовок
                            'media': [],
                            'image_counter': 0,
                        }

                    else:
                        # Проверка на наличие фразы в начале текста "^...^"
                        match_partial = re.match(r'^\^(.*?)\^\s*(.*)', author_input, re.S)
                        if match_partial:
                            # Извлекаем фразу и имя автора
                            phrase = match_partial.group(1).strip()  # Фраза из "^...^"
                            author_name = match_partial.group(2).strip()  # Остаток текста как автор

                            user_data[user_id] = {
                                'status': 'awaiting_image',
                                'artist_link': artist_link,
                                'extra_links': extra_links,
                                'author_name': author_name,  # Имя автора
                                'title': author_name,  # Используем как заголовок
                                'extra_phrase': phrase,  # Сохраняем фразу
                                'media': [],
                                'image_counter': 0,
                            }
                        else:
                            # Если нет фразы в "^...^", сохраняем всё как имя автора
                            author_name = author_input
                            user_data[user_id] = {
                                'status': 'awaiting_image',
                                'artist_link': artist_link,
                                'extra_links': extra_links,
                                'author_name': author_name,
                                'title': author_name,  # Заголовок статьи
                                'media': [],
                                'image_counter': 0,
                            }

                
                    # Обработка изображения
                    await handle_image(update, context)

                    # Вызов команды /publish после обработки изображения
                    await publish(update, context)

                    # Завершение процесса для данного пользователя
                    if user_id in user_data:
                        del user_data[user_id]  # Очистка данных пользователя, если нужно
                    else:
                        logger.warning(f"Попытка удалить несуществующий ключ: {user_id}")

                    user_data[user_id] = {'status': 'awaiting_artist_link'}

                    return ASKING_FOR_ARTIST_LINK


            # Проверка, если пользователь отправил изображение как фото (photo)
            elif update.message.photo:
                await message_to_reply.reply_text(
                    "Пожалуйста отправьте файл документом"
                )
                return ConversationHandler.END

    # Проверка, если событие пришло от callback_query
    elif update.callback_query:
        message_to_reply = update.callback_query.message
    else:
        return ConversationHandler.END

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


async def run_gpt(update: Update, context: CallbackContext) -> int:
    if update.message:
        user_id = update.message.from_user.id  # Когда вызвано командой /search
        message_to_reply = update.message
    elif update.callback_query:
        user_id = update.callback_query.from_user.id  # Когда нажата кнопка "Начать поиск"
        message_to_reply = update.callback_query.message
        
        # Убираем индикатор загрузки на кнопке
        await update.callback_query.answer()

    # Устанавливаем флаг режима GPT и сбрасываем другие режимы
    is_gpt_mode[user_id] = True
    is_search_mode[user_id] = False
    is_ocr_mode[user_id] = False
    keyboard = [
        [InlineKeyboardButton("❌ Сбросить диалог", callback_data='reset_dialog')],
        [InlineKeyboardButton("⬅️ Выйти из режима диалога", callback_data='stop_gpt')],
        [InlineKeyboardButton("🏙 Посмотреть чужие генерации", callback_data="view_shared")],        
        [InlineKeyboardButton("🎨 Сменить модель(стиль)", callback_data='choose_style')],        
        [InlineKeyboardButton("✏️ Придумать новую роль", callback_data='set_role_button')],
        [InlineKeyboardButton("📜 Выбрать роль", callback_data='role_select')],  
        [InlineKeyboardButton("📗 Помощь", callback_data='short_help_gpt')],           
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Отправляем сообщение о начале режима общения с GPT
    await message_to_reply.reply_text("Режим общения с GPT активирован. Отправьте сообщение чтобы начать диалог с ботом или воспользуйтесь одной из команд. Кроме того бот может искать и анализировать информацию в интеренете, анализировать содержимое ссылки веб-страницы, распознавать фото, видео, аудио, музыку, документы и тд. \n\nА так же генерировать изображения через SD3 или Flux если начать сообщение со слова \"Нарисуй\". Для подробностей воспользуйтесь кнопкой \"помощь\"",  
            reply_markup=reply_markup  # Добавляем кнопки
        )
    
    return RUNNING_GPT_MODE


async def handle_short_gpt_help(update: Update, context: CallbackContext) -> None:
    """Обработчик для кнопки 'Помощь по GPT'."""
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    help_text_1 = """
Режим диалога с ботом поддерживает следующие функции:

---Ведения связного диалога с контекстом в несколько сотен сообщений

---Выбор, придумывание и хранение ролей для диалога

---Доступ в интернет. Бот имеет доступ в сеть в связи с чем вы можете попросить его найти там что-то и предоставить информацию в удобном для вас виде. Например узнать что идёт в кино, погоду, найти и упорядочить какую-то информацию и тд

---Анализ содержания веб страниц по ссылке на них. Вы можете отправить боту ссылку на любую веб страницу и попросить бота что-то сделать с ней. Например отправить боту ссылку на научную статью написанную на английском языке и попросить пересказать выводы этой статьи на русском. Можете так же придумать что угодно ещё. Сылка и запрос к ней должны быть в одном сообщении

---Безлимитный анализ изображений, вы можете попросить бота что-то распознать с изображения, объяснить, дать совет и что угодно ещё

---Анализ музыки в виде mp3 файлов и голосовых сообщений. Например вы можете спросить что за жанр у данной песни, попросить посоветовать что-то похожее, распознать текст песни или голососвго сообщения и тд. У данной функции есть лимит в 20мб на отправляемый файл

---Анализ коротких видео и гиф. Так же как и с музыкой, есть лимит 20мб на файл

---Анализ .txt и .pdf документов. Для того чтобы он сработал корректно отправьте боту пояснение того что вам нужно сделать с информацией в файле ДО или одновременно с отправкой файла, но не после

===============================================================================

Так же в боте доступна генерация изображений. Для этого в режиме диалога с ботом начните своё сообщение с слова "Нарисуй: ***" где вместо *** вбейте свой запрос на любом языке. Если после генерации вы видите надпись "Ошибка при обработке запроса." вместо вашего запроса, то это значит что сломалась нейросеть переводящая запросы на английский. В таком случае вам придётся указать запрос на английском самостоятельно

Примеры запросов:
<pre>Нарисуй: кот на подоконнике</pre>
Обычный запрос, все настройки выставлены по-умолчанию.

<pre>нарисуй:765576, ангел в заснеженном лесу (3), [3:2]</pre>
Запрос с настройками. В данном случае 765576 - это <b>seed</b>, 3  - <b>guidance_scale</b>, а 3:2 - соотношение сторон изображения. <b>Steps</b> в круглых скобках при этом не указан и выставлен по-умолчанию. Так же "нарисуй" написано с маленькой буквы, это тоже правильный вариант.

<pre>Нарисуй дом в корнях огромного дерева (4, 20) [3:5]</pre>
Тут указан <b>Steps</b> - 20. А так же <b>guidance_scale</b> - 4 и соотношение 3:5. "Нарисуй" написано без двоеточия - такой вариант тоже считывается

<code>seed</code> - это идентификатор каждого конкретного сгенерированного изображения. Если вам понравилась какая-то из генераций, но вы хотите посмотреть как бы она выглядела с другими настройками, то вы можете использовать её seed для того чтобы изменять конкретно данную генерацию лишь слегка корректирую запрос или прочие настройки.
<code>guidance_scale</code> - это приближение генерации к тексту вашего запроса. Чем число выше, тем сильнее нейросеть пытается воссоздать именно текстовый запрос, однако сама генерация от этого может получитсья хуже, более грубой и с большим числом артефактов. Обычно корректное значение между 2 и 6, но в целом диапазон от 1 до 20
<code>Steps</code> - это шаги повторных обработок изображения. Чем их больше тем больше на изображении деталей и тем лучше оно прорисовано. Однако слишком большое число существенно замедляет время генерации и даёт не особо красивые перегруженные деталями генерации. Адекватные значения 15-30.

Кроме того, в некоторых моделях, наприме SD turbo используются свои очень специфические параметры. В упомянутой turbo напрмиер guidance_scale равен 1 а steps около 4-6 и только в таких значениях данная модель выдаёт хорошие результаты. Так что если вы поменяли настройки в генерации какой-то модели и она "сломалась", то вероятно причина именно в этом.
    """
    keyboard = [
        [InlineKeyboardButton("❌ Сбросить диалог", callback_data='reset_dialog')],
        [InlineKeyboardButton("⬅️ Выйти из режима диалога", callback_data='stop_gpt')],
        [InlineKeyboardButton("✏️ Придумать новую роль", callback_data='set_role_button')],
        [InlineKeyboardButton("📜 Выбрать роль", callback_data='role_select')],  
        [InlineKeyboardButton("🎨 Сменить модель(стиль)", callback_data='choose_style')] 
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Отправляем сообщение с кнопкой
    await query.edit_message_text(help_text_1, parse_mode="HTML", reply_markup=reply_markup)









async def stop_gpt(update: Update, context: CallbackContext) -> int:
    # Проверяем, был ли вызов через кнопку или команду
    if update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        await query.message.reply_text(
            "Режим общения с GPT отключен. Вы вернулись к основному режиму.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎨 Найти автора или проверить на ИИ 🎨", callback_data='start_search')],
                [InlineKeyboardButton("🌱 Распознать(растение, грибы, текст) 🌱", callback_data='start_ocr')], 
                [InlineKeyboardButton("‼️Полный Сброс Бота‼️", callback_data='restart')]
            ])
        )
    else:
        # Если вызов произошел через команду
        user_id = update.message.from_user.id
        await update.message.reply_text(
            "Режим общения с GPT отключен. Вы вернулись к основному режиму.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎨 Найти автора или проверить на ИИ 🎨", callback_data='start_search')],
                [InlineKeyboardButton("🌱 Распознать (Растение или текст) 🌱", callback_data='start_ocr')], 
                [InlineKeyboardButton("‼️Полный Сброс Бота‼️", callback_data='restart')]
            ])
        )

    is_ocr_mode[user_id] = False  # Выключаем режим поиска
    is_search_mode[user_id] = False
    is_gpt_mode[user_id] = False
    is_role_mode[user_id] = False
    is_asking_mode[user_id] = False  # Отключаем режим GPT для пользователя
    return ConversationHandler.END






async def send_reply_with_limit(update, text, reply_markup=None):
    MAX_MESSAGE_LENGTH = 4096

    # Экранируем Markdown перед разбиением
    text = escape_gpt_markdown_v2(text)

    # Разбиваем текст с учетом открытых/закрытых тегов
    text_parts = split_text_preserving_tags(text, MAX_MESSAGE_LENGTH)

    logger.info(f"text_parts {text_parts}.")
    for part in text_parts:
        logging.info(f"Отправка текста в Telegram: {part[:200]}...")  # Логируем первые 200 символов
        await update.message.reply_text(part, reply_markup=reply_markup, parse_mode='MarkdownV2')

def split_text_preserving_tags(text, max_length):
    """Разбивает текст, сохраняя последовательность открытых и закрытых тегов"""
    parts = []
    current_part = ""
    open_tags = []

    for line in text.split("\n"):
        if len(current_part) + len(line) + 1 > max_length:
            # Закрываем все открытые теги перед разрывом
            for tag in reversed(open_tags):
                current_part += f"\n{tag}"

            parts.append(current_part)
            current_part = ""

            # Повторяем открытые теги в новом фрагменте
            for tag in open_tags:
                current_part += f"{tag}\n"

        # Обновляем список открытых тегов
        if line.strip().startswith("```"):
            tag = line.strip()
            if tag in open_tags:
                open_tags.remove(tag)  # Закрываем блок
            else:
                open_tags.append(tag)  # Открываем блок

        current_part += line + "\n"

    # Добавляем последний кусок
    if current_part:
        for tag in reversed(open_tags):
            current_part += f"\n{tag}"  # Закрываем оставшиеся теги
        parts.append(current_part)

    return parts

def escape_gpt_markdown_v2(text):
    # Проверка на наличие экранирования и удаление, если оно присутствует
    if re.search(r'\\[\\\*\[\]\(\)\{\}\.\!\?\-\#\@\&\$\%\^\&\+\=\~]', text):
        # Убираем экранирование у всех специальных символов Markdown
        text = re.sub(r'\\([\\\*\[\]\(\)\{\}\.\!\?\-\#\@\&\$\%\^\&\+\=\~])', r'\1', text)

    # Временная замена ** на |TEMP| без экранирования
    text = re.sub(r'\*\*(.*?)\*\*', r'|TEMP|\1|TEMP|', text)

    # Временная замена ``` на |CODE_BLOCK| для исключения из экранирования
    text = text.replace('```', '|CODE_BLOCK|')

    # Временная замена ` на |INLINE_CODE| для исключения из экранирования
    text = text.replace('`', '|INLINE_CODE|')

    # Экранируем все специальные символы
    text = re.sub(r'(?<!\\)([\\\*\[\]\(\)\{\}\.\!\?\-\#\@\&\$\%\^\&\+\=\~\<\>])', r'\\\1', text)

    # Восстанавливаем |TEMP| обратно на *
    text = text.replace('|TEMP|', '*')

    # Восстанавливаем |CODE_BLOCK| обратно на ```
    text = text.replace('|CODE_BLOCK|', '```')

    # Восстанавливаем |INLINE_CODE| обратно на `
    text = text.replace('|INLINE_CODE|', '`')

    # Экранируем символ |
    text = re.sub(r'(?<!\\)\|', r'\\|', text)

    # Экранируем символ _ везде, кроме конца строки
    text = re.sub(r'(?<!\\)_(?!$)', r'\\_', text)

    return text





def chunk_buttons(buttons, chunk_size):
    """Группирует кнопки по chunk_size в строке."""
    return [buttons[i:i + chunk_size] for i in range(0, len(buttons), chunk_size)]



async def handle_role_select(update: Update, context: CallbackContext):
    """Обработчик для выбора роли из списка."""
    user_id = (
        update.callback_query.from_user.id
        if update.callback_query
        else update.message.from_user.id
    )

    # Получаем роли пользователя, если есть
    roles = user_roles.get(user_id, {})
    
    # Если ролей нет, отображаем только дефолтные роли
    if not roles:
        # Исключаем default_role из отображаемых ролей
        excluded_roles = {"default_role"}
        
        # Создаём кнопки для дефолтных ролей
        default_buttons = [
            InlineKeyboardButton(role_data["short_name"], callback_data=f"defaultrole_{role_id}")
            for role_id, role_data in DEFAULT_ROLES.items()
            if role_id not in excluded_roles
        ]

        # Группируем кнопки
        grouped_default_buttons = chunk_buttons(default_buttons, 3)
        new_role_button = [InlineKeyboardButton("✏️ Добавить новую роль", callback_data='set_role_button')]
        cancel_button = [InlineKeyboardButton("⬅️Отмена⬅️", callback_data='run_gpt')]  # Кнопка отмены        
        # Формируем клавиатуру и текст сообщения
        keyboard = InlineKeyboardMarkup(grouped_default_buttons + [new_role_button] + [cancel_button])
        message_text = "У вас пока нет своих ролей. Выберите одну из доступных ролей по умолчанию."

        # Отправляем сообщение
        if update.callback_query:
            await update.callback_query.answer()
            await update.effective_chat.send_message(message_text, reply_markup=keyboard, parse_mode='Markdown')
        else:
            await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode='Markdown')
        context.user_data['role_message_id'] = msg.message_id
        return

    # Определяем исключаемые роли
    excluded_roles = {"default_role", "selected_role"}

    # Определяем текущую выбранную роль
    current_role = None
    if "selected_role" in roles:
        current_role = f"Текущая роль: *{roles['selected_role']}*"
    elif "default_role" in roles and roles["default_role"] in DEFAULT_ROLES:
        current_role = f"Текущая роль: *{DEFAULT_ROLES[roles['default_role']]['short_name']}*"

    # Создаём кнопки для ролей по умолчанию, исключая default_role
    default_buttons = [
        InlineKeyboardButton(role_data["short_name"], callback_data=f"defaultrole_{role_id}")
        for role_id, role_data in DEFAULT_ROLES.items()
        if role_id not in excluded_roles
    ]

    # Создаём кнопки для пользовательских ролей, исключая selected_role
    custom_buttons = []
    if "short_names" in roles:
        custom_buttons = [
            InlineKeyboardButton(
                roles["short_names"].get(role_id, " ".join(str(role_text).split()[:5])),
                callback_data=f"newroleselect_{role_id}"
            )
            for role_id, role_text in roles.items()
            if role_id not in excluded_roles and role_id != "short_names"
        ]

    # Группируем кнопки
    grouped_default_buttons = chunk_buttons(default_buttons, 3)
    grouped_custom_buttons = chunk_buttons(custom_buttons, 1)

    # Добавляем новую кнопку в конец
    new_role_button = [InlineKeyboardButton("✏️ Добавить новую роль", callback_data='set_role_button')]
    cancel_button = [InlineKeyboardButton("⬅️Отмена⬅️", callback_data='run_gpt')]  # Кнопка отмены    

    # Объединяем кнопки и формируем клавиатуру
    keyboard = InlineKeyboardMarkup(grouped_default_buttons + grouped_custom_buttons + [new_role_button] + [cancel_button])

    # Формируем сообщение с учётом текущей роли
    message_text = "Выберите роль из списка."
    if current_role:
        message_text += f"\n\n{current_role}"

    # Отправляем ответ в зависимости от типа update
    if update.callback_query:
        await update.callback_query.answer()
        await update.effective_chat.send_message(message_text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode='Markdown')
    context.user_data['role_message_id'] = msg.message_id

# Обработчик выбора роли (включая роли по умолчанию)
async def handle_role_selected(update: Update, context: CallbackContext):
    """Обработчик выбора конкретной роли из кнопок."""
    user_id = update.callback_query.from_user.id
    query_data = update.callback_query.data

    if query_data.startswith("defaultrole_"):
        role_id = query_data.split("_")[1]
        selected_role_data = DEFAULT_ROLES.get(role_id)

        if selected_role_data:
            # Устанавливаем выбранную роль как default_role
            if user_id not in user_roles:
                user_roles[user_id] = {}

            user_roles[user_id]["default_role"] = role_id  # Сохраняем ID роли
            user_roles[user_id].pop("selected_role", None)             
            save_context_to_firebase(user_id)  # Сохраняем изменения в Firebase

            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                f"Вы выбрали предустановленную роль: {selected_role_data['short_name']}"
            )
        else:
            await update.callback_query.answer("Ошибка выбора роли.")

    elif query_data.startswith("newroleselect_"):
        role_id = query_data.split("_")[1]  # Получаем ID роли

        if user_id in user_roles and role_id in user_roles[user_id]:
            selected_role = user_roles[user_id][role_id]

            # Устанавливаем выбранную роль как "selected_role" и сбрасываем default_role
            user_roles[user_id]["selected_role"] = selected_role
            user_roles[user_id].pop("default_role", None)  # Удаляем default_role, если он существует

            save_context_to_firebase(user_id)

            # Создаём инлайн-кнопку для удаления роли
            delete_button = InlineKeyboardButton(
                "Удалить эту роль",
                callback_data=f"clear_role_{role_id}"
            )
            keyboard = InlineKeyboardMarkup([[delete_button]])

            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                f"Вы выбрали роль: {selected_role}",
                reply_markup=keyboard
            )
        else:
            await update.callback_query.answer("Ошибка выбора роли.")


async def handle_delete_role(update: Update, context: CallbackContext):
    """Обработчик удаления выбранной роли."""
    user_id = update.callback_query.from_user.id
    query_data = update.callback_query.data
    role_id = query_data.split("_")[2]  # Получаем ID роли из callback_data

    if user_id in user_roles and role_id in user_roles[user_id]:
        # Удаляем роль
        deleted_role = user_roles[user_id].pop(role_id)
        save_context_to_firebase(user_id)

        await update.callback_query.answer("Роль удалена.")
        await update.callback_query.message.reply_text(
            f"Роль '{deleted_role}' была успешно удалена."
        )

        # Удаляем старое сообщение с клавиатурой, если оно существует
        if 'role_message_id' in context.user_data:
            try:
                await context.bot.delete_message(
                    chat_id=update.callback_query.message.chat_id,
                    message_id=context.user_data['role_message_id']
                )
            except Exception as e:
                print(f"Ошибка при удалении сообщения: {e}")

        # Обновляем клавиатуру
        await handle_role_select(update, context)
    else:
        await update.callback_query.answer("Ошибка удаления роли.")


async def set_role(update: Update, context: CallbackContext):
    """Команда для установки новой роли пользователем."""
    user_id = update.message.from_user.id
    role_text = update.message.text.replace("/set_role", "").strip()
    
    if role_text:
        set_user_role(user_id, role_text)
        await update.message.reply_text(f"Ваша роль успешно сохранена и применена: {role_text}")
    else:
        await update.message.reply_text("Пожалуйста, введите роль после команды /set_role.")

async def handle_set_role_button(update: Update, context: CallbackContext):
    """Обработчик для кнопки установки роли."""
    user_id = update.callback_query.from_user.id
    
    # Завершаем текущий разговор с GPT, если он активен
    if is_gpt_mode.get(user_id, False):
        is_gpt_mode[user_id] = False  # Выключаем режим GPT
    
    # Включаем режим ролей
    is_role_mode[user_id] = True
    await update.callback_query.answer()  # Отправить ответ на нажатие кнопки

    # Отправляем сообщение с HTML-разметкой
    await update.callback_query.message.reply_text(
        "Пожалуйста, введите описание новой роли. Это может быть очень короткое, либо наоборот длинное и подробное описание. "
        "В круглых скобках в начале вы можете указать слово или фразу, которая будет отображаться в кнопке. Пример: \n"
        "<pre>(Лиса) Ты мудрая старая лиса, живущая на окраине волшебного леса</pre>",
        parse_mode='HTML'
    )
    
    return ASKING_FOR_ROLE


async def receive_role_input(update: Update, context: CallbackContext):
    """Обработчик для ввода роли пользователем."""
    user_id = update.message.from_user.id
    role_text = update.message.text.strip()

    if role_text:
        set_user_role(user_id, role_text)  # Устанавливаем роль
        await update.message.reply_text(f"Ваша роль успешно изменена на: {role_text}")
    else:
        await update.message.reply_text("Пожалуйста, введите роль после команды /set_role.")
    
    # Отключаем режим ролей и возвращаемся в режим GPT
    is_role_mode[user_id] = False
    is_gpt_mode[user_id] = True  # Включаем режим GPT обратно
    await handle_role_select(update, context)    
    return ConversationHandler.END  # Завершаем разговор, можно продолжить с основного состояния  



async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    username = update.message.from_user.username or update.message.from_user.first_name
    user_id = update.message.from_user.id  # Получение user_id
    caption = update.message.caption or ""

    logger.info("Обработка аудио от пользователя")

    # Скачивание аудиофайла
    audio = update.message.audio or update.message.voice
    file = await context.bot.get_file(audio.file_id)

    # Определение исходного расширения файла
    file_extension = os.path.splitext(file.file_path)[1] or ".oga"  # Если расширение неизвестно, используем .oga

    # Создание временного файла с исходным расширением
    fd, local_file_path = tempfile.mkstemp(suffix=file_extension)

    # Закрытие файлового дескриптора, чтобы освободить ресурс
    os.close(fd)

    # Загрузка аудио в файл
    await file.download_to_drive(local_file_path)

    try:
        # Генерация ответа с передачей user_id
        full_audio_response = await generate_audio_response(local_file_path, user_id, query=caption)



        # Отправка текста с результатом пользователю
        await update.message.reply_text(full_audio_response)

    finally:
        # Удаление временного файла
        os.remove(local_file_path)

async def handle_gptgif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    username = update.message.from_user.username or update.message.from_user.first_name
    user_id = update.message.from_user.id  # Получение user_id
    caption = update.message.caption or ""

    logger.info("Обработка GIF от пользователя")

    # Скачивание GIF
    animation = update.message.animation
    file = await context.bot.get_file(animation.file_id)

    # Определение исходного расширения файла
    file_extension = os.path.splitext(file.file_path)[1] or ".mp4"  # Если расширение неизвестно, используем .mp4

    # Создание временного файла с исходным расширением
    fd, local_file_path = tempfile.mkstemp(suffix=file_extension)

    # Закрытие файлового дескриптора, чтобы освободить ресурс
    os.close(fd)

    # Загрузка GIF в файл
    await file.download_to_drive(local_file_path)

    try:
        # Генерация ответа
        full_animation_response = await generate_animation_response(local_file_path, user_id, query=caption)


        # Отправка текста с результатом пользователю
        await update.message.reply_text(full_animation_response)
    finally:
        # Удаление временного файла
        os.remove(local_file_path)

async def handle_gptvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = str(update.message.chat_id)
    username = update.message.from_user.username or update.message.from_user.first_name
    user_id = update.message.from_user.id  # Получение user_id
    caption = update.message.caption or ""

    logger.info("Обработка видео от пользователя")


    # Скачивание видеофайла
    video = update.message.video
    file = await context.bot.get_file(video.file_id)

    # Определение исходного расширения файла
    file_extension = os.path.splitext(file.file_path)[1] or ".mp4"  # Если расширение неизвестно, используем .mp4

    # Создание временного файла с исходным расширением
    fd, local_file_path = tempfile.mkstemp(suffix=file_extension)

    # Закрытие файлового дескриптора, чтобы освободить ресурс
    os.close(fd)

    # Загрузка видео в файл
    await file.download_to_drive(local_file_path)

    try:
        # Генерация ответа
        full_video_response = await generate_video_response(local_file_path, user_id, query=caption)


        # Отправка текста с результатом пользователю
        await update.message.reply_text(full_video_response)
    finally:
        # Удаление временного файла
        os.remove(local_file_path)
        
async def handle_documentgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    username = update.message.from_user.username or update.message.from_user.first_name
    user_id = update.message.from_user.id
    caption = update.message.caption or ""
    reset_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("✂️Сбросить диалог✂️", callback_data='reset_dialog')],
        [InlineKeyboardButton("Выйти из режима диалога", callback_data='stop_gpt')],
        [InlineKeyboardButton("📜\nВыбрать роль", callback_data='role_select')], # Новая кнопка для запроса роли
    ])
    logger.info("Обработка текстового документа от пользователя")

    document = update.message.document
    file = await context.bot.get_file(document.file_id)

    file_extension = os.path.splitext(document.file_name)[1] or ".txt"

    fd, local_file_path = tempfile.mkstemp(suffix=file_extension)
    os.close(fd)

    await file.download_to_drive(local_file_path)

    try:
        full_text_response = await generate_document_response(local_file_path, user_id, caption)
        await send_reply_with_limit(update, full_text_response, reply_markup=reset_button)

    finally:
        os.remove(local_file_path)


async def gpt_running(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    user_message = update.message.text
    user_image = None

    reset_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("✂️Сбросить диалог✂️", callback_data='reset_dialog')],
        [InlineKeyboardButton("Выйти из режима диалога", callback_data='stop_gpt')],
        [InlineKeyboardButton("📜\nВыбрать роль", callback_data='role_select')], # Новая кнопка для запроса роли
    ])
      
    if update.message.document:
        mime_type = update.message.document.mime_type
        file_name = update.message.document.file_name.lower()
        
        if mime_type in ("text/plain", "application/pdf") or file_name.endswith((".txt", ".pdf")):
            return await handle_documentgpt(update, context)      
    if update.message.audio or update.message.voice:
        return await handle_audio(update, context)
    if update.message.animation:  # Проверка на GIF
        return await handle_gptgif(update, context)
    if update.message.video or update.message.document and update.message.document.mime_type.startswith("video"):
        return await handle_gptvideo(update, context)
    # Проверка, отправил ли пользователь изображение
    if update.message.photo:
        try:
            # Загружаем изображение
            photo_file = await update.message.photo[-1].get_file()
            img_data = io.BytesIO()
            await photo_file.download_to_memory(out=img_data)
            img = Image.open(img_data)
            width, height = img.size

            # Получаем caption изображения
            user_message = update.message.caption or "Изображение без описания"

            # Проверяем, начинается ли caption с "Дорисуй: " или "дорисуй:"
            match = re.match(r"(?i)^дорисуй:\s*(.+)", user_message)
            if match:
                inpaint_prompt = match.group(1).strip()
                new_image = inpaint_image(img, inpaint_prompt)
                if new_image:
                    bio = io.BytesIO()
                    new_image.save(bio, format="PNG")
                    bio.seek(0)
                    await update.message.reply_photo(photo=bio, caption=f"Изображение доработано по запросу: '{inpaint_prompt}'")
                else:
                    await update.message.reply_text("Ошибка при обработке изображения.")
                return

            # Обычная генерация описания
            add_to_context(user_id, f"[Изображение], с подписью: {user_message}", message_type="User_send_message:")
            response_text = await generate_image_description(user_id, query=user_message, image=img)

            logging.info(f"Ответ с изображением, который пытается отправить бот: {response_text}")

            if response_text:
                await send_reply_with_limit(update, response_text, reply_markup=reset_button)
            else:
                await update.message.reply_text("Произошла ошибка при генерации ответа. Попробуйте снова.")
            return
        except Exception as e:
            logging.error(f"Ошибка при загрузке изображения: {e}")
            await update.message.reply_text("Ошибка при обработке изображения. Попробуйте снова.")
            return
    if update.callback_query and update.callback_query.data == 'reset_dialog':
        user_id = update.callback_query.from_user.id
        user_roles[user_id] = (
            "Ты играешь роль телеграм чат бота "
        )
        save_context_to_firebase(user_id)
        
        await update.callback_query.answer("Диалог и роль сброшены.")
        return ASKING_FOR_ROLE  # Или другое состояние после сброса        


    else:
        # Обработка текстового запроса без изображения
        draw_triggers = ["нарисуй", "нарисуй:", "Нарисуй", "Нарисуй:", "draw", "draw:", "Draw", "Draw:"]

        if any(user_message.startswith(trigger) for trigger in draw_triggers):
            prompt_text = user_message.split(maxsplit=1)[1] if len(user_message.split()) > 1 else ""

            if not prompt_text:
                await update.message.reply_text("Пожалуйста, укажите описание для генерации изображения после слова 'нарисуй'.")
                return RUNNING_GPT_MODE

            # Запускаем асинхронную генерацию без перевода
            asyncio.create_task(limited_image_generation(update, context, user_id, prompt_text))

        else:
            add_to_context(user_id, user_message, message_type="user_message")
            response_text = await generate_gemini_response(user_id, query=user_message)

            if response_text:
                await send_reply_with_limit(update, response_text, reply_markup=reset_button)
            else:
                await update.message.reply_text("Произошла ошибка при генерации ответа. Попробуйте снова.")

        return RUNNING_GPT_MODE










# Модели и их настройки
MODELS = {
    "🌠stable": {
        "stabilityai/stable-diffusion-3.5-large-turbo": {
            "add_prompt": "",
            "negative": True
        },
        "stabilityai/stable-diffusion-3.5-large": {
            "add_prompt": "",
            "negative": True
        },
        "alvdansen/phantasma-anime": {
            "add_prompt": "",
            "negative": True
        },  
        "alvdansen/frosting_lane_redux": {
            "add_prompt": "",
            "negative": True
        },      
        "alvdansen/digital-manga-cuties": {
            "add_prompt": "",
            "negative": True
        },                
        "alvdansen/littletinies": {
            "add_prompt": "",
            "negative": True
        },
        "alvdansen/soft-and-squishy-linework": {
            "add_prompt": "",
            "negative": True
        },        
         
        "alvdansen/BandW-Manga": {
            "add_prompt": "",
            "negative": True
        },

        "alvdansen/soft-ones": {
            "add_prompt": "",
            "negative": True
        },
        "artificialguybr/PixelArtRedmond": {
            "add_prompt": "pixel art ",
            "negative": True
        },
        "alvdansen/soft-focus-3d": {
            "add_prompt": "3d model ",
            "negative": True
        },
        "artificialguybr/analogredmond-v2": {
            "add_prompt": "photo ",
            "negative": True
        },
        "prithivMLmods/SD3.5-Large-Photorealistic-LoRA": {
            "add_prompt": "photo ",
            "negative": True
        },
    },
    "🌃flux": {
        "black-forest-labs/FLUX.1-dev": {
            "add_prompt": "",
            "negative": False
        },
        "Shakker-Labs/FLUX.1-dev-LoRA-add-details": {
            "add_prompt": "",
            "negative": False
        },
        "XLabs-AI/flux-RealismLora": {
            "add_prompt": "",
            "negative": False
        },
        "dennis-sleepytales/frosting_lane_flux": {
            "add_prompt": "",
            "negative": False
        },          
        "glif-loradex-trainer/araminta": {
            "add_prompt": "",
            "negative": False
        },
        "dennis-sleepytales/softserve_anime": {
            "add_prompt": "",
            "negative": False
        },
        "bingbangboom/flux_dreamscape": {
            "add_prompt": "",
            "negative": False
        },
        "prithivMLmods/Canopus-LoRA-Flux-Anime": {
            "add_prompt": "",
            "negative": False
        },                                      
        "dennis-sleepytales/flux_ghibsky": {
            "add_prompt": "",
            "negative": False
        },  
        "strangerzonehf/Flux-Ghibli-Art-LoRA": {
            "add_prompt": "Anime ",
            "negative": False
        },                    
        "dataautogpt3/FLUX-AestheticAnime": {
            "add_prompt": "",
            "negative": False
        },
        "glif/90s-anime-art": {
            "add_prompt": " anime ",
            "negative": False
        },
        "prithivMLmods/Flux-Dev-Real-Anime-LoRA": {
            "add_prompt": "",
            "negative": False
        },
        "alvdansen/plushy-world-flux": {
            "add_prompt": "",
            "negative": False
        },



        "bingbangboom/oneImageLoraTest": {
            "add_prompt": "",
            "negative": False
        },
        "bingbangboom/flux_oilscape": {
            "add_prompt": "oil paint ",
            "negative": False
        },

        "prithivMLmods/Canopus-Pixar-3D-Flux-LoRA": {
            "add_prompt": "Pixar 3D ",
            "negative": False
        },  
        "alvdansen/flux-koda": {
            "add_prompt": "",
            "negative": False
        },
        "alvdansen/flux_film_foto": {
            "add_prompt": "",
            "negative": False
        },
   
                               
    },
    "💡others": { 
        "fofr/flux-80s-cyberpunk": {
            "add_prompt": "80s cyberpunk ",
            "negative": False
        },     
        "nerijs/pixel-art-xl": {
            "add_prompt": "pixel art ",
            "negative": True
        },
        "sWizad/pokemon-trainer-sprite-pixelart": {
            "add_prompt": "pixel art ",
            "negative": True
        },
        "artificialguybr/LogoRedmond-LogoLoraForSDXL-V2": {
            "add_prompt": "logo design ",
            "negative": True
        },
        "artificialguybr/StickersRedmond": {
            "add_prompt": "sticker design ",
            "negative": True
        },
        "Shakker-Labs/FLUX.1-dev-LoRA-Logo-Design": {
            "add_prompt": "logo design ",
            "negative": False
        },
        "gokaygokay/Flux-Game-Assets-LoRA-v2": {
            "add_prompt": "game assets ",
            "negative": False
        },
        "xey/sldr_flux_nsfw_v2-studio": {
            "add_prompt": "nsfw ",
            "negative": False
        },
    }
}

MODEL_SHORTNAMES = {
    # Stable Diffusion
    "stabilityai/stable-diffusion-3.5-large-turbo": "⏳ SD Turbo ⏳",
    "stabilityai/stable-diffusion-3.5-large": "SD Large",
    "alvdansen/phantasma-anime": "Phantasma Anime",
    "alvdansen/frosting_lane_redux": "Frosting Lane SD", 
    "alvdansen/digital-manga-cuties": "Manga Cuties",           
    "alvdansen/littletinies": "Little Tinies",
    "alvdansen/soft-and-squishy-linework": "Soft Linework",    
    "alvdansen/BandW-Manga": "Simple Draw",
    "alvdansen/soft-ones": "Soft Ones",
    "artificialguybr/PixelArtRedmond": "PixelArt",
    "alvdansen/soft-focus-3d": "Soft Focus 3D",
    "artificialguybr/analogredmond-v2": "Старые фотографии",
    "prithivMLmods/SD3.5-Large-Photorealistic-LoRA": "Фотографии",
   
    
    # FLUX
    "black-forest-labs/FLUX.1-dev": "FLUX (оригинальный)",
    "Shakker-Labs/FLUX.1-dev-LoRA-add-details": "FLUX more details",
    "XLabs-AI/flux-RealismLora": "Realism Lora",
    "dennis-sleepytales/frosting_lane_flux": "Frosting lane Flux",

    #alvdansen/frosting_lane_flux     
    "glif-loradex-trainer/araminta": "Araminta Illust Art",
    "dennis-sleepytales/softserve_anime": "Softserve Anime",
    #alvdansen/softserve_anime    
    "bingbangboom/flux_dreamscape": "Dreamscape",
    "prithivMLmods/Canopus-LoRA-Flux-Anime": "Canopus Anime",          
    "dennis-sleepytales/flux_ghibsky": "Ghibsky", 
    #aleksa-codes/flux-ghibsky-illustration
    "strangerzonehf/Flux-Ghibli-Art-LoRA": "Flux Details Anime",
    "dataautogpt3/FLUX-AestheticAnime": "Aesthetic Anime",
    "glif/90s-anime-art": "90s Anime",
    "prithivMLmods/Flux-Dev-Real-Anime-LoRA": "Real Anime",

    "alvdansen/plushy-world-flux": "Plushy World",    
    "bingbangboom/oneImageLoraTest": "Pastel",
    "bingbangboom/flux_oilscape": "OilPaint",

    "prithivMLmods/Canopus-Pixar-3D-Flux-LoRA": "Pixar",

    "alvdansen/flux-koda": "Flux Koda",
    "alvdansen/flux_film_foto": "Film Foto",

    
    
    # OTHERS
    "nerijs/pixel-art-xl": "PixelArt V2",
    "sWizad/pokemon-trainer-sprite-pixelart": "Pixel(персонажи)",
    "artificialguybr/LogoRedmond-LogoLoraForSDXL-V2": "Logo V2",
    "artificialguybr/StickersRedmond": "Stickers",

    "xey/sldr_flux_nsfw_v2-studio": "NSFW",
    "Shakker-Labs/FLUX.1-dev-LoRA-Logo-Design": "Flux Logo Design",
    "gokaygokay/Flux-Game-Assets-LoRA-v2": "3D Game Assets",
    "fofr/flux-80s-cyberpunk": "Flux 80s Cyberpunk",           
}










# Обработчик команды выбора стиля
async def choose_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌠 Stable Diffusion", callback_data='category_🌠stable')],
        [InlineKeyboardButton("🌃 FLUX", callback_data='category_🌃flux')],
        [InlineKeyboardButton("💡 others", callback_data='category_💡others')],
        [InlineKeyboardButton("Таблица примеров", callback_data='examples_table')]        
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Проверяем, откуда вызвана команда (из текста или кнопки)
    if update.message:
        await update.message.reply_text(
            "Выберите категорию модели\n\n 🌠 Генерация моделей из категории Stable diffusion занимает в среднем 8-30сек.\n 🌃 Из Flux 30-200сек в зависимости от запроса и нагрузки на сервера. \n\n ⏳ SD turbo - самая быстрая модель, генерация одного изображения занимает всего 3-5 секунд в среднем\n\n В таблице примеров можно посмотреть как приблизительно выглядят генерации каждой из моделей", reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            "Выберите категорию модели\n\n 🌠 Генерация моделей из категории Stable diffusion занимает в среднем 8-30сек.\n 🌃 Из Flux 30-200сек в зависимости от запроса и нагрузки на сервера. \n\n ⏳ SD turbo - самая быстрая модель, генерация одного изображения занимает всего 3-5 секунд в среднем\n\n В таблице примеров можно посмотреть как приблизительно выглядят генерации каждой из моделей", reply_markup=reply_markup
        )
        await update.callback_query.answer()

# Обработчик кнопки "Выбрать стиль"
async def select_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await choose_style(update, context)


async def category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    category = query.data.split('_')[1]
    
    # Список всех категорий
    categories = ["🌠stable", "🌃flux", "💡others"]
    other_categories = [c for c in categories if c != category]  # Выбираем две другие категории
    
    # Верхние кнопки с другими категориями
    buttons = [
        [
            InlineKeyboardButton(other_categories[0].capitalize(), callback_data=f"category_{other_categories[0]}"),
            InlineKeyboardButton(other_categories[1].capitalize(), callback_data=f"category_{other_categories[1]}")
        ]
    ]
    
    # Разделитель
    buttons.append([InlineKeyboardButton("———————————", callback_data="none")])

    # Карта приоритетных моделей для разных категорий
    priority_models = {
        "🌠stable": ("stabilityai/stable-diffusion-3.5-large-turbo", "SD Turbo"),
        "🌃flux": ("black-forest-labs/FLUX.1-dev", "FLUX (оригинальный)")
    }

    # Если в текущей категории есть приоритетная модель, добавляем её первой
    if category in priority_models:
        model_id, model_name = priority_models[category]
        if model_id in MODELS[category]:
            buttons.append([InlineKeyboardButton(model_name, callback_data=f"model_{category}_{model_id}")])

    # Добавляем кнопки с остальными моделями
    row = []
    for model in MODELS[category]:
        if category in priority_models and model == priority_models[category][0]:  # Пропускаем приоритетную модель
            continue
        
        short_name = MODEL_SHORTNAMES.get(model, model)  # Используем укороченное имя или оригинальное
        btn = InlineKeyboardButton(short_name, callback_data=f"model_{category}_{model}")
        row.append(btn)

        if len(row) == 2:  # Два в ряд
            buttons.append(row)
            row = []

    if row:  # Добавляем последний ряд, если осталась одна кнопка
        buttons.append(row)
    
    # Нижний разделитель
    buttons.append([InlineKeyboardButton("———————————", callback_data="none")])
    
    # Кнопка "Отмена"
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancelmodel")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(
        text=f"Доступные модели {category}. \n\n  🌠 Генерация моделей из категории Stable diffusion занимает в среднем 8-30сек.\n 🌃 Из Flux 30-250сек в зависимости от запроса и нагрузки на сервера. \n\n ⏳ SD turbo - самая быстрая модель, генерация одного изображения занимает всего 3-5 секунд в среднем",
        reply_markup=reply_markup
    )

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()


# Обработчик выбора модели
async def model_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, category, model_name = query.data.split('_', 2)
    user_id = update.effective_user.id
    
    # Сохраняем модель в Firebase
    set_user_model(user_id, model_name)
    
    context.user_data['selected_model'] = {
        'name': model_name,
        'params': MODELS[category][model_name]
    }
    
    await query.edit_message_text(
        text=f"✅ Вы выбрали модель: {MODEL_SHORTNAMES.get(model_name, model_name)}\n\n"
             f"Теперь введите промпт для генерации, сообщение должно начинаться со слова \"нарисуй\""
    )



def find_model_params(model_name: str) -> dict:
    """Ищет параметры модели в MODELS по имени."""
    for category in MODELS.values():
        if model_name in category:
            return category[model_name]
    # Возвращаем параметры по умолчанию, если модель не найдена
    return MODELS['🌠stable']["stabilityai/stable-diffusion-3.5-large-turbo"]

import itertools

# Два токена API
# Загружаем переменные окружения из секретного файла
load_dotenv("/etc/secrets/HF.env")

# Получаем токены API
HF_API_KEYS = itertools.cycle([
    os.getenv("HF_API_KEY_1"),  # Первый токен
    os.getenv("HF_API_KEY_2")   # Второй токен
])

image_queue = asyncio.Queue()
user_positions = {}
global_semaphore = asyncio.Semaphore(4)

async def limited_image_generation(update, context, user_id, prompt):
    """Добавляем задачи в очередь и корректно определяем позицию"""
    # Проверяем текущий размер очереди
    position = image_queue.qsize()

    if position > 0:  # Если в очереди уже есть задачи, выдаем позицию
        user_positions[user_id] = position + 1
        await update.message.reply_text(f"Очередь на генерацию: {position + 1}-й в списке. Ожидайте...")
    else:  # Если очередь пуста, пользователь будет первым, но не показываем лишний текст
        user_positions[user_id] = 1

    # Добавляем задачу в очередь
    await image_queue.put((update, context, user_id, prompt))

    # Запускаем обработку очереди, если не запущена
    asyncio.create_task(process_queue())
async def process_queue():
    """Фоновая задача для обработки очереди"""
    while True:
        async with global_semaphore:
            # Достаем задачу из очереди
            next_task = await image_queue.get()
            update, context, user_id, prompt = next_task
            
            try:
                await generate_image(update, context, user_id, prompt)
            except Exception as e:
                logger.error(f"Ошибка генерации: {e}")
                await update.message.reply_text("⚠️ Ошибка при обработке вашего запроса")
            
            # Обновляем позиции в очереди
            for uid in user_positions:
                if user_positions[uid] > user_positions.get(user_id, 0):
                    user_positions[uid] -= 1
            if user_id in user_positions:
                del user_positions[user_id]     


async def generate_image(update, context, user_id, prompt, query_message=None):
    """Генерация изображения с учетом выбранной модели"""
    # Получаем модель из контекста или Firebase
    selected_model = context.user_data.get('selected_model')

    if not selected_model:
        model_name = get_user_model(user_id)
        model_params = find_model_params(model_name)
        selected_model = {
            'name': model_name,
            'params': model_params
        }
        context.user_data['selected_model'] = selected_model

    model_name = selected_model['name']
    model_params = selected_model['params']
    if model_name == "glif-loradex-trainer/araminta":
        model_name = "glif-loradex-trainer/araminta_k_flux_dev_illustration_art"

    # Чередуем токены API
    HF_API_KEY = next(HF_API_KEYS)
    logger.info(f"Используется API-ключ: {HF_API_KEY}")

    client_image = AsyncInferenceClient(api_key=HF_API_KEY, timeout=300)

    # Определяем, куда отправить сообщение
    response_target = update.message if update.message else query_message

    if response_target:
        await response_target.reply_text(f"Ожидайте, генерирую изображение по запросу: '{prompt}'...")

    # Получаем add_prompt для выбранной модели
    original_prompt = prompt
    logger.info(f"original_prompt: {original_prompt}")
    add_prompt = selected_model['params']['add_prompt']

    retries = 1  # Количество попыток
    while retries >= 0:
        try:
            start_time = time.time()  # Фиксируем начальное время
            prompt = original_prompt  
            # Инициализация параметров по умолчанию
            seed = random.randint(1, 2000000000)  # Генерация случайного seed
            guidance_scale = None
            num_inference_steps = None
            width, height = 1024, 1024  # Значения по умолчанию

            # Парсинг seed из начала текста
            seed_match = re.match(r"^(\d+),", prompt)
            if seed_match:
                seed = int(seed_match.group(1))
                prompt = re.sub(r"^\d+,", "", prompt).strip()

            # Парсинг соотношения сторон из квадратных скобок
            aspect_ratio_match = re.search(r"\[(\d+):(\d+)\]$", prompt)
            if aspect_ratio_match:
                aspect_width = int(aspect_ratio_match.group(1))
                aspect_height = int(aspect_ratio_match.group(2))
                prompt = re.sub(r"\[\d+:\d+\]$", "", prompt).strip()

                # Вычисление ширины и высоты, учитывая ограничения
                if aspect_width >= aspect_height:
                    width = min(1400, max(512, int(1400 * (aspect_width / aspect_height))))
                    height = min(1400, max(512, int(width * (aspect_height / aspect_width))))
                else:
                    height = min(1400, max(512, int(1400 * (aspect_height / aspect_width))))
                    width = min(1400, max(512, int(height * (aspect_width / aspect_height))))

            # Теперь парсим guidance_scale и num_inference_steps
            params_match = re.search(r"\((\d+(\.\d+)?)(?:,\s*(\d+))?\)", prompt)
            if params_match:
                guidance_scale = float(params_match.group(1))  # Всегда будет найдено
                num_inference_steps = int(params_match.group(3)) if params_match.group(3) else None  # Проверяем наличие второго числа
                prompt = re.sub(r"\([\d\.]+(?:,\s*\d+)?\)$", "", prompt).strip()

            # Очистка промта от всех парсинговых значений
            clean_prompt = prompt.strip()

            # Формирование full_prompt на основе очищенного промта и add_prompt
            mix_prompt = f"{add_prompt} {clean_prompt}"
            full_prompt = await translate_promt_with_gemini(user_id, query=mix_prompt)
            logger.info(f"full_prompt: {full_prompt}")

            # Коррекция размеров кратно 64
            width = max(512, min(1408, width - (width % 64)))
            height = max(512, min(1408, height - (height % 64)))
            # **Заданный negative_prompt для большинства изображений**
            negative_prompt = (
                "blurry, distorted, deformed, bad anatomy, bad proportions, extra limbs, "
                "missing fingers, too many fingers, malformed hands, long neck, watermark, "
                "low quality, low resolution, grainy, unnatural lighting, bad perspective, "
                "mutated body, disproportional, extra heads, floating limbs, extra eyes, "
                "bad composition, broken symmetry, duplicate elements, jpeg artifacts"
                if selected_model['params']['negative']
                else None
            )

            logger.info(f"width: {width}")
            logger.info(f"height: {height}")
            # Параметры для генерации изображения
            params = {
                "height": height,
                "width": width,
                "seed": seed,
                "max_sequence_length": 512,
            }
            if selected_model['params']['negative']:
                params["negative_prompt"] = negative_prompt
            # Добавляем guidance_scale, если он указан
            if "guidance_scale" in locals():
                params["guidance_scale"] = guidance_scale

            # Добавляем num_inference_steps, если он указан
            if "num_inference_steps" in locals():
                params["num_inference_steps"] = num_inference_steps

            # Генерация изображения
            image = await client_image.text_to_image(full_prompt, model=model_name, **params)
            logger.info(f"prompt на генерацию: {full_prompt}")
            elapsed_time = time.time() - start_time  # Вычисляем прошедшее время

            MAX_CAPTION_LENGTH = 1024  # Максимальная длина caption в Telegram

            caption = (
                f"`{original_prompt}`\n\n"
                f"Seed: `{seed}, `\n"
                + (f"Guidance Scale: {guidance_scale}\n" if guidance_scale is not None else "")
                + (f"Steps: {num_inference_steps}\n" if num_inference_steps is not None else "")
                + f"Resolution: {width}x{height}\n"
                f"Время генерации: {elapsed_time:.2f} сек.\n\n"
                f"Модель: `{model_name}`\n"                
                f"Переведённый prompt: \n```\nНарисуй: {full_prompt}```\n"
            )

            with io.BytesIO() as output:
                image.save(output, format="PNG")
                output.seek(0)

                # Загружаем изображение на Catbox (если нужно)
                catbox_url = await upload_image_to_catbox_in_background(output.getvalue())

                # Определяем источник запроса
                message = update.message if update.message else update.callback_query.message
                user_id = update.effective_user.id  # Получаем user_id

                # Создаем клавиатуру с кнопками
                keyboard = [
                    [InlineKeyboardButton("📒 Сохранить чтобы не потерять", callback_data=f"save_{user_id}_{message.message_id}")],                                    
                    [InlineKeyboardButton("🗂 Мои сохранённые генерации", callback_data="scheduled_by_tag")],
                    [InlineKeyboardButton("🌃 Опубликовать в общую папку", callback_data=f"neuralpublic_{user_id}_{message.message_id}")],    
                    [InlineKeyboardButton("🏙 Посмотреть чужие публикации", callback_data="view_shared")],                                        
                    [InlineKeyboardButton("🎨 Выбрать стиль", callback_data='choose_style')],
                    [InlineKeyboardButton("🔄 Повторить генерацию", callback_data=f"regenerate_{user_id}_{message.message_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Проверяем длину caption
                if len(caption) > MAX_CAPTION_LENGTH:
                    sent_message = await message.reply_photo(photo=output)

                    # Сохраняем информацию о первом сообщении (с фото)
                    context.user_data[f"split_message_{user_id}_{sent_message.message_id}"] = {
                        "full_caption": caption,
                        "file_id": sent_message.photo[-1].file_id,
                    }
                    keyboard[0][0] = InlineKeyboardButton(
                        "📒 Сохранить чтобы не потерять",
                        callback_data=f"save_{user_id}_{sent_message.message_id}"
                    )
                    # Обновляем callback_data для кнопки публикации
                    keyboard[2][0] = InlineKeyboardButton(
                        "🌃 Опубликовать в общую папку",
                        callback_data=f"neuralpublic_{user_id}_{sent_message.message_id}"
                    )

                    # Отправляем caption отдельно, но уже в формате HTML
                    await message.reply_text(
                        text=escape_gpt_markdown_v2(caption),
                        parse_mode="MarkdownV2",  # Меняем MarkdownV2 → HTML
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    # Если caption влезает, отправляем обычным способом
                    sent_message = await message.reply_photo(
                        photo=output,
                        caption=escape_gpt_markdown_v2(caption),
                        parse_mode="MarkdownV2",
                        reply_markup=reply_markup
                    )                            
            break  # Если все прошло успешно, выходим из цикла
        except Exception as e:
            logger.info(f"error: {e}")            
            retries -= 1
            message = update.message if update.message else update.callback_query.message

            if retries >= 0:
                await message.reply_text(f"⏳ Что-то немного сломалось но бот пыается исправить это. Пожалуйста подождите ещё какое-то время")
                await asyncio.sleep(10)  # Подождать 10 секунд перед повтором
            else:
                await message.reply_text(f"Произошла ошибка при генерации изображения. Попробуйте: \n\n1)Подождать 30 секунд и повторить. \n 2)Если пункт 1 не помог, то сменить модель(стиль), возможно что-то сломалось в данной модели. \n 3)Если смена стиля не помогла то подождите несколько часов и повторите попытку, возможно что-то с серверами. \n\n Если ничего из этого не помогло то пожалуйтса сообщите о проблеме через команду /send, веротяно что-то сломалось в боте ")

async def handle_neuralpublic_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    # Извлекаем user_id и message_id из callback_data
    parts = query.data.split('_')
    user_id = int(parts[1])
    message_id = int(parts[2])

    # Проверяем, не был ли caption разбит на части
    saved_data = context.user_data.get(f"split_message_{user_id}_{message_id}")
    if saved_data:
        caption = query.message.text_html
        file_id = saved_data["file_id"]
    else:
        caption = query.message.caption_html
        logger.info(f"caption2 {caption} ")         
        file_id = query.message.photo[-1].file_id

    # Сохраняем данные о генерации в контексте
    context.user_data["shared_generation_data"] = {
        "user_id": user_id,
        "message_id": message_id,
        "caption": caption,
        "file_id": file_id,
    }

    # Отображаем клавиатуру с эмодзи
    emojis = [
        "👀", "🤷‍♂️", "🧶", "🦊", "🦄", "🦆", "🐳", "🌿", "🌸", "🍓",
        "🍑", "🍆", "🌈", "🌧", "☀️", "⭐️", "🫖", "🌙", "🌠", "❄️",
        "🗑", "📎", "✏️", "🎨", "😈", "📷", "📚", "⏳", "✅", "❇️",
        "❌", "🔄", "🩷", "💛", "💚", "💙", "❤️", "💜", "🖤", "🤍",
    ]
    reply_markup = createneural_emoji_keyboard(emojis, user_id, message_id)
    await query.message.reply_text("Выберите метку для публикации в общую папку:", reply_markup=reply_markup)

def createneural_emoji_keyboard(emojis, user_id, message_id):
    keyboard = []
    row = []
    for emoji in emojis:
        row.append(InlineKeyboardButton(emoji, callback_data=f"sharedtag_{emoji}_{user_id}_{message_id}"))
        if len(row) == 4:  # Если в строке 4 кнопки, добавляем её в клавиатуру
            keyboard.append(row)
            row = []  # Начинаем новую строку
    if row:  # Добавляем оставшиеся кнопки, если они есть
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

async def handle_shared_tag_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()

    # Извлекаем данные из callback_data
    _, tag, user_id_str, message_id_str = query.data.split('_')
    user_id = int(user_id_str)
    message_id = int(message_id_str)

    # Получаем данные из контекста
    generation_data = context.user_data.get("shared_generation_data")
    if not generation_data:
        await query.message.reply_text("🚫 Ошибка: данные генерации не найдены")
        return

    # Формируем данные для сохранения
    media_group_data = {
        "media": [{
            "caption": generation_data["caption"],
            "file_id": generation_data["file_id"],
            "parse_mode": "HTML"
        }],
        "scheduled": tag
    }

    # Сохраняем в отдельную ветку shared_publications
    save_to_shared_publications(user_id, f"{user_id}_{message_id}", media_group_data)

    # Очищаем контекст
    context.user_data.pop("shared_generation_data", None)

    # Отправляем подтверждение
    await query.message.reply_text(
        "✅ Публикация успешно добавлена в общий доступ!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏙 Посмотреть общие публикации", callback_data="view_shared")]
        ])
    )
async def handle_sharefromuser_publication(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    # Проверяем корректность данных
    if "_" in query.data:
        _, key = query.data.split("_", 1)
    else:
        await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
        return

    user_id = str(update.effective_user.id)
    logger.info(f"key {key} ")
    # Копируем публикацию в shared_publications
    success = copy_to_shared_publications(user_id, key)

    if success:
        # Отправляем подтверждение
        await query.message.reply_text(
            "✅ Публикация успешно добавлена в общий доступ!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏙 Посмотреть общие публикации", callback_data="view_shared")]
            ])
        )
    else:
        await query.message.reply_text("🚫 Ошибка: Не удалось найти публикацию.")



# Формирование клавиатуры с метками публикаций
def generate_shared_keyboard(publications, user_id):
    scheduled_counts = {}

    # Подсчёт количества публикаций для каждой метки
    for owner_id, user_data in publications.items():
        for post_id, post_data in user_data.items():
            label = post_data.get("scheduled", "🧶")
            scheduled_counts[label] = scheduled_counts.get(label, 0) + 1
    
    keyboard = [[InlineKeyboardButton("📜 Все записи", callback_data="view_shared_all")]]
    
    # Добавляем кнопку "⭐ Избранные", если у пользователя есть избранные записи
    favorite_count = sum(
        1 for owner_id, user_data in publications.items()
        for post_id, post_data in user_data.items()
        if user_id in post_data.get("favorites", [])
    )
    if favorite_count > 0:
        keyboard.append([InlineKeyboardButton(f"⭐ Избранные ({favorite_count})", callback_data="view_shared_favorites")])

    row = []
    for label, count in scheduled_counts.items():
        row.append(InlineKeyboardButton(f"{label} ({count})", callback_data=f"view_shared_{label}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)

# Обработчик кнопки "🌍 Общие публикации"
async def handle_view_shared(update: Update, context: CallbackContext):
    await update.callback_query.answer()  # Гасим нажатие кнопки

    user_id = update.callback_query.from_user.id
    publications = load_shared_publications()
    keyboard = generate_shared_keyboard(publications, user_id)
    
    await update.callback_query.message.reply_text(
        "Выберите метку для просмотра публикаций:", 
        reply_markup=keyboard
    )


# Обработчик выбора метки публикации
from html import unescape
async def handle_select_scheduled(update: Update, context: CallbackContext):
    query = update.callback_query
    selected_label = query.data.replace("view_shared_", "")
    user_id = query.from_user.id
    publications = load_shared_publications()

    post_buttons = []
    
    for owner_id, user_data in publications.items():
        for post_id, post_data in user_data.items():
            label = post_data.get("scheduled", "🧶")
            favorites = post_data.get("favorites", [])
            fav_count = len(favorites)  # Количество добавлений в избранное

            # Фильтруем публикации: если выбраны "⭐ Избранные", показываем только те, где user_id в favorites
            if selected_label == "favorites":
                if user_id not in favorites:
                    continue  
            elif selected_label != "all" and label != selected_label:
                continue  

            # Обрезка caption
            caption = post_data["media"][0]["caption"]
            caption = re.sub(r"<.*?>", "", caption)  # Убираем HTML-теги
            caption = unescape(caption)  # Декодируем HTML-сущности
            caption = re.split(r"\bseed\b", caption, flags=re.IGNORECASE)[0]  # Обрезаем по "seed"
            caption = re.sub(r"^\d+,\s*", "", caption)  # Убираем числа в начале строки
            
            # Обрезаем caption до ближайшего пробела перед 23 символами
            if len(caption) > 31:
                cutoff = caption[:31].rfind(" ")
                caption = caption[:cutoff] if cutoff != -1 else caption[:31]

            # Добавляем количество добавлений в избранное
            text_preview = f"{caption.strip()} ({fav_count})" if fav_count > 0 else caption

            post_buttons.append((
                fav_count,  # Для сортировки
                InlineKeyboardButton(
                    f"{label}: {text_preview}",
                    callback_data=f"viewneuralpost_{owner_id}_{post_id}"
                )
            ))

    # Сортируем кнопки по количеству добавлений в избранное (по убыванию)
    post_buttons.sort(reverse=True, key=lambda x: x[0])

    if not post_buttons:
        await query.answer("Нет публикаций с данной меткой.", show_alert=True)
        return

    keyboard = [[button[1]] for button in post_buttons]
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="view_shared")])
    
    await query.message.edit_text("Выберите публикацию из списка представленного ниже:", reply_markup=InlineKeyboardMarkup(keyboard))



# Обработчик показа конкретной публикации
# Обработчик показа конкретной публикации
async def handle_view_post(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    try:
        query = update.callback_query
        logger.info(f"query {query}") 
        _, user_id, post_id = query.data.split("_", 2)
        publications = load_shared_publications()
        
        post_data = publications.get(user_id, {}).get(post_id)
        
        if not post_data:
            await query.answer("Публикация не найдена.", show_alert=True)
            return
        
        media = post_data["media"][0]
        caption = media["caption"]
        original_caption = caption
        logger.info(f"caption {caption}")
        # Проверяем длину caption
        if len(caption) > 1024:
            # Если caption слишком длинный, отправляем фото без подписи
            await context.bot.send_photo(
                chat_id=query.message.chat.id,
                photo=media["file_id"]
            )
            send_caption_separately = True
            logger.info(f"send_caption_separately {send_caption_separately}")                
        else:
            # Если caption в пределах лимита, отправляем его вместе с фото
            await context.bot.send_photo(
                chat_id=query.message.chat.id,
                photo=media["file_id"],
                caption=caption,
                parse_mode="HTML"
            )
            send_caption_separately = False
            logger.info(f"send_caption_separately {send_caption_separately}")          
        logger.info(f"send_caption_separately {send_caption_separately}")                
        # Получаем количество добавлений в избранное
        favorites = post_data.get("favorites", [])
        fav_count = len(favorites)

        # Формируем текст второго сообщения
       
        # Генерация клавиатуры с оставшимися постами
        selected_label = post_data.get("scheduled", "🧶")
        post_buttons = []
        fav_text = f"Этот пост добавлен в избранное {fav_count} раз(а)\n" if fav_count > 0 else ""
        remaining_posts_text = f"Ниже можно посмотреть список других постов с меткой {selected_label}:" 
        # Добавляем дополнительные кнопки перед списком записей
        if int(query.from_user.id) in favorites:
            fav_button = InlineKeyboardButton("❌ Удалить из избранного", callback_data=f"favorite_{user_id}_{post_id}")
        else:
            fav_button = InlineKeyboardButton("⭐ Сохранить в избранное", callback_data=f"favorite_{user_id}_{post_id}")


        extra_buttons = [
            [
                InlineKeyboardButton("Пост ТГ", callback_data=f"publish_{post_id}"),
                InlineKeyboardButton("Пост ВК", callback_data=f"vkpub_{post_id}")
            ],
            [fav_button],  # Используем динамически выбранную кнопку
            [InlineKeyboardButton("========......========", callback_data="no_action")]
        ]

        for u_id, user_data in publications.items():
            for p_id, p_data in user_data.items():
                if u_id == user_id and p_id != post_id:  # Исключаем уже показанный пост
                    label = p_data.get("scheduled", "🧶")
                    # Фильтрация записей по выбранной метке
                    if selected_label != "all" and label != selected_label:
                        continue  
                    # 🎯 Обрабатываем caption так же, как в handle_select_scheduled
                    caption = p_data["media"][0]["caption"]
                    caption = re.sub(r"<.*?>", "", caption)  # Убираем HTML-теги
                    caption = unescape(caption)  # Декодируем HTML-сущности
                    caption = re.split(r"\bseed\b", caption, flags=re.IGNORECASE)[0]  # Обрезаем по "seed"
                    caption = re.sub(r"^\d+,\s*", "", caption)  # Убираем числа в начале строки

                    # Обрезаем caption до ближайшего пробела перед 23 символами
                    if len(caption) > 31:
                        cutoff = caption[:31].rfind(" ")
                        caption = caption[:cutoff] if cutoff != -1 else caption[:31]

                    text_preview = f"{caption.strip()} ({fav_count})" if fav_count > 0 else caption

                    post_buttons.append(
                        InlineKeyboardButton(f"{label} {text_preview}", callback_data=f"viewneuralpost_{u_id}_{p_id}")
                    )

        keyboard = extra_buttons if all(isinstance(i, list) for i in extra_buttons) else [[button] for button in extra_buttons]

        if post_buttons:
            keyboard.extend([[button] for button in post_buttons])
        else:
            keyboard.append([InlineKeyboardButton("Других постов с этой меткой пока нет", callback_data="no_posts_available")])

        keyboard.append([InlineKeyboardButton("⬅ Другие посты", callback_data="view_shared")])

        # Если caption был слишком длинным, отправляем его отдельным сообщением
        if send_caption_separately:
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=f"{original_caption}\n\n{fav_text}{remaining_posts_text}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=f"{fav_text}{remaining_posts_text}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await query.answer("Произошла ошибка.")



async def handle_add_favorite(update: Update, context: CallbackContext):
    await update.callback_query.answer()    
    query = update.callback_query
    _, owner_id, post_id = query.data.split("_", 2)
    user_id = query.from_user.id

    added = add_to_favorites(user_id, owner_id, post_id, context)

    # Отправляем сообщение в зависимости от результата
    text = "✅ Пост добавлен в избранное." if added else "❌ Пост удалён из избранного."
    await query.message.reply_text(text)


async def regenerate_image(update, context):
    """Обработчик для повторной генерации с новым seed"""
    query = update.callback_query
    await query.answer()

    # Получаем user_id и message_id из callback_data
    data_parts = query.data.split("_")
    if len(data_parts) < 3:
        return  # Неправильный формат callback_data

    user_id = int(data_parts[1])
    message_id = int(data_parts[2])

    # Отправляем пользователю сообщение о начале повторной генерации
    await context.bot.send_message(chat_id=user_id, text="Ожидайте, повторная генерация запущена")

    # Извлекаем текст из оригинального сообщения с кнопкой
    if not query.message:
        return  # Сообщение не найдено

    full_text = query.message.text if query.message.text else query.message.caption
    if not full_text:
        return  # Нет текста для обработки

    # Парсим промпт из текста сообщения
    prompt_match = re.search(r"^(.+?)\n\nSeed:", full_text, re.DOTALL)
    if prompt_match:
        prompt = prompt_match.group(1).strip()
    else:
        prompt = full_text  # Если шаблон не найден, используем весь текст


    prompt = re.sub(r"^\d+,\s*", "", prompt).strip()
    logger.info(f"Повторная генерация с prompt: {prompt}")    
    # Запускаем генерацию с новым seed
    await generate_image(update, context, user_id, prompt, query_message=query.message)

from huggingface_hub import InferenceClient
def inpaint_image(image: Image.Image, prompt: str):
    """Дорисовка изображения с помощью image-to-image генерации."""
    HF_API_KEY = next(HF_API_KEYS)
    client = InferenceClient(api_key=HF_API_KEY, timeout=500)

    # Оптимальные размеры для SDXL (множители 128)
    width, height = image.size
    width = max(512, min(1408, width - (width % 64)))
    height = max(512, min(1408, height - (height % 64)))

    img_bytes = io.BytesIO()
    image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    logging.info(f"width: {width}")   
    logging.info(f"height: {height}")   
    logging.info(f"prompt: {prompt}")  
    prompt = str(prompt)        
    try:
        generated_image = client.image_to_image(
            image=img_bytes.getvalue(),
            prompt=prompt,
            model="stabilityai/stable-diffusion-xl-refiner-1.0",
            denoising_start=0.9,
            num_inference_steps=50,
            guidance_scale=5.0,
            width=width,  # Передаём размеры отдельно
            height=height
        )
        logging.info(f"generated_image: {generated_image}")         
        return generated_image
    except Exception as e:
        logging.info(f"Ошибка при генерации: {str(e)}")
        return None

async def handle_save_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    # Извлекаем user_id и message_id из callback_data
    parts = query.data.split('_')
    user_id = int(parts[1])
    message_id = int(parts[2])

    # Проверяем, не был ли caption разбит на части
    saved_data = context.user_data.get(f"split_message_{user_id}_{message_id}")
    if saved_data:
        caption = query.message.text_html
        file_id = saved_data["file_id"]
    else:
        caption = query.message.caption_html
        logger.info(f"caption2 {caption} ")         
        file_id = query.message.photo[-1].file_id

    # Сохраняем данные о генерации в контексте
    context.user_data["generation_data"] = {
        "user_id": user_id,
        "message_id": message_id,
        "caption": caption,
        "file_id": file_id,
    }

    # Отображаем клавиатуру с эмодзи
    emojis = [
        "👀", "🤷‍♂️", "🧶", "🦊", "🦄", "🦆", "🐳", "🌿", "🌸", "🍓",
        "🍑", "🍆", "🌈", "🌧", "☀️", "⭐️", "🫖", "🌙", "🌠", "❄️",
        "🗑", "📎", "✏️", "🎨", "😈", "📷", "📚", "⏳", "✅", "❇️",
        "❌", "🔄", "🩷", "💛", "💚", "💙", "❤️", "💜", "🖤", "🤍",
    ]
    reply_markup = create_emoji_keyboard(emojis, user_id, message_id)
    await query.message.reply_text("Выберите метку для записи:", reply_markup=reply_markup)




async def upload_image_to_catbox_in_background(image_bytes: bytes):
    """Фоновая задача для загрузки изображения на Catbox."""
    file_path = "temp_image.png"  # Локальный путь для временного хранения изображения
    try:
        # Сохраняем изображение во временный файл
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
        # Загружаем изображение на Catbox
        catbox_url = await second_upload_image(file_path)
        logging.info(f"Изображение успешно загружено на Catbox: {catbox_url}")
    except Exception as e:
        logging.error(f"Не удалось загрузить изображение на Catbox: {e}")
    finally:
        # Удаляем временный файл
        if os.path.exists(file_path):
            os.remove(file_path)

async def examples_table_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Отправляем промежуточное сообщение
    loading_message = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⏳ Таблица загружается, подождите немного..."
    )

    # Список URL-ов для изображений с обоих хостингов
    image_urls = [
        ("https://files.catbox.moe/5ux771.jpg", "https://i.ibb.co/3mJjVcy5/2.jpg"),
        ("https://files.catbox.moe/0pqvrr.jpg", "https://i.ibb.co/LhJ7sjj6/3.jpg"),
        ("https://files.catbox.moe/tqqvrn.jpg", "https://i.ibb.co/dwRCWM14/4.jpg"),
        ("https://files.catbox.moe/sy67tu.jpg", "https://i.ibb.co/jkhfq6Bm/5.jpg")
    ]

    async def is_image_available(url):
        """Проверяет доступность изображения по URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url) as response:
                    return response.status == 200
        except Exception:
            return False

    # Формируем медиа группу
    media_group = []
    for idx, (catbox_url, ibb_url) in enumerate(image_urls):
        # Проверяем доступность изображения на catbox
        if not await is_image_available(catbox_url):
            image_url = ibb_url  # Если catbox недоступен, используем ibb
        else:
            image_url = catbox_url

        # Добавляем описание только к первому изображению
        caption = (
            '<b>Пример:</b>\n'
            '<code>Нарисуй: 322434, цифровой арт с совой сидящей на ветке на фоне луны (3, 15) [3:2]</code>\n\n'
            'В данном случае 322434 - это seed, 3 - guidance_scale, '
            '15 - num_inference_steps, 3:2 - соотношение сторон. '
            'Подробнее смотрите по кнопке помощи.'
        ) if idx == 0 else None

        media_group.append(
            InputMediaPhoto(
                media=image_url,
                caption=caption,
                parse_mode='HTML'
            )
        )

    # Отправляем медиа группу
    sent_messages = await context.bot.send_media_group(
        chat_id=query.message.chat_id,
        media=media_group
    )

    # Удаляем промежуточное сообщение
    await context.bot.delete_message(
        chat_id=query.message.chat_id,
        message_id=loading_message.message_id
    )

    # Добавляем кнопку "Помощь" под последним сообщением медиагруппы
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📗 Помощь", callback_data='short_help_gpt')],
        [InlineKeyboardButton("🎨 Сменить модель(стиль)", callback_data='choose_style')] 
    ])
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Нажмите кнопку ниже для получения дополнительной информации:",
        reply_markup=keyboard
    )






# Функция для обработки нажатия кнопки "Сбросить диалог"
async def reset_dialog(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    
    # Сброс контекста в Firebase
    reset_firebase_dialog(user_id)
    
    await query.answer("Диалог сброшен.")

    # Обновляем клавиатуру
    keyboard = [
        [InlineKeyboardButton("📗\nПомощь", callback_data='short_help_gpt')],
        [InlineKeyboardButton("Выйти из режима диалога", callback_data='stop_gpt')],
        [InlineKeyboardButton("📜\nВыбрать роль", callback_data='role_select')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text="Диалог сброшен. Вы можете начать новый разговор.",
        reply_markup=reply_markup
    )



async def mushrooms_gpt(update, context):
    user_id = update.effective_user.id
    img_url = context.user_data.get('img_url')

    # Проверяем наличие изображения в контексте
    if not img_url:
        await update.callback_query.answer("Изображение не найдено.")
        return

    try:
        # Отправляем первоначальное сообщение
        processing_message = await update.callback_query.message.reply_text("Запрос принят, ожидайте...")
        
        # Открываем файл temp_image.jpg для обработки
        with open('temp_image.jpg', 'rb') as file:
            # Загружаем изображение как объект PIL.Image
            image = Image.open(file)
            image.load()  # Загружаем изображение полностью
            
            # Генерация ответа через Gemini
            response = await generate_mushrooms_response(user_id, image=image)
            
            # Экранируем текст для MarkdownV2
            response_text = escape_gpt_markdown_v2(response or "Ошибка при определении проблемы с растением.")
            
            # Создаем клавиатуру
            keyboard = [
                [InlineKeyboardButton("Отменить режим распознавания", callback_data='finish_ocr')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Обновляем сообщение с результатом
            await processing_message.edit_text(
                response_text,
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            await update.callback_query.answer()
    except Exception as e:
        logging.info(f"Ошибка при генерации описания проблемы растения: {e}")
        await processing_message.edit_text("Произошла ошибка при обработке изображения.")




async def text_plant_help_with_gpt(update, context):
    user_id = update.effective_user.id
    img_url = context.user_data.get('img_url')

    # Проверяем наличие изображения в контексте
    if not img_url:
        await update.callback_query.answer("Изображение не найдено.")
        return

    try:
        # Отправляем первоначальное сообщение
        processing_message = await update.callback_query.message.reply_text("Запрос принят, ожидайте...")
        
        # Открываем файл temp_image.jpg для обработки
        with open('temp_image.jpg', 'rb') as file:
            # Загружаем изображение как объект PIL.Image
            image = Image.open(file)
            image.load()  # Загружаем изображение полностью
            
            # Генерация ответа через Gemini
            response = await generate_plant_issue_response(user_id, image=image)
            
            # Экранируем текст для MarkdownV2
            response_text = escape_gpt_markdown_v2(response or "Ошибка при определении проблемы с растением.")
            
            # Создаем клавиатуру
            keyboard = [
                [InlineKeyboardButton("Отменить режим распознавания", callback_data='finish_ocr')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Обновляем сообщение с результатом
            await processing_message.edit_text(
                response_text,
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            await update.callback_query.answer()
    except Exception as e:
        logging.info(f"Ошибка при генерации описания проблемы растения: {e}")
        await processing_message.edit_text("Произошла ошибка при обработке изображения.")



async def text_rec_with_gpt(update, context):
    user_id = update.effective_user.id
    img_url = context.user_data.get('img_url')

    # Проверяем наличие изображения в контексте
    if not img_url:
        await update.callback_query.answer("Изображение не найдено.")
        return

    try:
        # Открываем файл temp_image.jpg для обработки
        with open('temp_image.jpg', 'rb') as file:
            # Загружаем изображение как объект PIL.Image
            image = Image.open(file)
            image.load()  # Загружаем изображение полностью
            
            # Запрос для Gemini с указанием распознавания текста            
            # Генерация ответа через Gemini
            response = await generate_text_rec_response(user_id, image=image, query=None)
            
            # Сохраняем распознанный текст в context.user_data
            context.user_data['recognized_text'] = response

        # Проверяем и отправляем ответ пользователю
        await update.callback_query.message.reply_text(response or "Ошибка при распознавании текста.")
        await update.callback_query.answer()        
        # Кнопка для уточнения вопроса
        followup_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("Задать уточняющий вопрос", callback_data='ask_followup')]
        ])
        
        # Предлагаем задать уточняющий вопрос
        await update.callback_query.message.reply_text(
            "Хотите задать уточняющий вопрос или дать команду касательно распознанного текста?",
            reply_markup=followup_button
        )

    except Exception as e:
        await update.callback_query.message.reply_text("Произошла ошибка при обработке изображения.")
        print(f"Error: {e}")

async def handle_followup_question(update, context):
    """Функция, обрабатывающая нажатие кнопки для уточняющего вопроса."""
    user_id = update.callback_query.from_user.id
    # Завершаем текущий разговор с GPT, если он активен
    if is_ocr_mode.get(user_id, False):
        is_ocr_mode[user_id] = False  # Выключаем режим GPT
    
    # Включаем режим ролей
    is_asking_mode[user_id] = True    
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Пожалуйста, введите ваш уточняющий вопрос.")
    return ASKING_FOR_FOLLOWUP

MAX_MESSAGE_LENGTH = 4096

def split_text_into_chunks(text, max_length=MAX_MESSAGE_LENGTH):
    """Разделяет текст на части, каждая из которых не превышает max_length."""
    chunks = []
    while len(text) > max_length:
        split_index = text.rfind("\n", 0, max_length)
        if split_index == -1:  # Если нет переносов строки, делим по max_length
            split_index = max_length
        chunks.append(text[:split_index].strip())
        text = text[split_index:].strip()
    chunks.append(text)
    return chunks

async def receive_followup_question(update, context):
    """Обработка уточняющего вопроса после распознавания текста."""
    user_id = update.message.from_user.id
    followup_question = update.message.text

    # Извлекаем распознанный текст из context.user_data
    recognized_text = context.user_data.get('recognized_text', '')

    # Объединяем распознанный текст с уточняющим вопросом
    full_query = f"{recognized_text}\n\n{followup_question}"

    # Отправляем вопрос с распознанным текстом в Gemini
    response = await generate_text_rec_response(user_id, query=full_query)

    if response:
        # Разделяем ответ на части, если он превышает длину сообщения Telegram
        response_chunks = split_text_into_chunks(response)

        # Отправляем каждую часть пользователю
        for chunk in response_chunks:
            await update.message.reply_text(chunk)  # Добавлено await
    else:
        await update.message.reply_text("Ошибка при обработке уточняющего вопроса.")  # Добавлено await

    # Создаем клавиатуру с кнопкой "Отменить режим распознавания"
    keyboard = [
        [InlineKeyboardButton("Отменить режим распознавания", callback_data='finish_ocr')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем клавиатуру после всех сообщений
    await update.message.reply_text("Режим распознавания активен.", reply_markup=reply_markup)  # Добавлено await

    is_role_mode[user_id] = False
    is_ocr_mode[user_id] = True  # Включаем режим GPT обратно
    return ConversationHandler.END  # Завершение уточняющего вопроса






async def search_image_saucenao(image_path: str):
    url = 'https://saucenao.com/search.php'
    params = {
        'api_key': 'd3d3b527510c50ca559d38901614b0da7c86db75',
        'output_type': 0,
        'numres': 10,
        'db': 999,
    }

    async with aiohttp.ClientSession() as session:
        with open(image_path, 'rb') as image_file:
            files = {'file': image_file}

            async with session.post(url, params=params, data=files) as response:
                # Проверка на превышение лимита
                if response.status == 429:
                    html_content = await response.text()
                    if "Daily Search Limit Exceeded" in html_content:
                        raise Exception("Лимит превышен")  # Бросаем исключение, если превышен лимит
                    else:
                        logging.error("Ошибка 429: неизвестная причина")
                        return None, [], None, None, None, None, None, None, None
                
                # Проверка успешного ответа
                if response.status == 200:
                    html_content = await response.text()
                    soup = BeautifulSoup(html_content, 'html.parser')

                    # Находим все блоки результатов
                    result_blocks = soup.find_all('td', class_='resulttablecontent')
                    results = []

                    # Проверяем, до какого места мы можем обрабатывать результаты
                    for block in result_blocks:
                        if block.find_parent(class_='result', id='result-hidden-notification'):
                            break

                        similarity_info = block.find('div', class_='resultsimilarityinfo')
                        if similarity_info:
                            similarity_percentage = float(similarity_info.text.replace('%', '').strip())
                            
                            if similarity_percentage >= 60:
                                results.append((similarity_percentage, block))

                    # Инициализируем переменные
                    authors_text = None
                    links = []
                    jp_name = None
                    details_text = None
                    ep_name = None
                    ep_time = None
                    dA_id = None
                    full_author_text = None
                    pixiv_id = None
                    twitter_id = None

                    if results:
                        results.sort(key=lambda x: x[0], reverse=True)
                        best_match = results[0][1]

                        result_title_div = best_match.find('div', class_='resulttitle')
                        authors_parts = []
                        details_parts = []

                        if result_title_div:
                            for elem in result_title_div.children:
                                if elem.name == "strong" and 'subtext' not in elem.get("class", []):
                                    authors_text = elem.text.strip()
                                    break
                                elif elem.name == "small":
                                    details_parts.append(elem.text.strip())
                            
                            if not authors_text:
                                authors_text = " ".join(authors_parts).replace("  ", " ").strip()
                            details_text = result_title_div.get_text(separator="\n", strip=True)
                            details_text = "\n".join(details_text.splitlines()[1:]).strip()

                        result_content_div = best_match.find('div', class_='resultcontentcolumn')

                        if result_content_div:
                            ep_name = ""
                            ep_time = None

                            ep_span = result_content_div.find('span', class_='subtext', string="EP")
                            if ep_span:
                                ep_name = ep_span.find_next('strong').next_sibling.strip()
                                ep_name = f"Название эпизода: {ep_name}"

                            subtext_spans = result_content_div.find_all('span', class_='subtext')
                            for span in subtext_spans:
                                if "Est Time:" in span.get_text():
                                    ep_time = span.get_text().replace("Est Time:", "").strip()
                                    ep_time = f"Таймметка скриншота в эпизоде: {ep_time}"
                                    break

                            dA_id_link = result_content_div.find('a', href=True)
                            if dA_id_link and "deviantart" in dA_id_link['href']:
                                dA_id = dA_id_link['href']
                            pixiv_id_link = result_content_div.find('a', href=True)
                            if pixiv_id_link and "pixiv" in pixiv_id_link['href']:
                                pixiv_id = pixiv_id_link['href']   
                            twitter_id_link = result_content_div.find('a', href=True)
                            if twitter_id_link and "twitter.com" in twitter_id_link['href']: 
                                twitter_id = twitter_id_link['href']  # Формируем строку в нужном формате
                            else:
                                twitter_id = None                                              

                            full_author_text = ""
                            author_tag = result_content_div.find('strong', string=lambda text: text.strip() == "Author:")
                            if author_tag:
                                author_link_tag = author_tag.find_next('a', class_='linkify')
                                if author_link_tag:
                                    author_name = author_link_tag.text.strip()
                                    author_url = author_link_tag['href']
                                    full_author_text = f"{author_name} - {author_url}"

                            result_miscinfo_div = best_match.find('div', class_='resultmiscinfo')
                            external_links = [a['href'] for a in result_miscinfo_div.find_all('a', href=True)] if result_miscinfo_div else []

                            jp_name_div = result_content_div.find('span', class_='subtext', string="JP")
                            jp_name = jp_name_div.find_next_sibling(text=True).strip() if jp_name_div else None

                        return authors_text, external_links, jp_name, details_text, ep_name, ep_time, dA_id, full_author_text, pixiv_id, twitter_id
                    else:
                        return None, [], None, None, None, None, None, None, None, None
                else:
                    logging.error(f"Ошибка {response.status}: {await response.text()}")
                    return None, [], None, None, None, None, None, None, None




async def second_upload_image(file_path: str) -> str:
    try:
        # Попытка загрузки на Catbox с таймаутом 5 секунд
        return await asyncio.wait_for(upload_catbox(file_path), timeout=5)
    except asyncio.TimeoutError:
        print("Таймаут при загрузке на Catbox. Переход к FreeImage.")
        return await upload_free_image(file_path)
    except Exception as e:
        print(f"Ошибка при загрузке на Catbox: {e}")
        return await upload_free_image(file_path)

async def upload_catbox(file_path: str) -> str:
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            form = aiohttp.FormData()
            form.add_field('reqtype', 'fileupload')
            form.add_field('fileToUpload', f)
            form.add_field('userhash', '1f68d2a125c66f6ab79a4f89c')  # Замените на ваш реальный userhash

            async with session.post('https://catbox.moe/user/api.php', data=form) as response:
                if response.status == 200:
                    return await response.text()  # возвращает URL загруженного файла
                else:
                    raise Exception(f"Ошибка загрузки на Catbox: {response.status}")

async def upload_free_image(file_path: str) -> str:
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:  # Открываем файл заново
            form = aiohttp.FormData()
            form.add_field('key', '6d207e02198a847aa98d0a2a901485a5')  # Ваш API ключ для freeimage.host
            form.add_field('action', 'upload')
            form.add_field('source', f)  # Используем файл для загрузки

            async with session.post('https://freeimage.host/api/1/upload', data=form) as free_image_response:
                if free_image_response.status == 200:
                    response_json = await free_image_response.json()
                    return response_json['image']['url']  # Проверьте правильность пути к URL в ответе
                else:
                    raise Exception(f"Ошибка загрузки на Free Image Hosting: {free_image_response.status}")




async def parse_yandex_results(img_url):
    search_url = f"https://yandex.ru/images/search?source=collections&rpt=imageview&url={img_url}"
    response = requests.get(search_url)
    soup = BeautifulSoup(response.text, 'lxml')
    
    similar_images = soup.find_all('li', class_='cbir-similar__thumb')
    result_links = []
    for i in similar_images:
        result_links.append(f"https://yandex.ru{i.find('a').get('href')}")
    
    return result_links


async def ai_or_not(update: Update, context: CallbackContext):
    img_url = context.user_data.get('img_url')

    if img_url is None:
        await update.callback_query.answer("Не удалось найти URL изображения.")
        return

    api_user = '1334786424'  # Ваш api_user
    api_secret = 'HaC88eFy4NLhyo86Md9aTKkkKaQyZeEU'  # Ваш api_secret

    params = {
        'url': img_url,
        'models': 'genai',
        'api_user': api_user,
        'api_secret': api_secret
    }

    async with aiohttp.ClientSession() as session:
        for attempt in range(5):  # Пять попыток
            async with session.get('https://api.sightengine.com/1.0/check.json', params=params) as response:
                if response.status == 200:
                    output = await response.json()
                    ai_generated_score = output['type']['ai_generated']

                    keyboard = [
                        [InlineKeyboardButton("Sightengine", url="https://sightengine.com/detect-ai-generated-images")],
                        [InlineKeyboardButton("Illuminarty AI", url="https://app.illuminarty.ai/#/")]
                    ]

                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await update.callback_query.answer()
                    await update.callback_query.message.reply_text(
                        f"Изображение сгенерировано АИ с вероятностью: {ai_generated_score * 100:.2f}% \n\n Вы можете прислать другое изображение для проверки, либо проверить самостоятельно на следующих ресурсах:",
                        reply_markup=reply_markup
                    )

                    return
                elif response.status == 429:
                    await asyncio.sleep(5)  # Ждем 5 секунд перед следующей попыткой
                else:
                    error_message = await response.text()
                    await update.callback_query.answer("Ошибка при обращении к API Sightengine.")
                    print(f"Ошибка API: {response.status} - {error_message}")
                    return

    await update.callback_query.answer("Не удалось обработать изображение после нескольких попыток.")





async def start_search(update: Update, context: CallbackContext) -> int:
    if update.message:
        user_id = update.message.from_user.id  # Когда вызвано командой /search
        message_to_reply = update.message
    elif update.callback_query:
        user_id = update.callback_query.from_user.id  # Когда нажата кнопка "Начать поиск"
        message_to_reply = update.callback_query.message
        await update.callback_query.answer()

    # Устанавливаем флаг для режима поиска и сбрасываем другие флаги
    is_search_mode[user_id] = True
    is_gpt_mode[user_id] = False
    is_ocr_mode[user_id] = False

    # Создаем кнопку "Отменить поиск"
    keyboard = [
        [InlineKeyboardButton("Отменить поиск", callback_data='finish_search')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем сообщение с кнопкой
    await message_to_reply.reply_text(
        "Пожалуйста, отправьте изображение для поиска источника или для проверки, сгенерировано ли оно нейросетью.",
        reply_markup=reply_markup
    )
    
    return ASKING_FOR_FILE

async def handle_file(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id

    # Проверка, если пользователь находится в режиме поиска
    if user_id in is_search_mode and is_search_mode[user_id]:
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            image_path = 'temp_image.jpg'
            await file.download_to_drive(image_path)
            # Здесь логика для поиска по изображению
            return ASKING_FOR_FILE
        elif update.message.document:
            if update.message.document.mime_type.startswith('image/'):
                file = await update.message.document.get_file()
                image_path = 'temp_image.jpg'
                await file.download_to_drive(image_path)
                # Логика для обработки документов
                return ASKING_FOR_FILE
            else:
                await update.message.reply_text("Пожалуйста, отправьте изображение для поиска источников.")
                return ASKING_FOR_FILE
        else:
            await update.message.reply_text("Пожалуйста, отправьте изображение для поиска источников.")
            return ASKING_FOR_FILE
    
    # Проверка, если пользователь находится в режиме OCR
    if user_id in is_ocr_mode and is_ocr_mode[user_id]:
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            image_path = 'temp_image.jpg'
            await file.download_to_drive(image_path)
            # Логика для OCR-обработки
            return ASKING_FOR_OCR
        elif update.message.document:
            if update.message.document.mime_type.startswith('image/'):
                file = await update.message.document.get_file()
                image_path = 'temp_image.jpg'
                await file.download_to_drive(image_path)
                return ASKING_FOR_OCR
            else:
                await update.message.reply_text("Пожалуйста, отправьте изображение для OCR.")
                return ASKING_FOR_OCR
        else:
            await update.message.reply_text("Пожалуйста, отправьте изображение для OCR.")
            return ASKING_FOR_OCR


    if user_id in is_gpt_mode and is_gpt_mode[user_id]:
        if update.message.text:
            # Обрабатываем текст сообщения через GPT
            user_message = update.message.text
            response = generate_gemini_response(user_id, query=user_message)
            await update.message.reply_text(response)
            return RUNNING_GPT_MODE
        elif update.message.photo or update.message.document:
            await update.message.reply_text("В режиме GPT поддерживается только текстовый ввод.")
            return RUNNING_GPT_MODE            

    if user_id in is_role_mode and is_role_mode[user_id]:
        if update.message.text:
            # Обрабатываем текст сообщения через GPT
            user_message = update.message.text
            response = generate_gemini_response(user_id, query=user_message)
            await update.message.reply_text(response)
            return RUNNING_GPT_MODE
        elif update.message.photo or update.message.document:
            await update.message.reply_text("В режиме GPT поддерживается только текстовый ввод.")
            return RUNNING_GPT_MODE 

    if user_id in is_asking_mode and is_asking_mode[user_id]:
        if update.message.text:
            # Обрабатываем текст сообщения через GPT
            user_message = update.message.text
            response = generate_gemini_response(user_id, query=user_message)
            await update.message.reply_text(response)
            return ASKING_FOR_FOLLOWUP
        elif update.message.photo or update.message.document:
            await update.message.reply_text("В режиме GPT поддерживается только текстовый ввод.")
            return ASKING_FOR_FOLLOWUP

    # Если пользователь отправил команду /restart, сбрасываем состояние
    if update.message.text == "/restart":
        return await restart(update, context)

    await update.message.reply_text("Пожалуйста, отправьте файл документом или изображение.")
    return ASKING_FOR_FILE

async def finish_search(update: Update, context: CallbackContext) -> int:
    # Проверяем, вызвана ли функция через кнопку или командой
    if update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()  # Отвечаем на запрос, чтобы убрать индикатор загрузки на кнопке
        await query.edit_message_text(
            "Вы вышли из режима поиска и вернулись к основным функциям бота",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎨 Найти автора или проверить на ИИ 🎨", callback_data='start_search')],
                [InlineKeyboardButton("🌱 Распознать(растение, грибы, текст) 🌱", callback_data='start_ocr')],
                [InlineKeyboardButton("🦊 Поговорить с ботом 🦊", callback_data='run_gpt')],
                [InlineKeyboardButton("‼️ Полный сброс процесса ‼️", callback_data='restart')]
            ])
        )
    else:
        # Если вызов произошел через команду
        user_id = update.message.from_user.id
        await update.message.reply_text(
            "Вы вышли из режима поиска и вернулись к основным функциям бота",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎨 Найти автора или проверить на ИИ 🎨", callback_data='start_search')],
                [InlineKeyboardButton("🌱 Распознать(растение, грибы, текст) 🌱", callback_data='start_ocr')],
                [InlineKeyboardButton("🦊 Поговорить с ботом 🦊", callback_data='run_gpt')],
                [InlineKeyboardButton("‼️ Полный сброс процесса ‼️", callback_data='restart')]
            ])
        )

    is_search_mode[user_id] = False  # Выключаем режим поиска
    return ConversationHandler.END

# Основная логика обработчика сообщений
async def main_logic(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id

    # Если пользователь находится в режиме поиска, игнорируем основную логику
    if is_search_mode.get(user_id, False):
        return

    # Если пользователь находится в режиме OCR, игнорируем основную логику
    if is_ocr_mode.get(user_id, False):
        return ASKING_FOR_OCR

    if is_gpt_mode.get(user_id, False):
        return RUNNING_GPT_MODE        

    if is_role_mode.get(user_id, False):
        return ASKING_FOR_ROLE 

    if is_asking_mode.get(user_id, False):
        return ASKING_FOR_FOLLOWUP


    # Основная логика обработки сообщений
    await update.message.reply_text("Обрабатываем сообщение в основной логике.")
    return ConversationHandler.END

# Добавим функцию для обработки неизвестных сообщений в режиме поиска
async def unknown_search_message(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Пожалуйста, отправьте фото или документ.")
    return ASKING_FOR_FILE

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

    # Удаляем все данные пользователя
    if user_id in user_data:
        del user_data[user_id]  # Удаляем старые данные пользователя  

    if user_id in is_search_mode:
        del is_search_mode[user_id]  # Выключаем режим поиска, если он включен

    if user_id in is_ocr_mode:
        del is_ocr_mode[user_id]

    if user_id in is_gpt_mode:
        del is_gpt_mode[user_id]

    if user_id in is_asking_mode:
        del is_asking_mode[user_id]

    if user_id in is_role_mode:
        del is_role_mode[user_id] 

    if user_id in waiting_for_forward:
        del waiting_for_forward[user_id] 

    if user_id in waiting_for_caption:
        del waiting_for_caption[user_id] 

    if user_id in waiting_for_vk:
        del waiting_for_vk[user_id] 
    logger.info(f"User {user_id} restarted the process.") 

    # Отправляем сообщение с кнопками
    keyboard = [
        [InlineKeyboardButton("🗂 Папки с сохранёнными постами 🗂", callback_data="scheduled_by_tag")],
        [InlineKeyboardButton("🎨 Найти автора или проверить на ИИ 🎨", callback_data='start_search')],
        [InlineKeyboardButton("🌱 Распознать (Растениеи, гриб, текст) 🌱", callback_data='start_ocr')],            
        [InlineKeyboardButton("🦊 Поговорить с ботом 🦊", callback_data='run_gpt')],
        [InlineKeyboardButton("📖 Посмотреть помощь", callback_data="osnhelp")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message_to_reply.reply_text(
        '✅Бот успешно перезапущен \n⸜(⸝⸝⸝´꒳`⸝⸝⸝)⸝\n\n'
        'Этот бот поможет вам создать публикацию для телеграм канала или вк группы с изображениями высокого разрешения.\n\n'
        'Для начала пожалуйста отправьте мне текст который будет служить подписью к вашей будущей записи в телеграм посте.  \n\nЕсли текста нет, то напишите "нет"\n\n Либо воспользуйтесь одной из кнопок(в кнопке 🦊 доступна генерация изображений и много чего ещё):',                       

        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    # Устанавливаем новое состояние после перезапуска
    user_data[user_id] = {'status': 'awaiting_artist_link'}
    
    return ASKING_FOR_ARTIST_LINK

async def rerestart(update: Update, context: CallbackContext) -> int:
    # Проверка типа события
    if update.message:
        user_id = update.message.from_user.id
        message_to_reply = update.message
    elif update.callback_query:
        user_id = update.callback_query.from_user.id
        message_to_reply = update.callback_query.message
    else:
        return ConversationHandler.END

    # Удаляем все данные пользователя
    if user_id in user_data:
        del user_data[user_id]  # Удаляем старые данные пользователя  

    if user_id in is_search_mode:
        del is_search_mode[user_id]  # Выключаем режим поиска, если он включен

    if user_id in is_ocr_mode:
        del is_ocr_mode[user_id]

    if user_id in is_gpt_mode:
        del is_gpt_mode[user_id]

    if user_id in is_asking_mode:
        del is_asking_mode[user_id]

    if user_id in is_role_mode:
        del is_role_mode[user_id] 

    if user_id in waiting_for_forward:
        del waiting_for_forward[user_id] 

    if user_id in waiting_for_vk:
        del waiting_for_vk[user_id] 
    logger.info(f"User {user_id} restarted the process.") 

    # Отправляем сообщение с кнопками
    keyboard = [
        [InlineKeyboardButton("🗂 Папки с сохранёнными постами 🗂", callback_data="scheduled_by_tag")],
        [InlineKeyboardButton("🎨 Найти автора или проверить на ИИ 🎨", callback_data='start_search')],
        [InlineKeyboardButton("🌱 Распознать (Растение, гриб, текст) 🌱", callback_data='start_ocr')],            
        [InlineKeyboardButton("🦊 Поговорить с ботом 🦊", callback_data='run_gpt')],
        [InlineKeyboardButton("📖 Посмотреть помощь", callback_data="osnhelp")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message_to_reply.reply_text(
        '✅Ваш пост успешно создан и бот перезапущен, теперь ждёт ваших навых постов! \n(=^・ェ・^=)\n\n'
        'Либо же вы можете отредактировать, сохранить в папку или опубликовать в соцсети созданный только что или один из созданных ранее постов. \n\nДля начала создания нового поста пришлите текст который будет служить подписью. Если подпись не нужна то пришлите "нет"\n\n',
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    # Устанавливаем новое состояние после перезапуска
    user_data[user_id] = {'status': 'awaiting_artist_link'}
    
    return ASKING_FOR_ARTIST_LINK


async def start_ocr(update: Update, context: CallbackContext) -> int:
    if update.message:
        user_id = update.message.from_user.id  # Когда вызвано командой /search
        message_to_reply = update.message
    elif update.callback_query:
        user_id = update.callback_query.from_user.id  # Когда нажата кнопка "Начать поиск"
        message_to_reply = update.callback_query.message
        await update.callback_query.answer()    

    is_ocr_mode[user_id] = True    
    is_search_mode[user_id] = False
    is_gpt_mode[user_id] = False
  # Устанавливаем флаг для пользователя в режим поиска

    # Создаем кнопку "Отменить поиск"
    keyboard = [
        [InlineKeyboardButton("Отменить режим распознавания", callback_data='finish_ocr')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем сообщение с кнопкой
    await message_to_reply.reply_text(
        "Пожалуйста, отправьте изображение для поиска или распознавания. Лучше отправлять сжатые изображения, тогда бот работает быстрее. Оригиналы в виде файлов отправляйте только по необходимости (мелкий текст, мелкие растения и тд)",
        reply_markup=reply_markup
    )
    
    return ASKING_FOR_OCR

async def finish_ocr(update: Update, context: CallbackContext) -> int:
    keyboard = [
        [InlineKeyboardButton("🎨 Найти автора или проверить на ИИ 🎨", callback_data='start_search')],
        [InlineKeyboardButton("🌱 Распознать(растение, грибы, текст) 🌱", callback_data='start_ocr')],
        [InlineKeyboardButton("🦊 Поговорить с ботом 🦊", callback_data='run_gpt')],
        [InlineKeyboardButton("‼️ Полный сброс процесса ‼️", callback_data='restart')]

    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:  # Если функция вызвана через нажатие кнопки
        query = update.callback_query
        user_id = query.from_user.id
        is_ocr_mode[user_id] = False  # Выключаем режим поиска
        is_search_mode[user_id] = False
        is_gpt_mode[user_id] = False
        is_role_mode[user_id] = False
        is_asking_mode[user_id] = False  # Выключаем режим поиска
        
        await query.answer()  # Отвечаем на запрос, чтобы убрать индикатор загрузки на кнопке
        await query.edit_message_text(
            "Вы вышли из режима распознавания и вернулись к основным функциям бота. Вы можете продолжить заполнять статью на том моменте на котором остановились, либо воспользоваться одной из кнопок:", 
            reply_markup=reply_markup  # Добавляем кнопки
        )
    
    elif update.message:  # Если функция вызвана через команду /fin_ocr
        user_id = update.message.from_user.id
        is_ocr_mode[user_id] = False  # Выключаем режим поиска
        is_search_mode[user_id] = False
        is_gpt_mode[user_id] = False
        is_role_mode[user_id] = False
        is_asking_mode[user_id] = False  # Выключаем режим поиска
        
        await update.message.reply_text(
            "Вы вышли из режима распознавания и вернулись к основным функциям бота. Вы можете продолжить заполнять статью на том моменте на котором остановились, либо воспользоваться одной из кнопок:", 
            reply_markup=reply_markup  # Добавляем кнопки
        )

    return ConversationHandler.END
    
# Добавим функцию для обработки неизвестных сообщений в режиме поиска
async def unknown_ocr_message(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Пожалуйста, отправьте фото или документ.")
    return ASKING_FOR_OCR

# Обработчик нажатия на кнопку "Распознать текст"
async def ocr_space_with_url(img_url, api_key):
    ocr_url = "https://api.ocr.space/parse/imageurl"

    async with aiohttp.ClientSession() as session:
        params = {
            'apikey': api_key,
            'url': img_url,
            'language': 'rus',  # Указываем язык
            'isOverlayRequired': 'False',  # Нужно ли накладывать текст на изображение
            'detectOrientation': 'True',  # Определять ориентацию текста
            'scale': 'True'  # Масштабировать изображение
        }

        async with session.get(ocr_url, params=params) as response:
            if response.status == 200:
                result = await response.json()
                try:
                    return result["ParsedResults"][0]["ParsedText"]
                except (KeyError, IndexError):
                    return "Текст не был распознан."
            else:
                return f"Ошибка API OCR.space: {response.status}"


# Измененный обработчик кнопки для OCR
async def button_ocr(update, context):
    query = update.callback_query
    await query.answer()

    # Получаем URL изображения с Catbox
    img_url = context.user_data.get('img_url')

    if query.data == 'recognize_text':
        if img_url:
            # Вызов функции для распознавания текста через Google Cloud Vision API с использованием URL
            api_key = 'K86410931988957'  # Ваш ключ API
            recognized_text = await ocr_space_with_url(img_url, api_key)
            keyboard = [
                [InlineKeyboardButton("Отменить режим распознавания", callback_data='finish_ocr')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            # Отправляем распознанный текст пользователю
            await query.message.reply_text(
                f"Распознанный текст:\n{recognized_text}\n\nОтправьте следующее изображение для распознавания либо нажмите кнопку ниже",
                reply_markup=reply_markup  # Добавляем кнопку к последнему сообщению
            )
        else:
            # Отправляем сообщение об ошибке с кнопкой
            await query.message.reply_text(
                "URL изображения не найден. Попробуйте ещё раз.",
                reply_markup=reply_markup  # Добавляем кнопку к этому сообщению
            )

    elif query.data == 'recognize_plant':
        await recognize_plant(update, context)  # Вызов функции для распознавания растения
    else:
        await query.message.reply_text("Неизвестная команда.")





async def recognize_plant(update: Update, context: CallbackContext) -> None:
    user_id = update.callback_query.from_user.id
    img_url = context.user_data.get('img_url')

    if not img_url:
        await update.callback_query.answer("Сначала загрузите изображение.")
        return



    api_key = "2b10C744schFhHigMMjMsDmV"
    project = "all"  
    lang = "ru"   
    include_related_images = "true"  

    # URL-кодирование для изображения
    encoded_image_url = aiohttp.helpers.quote(img_url)

    # Формирование URL для запроса
    api_url = (
        f"https://my-api.plantnet.org/v2/identify/{project}?"
        f"images={encoded_image_url}&"
        f"organs=auto&"
        f"lang={lang}&"
        f"include-related-images={include_related_images}&"
        f"api-key={api_key}"
    )
    
    # Отправляем сообщение с начальным текстом
    initial_message = await update.callback_query.message.reply_text("Запрос принят...")

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            status = response.status


            if status == 200:
                prediction = await response.json()


                if prediction.get('results'):
                    keyboard = []
                    for idx, plant in enumerate(prediction['results'][:3]):
                        species = plant.get('species', {})
                        scientific_name = species.get('scientificNameWithoutAuthor', 'Неизвестное растение')
                        common_names = species.get('commonNames', [])
                        common_name_str = ', '.join(common_names) if common_names else 'Название отсутствует'
                        
                        # Извлекаем процент сходства
                        similarity_score = plant.get('score', 0) * 100  # Предполагаем, что значение score от 0 до 1
                        similarity_text = f"{similarity_score:.2f}%"  # Форматируем до двух знаков после запятой
                        
                        # Сохраняем данные о растениях в context.user_data для обработки нажатий
                        images = plant.get('images', [])
                        context.user_data[f"plant_{idx}"] = {
                            "scientific_name": scientific_name,
                            "common_names": common_name_str,
                            "images": images
                        }


                        # Создаем кнопку для каждого растения с процентом сходства в начале
                        keyboard.append([InlineKeyboardButton(
                            text=f"{similarity_text} - {scientific_name} ({common_name_str})",
                            callback_data=f"plant_{idx}"
                        )])

                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await initial_message.edit_text(
                        "Выберите одно из предложенных растений:",
                        reply_markup=reply_markup
                    )
                else:
                    await initial_message.edit_text("Растение не найдено.")
            else:
                error_message = await response.text()

                await initial_message.edit_text("Ошибка при распознавании растения. Данное растение в базе не обнаружено, убедитесь что это именно растение, цветок, фрукт или овощь а не что-то иное. Так же можете попробовать сфотографировать под иным ракурсом")






# Инициализация Wikipedia API с User-Agent
user_agent = "MyPlantBot/1.0 sylar1907942@gmail.com)"
wiki_wiki = wikipediaapi.Wikipedia(language='ru', user_agent=user_agent)  


wikipedia.set_lang('ru')  # Установите язык на русский

async def get_wikipedia_link(scientific_name: str, common_names: list) -> tuple:
    try:
        # Выполняем поиск по научному названию
        search_results = wikipedia.search(scientific_name)


        # Проверяем, есть ли результаты поиска
        if search_results:
            for article_title in search_results:
                # Проверяем, относится ли статья к категории "растения"
                page = wiki_wiki.page(article_title)
                if page.exists():
                    categories = page.categories
                    # Проверяем наличие ключевых категорий
                    if any('растения' in cat.lower() for cat in categories):

                        # Формируем и возвращаем ссылку на статью
                        return (f"https://ru.wikipedia.org/wiki/{article_title.replace(' ', '_')}", article_title)

        # Если результаты по научному названию не найдены, ищем по общим названиям
        for name in common_names:
            search_results = wikipedia.search(name)

            if search_results:
                for article_title in search_results:
                    # Проверяем, относится ли статья к категории "растения"
                    page = wiki_wiki.page(article_title)
                    if page.exists():
                        categories = page.categories
                        if any('растения' in cat.lower() for cat in categories):

                            # Формируем и возвращаем ссылку на статью
                            return (f"https://ru.wikipedia.org/wiki/{article_title.replace(' ', '_')}", article_title)
    
    except Exception as e:
        logger.error(f"Error fetching Wikipedia link: {e}")

    # Если ничего не найдено или статья не относится к растениям, возвращаем None
    return (None, None)





def escape_markdown_v2(text: str) -> str:
    # Проверка на наличие экранирования и удаление, если оно присутствует
    if re.search(r'\\[\\\*\[\]\(\)\{\}\.\!\?\-\#\@\&\$\%\^\&\+\=\~]', text):
        # Убираем экранирование у всех специальных символов Markdown
        text = re.sub(r'\\([\\\*\[\]\(\)\{\}\.\!\?\-\#\@\&\$\%\^\&\+\=\~])', r'\1', text)

    # Временная замена ** на |TEMP| без экранирования
    text = re.sub(r'\*\*(.*?)\*\*', r'|TEMP|\1|TEMP|', text)

    # Временная замена ``` на |CODE_BLOCK| для исключения из экранирования
    text = text.replace('```', '|CODE_BLOCK|')

    # Временная замена ` на |INLINE_CODE| для исключения из экранирования
    text = text.replace('`', '|INLINE_CODE|')

    # Экранируем все специальные символы
    text = re.sub(r'(?<!\\)([\\\*\[\]\(\)\{\}\.\!\?\-\#\@\&\$\%\^\&\+\=\~])', r'\\\1', text)

    # Восстанавливаем |TEMP| обратно на *
    text = text.replace('|TEMP|', '*')

    # Восстанавливаем |CODE_BLOCK| обратно на ```
    text = text.replace('|CODE_BLOCK|', '```')

    # Восстанавливаем |INLINE_CODE| обратно на `
    text = text.replace('|INLINE_CODE|', '`')

    # Экранируем символ |
    text = re.sub(r'(?<!\\)\|', r'\\|', text)

    # Экранируем символ _ везде, кроме конца строки
    text = re.sub(r'(?<!\\)_(?!$)', r'\\_', text)

    return text


async def button_more_plants_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    plant_key = query.data  # Получаем callback_data, например 'plant_0'
    


    plant_data = context.user_data.get(plant_key)
    if plant_data:
        scientific_name = plant_data['scientific_name']
        common_names = plant_data['common_names']
        context.user_data['scientific_name'] = scientific_name

        if isinstance(common_names, str):
            common_names = [common_names]  # Преобразуем в список, если это строка
        
        wikipedia_link, article_title = await get_wikipedia_link(scientific_name, common_names)

        description = ""
        if wikipedia_link:
            try:
                # Получаем краткое описание статьи по найденному названию статьи
                summary = wikipedia.summary(article_title, sentences=12)
                description += f"{(summary)}\n\n"
            except Exception as e:
                logger.error(f"Error fetching summary for {article_title}: {e}")
                description += "Краткое описание недоступно\n\n"
        else:

            description = "\n\nИнформация по данному растению не найдена\n\n"

        images = plant_data.get('images', [])


        if images:
            media = []  # Список для хранения объектов медиа
            for idx, img in enumerate(images):
                img_url = img['url']['o'] if 'url' in img else None
                if img_url:
                    if idx == 0:
                        # Подготавливаем подпись и добавляем в лог
                        caption = (
                            f"Растение: {escape_markdown_v2(scientific_name)}\n"
                            f"Общие названия: {escape_markdown_v2(', '.join(common_names))}\n"
                            f"{truncate_text_with_link(description, 300, wikipedia_link, scientific_name)}"
                        )

                        media.append(InputMediaPhoto(media=img_url, caption=caption))
                    else:
                        media.append(InputMediaPhoto(media=img_url))

            if media:

                
                try:
                    await query.message.reply_media_group(media)  # Отправляем медиагруппу

                except Exception as e:

                    await query.message.reply_text("Ошибка при отправке изображений. Проверьте форматирование текста.")
            else:
                await query.message.reply_text("Изображения не найдены")
        else:
            await query.message.reply_text("Изображений нет")
        
        # Отправляем сообщение с кнопками после медиа
        keyboard = [
            [InlineKeyboardButton("Подробнее об этом растении", callback_data='gpt_plants_more')],         
            [InlineKeyboardButton("Помощь по уходу за этим растением", callback_data='gpt_plants_help')],        
            [InlineKeyboardButton("Отменить режим распознавания", callback_data='finish_ocr')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "Для получения более подробной информации об этом растении либо об уходе за ним, воспользуйтесь кнопками ниже. Либо отправьте следующее изображение",
            reply_markup=reply_markup  # Добавляем кнопку к этому сообщению
        )
    else:
        await query.message.reply_text("Данные о растении не найдены")
    
    await query.answer()


async def gpt_plants_more_handler(update, context):
    """Асинхронный обработчик для запроса ухода за растением по научному названию."""
    user_id = update.callback_query.from_user.id
    scientific_name = context.user_data.get("scientific_name")
    await update.callback_query.answer()

    if not scientific_name:
        await update.callback_query.answer("Научное название не указано. Попробуйте снова.")
        return

    # Формируем запрос с научным названием
    query = f" Расскажи больше про {scientific_name}, например, интересные факты, способы применения, укажи если ядовито, какие-то особенности и прочее. При этом будь лаконичной. В ответе используй разметку markdown_v2"

    # Генерация ответа без контекста
    response_text = await generate_plant_help_response(user_id, query=query)
    response_text = limit_response_length(response_text)  # Оставляем ограничение длины
    logger.info(f"response_text {response_text}")
    keyboard = [
        [InlineKeyboardButton("Помощь по уходу за этим растением", callback_data='gpt_plants_help')],        
        [InlineKeyboardButton("Отменить режим распознавания", callback_data='finish_ocr')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Редактируем существующее сообщение с новым ответом и кнопками
    await update.callback_query.message.edit_text(response_text, reply_markup=reply_markup, parse_mode='MarkdownV2')


async def gpt_plants_help_handler(update, context):
    """Асинхронный обработчик для запроса ухода за растением по научному названию."""
    user_id = update.callback_query.from_user.id
    scientific_name = context.user_data.get("scientific_name")
    await update.callback_query.answer()

    if not scientific_name:
        await update.callback_query.answer("Научное название не указано. Попробуйте снова.")
        return

    # Формируем запрос с научным названием
    query = f"Как ухаживать за {scientific_name}?В ответе используй разметку markdown_v2"

    # Генерация ответа без контекста
    response_text = await generate_plant_help_response(user_id, query=query)
    response_text = limit_response_length(response_text)

    keyboard = [
        [InlineKeyboardButton("Подробнее об этом растении", callback_data='gpt_plants_more')],         
        [InlineKeyboardButton("Отменить режим распознавания", callback_data='finish_ocr')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Редактируем существующее сообщение с новым ответом и кнопками
    await update.callback_query.message.edit_text(response_text, reply_markup=reply_markup, parse_mode='MarkdownV2')





def truncate_text_with_link(text: str, max_length: int, link: str, scientific_name: str) -> str:
    """Обрезает текст до max_length символов, добавляет ссылку на статью или Google-поиск, с экранированием MarkdownV2."""
    ellipsis = '...'

    # Если ссылка на Википедию отсутствует, формируем ссылку на Google-поиск
    if link:
        link_text = f"\n[Узнать больше на Википедии]({link})"
    else:
        google_search_link = f"https://www.google.com/search?q={scientific_name.replace(' ', '+')}"
        link_text = f"\n[Найти в Google]({google_search_link})"
    
    # Вычисляем допустимую длину для текста без учета ссылки
    available_length = max_length - len(link_text) - len(ellipsis)

    # Если текст нужно обрезать
    if len(text) > available_length:
        truncated_text = text[:available_length] + ellipsis
    else:
        truncated_text = text

    # Экранируем текст, чтобы избежать ошибок MarkdownV2
    escaped_truncated_text = (truncated_text)
    escaped_link_text = (link_text)

    # Возвращаем финальный текст с экранированной ссылкой
    return escaped_truncated_text + escaped_link_text










async def help_command(update: Update, context: CallbackContext) -> None:
    """Обработчик для кнопки 'Помощь по GPT'."""
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    HELP_TEXT = """▶️Пост в Анемоне формируется из двух частей - непосредственно сам пост, видимый в телеграме, плюс статья Telagraph, доступная по ссылке (для примера посмотрите любой из последних постов в группе). Бот позволяет сделать обе части.  

    ▶️Статья в Telegraph формируется в порядке отправки вами изображений и текста боту.  
    Во время создания статьи, с помощью соответствующих кнопок вы можете:  
    - открыть предпросмотр телеграф статьи;  
    - удалить последний добавленный элемент (работает неограниченное количество раз, пока статья не станет пустой);  
    - редактировать всё содержимое вашей статьи через список добавленных изображений и текста. С любым фрагментом можно делать что угодно: менять текст на изображение и наоборот, удалять, исправлять. Однако это возможно только до тех пор, пока вы не используете кнопку "К Завершению Публикации". После её нажатия редактировать статью уже будет нельзя, только наполнить новую.  

    ▶️Поддерживаемые тэги разметки статьи:  
    - <code>***</code> — горизонтальная линия-разделитель (отправьте три звёздочки отдельным сообщением, в этом месте в статье Telegraph появится разделитель);  
    - <code>_текст_</code> — курсив;  
    - <code>*текст*</code> — жирный текст;  
    - <code>[текст ссылки](ссылка)</code> — гиперссылка;  
    - <code>видео:</code> — вставка видео с Vimeo или YouTube;  
    - <code>цитата:</code> — цитата;  
    - <code>цитата по центру:</code> — центрированная цитата;  
    - <code>заголовок:</code> — заголовок;  
    - <code>подзаголовок:</code> — подзаголовок.  

    Последние 5 тэгов пишутся в начале сообщения и применяются ко всему сообщению целиком. Каждое новое сообщение — это новый абзац. Сообщения без тэгов — обычный текст.  

    Пример:  
    - <pre>цитата: *Волк* никогда не будет жить в загоне, но загоны всегда будут жить в *волке*</pre> — в статье Telegraph примет вид цитаты, в которой слово "волк" выделено жирным;  
    - <pre>видео: ссылка_на_видео</pre> — вставка интерактивного видео YouTube или Vimeo.  



    """

    keyboard = [
        [InlineKeyboardButton("‼️Сброс Публикации и Возврат к Началу‼️", callback_data='restart')],
        [InlineKeyboardButton("Удалить последний элемент", callback_data='delete_last')],
        [InlineKeyboardButton("Ссылка на статью", callback_data='preview_article')],
        [InlineKeyboardButton("Редактировать", callback_data='edit_article')],
        [InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Отправляем сообщение с кнопкой
    await query.edit_message_text(HELP_TEXT, parse_mode="HTML", reply_markup=reply_markup)




async def handle_artist_link(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in user_data and user_data[user_id]['status'] == 'awaiting_artist_link':
        user_data[user_id]['artist_link'] = update.message.text
        logger.info(f"User {user_id} provided author link:")


        await update.message.reply_text(
            '🌟Хорошо. Теперь отправьте имя автора. \n\n <i>Чтобы скрыть слово "Автор:", используйте символ "^" в начале и конце сообщения. Например: ^Имя^</i>',
            parse_mode='HTML' # Добавляем клавиатуру
        )
        user_data[user_id]['status'] = 'awaiting_author_name'
        return ASKING_FOR_AUTHOR_NAME
    else:
        await update.message.reply_text('🚫Ошибка: данные не найдены.')
        return ConversationHandler.END

# Ввод имени художника
async def handle_author_name(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id

    # Проверка, что пользователь находится в нужном состоянии
    if user_id in user_data and user_data[user_id].get('status') == 'awaiting_author_name':

        # Если авторское имя ещё не сохранено
        if 'author_name' not in user_data[user_id]:
            author_input = update.message.text.strip()

            # Проверяем, если авторское имя обернуто в "^...^"
            match_full = re.match(r'^\^(.*)\^$', author_input, re.S)
            if match_full:
                # Если весь текст внутри "^...^", используем его как заголовок и убираем авторское имя
                title = match_full.group(1).strip()
                user_data[user_id]['title'] = title
                user_data[user_id]['author_name'] = ""  # Очищаем author_name
                user_data[user_id]['extra_phrase'] = ""  # Нет доп. фразы
            else:
                # Проверка на наличие фразы в начале текста "^...^"
                match_partial = re.match(r'^\^(.*?)\^\s*(.*)', author_input, re.S)
                if match_partial:
                    # Извлекаем фразу и имя автора
                    phrase = match_partial.group(1).strip()  # Фраза из "^...^"
                    author_name = match_partial.group(2).strip()  # Остаток текста как автор
                    user_data[user_id]['extra_phrase'] = phrase  # Сохраняем фразу
                    user_data[user_id]['author_name'] = author_name  # Имя автора
                    user_data[user_id]['title'] = author_name  # Используем как заголовок
                else:
                    # Если нет фразы в "^...^", сохраняем всё как имя автора
                    author_name = author_input
                    user_data[user_id]['author_name'] = author_name
                    user_data[user_id]['title'] = author_name  # Заголовок статьи

        else:
            # Если author_name уже есть, просто используем его для заголовка
            author_name = user_data[user_id]['author_name']
            user_data[user_id]['title'] = author_name  # Обновляем заголовок

        # Переход к следующему этапу
        keyboard = [
            [InlineKeyboardButton("Помощь и разметка", callback_data='help_command')],
            [InlineKeyboardButton("‼️Полный сброс процесса‼️", callback_data='restart')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            'Отлично \n🌌Теперь приступим к наполнению публикации контентом. Отправьте изображения файлом (без сжатия) или текст. Если вы отправите изображение с подписью, то в статье телеграф текст будет так же отображаться как подпись под изображением.\n\n'
            'Текст поддерживает различное форматирование. Для получения списка тэгов нажмите на кнопку помощи.\n\n'
            '<i>Так же вы можете переслать в бот сообщения с текстом и/или изображениями, и бот тут же автоматически перенесет всё это в статью в той же очерёдности</i>',
            parse_mode='HTML',
            reply_markup=reply_markup  # Добавляем клавиатуру
        )
        user_data[user_id]['status'] = 'awaiting_image'
        return ASKING_FOR_IMAGE

    else:
        await update.message.reply_text('🚫Ошибка: данные не найдены. Попробуйте снова или нажмите /restart.')
        return ConversationHandler.END



def compress_image(file_path: str, output_path: str) -> None:
    # Определяем максимальный размер файла в байтах (5 МБ)
    max_size = 5 * 1024 * 1024

    # Проверяем, является ли файл GIF или .rar
    if file_path.endswith('.gif') or file_path.endswith('.rar'):
        return

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
            img = img.resize((width // 2, height // 2), Image.Resampling.LANCZOS)  # Заменён ANTIALIAS
            img.save(output_path, format='JPEG', quality=quality)

        # Удаляем временный JPG файл, если он был создан
        if file_path.endswith('.jpg'):
            os.remove(file_path)

# Функция для загрузки изображения на сloudinary
async def upload_image_to_cloudinary(file_path: str) -> str:
    CLOUDINARY_URL = 'https://api.cloudinary.com/v1_1/dmacjjaho/image/upload'
    UPLOAD_PRESET = 'ml_default'
    timeout = ClientTimeout(total=10)  # Таймаут в 10 секунд    
    
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
    timeout = ClientTimeout(total=4)  # Таймаут в 10 секунд
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
                    try:
                        # Попытка загрузки на Cloudinary
                        return await upload_image_to_cloudinary(file_path)
                    except Exception as e:
                        logging.error(f"Ошибка загрузки на Cloudinary: {e}")
                        raise Exception("Не удалось загрузить изображение на все сервисы.")



# Определяем разметку тегов
markup_tags = {
    '*': 'strong',  # Жирный текст
    '_': 'em',      # Курсив
}


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
                try:
                    text = ''.join(
                        str(child['children'][0]) if isinstance(child['children'][0], str) else ''
                        for child in text['children']
                        if isinstance(child, dict) and 'children' in child
                    )
                except Exception as e:
                    print(f"Ошибка при обработке текста: {e}")
                    print(f"Текстовые данные: {text}")
                    text = "Ошибка обработки текста"
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
    
    keyboard.append([InlineKeyboardButton("🌌 Предпросмотр ссылки 🌌", callback_data='preview_article')])
    keyboard.append([InlineKeyboardButton("Помощь и разметка", callback_data='help_command')])
    keyboard.append([InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')])
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
            keyboard.append([InlineKeyboardButton("🌌 Предпросмотр ссылки 🌌", callback_data='preview_article')])
            keyboard.append([InlineKeyboardButton("Помощь и разметка", callback_data='help_command')])
            keyboard.append([InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')])

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
                InlineKeyboardButton("🌌 Предпросмотр статьи🌌 ", callback_data='preview_article')
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
                            preview_text = f"Обн изобр-ие"  # Нумерация только для изображений
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
                        InlineKeyboardButton("🌌 Предпросмотр статьи🌌 ", callback_data='preview_article')
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
                                    keyboard = []
                                    image_counter = 1  # Счётчик для изображений

                                    # Настройки пагинации
                                    items_per_page = 30  # Количество кнопок на странице
                                    total_pages = (len(media) + items_per_page - 1) // items_per_page  # Общее количество страниц
                                    current_page = user_data[user_id].get('current_page', 0)  # Текущая страница

                                    # Ограничиваем текущую страницу
                                    current_page = max(0, min(current_page, total_pages - 1))

                                    # Создаём новый список кнопок для содержания статьи
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

                                    keyboard.append([InlineKeyboardButton("🌌 Предпросмотр статьи🌌", callback_data='preview_article')])
                                    keyboard.append([InlineKeyboardButton("Помощь и разметка", callback_data='help_command')])
                                    keyboard.append([InlineKeyboardButton("Найти автора или проверить на ИИ", callback_data='start_search')])
                                    keyboard.append([InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')])


                                    # Отправляем новое сообщение с обновлённым списком кнопок
                                    reply_markup = InlineKeyboardMarkup(keyboard)
                                    sent_message_with_buttons = await context.bot.send_message(
                                        chat_id=update.message.chat_id,
                                        text='✅ Изображение Заменено. \n📝 Текущее содержание статьи:',
                                        reply_markup=reply_markup
                                    )

                                    # Сохраняем ID нового сообщения с кнопками
                                    user_data[user_id]['last_image_message_id'] = sent_message_with_buttons.message_id
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
                            [InlineKeyboardButton("Ссылка на статью", callback_data='preview_article')],
                            [InlineKeyboardButton("Редактировать", callback_data='edit_article')],
                            [InlineKeyboardButton("📗 Помощь и разметка Telegraph📗", callback_data='help_command')],
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
                            text=f'✅ {image_counter} {image_text} добавлено. ヽ(o＾▽＾o)ノ\n\n Дождитесь загрузки остальных изображений, если их больше чем одно. Затем вы можете продолжить присылать изображения или перейти к завершению.\n\n Так же на этом этапе можно заполнить текстом и изображениями создающуюся параллеольно статью telegraph, если она вам нужна, для этого используются кнопки ниже.\n\n Если статья telegraph вам не нужна то просто проигнорируйте все кнопки ниже и сразу жмите \n" К Завершению публикации " ',
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
                            [InlineKeyboardButton("Ссылка на статью", callback_data='preview_article')],
                            [InlineKeyboardButton("Редактировать", callback_data='edit_article')],
                            [InlineKeyboardButton("📗 Помощь и разметка Telegraph📗", callback_data='help_command')],
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
                            text=f'✅ {image_counter} {image_text} добавлено.\n\n ヽ(o＾▽＾o)ノ Дождитесь загрузки остальных изображений, если их больше чем одно. Затем вы можете продолжить присылать изображения или перейти к завершению.\n\n Так же на этом этапе можно заполнить текстом и изображениями создающуюся параллеольно статью telegraph, если она вам нужна, для этого используются кнопки ниже.\n\n Если статья telegraph вам не нужна то просто проигнорируйте все кнопки ниже и сразу жмите \n" К Завершению публикации " ',
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
    # Если пользователь отвечает "нет" в любом регистре и с точкой или без
    if message_text.lower() in ["нет", "нет."]:
        # Отправляем сообщение с кнопкой завершения публикации
        keyboard = [
            [InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Отлично! В таком случае нажмите кнопку ниже:",
            reply_markup=reply_markup
        )
        return ASKING_FOR_IMAGE  # Указываем нужный этап разговора (если требуется)
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
            [InlineKeyboardButton("Ссылка на статью", callback_data='preview_article')],
            [InlineKeyboardButton("Редактировать", callback_data='edit_article')],
            [InlineKeyboardButton("📗 Помощь и разметка Telegraph 📗", callback_data='help_command')],
            [InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard) 

        if 'text_counter' not in user_data[user_id]:
            user_data[user_id]['text_counter'] = 0

        # Когда бот получает текст, увеличиваем счётчик
        user_data[user_id]['text_counter'] += 1
        text_counter = user_data[user_id]['text_counter']

        # Используем счётчик текста в сообщении
        text_message = "текст" if text_counter == 1 else "текст"
        sent_message = await update.message.reply_text(
            f'✅ {text_message} успешно добавлен.\nヽ(o＾▽＾o)ノ\n\n Вы можете продолжить присылать контент или нажать " К Завершению Публикации " для перехода к завершающему этапу.\n\n',
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

def extract_text_from_json(data):
    if isinstance(data, dict):
        # Если текущий элемент - это словарь, рекурсивно обрабатываем его ключ 'children'
        return ''.join(extract_text_from_json(child) for child in data.get('children', []))
    elif isinstance(data, list):
        # Если текущий элемент - это список, обрабатываем каждый элемент списка
        return ''.join(extract_text_from_json(item) for item in data)
    elif isinstance(data, str):
        # Если текущий элемент - это строка, возвращаем её
        return data
    return ''



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
    
    keyboard.append([InlineKeyboardButton("🌌 Предпросмотр 🌌", callback_data='preview_article')])
    keyboard.append([InlineKeyboardButton("Помощь и разметка", callback_data='help_command')])
    keyboard.append([InlineKeyboardButton("🌠 К Завершению Публикации 🌠", callback_data='create_article')])
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
        raise  # Перекидываем исключение для повторных попыток

async def send_media_group(update, media_group, caption):
    if not media_group:
        return
    try:
        await update.message.reply_text(caption, parse_mode='HTML')
        await update.message.reply_media_group(media=media_group)
    except Exception as e:
        raise

async def send_media_group_with_retries(update, media_group, max_retries=3, delay=2):
    retries = 0

    # Определяем, является ли событие сообщением или callback-запросом
    if update.message:
        message_to_reply = update.message
    elif update.callback_query:
        message_to_reply = update.callback_query.message
    else:
        return None  # Не удалось определить источник, возвращаем None

    message_id = None  # ID первого сообщения в группе

    while retries < max_retries:
        try:
            # Обрабатываем изображения в медиагруппе
            processed_media_group = []
            for media in media_group:
                if media.type == "photo":
                    processed_image, _ = await process_image(media.media)  # Игнорируем второй элемент (is_gif)
                    if not processed_image:
                        raise Exception("Failed to process image for media group")
                    
                    # Добавляем обработанное изображение в новый объект InputMedia
                    processed_media_group.append(
                        InputMediaPhoto(
                            media=processed_image,
                            caption=media.caption if hasattr(media, "caption") else None,
                            parse_mode=media.parse_mode if hasattr(media, "parse_mode") else None
                        )
                    )
                elif media.type == "animation":
                    processed_image, _ = await process_image(media.media)  # Игнорируем второй элемент (is_gif)
                    if not processed_image:
                        raise Exception("Failed to process animation for media group")
                    
                    # Добавляем обработанную анимацию в новый объект InputMedia
                    processed_media_group.append(
                        InputMediaAnimation(
                            media=processed_image,
                            caption=media.caption if hasattr(media, "caption") else None,
                            parse_mode=media.parse_mode if hasattr(media, "parse_mode") else None
                        )
                    )
                else:
                    # Оставляем остальные типы медиа без изменений
                    processed_media_group.append(media)

            # Отправляем медиагруппу и сохраняем результат
            sent_messages = await message_to_reply.reply_media_group(processed_media_group)

            # Сохраняем message_id первого изображения
            if sent_messages:
                message_id = sent_messages[0].message_id  # ID первого отправленного сообщения

            return message_id  # Успешная отправка, возвращаем ID первого сообщения
        except Exception as e:
            retries += 1
            if retries < max_retries:
                await asyncio.sleep(delay)

    return None  # Если все попытки не удались, возвращаем None




async def convert_image_repost(photo_url: str):
    """
    Загружает изображение по URL, конвертирует в формат JPG,
    уменьшает разрешение, если необходимо, и сжимает для публикации.
    Если файл - это GIF, возвращает его без изменений.
    """
    try:
        # Загрузка файла по URL
        async with aiohttp.ClientSession() as session:
            async with session.get(photo_url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch file from URL: {photo_url}")
                
                # Определяем MIME-тип файла из заголовков ответа
                content_type = response.headers.get('Content-Type', '')
                
                # Если файл - GIF, возвращаем его без изменений
                if content_type == 'image/gif':
                    gif_data = await response.read()
                    return io.BytesIO(gif_data)  # Возвращаем как файл в памяти

                # Если это не GIF, продолжаем обработку
                img_data = await response.read()

        # Открытие изображения
        img = Image.open(io.BytesIO(img_data))

        # Конвертация изображения в формат JPEG (если не JPEG)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Уменьшаем разрешение, если максимальная сторона > 2450px
        max_dimension = 2500
        if max(img.width, img.height) > max_dimension:
            scale = max_dimension / max(img.width, img.height)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Сохраняем изображение в буфер
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=100)
        output.seek(0)

        # Проверяем размер файла (если > 2MB, сжимаем)
        max_file_size = 2 * 1024 * 1024  # 2MB
        if len(output.getvalue()) > max_file_size:
            # Понижаем качество изображения
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=85)
            output.seek(0)

            # Если размер все еще больше 2MB, уменьшаем разрешение
            if len(output.getvalue()) > max_file_size:
                scale = (max_file_size / len(output.getvalue())) ** 0.5
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                output = io.BytesIO()
                img.save(output, format="JPEG", quality=85)
                output.seek(0)

        return output  # Возвращаем обработанный файл в памяти
    except Exception as e:
        return None


async def process_image(photo_url):
    """
    Загружает изображение, конвертирует его в формат JPG,
    проверяет разрешение и размер, применяет необходимые преобразования.
    GIF-файлы остаются без изменений.
    """
    try:
        # Загрузка изображения из URL
        async with aiohttp.ClientSession() as session:
            async with session.get(photo_url) as response:
                if response.status == 200:
                    img_data = await response.read()
                else:
                    raise Exception("Failed to fetch image from URL")

        # Открываем изображение
        img = Image.open(io.BytesIO(img_data))

        # Если формат GIF, возвращаем исходные данные
        if img.format == "GIF":
            logger.info("Image is a GIF, returning original data")
            output = io.BytesIO(img_data)
            output.seek(0)
            return output, True

        # Конвертация в формат JPEG (если не JPEG)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Уменьшение разрешения, если большая сторона > 2300px
        max_dimension = 2500
        if max(img.width, img.height) > max_dimension:
            scale = max_dimension / max(img.width, img.height)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Сохраняем изображение в буфер памяти и проверяем размер
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=100)
        output.seek(0)
        
        # Проверка размера файла (если > 2MB, сжимаем)
        max_file_size = 2 * 1024 * 1024  # 2MB
        if len(output.getvalue()) > max_file_size:
            # Попробуем снизить качество
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=85)
            output.seek(0)

            # Если файл всё ещё больше 2MB, уменьшаем разрешение
            if len(output.getvalue()) > max_file_size:
                scale = (max_file_size / len(output.getvalue())) ** 0.5
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                output = io.BytesIO()
                img.save(output, format="JPEG", quality=85)
                output.seek(0)

        return output, False  # Возвращаем обработанное изображение и флаг is_gif=False
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        return None, False




async def send_photo_with_retries(update, photo_url, caption, parse_mode, reply_markup=None, max_retries=3, delay=2):
    retries = 0
    if update.message:
        message_to_reply = update.message
    elif update.callback_query:
        message_to_reply = update.callback_query.message
    else:
        return None

    while retries < max_retries:
        try:
            # Обработка изображения
            processed_image, is_gif = await process_image(photo_url)
            if not processed_image:
                raise Exception("Failed to process media")
            if is_gif:
                await message_to_reply.reply_text("Gif обрабатывается, ожидайте...\n\nВ боте GIF будет отображаться в сжатом виде. Не переживайте, так и должно быть для ускорения работы бота. Однако если вы воспользуетесь кнопкой публикации то на ваш канал отправится именно полный вариант")

            # Выбор метода отправки
            if is_gif:
                message = await message_to_reply.reply_animation(
                    animation=processed_image,
                    filename="animation.gif",
                    caption=caption,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            else:
                message = await message_to_reply.reply_photo(
                    photo=processed_image,
                    caption=caption,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            return message
        except Exception as e:
            logger.error(f"Failed to send media: {e}")
            retries += 1
            if retries < max_retries:
                logger.info(f"Retrying in {delay} seconds... (Attempt {retries}/{max_retries})")
                await asyncio.sleep(delay)
    return None   



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
            author_name = "by AnemoneBot"
            author_link = "https://t.me/anemone2_bot"
            artist_link = user_data[user_id].get('artist_link', '')
            media = user_data[user_id].get('media', [])
            title = user_data[user_id].get('title', 'Предпросмотр статьи')
            if not title:
                title = author_name
            if title.lower() in ["нет", "нет."]:
                title = "*"  # Заменяем на "*"  
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


from urllib.parse import urlparse


def format_link(link: str) -> str:
    # Парсим URL
    parsed_url = urlparse(link)
    domain = parsed_url.netloc  # Получаем домен, например, ema3art.tumblr.com
    # Убираем "www." если оно есть
    domain = domain.replace('www.', '')

    # Словарь для специальных названий
    custom_names = {
        'x.com': 'x.com',
        'pixiv.net': 'pixiv',
        'weibo.com': 'weibo',
        'artstation.com': 'artstation',
        'zcool.com.cn': 'zcool',
        't.me': 't.me',  # Добавлено для Telegram
    }

    # Проверяем, является ли это Tumblr-ссылкой
    if 'tumblr.com' in domain:
        link_name = 'tumblr'
    elif 'lofter.com' in domain:
        # Для lofter используем фиксированное имя
        link_name = 'lofter'
    elif domain in custom_names:
        # Используем специальное название, если оно задано
        link_name = custom_names[domain]
    else:
        # Убираем домен верхнего уровня (.com, .net, и т.д.)
        link_name = domain.split('.')[0]

    # Формируем гиперссылку
    return f"<a href=\"{link}\">{link_name}</a>"





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
            author_name = "by AnemoneBot"
            author_link = "https://t.me/anemone2_bot"
            artist_link = user_data[user_id]['artist_link']
            media = user_data[user_id].get('media', [])
            title = user_data[user_id].get('title', 'test')
            # Проверяем значение title
            
            if not title:
                title = author_name
            if title.lower() in ["нет", "нет."]:
                title = "*"  # Заменяем на "*"                              

            extra_links = user_data[user_id].get('extra_links', [])
            if extra_links:
                links_string = " • " + " • ".join(format_link(link) for link in extra_links)
            else:
                links_string = "" 
            # Извлекаем фразу перед "Автор", если она есть
            extra_phrase = user_data[user_id].get('extra_phrase', "")
            author_name_final = user_data[user_id].get('author_name', '')           
            # Проверяем значение author_name_final в зависимости от user_id
            if user_id == 6217936347:
                if author_name_final:
                    author_name_final = f"Автор: {author_name_final}"

            # Формируем строку с фразой перед "Автор", если она есть
            if extra_phrase:
                author_line = f"{extra_phrase}\n\n{author_name_final}"
            else:
                author_line = f"{author_name_final}"
            # Проверяем, есть ли авторское имя
            if not author_name_final:
                author_line = title  # Если это заголовок из "^...^", то используем только заголовок
            else:
                # Формируем строку с фразой перед "Автор", если она есть
                if extra_phrase:
                    author_line = f"{extra_phrase}\n\n{author_name_final}"
                else:
                    author_line = f"{author_name_final}"


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

                if author_line.lower().strip() in ["*", "нет", "нет."]:
                    author_line = ""
                if image_count > 1:
                    # Фильтруем только изображения, чтобы избежать смешивания с текстом
                    image_media = [item for item in media if item['type'] == 'image']
                    
                    # Разделение только изображений на группы по 10
                    media_groups = [image_media[i:i + 10] for i in range(0, len(image_media), 10)]
                    media_group_data = []
                    
                    # Для хранения информации о том, был ли добавлен текст
                    text_added = False
                    first_message_id = None
                    for group in media_groups:
                        media_group = []

                        for idx, item in enumerate(group):
                            caption = None
                            
                            # Если текст ещё не добавлен, добавляем подпись к первому изображению
                            if not text_added:
                                caption = f'{author_line}\n<a href="{article_url}">Оригинал</a>{links_string}'
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
                        message_id = await send_media_group_with_retries(update, media_group)
                        if message_id is None:
                            await message_to_reply.reply_text(f'🚫Ошибка при отправке медиа-группы.')
                            return
                        await update.effective_chat.pin_message(message_id)
                        if caption:
                            await message_to_reply.reply_text(
                                f"✅ Медиагруппа отправлена с подписью.",
                                reply_markup=create_publish_button(user_id),  # Кнопка публикации
                                disable_web_page_preview=True
                            )

                        # Сохраняем message_id в хранилище
                        key = f"{user_id}_{message_id}"  # Создаем ключ как строку
                        if user_id not in media_group_storage:
                            media_group_storage[user_id] = {}

                        media_group_storage[user_id][key] = {
                            "media": media_group_data,
                            "scheduled": 'Отсутствует',
                        }
                        await update.effective_chat.pin_message(message_id)                        
                        save_media_group_data(media_group_storage, user_id)  # Сохраняем в файл


                if image_count == 1:
                    single_image = next((item for item in media if item['type'] == 'image'), None)
                    if single_image:
                        caption = f'{author_line}\n<a href="{article_url}">Оригинал</a>{links_string}'
                        
                        # Формируем временный ключ
                        temp_key = f"{user_id}_0"  # Используем временный ключ до получения message_id
                        
                        # Формируем временную запись
                        media_group_storage.setdefault(user_id, {})  # Убедитесь, что для user_id есть пространство
                        media_group_storage[user_id][temp_key] = {
                            "media": [
                                {
                                    "file_id": single_image['url'],
                                    "caption": caption,
                                    "parse_mode": 'HTML'
                                }
                            ],
                            "scheduled": 'Отсутствует'  # Добавляем scheduled со значением None
                        }
                        
                        # Отправляем изображение
                        message = await send_photo_with_retries(
                            update=update,
                            photo_url=single_image['url'],
                            caption=caption,
                            parse_mode='HTML'
                        )
                        if not message:
                            await message_to_reply.reply_text('🚫Ошибка при отправке изображения. /restart')
                            return
                        
                        # Обновляем ключ с использованием message_id
                        message_id = message.message_id
                        updated_key = f"{user_id}_{message_id}"
                        media_group_storage[user_id][updated_key] = media_group_storage[user_id].pop(temp_key)
                        
                        # Закрепляем сообщение
                        await update.effective_chat.pin_message(message_id)
                        
                        # Сохраняем данные в Firebase
                        save_media_group_data(media_group_storage, user_id)

                elif image_count == 0:
                    message_with_link = f'{author_line}\n<a href="{article_url}">Оригинал</a>'
                    
                    # Формируем временный ключ
                    temp_key = f"{user_id}_0"  # Используем временный ключ до получения message_id
                    
                    # Формируем временную запись
                    media_group_storage.setdefault(user_id, {})  # Убедитесь, что для user_id есть пространство
                    media_group_storage[user_id][temp_key] = {
                        "media": [
                            {
                                "file_id": None,  # Так как изображений нет
                                "caption": message_with_link,
                                "parse_mode": 'HTML'
                            }
                        ],
                        "scheduled": 'Отсутствует'  # Добавляем scheduled со значением None
                    }
                    
                    # Отправляем сообщение
                    message = await message_to_reply.reply_text(message_with_link, parse_mode='HTML')
                    if not message:
                        await message_to_reply.reply_text('🚫Ошибка при отправке сообщения. /restart')
                        return
                    
                    # Обновляем ключ с использованием message_id
                    message_id = message.message_id
                    updated_key = f"{user_id}_{message_id}"
                    media_group_storage[user_id][updated_key] = media_group_storage[user_id].pop(temp_key)
                    
                    # Сохраняем данные в Firebase
                    save_media_group_data(media_group_storage, user_id)

                    # Отправляем уведомление пользователю
                    await message_to_reply.reply_text(
                        "✅ Сообщение без изображений успешно отправлено.",
                        disable_web_page_preview=True
                    )



                image_text = (
                    "изображение" if image_count % 10 == 1 and image_count % 100 != 11
                    else "изображения" if 2 <= image_count % 10 <= 4 and (image_count % 100 < 10 or image_count % 100 >= 20)
                    else "изображений"
                )

                await message_to_reply.reply_text(
                    f'Готово✅\n====--- В посте {image_count} {image_text}. ---====\n\nНажмите одну из кнопок ниже чтобы опубликовать его в вашу группу или канал, отредактировать или предложить в Анемон',
                    reply_markup=create_publish_button(user_id, message_id)  # Передаем message_id
                )

                # Отправляем сообщение с кнопкой для публикации в ВК
   
                # Закрепляем сообщение

                publish_data[user_id] = {
                    'title': title,
                    'article_url': article_url,
                    'image_count': image_count,
                    'author_line': author_line
                }

                del user_data[user_id]


                # Вызов команды restart
                await rerestart(update, context)

                return ConversationHandler.END
            else:
                await message_to_reply.reply_text('🚫Ошибка при создании статьи. /restart')
        except requests.RequestException as e:
            logger.info(f"Request error: {e}")
            await message_to_reply.reply_text('🚫Ошибка при создании статьи. /restart')
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            await message_to_reply.reply_text('🚫Произошла неожиданная ошибка. /restart')









def create_publish_button(user_id, message_id):
    keyboard = [
        [
            InlineKeyboardButton("🗂 Сохранить пост себе в папку 🗂", callback_data=f"snooze_with_tag_{user_id}_{message_id}")
        ],   
        [
            InlineKeyboardButton("Опубликовать в Telegram", callback_data=f"publish_{user_id}_{message_id}")
        ],        
        [
            InlineKeyboardButton("Опубликовать в ВК", callback_data=f"vkpub_{user_id}_{message_id}")
        ],
        [
            InlineKeyboardButton("✏️ Заменить подпись ✏️", callback_data=f"caption_{user_id}_{message_id}")
        ],        
        [
            InlineKeyboardButton("🌠 Предложить этот пост в Анемон 🌠", callback_data=f"share_{user_id}_{message_id}")
        ], 
        [
            InlineKeyboardButton("🔄 Случайно перемешать изображения 🔄", callback_data=f"shuffle_{user_id}_{message_id}")
        ],
        [
            InlineKeyboardButton("🎨 Сортировать по палитре 🎨", callback_data=f"palettesort_{user_id}_{message_id}")
        ],
        [
        InlineKeyboardButton("🔀 Поменять 2 изображения местами 🔀", callback_data=f"swapimages_{user_id}_{message_id}")
        ],
        [
        InlineKeyboardButton("❌ Удалить 1 изображение ❌", callback_data=f"filedelete_{user_id}_{message_id}")
        ]                     
    ]        
    return InlineKeyboardMarkup(keyboard)  

def create_publish_and_snooze_buttons(user_id, message_id):
    """Создает клавиатуру с кнопками для публикации и отложенной отправки."""
    keyboard = [
        [
            InlineKeyboardButton("🗂 Сохранить пост себе в папку 🗂", callback_data=f"snooze_with_tag_{user_id}_{message_id}")
        ],
        [
            InlineKeyboardButton("🔄 Случайно перемешать изображения 🔄", callback_data=f"shuffle_{user_id}_{message_id}")
        ],
        [
            InlineKeyboardButton("🎨 Сортировать по палитре 🎨", callback_data=f"palettesort_{user_id}_{message_id}")
        ],
        [
        InlineKeyboardButton("Поменять 2 изображения местами", callback_data=f"swapimages_{user_id}_{message_id}")
        ],
        [
        InlineKeyboardButton("❌ Удалить 1 изображение ❌", callback_data=f"filedelete_{user_id}_{message_id}")
        ]                

    ]
    return InlineKeyboardMarkup(keyboard)




def create_shuffle_buttons(user_id, message_id):

    keyboard = [
        [
            InlineKeyboardButton("Опубликовать в Telegram", callback_data=f"publish_{user_id}_{message_id}")
        ],
        [
            InlineKeyboardButton("Опубликовать в ВК", callback_data=f"vkpub_{user_id}_{message_id}")
        ],
        [
            InlineKeyboardButton("🗂 Сохранить пост себе в папку 🗂", callback_data=f"snooze_with_tag_{user_id}_{message_id}")
        ],
        [
            InlineKeyboardButton("🔄 Случайно перемешать ещё раз 🔄", callback_data=f"shuffle_{user_id}_{message_id}")
        ],
        [
            InlineKeyboardButton("🎨 Сортировать по палитре 🎨", callback_data=f"palettesort_{user_id}_{message_id}")
        ],
        [
        InlineKeyboardButton("Поменять 2 изображения местами", callback_data=f"swapimages_{user_id}_{message_id}")
        ],
        [
        InlineKeyboardButton("❌ Удалить 1 изображение ❌", callback_data=f"filedelete_{user_id}_{message_id}")
        ]    
    ]
    return InlineKeyboardMarkup(keyboard)    


async def handle_tag_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()

    # Извлекаем выбранный смайлик и данные
    _, tag, user_id_str, message_id_str = query.data.split('_')
    user_id = int(user_id_str)
    message_id = int(message_id_str)
    # Проверяем, есть ли данные о генерации в контексте
    global media_group_storage
    # Загружаем данные

    generation_data = context.user_data.get("generation_data")
    if generation_data:
        # Если данные о генерации есть, используем их
        media_group_storage = load_publications_from_firebase()
        user_data = media_group_storage.get(str(user_id), {})

        # Формируем данные для сохранения
        media_group_data = {
            "media": [
                {
                    "caption": generation_data["caption"],  # HTML-капшн
                    "file_id": generation_data["file_id"],  # URL изображения
                    "parse_mode": "HTML"
                }
            ],
            "scheduled": tag  # Метка (эмодзи)
        }

        # Сохраняем данные в Firebase
        user_data[f"{user_id}_{message_id}"] = media_group_data
        media_group_storage[str(user_id)] = user_data
        save_publications_to_firebase(user_id, f"{user_id}_{message_id}", media_group_data)

        # Очищаем данные о генерации из контекста
        context.user_data.pop("generation_data", None)

        # Уведомление пользователя
        await query.message.reply_text(
            f"✅ Запись успешно добавлена в папку {tag}.\n Теперь вы можете найти её там и продолжить редактирование, либо опубликовать",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗂 Посмотреть мои папки 🗂", callback_data="scheduled_by_tag")],
                [InlineKeyboardButton("‼️ Перезапуск бота ‼️", callback_data='restart')]
            ])
        )
        return
    media_group_storage = load_publications_from_firebase()   

    # Доступ к данным по user_id
    user_data = media_group_storage.get(str(user_id))
  
    if not user_data:
        await query.message.reply_text("🚫 Ошибка: Данные пользователя не найдены.")
        return

    # Доступ к данным по message_id
    message_key = f"{user_id}_{message_id}"
    media_group_data = user_data.get(message_key)
    if not media_group_data:
        await query.message.reply_text("🚫 Ошибка: Данные о медиагруппе не найдены.")
        return

    # Обновляем значение ключа 'scheduled'
    media_group_data["scheduled"] = tag

    # Сохраняем обновлённые данные обратно
    user_data[message_key] = media_group_data
    media_group_storage[str(user_id)] = user_data

    # Сохраняем обновлённый словарь в Firebase
    save_media_group_data(media_group_storage, user_id)

    # Уведомление пользователя
    await query.message.reply_text(
        f"✅ Запись успешно добавлена в папку {tag}.\n Теперь вы можете найти её там и продолжить редактирование, либо опубликовать",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗂 Посмотреть мои папки 🗂", callback_data="scheduled_by_tag")],
            [InlineKeyboardButton("‼️ Перезапуск бота ‼️", callback_data='restart')]
        ])
    )






def create_emoji_keyboard(emojis, user_id, message_id):
    keyboard = []
    row = []
    for emoji in emojis:
        row.append(InlineKeyboardButton(emoji, callback_data=f"tag_{emoji}_{user_id}_{message_id}"))
        if len(row) == 4:  # Если в строке 4 кнопки, добавляем её в клавиатуру
            keyboard.append(row)
            row = []  # Начинаем новую строку
    if row:  # Добавляем оставшиеся кнопки, если они есть
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

# Асинхронная функция обработки
async def handle_snooze_with_tag_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    # Извлекаем данные из callback_data
    print(f"Received callback data: {query.data}")  # Диагностика
    parts = query.data.split('_')
    user_id_str = parts[-2]  # Предпоследний элемент — user_id
    message_id_str = parts[-1]  # Последний элемент — message_id

    user_id = int(user_id_str)
    message_id = int(message_id_str)

    emojis = [
        "👀", "🤷‍♂️", "🧶", "🦊", "🦄", "🦆", "🐳", "🌿", "🌸", "🍓",
        "🍑", "🍆", "🌈", "🌧", "☀️", "⭐️", "🫖", "🌙", "🌠", "❄️",
        "🗑", "📎", "✏️", "🎨", "😈", "📷", "📚", "⏳", "✅", "❇️",
        "❌", "🔄", "🩷", "💛", "💚", "💙", "❤️", "💜", "🖤", "🤍",
    ]

    # Создаём клавиатуру с эмодзи
    reply_markup = create_emoji_keyboard(emojis, user_id, message_id)

    # Отправляем сообщение с клавиатурой
    await query.message.reply_text("Выберите метку для записи:", reply_markup=reply_markup)



# Функция для отображения отложенных записей с определённой меткой
async def show_scheduled_by_tag(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    # Получаем выбранную метку из callback_data
    _, _, tag = query.data.split('_')

    # Если пришёл ключ "nofolder", заменяем его на "Отсутствует"
    if tag == "nofolder":
        tag = "Отсутствует"

    global media_group_storage
    # Загружаем данные из файла
    media_group_storage = load_publications_from_firebase()

    # ID текущего пользователя
    current_user_id = str(update.effective_user.id)

    scheduled = []
    # Проверяем данные только для текущего пользователя
    if current_user_id in media_group_storage:
        user_publications = media_group_storage[current_user_id]
        for message_id, data in user_publications.items():
            if isinstance(data, dict):
                record_tag = data.get('scheduled', '')

                # Пропускаем записи с 'scheduled' == null
                if record_tag is None:
                    continue

                elif record_tag == tag:  # Если метка совпадает
                    # Проверяем, что 'media' — это список
                    if 'media' in data and isinstance(data['media'], list):
                        media_list = data['media']
                        if media_list:
                            raw_caption = media_list[0].get('caption', '')

                            # Используем BeautifulSoup для очистки от HTML-разметки
                            soup = BeautifulSoup(raw_caption, 'html.parser')

                            # Оставляем только текст из гиперссылок
                            for a in soup.find_all('a'):
                                a.replace_with(a.get_text())

                            # Получаем очищенный текст
                            cleaned_caption = soup.get_text()

                            # Логика определения финального текста
                            if "автор: " in cleaned_caption.lower():
                                # Если есть "автор: ", берём текст после него до конца строки или первой ссылки
                                match = re.search(r'автор:\s*([^•<\n]+)', cleaned_caption, re.IGNORECASE)
                                caption = match.group(1).strip() if match else ''
                            else:
                                # Если "автор: " нет, берём первые 3 слова очищенного текста
                                caption = ' '.join(cleaned_caption.split()[:3])

                            # Добавляем в список с подписью
                            scheduled.append((message_id, caption, tag))



    if scheduled:
        keyboard = [
            [InlineKeyboardButton("🗂 Другие папки 🗂", callback_data="scheduled_by_tag")],
            [InlineKeyboardButton("------------------------", callback_data="separator")]
        ]
        for index, (key, caption, tag) in enumerate(scheduled):
            keyboard.append([InlineKeyboardButton(f"📗 {caption} ({tag})", callback_data=f"view_{key}")])
            keyboard.append([
                InlineKeyboardButton("Удалить", callback_data=f"yrrasetag_{key}"),
                InlineKeyboardButton("Пост в ТГ", callback_data=f"publish_{key}"),
                InlineKeyboardButton("Пост в ВК", callback_data=f"vkpub_{key}")
            ])
        
        # Добавьте кнопку "Удалить все с меткой"
        keyboard.append([
            InlineKeyboardButton("------------------------", callback_data="separator")
        ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить все из этой папки 🗑", callback_data=f"tagdelete_{tag}")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(f"📋 Записи из папки {tag}:", reply_markup=reply_markup)
    else:
        await query.message.reply_text(f"🛑 Нет записей с меткой {tag}.")


async def delete_all_by_tag(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    # Получаем выбранную метку из callback_data
    _, tag = query.data.split('_')
    global media_group_storage
    # Загружаем данные из файла
    media_group_storage = load_publications_from_firebase()

    # ID текущего пользователя
    current_user_id = str(update.effective_user.id)

    # Проверяем, что данные есть для текущего пользователя
    if current_user_id in media_group_storage:
        user_publications = media_group_storage[current_user_id]

        # Собираем ключи для удаления
        keys_to_delete = [
            key for key, data in user_publications.items()
            if isinstance(data, dict) and data.get('scheduled') == tag
        ]

        print(f"Tag from callback_data: '{tag}'")
        print(f"Keys to delete: {keys_to_delete}")

        # Удаляем записи из базы и локального хранилища
        delete_from_firebase(keys_to_delete, current_user_id)
        for key in keys_to_delete:
            user_publications.pop(key, None)

        # Если у пользователя больше нет записей, удаляем его из общего хранилища
        if not user_publications:
            media_group_storage.pop(current_user_id, None)

        print(f"Media group storage after deletion: {media_group_storage}")

        # Сохраняем обновлённые данные обратно в файл
        save_media_group_data(media_group_storage, current_user_id)

        await query.message.reply_text(f"✅ Все записи из папки '{tag}' удалены.")
    else:
        await query.message.reply_text("🚫 У вас нет записей с такой меткой.")


async def yrrase_scheduled(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    # Проверяем формат callback_data
    if query.data and '_' in query.data:
        _, key = query.data.split('_', maxsplit=1)
    else:
        await query.message.reply_text("🛑 Неверный формат callback_data.")
        return

    global media_group_storage
    # Загружаем данные из файла
    media_group_storage = load_publications_from_firebase()

    # ID текущего пользователя
    current_user_id = str(update.effective_user.id)

    # Проверяем, что данные есть для текущего пользователя
    if current_user_id in media_group_storage:
        user_publications = media_group_storage[current_user_id]

        # Проверяем, существует ли запись с указанным ключом
        if key in user_publications:
            scheduled_tag = user_publications[key].get('scheduled', None)

            # Интерпретируем None как метку "отсутствует"
            if scheduled_tag is None:
                scheduled_tag = "отсутствует"

            # Удаляем запись из базы данных и локального хранилища
            delete_from_firebase([key], current_user_id)
            user_publications.pop(key, None)

            # Если у пользователя больше нет записей, удаляем его из общего хранилища
            if not user_publications:
                media_group_storage.pop(current_user_id, None)

            # Сохраняем обновлённые данные обратно в файл
            save_media_group_data(media_group_storage, current_user_id)

            # Собираем оставшиеся записи с той же меткой
            remaining_records = []
            for record_key, data in user_publications.items():
                record_tag = data.get('scheduled', None)
                if record_tag is None:
                    record_tag = "отсутствует"

                # Сравниваем с текущей меткой
                if record_tag == scheduled_tag:
                    caption = data['media'][0].get('caption', '')
                    # Извлекаем текст до гиперссылок
                    cleaned_caption = re.split(r'<a href="[^"]+">[^<]+</a>', caption, maxsplit=1)[0].strip()
                    # Если текста нет, использовать "Запись без подписи"
                    if not cleaned_caption:
                        cleaned_caption = "Запись без подписи"
                    remaining_records.append((record_key, cleaned_caption, record_tag))

            # Формируем обновлённую клавиатуру
            keyboard = []
            if remaining_records:
                keyboard.append([InlineKeyboardButton("🗂 Другие папки 🗂", callback_data="scheduled_by_tag")])
                keyboard.append([InlineKeyboardButton("------------------------", callback_data="separator")])

                for record_key, caption, tag in remaining_records:
                    keyboard.append([InlineKeyboardButton(f"📗 {caption} ({tag})", callback_data=f"view_{record_key}")])
                    keyboard.append([
                        InlineKeyboardButton("Удалить", callback_data=f"yrrasetag_{record_key}"),
                        InlineKeyboardButton("Пост в ТГ", callback_data=f"publish_{record_key}"),
                        InlineKeyboardButton("Пост в ВК", callback_data=f"vkpub_{record_key}"),
                    ])
            else:
                keyboard.append([InlineKeyboardButton("🗂 Другие папки 🗂", callback_data="scheduled_by_tag")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.edit_text(
                f"✅ Запись удалена. \nОстальные записи в папке '{scheduled_tag}':",
                reply_markup=reply_markup
            )
        else:
            await query.message.reply_text("🚫 Указанная запись не найдена.")
    else:
        await query.message.reply_text("🚫 У вас нет записей для удаления.")


# Функция для обработки команды /scheduledmark
async def handle_scheduled_tags(update: Update, context: CallbackContext) -> None:
    # Определяем, вызвана ли функция командой или нажатием кнопки
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        send_method = query.message.reply_text
        user_id = str(query.from_user.id)
    else:
        send_method = update.message.reply_text
        user_id = str(update.message.from_user.id)
    global media_group_storage
    # Загружаем данные
    media_group_storage = load_publications_from_firebase()
    tag_counts = {}  # Словарь для подсчёта количества постов на метку
    other_count = 0  # Счётчик для временных меток
    no_folder_count = 0  # Счётчик для записей без метки ("Отсутствует")

    # Проверяем, есть ли записи для данного user_id
    if user_id not in media_group_storage:
        await send_method("🛑 У вас нет записей.")
        return

    # Фильтруем записи только для данного пользователя
    user_publications = media_group_storage[user_id]

    # Подсчёт количества записей для каждой метки
    for message_id, data in user_publications.items():
        if isinstance(data, dict) and 'scheduled' in data:
            tag = data['scheduled']
            
            # Пропускаем записи с scheduled == null
            if tag is None:
                continue
            
            # Увеличиваем счётчик для записей без метки
            if tag == "Отсутствует":
                no_folder_count += 1
                continue

            # Проверяем, является ли метка временем
            try:
                datetime.strptime(tag, "%Y-%m-%d %H:%M")
                other_count += 1
            except ValueError:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Создаём клавиатуру с метками
    keyboard = []
    row = []
    for tag, count in sorted(tag_counts.items()):
        row.append(InlineKeyboardButton(f"{tag} ({count})", callback_data=f"filter_tag_{tag}"))
        if len(row) == 4:  # Максимум 4 кнопки в строке
            keyboard.append(row)
            row = []
    if row:  # Добавляем оставшиеся кнопки
        keyboard.append(row)

    # Добавляем кнопку "Прочее", если есть временные метки
    if other_count > 0:
        keyboard.append([InlineKeyboardButton(f"Нет метки ({other_count})", callback_data="filter_tag_other")])

    # Добавляем кнопку "Записи без папки", если есть записи с меткой "Отсутствует"
    if no_folder_count > 0:
        keyboard.append([InlineKeyboardButton(f"Записи без папки ({no_folder_count})", callback_data="filter_tag_nofolder")])

    total_count = sum(tag_counts.values()) + other_count + no_folder_count
    # Отправляем сообщение с клавиатурой
    if keyboard:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_method("Выберите папку для отображения записей:", reply_markup=reply_markup)
    else:
        await send_method("🛑 Нет доступных меток.")





from telegram import Update, MessageOriginChannel  # Добавлен импорт MessageOriginChannel
from telegram.ext import CallbackContext
import logging




async def handle_forwarded_message(update: Update, context: CallbackContext):
    message = update.message
    user_id = message.from_user.id


    # Проверяем, является ли сообщение пересланным из канала
    if message.forward_origin and isinstance(message.forward_origin, MessageOriginChannel):
        channel_data = message.forward_origin.chat

        # Получаем ID канала
        chat_id = channel_data.id

        try:
            # Проверяем права администратора
            is_admin = await check_admin_rights(context, chat_id, user_id)
            if not is_admin:
                await message.reply_text("🚫 У вас или у бота нет прав администратора в этом канале.")
                return

            # Сохраняем ID канала
            save_channel_to_firebase(chat_id, user_id)
            await message.reply_text(f"Канал успешно привязан! ID канала: {chat_id}")

            # Сбрасываем состояние ожидания
            del waiting_for_forward[user_id]
        except Exception as e:

            
            # Создаем разметку с кнопкой
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("‼️ Перезапуск бота ‼️", callback_data='restart')]
            ])
            
            # Отправляем сообщение с кнопкой
            await message.reply_text(
                "Произошла ошибка при привязке канала.", 
                reply_markup=keyboard
            )
    else:
        # Создаем разметку с кнопкой для другого сообщения
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("‼️ Перезапуск бота ‼️", callback_data='restart')]
        ])
        
        # Отправляем сообщение с кнопкой
        await message.reply_text(
            "Пожалуйста, пересылайте только сообщения из каналов. \n\nЕсли вы передумали, то перезапустите бота:",
            reply_markup=keyboard
        )


async def check_admin_rights(context: CallbackContext, chat_id: int, user_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором в указанном канале.
    """
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return any(admin.user.id == user_id for admin in admins)
    except Exception as e:
        logging.error(f"Ошибка при проверке прав администратора: {e}")
        return False

import mimetypes









async def handle_replace_caption(update: Update, context: CallbackContext) -> int:
    """Обрабатывает нажатие на кнопку 'заменить текст'."""
    query = update.callback_query
    await query.answer()

    # Извлекаем user_id и message_id из callback_data
    _, user_id_str, message_id_str = query.data.split('_', maxsplit=2)
    user_id = int(user_id_str)
    message_id = int(message_id_str)
    key = f"{user_id}_{message_id}"
    global media_group_storage
    # Загружаем данные из Firebase
    media_group_storage = load_publications_from_firebase()

    # Проверяем, есть ли записи для указанного user_id
    user_publications = media_group_storage.get(str(user_id))
    if not user_publications:
        await query.message.reply_text("🚫 Ошибка: Пользовательские данные не найдены.")
        return ConversationHandler.END

    # Проверяем, что запись существует
    publication = user_publications.get(key)
    if not publication:
        await query.message.reply_text("🚫 Запись не найдена.")
        return ConversationHandler.END

    # Проверяем, что в публикации есть медиа
    media = publication.get('media')
    if not media or not isinstance(media, list):
        await query.message.reply_text("🚫 Ошибка: В записи отсутствуют медиафайлы.")
        return ConversationHandler.END

    # Извлекаем подпись первого изображения
    first_caption = media[0].get('caption', '🚫 Подпись отсутствует.')

    # Сохраняем информацию о текущей публикации для этого пользователя
    waiting_for_caption[user_id] = key
    if user_id not in waiting_for_caption:
        waiting_for_caption[user_id] = True  # Помещаем пользователя в состояние ожидания

    # Создаём разметку для кнопки "Отмена"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Отмена", callback_data='restart')]]
    )

    # Отправляем текущую подпись и входим в режим ожидания новой
    await query.message.reply_text(
        text=f"Текущая подпись:\n\n{first_caption}\n\nВведите новую подпись. Всё форматирование, например жирный текст, спойлеры, гиперссылки будет сохранено.",
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=keyboard  # Добавляем кнопки
    )

    return





async def handle_new_caption(update: Update, context: CallbackContext, key) -> int:
    """Обрабатывает ввод новой подписи."""
    user_id = str(update.effective_user.id)
    logger.info(f"Полученный Context: {context.__dict__}")
    logger.info(f"Полученный user_id: {user_id}")     
    handle_caption = key  
    # Логирование полного объекта Update
    logger.info(f"Полученный Update: {update.to_dict()}")
    
    if user_id not in user_data:
        user_data[user_id] = {}  # Инициализация пустого словаря для пользователя
    
    # Получаем новую подпись
    new_caption = update.message.text.strip()  # Убираем лишние пробелы

    if not new_caption:
        await update.message.reply_text("🚫 Ошибка: Подпись не может быть пустой.")
        return WAITING_FOR_NEW_CAPTION

    global media_group_storage
    media_group_storage = load_publications_from_firebase()

    # Проверяем, существует ли запись
    user_publications = media_group_storage.get(user_id)
    if not user_publications or key not in user_publications:
        await update.message.reply_text("🚫 Запись не найдена.")
        del waiting_for_caption[user_id]
        return ConversationHandler.END

    publication = user_publications[key]

    # Проверяем, что запись содержит медиафайлы
    media = publication.get('media')
    if not media or not isinstance(media, list):
        await update.message.reply_text("🚫 Ошибка: В записи отсутствуют медиафайлы.")
        del waiting_for_caption[user_id]
        return ConversationHandler.END

    # Форматируем подпись с учётом Telegram-разметки
    formatted_caption = format_text_to_html(update.message)
    media[0]['caption'] = formatted_caption

    # Сохраняем обновленные данные в Firebase
    save_publications_to_firebase(user_id, key, publication)
    
    try:
        user_id = update.effective_user.id        
        # Создание клавиатуры с кнопками
        keyboard = [
            [InlineKeyboardButton("📄 Посмотреть обновлённую запись 📄", callback_data=f"view_{key}")],
            [
                InlineKeyboardButton("Пост ТГ", callback_data=f"publish_{key}"),
                InlineKeyboardButton("Пост ВК", callback_data=f"vkpub_{key}"),                
                InlineKeyboardButton("Удалить", callback_data=f"erase_{key}")
            ],
            [InlineKeyboardButton("🗂 Мои папки 🗂", callback_data="scheduled_by_tag")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем сообщение с кнопками
        await update.message.reply_text(f"✅ Подпись успешно обновлена на:\n{formatted_caption}", reply_markup=reply_markup, parse_mode='HTML', disable_web_page_preview=True,)
    except Exception as e:
        await update.message.reply_text(f"🚫 Ошибка сохранения данных: {e}")
    finally:
        del waiting_for_caption[user_id]
        
    # Завершаем обработку
    return ASKING_FOR_ARTIST_LINK



async def handle_publish_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Ответ пользователю, что нажатие обработано
    temp_message = await query.message.reply_text("📤 Пост переносится, ожидайте...")
    # Извлекаем user_id и message_id из callback_data
    _, user_id_str, message_id_str = query.data.split('_')
    user_id = int(user_id_str)
    message_id = int(message_id_str)
    global media_group_storage
    # Загружаем данные из Firebase
    media_group_storage = load_publications_from_firebase()

    # Проверяем, есть ли записи для указанного user_id
    user_data = media_group_storage.get(str(user_id))
    if not user_data:
        await temp_message.edit_text("🚫 Ошибка: Пользовательские данные не найдены.")
        return

    # Проверяем наличие конкретной записи
    key = f"{user_id}_{message_id}"
    media_group_data = user_data.get(key)

    if media_group_data:
        try:
            # Если данные - это строка, преобразуем в словарь
            if isinstance(media_group_data, str):
                media_group_data = json.loads(media_group_data)

            # Извлекаем список медиа
            media_items = media_group_data.get('media')
            if not media_items or not isinstance(media_items, list):
                await temp_message.edit_text("🚫 Ошибка: Некорректный формат данных.")
                return
        except json.JSONDecodeError as e:
            await temp_message.edit_text(f"🚫 Ошибка преобразования данных: {e}")
            return

        # Загружаем привязанные каналы из Firebase
        channel_ref = db.reference('users_publications/channels')
        channels_data = channel_ref.get() or {}

        # Ищем каналы, где текущий пользователь указан как администратор
        user_channels = [
            chat_id for chat_id, info in channels_data.items()
            if user_id in info.get('user_ids', [])
        ]

        if not user_channels:
            # Создаем кнопку и клавиатуру
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("‼️Перезапуск бота‼️", callback_data='restart')]]
            )
            
            await temp_message.edit_text(
                "Сейчас у вас нет привязанных каналов. Перешлите в бот любой пост из вашего канала, чтобы привязать его. Не убирайте галочку с \"Показывать отправителя\" чтобы бот смог увидеть ваш канал. \n\nТак же для публикации постов бот должен быть добавлен в ваш канал.",
                reply_markup=keyboard  # Добавляем клавиатуру к сообщению
            )

            # Устанавливаем пользователя в состояние ожидания пересланного сообщения
            if user_id not in waiting_for_forward:
                waiting_for_forward[user_id] = True  # Помещаем пользователя в состояние ожидания

            return

        # Используем первый привязанный канал для публикации
        chat_id = user_channels[0]

        # Создаём медиагруппу для отправки в канал
        media_group = []
        for item in media_items:
            file_url = item['file_id']

            # Определяем MIME-тип файла по URL
            mime_type, _ = mimetypes.guess_type(file_url)

            # Обрабатываем файл через convert_image_repost
            processed_image = await convert_image_repost(file_url)

            if processed_image is not None:
                caption = item.get('caption')  # None, если 'caption' отсутствует
                parse_mode = item.get('parse_mode')  # None, если 'parse_mode' отсутствует

                if mime_type == "image/gif":  # Если это GIF
                    media_group.append(
                        InputMediaDocument(
                            media=processed_image,  # Используем обработанный GIF
                            caption=caption,
                            filename="animation.gif",
                            parse_mode=parse_mode
                        )
                    )
                else:  # Любое другое изображение
                    media_group.append(
                        InputMediaPhoto(
                            media=processed_image,  # Используем обработанное изображение
                            caption=caption,
                            parse_mode=parse_mode
                        )
                    )
            else:
                await temp_message.edit_text(f"🚫 Ошибка при обработке файла: {file_url}")
                return

        # Публикуем медиагруппу в канале
        try:
            await context.bot.send_media_group(
                chat_id=chat_id,  # Канал, в который нужно публиковать
                media=media_group
            )
            await temp_message.edit_text(f"✅ Пост успешно опубликован в канале {chat_id}!")
        except Forbidden as e:
            if "bot is not a member of the channel chat" in str(e):
                await temp_message.edit_text(
                    "🚫 Для возможности публиковать посты из бота в ваш канал, пожалуйста, добавьте бота в ваш канал с разрешением на публикацию. "
                    "Если вы не хотите этого делать, то можете пересылать посты вручную."
                )
            else:
                await temp_message.edit_text(f"🚫 Ошибка доступа: {e}")
        except Exception as e:
            await temp_message.edit_text(f"🚫 Ошибка при публикации поста: {e}")
    else:
        await temp_message.edit_text("🚫 Ошибка: Данные о медиагруппе не найдены.")


async def handle_share_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Ответ пользователю, что нажатие обработано

    # Извлекаем user_id и message_id из callback_data
    _, user_id_str, message_id_str = query.data.split('_')
    user_id = int(user_id_str)
    message_id = int(message_id_str)
    global media_group_storage
    # Загружаем данные из Firebase
    media_group_storage = load_publications_from_firebase()

    # Проверяем, есть ли записи для указанного user_id
    user_data = media_group_storage.get(str(user_id))
    if not user_data:
        await query.message.reply_text("🚫 Ошибка: Пользовательские данные не найдены.")
        return

    # Проверяем наличие конкретной записи
    key = f"{user_id}_{message_id}"
    media_group_data = user_data.get(key)

    if media_group_data:
        try:
            # Если данные - это строка, преобразуем в словарь
            if isinstance(media_group_data, str):
                media_group_data = json.loads(media_group_data)

            # Извлекаем список медиа
            media_items = media_group_data.get('media')
            if not media_items or not isinstance(media_items, list):
                await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
                return
        except json.JSONDecodeError as e:
            await query.message.reply_text(f"🚫 Ошибка преобразования данных: {e}")
            return

        # Создаём медиагруппу для отправки в группу
        media_group = []
        for item in media_items:
            file_url = item['file_id']

            # Определяем MIME-тип файла по URL
            mime_type, _ = mimetypes.guess_type(file_url)

            # Обрабатываем файл через convert_image_repost
            processed_image = await convert_image_repost(file_url)

            if processed_image is not None:
                caption = item.get('caption')  # None, если 'caption' отсутствует
                parse_mode = item.get('parse_mode')  # None, если 'parse_mode' отсутствует

                if mime_type == "image/gif":  # Если это GIF
                    media_group.append(
                        InputMediaDocument(
                            media=processed_image,  # Используем обработанный GIF
                            caption=caption,
                            filename="animation.gif",
                            parse_mode=parse_mode
                        )
                    )
                else:  # Любое другое изображение
                    media_group.append(
                        InputMediaPhoto(
                            media=processed_image,  # Используем обработанное изображение
                            caption=caption,
                            parse_mode=parse_mode
                        )
                    )
            else:
                await query.message.reply_text(f"🚫 Ошибка при обработке файла: {file_url}")
                return

        # Отправляем сообщение, кто предложил пост
        user_name = query.from_user.username or "Неизвестный пользователь"
        first_name = query.from_user.first_name or "Без имени"
        proposed_message = f"Пост предложен пользователем {first_name} (@{user_name})"

        try:
            # Отправляем информацию о пользователе в канал
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=proposed_message
            )

            # Публикуем медиагруппу в заранее заданной группе
            await context.bot.send_media_group(
                chat_id=GROUP_CHAT_ID,  # Заранее заданная группа
                media=media_group
            )
            await query.message.reply_text("✅ Пост успешно предложен в Анемон!")
        except Exception as e:
            await query.message.reply_text(f"🚫 Ошибка при публикации поста: {e}")
    else:
        await query.message.reply_text("🚫 Ошибка: Данные о медиагруппе не найдены.")


from datetime import datetime













async def swap_images(update: Update, context: CallbackContext) -> None:
    """Начинаем процесс замены изображений."""
    query = update.callback_query
    await query.answer()

    if query and '_' in query.data:
        _, key = query.data.split('_', maxsplit=1)
    else:
        await query.message.reply_text("🛑 Неверный формат данных.")
        return

    global media_group_storage
    # Загружаем данные из файла
    media_group_storage = load_publications_from_firebase()


    # Разбиваем ключ на user_id и user_message
    user_id, user_message = key.split('_', maxsplit=1)

    # Проверяем наличие user_id
    if user_id in media_group_storage:
        user_publications = media_group_storage[user_id]
        # Проверяем наличие записи под user_message
        if key in user_publications:
            media_group = user_publications[key]

            # Проверяем, является ли media_group словарём с ключом 'media'
            if isinstance(media_group, dict) and 'media' in media_group:
                media = media_group['media']
            else:
                await query.message.reply_text("🛑 Некорректный формат данных.")
                return

            if len(media) < 2:
                await query.message.reply_text("🛑 Недостаточно изображений для замены.")
                return

            # Создаём кнопки для выбора первого изображения
            keyboard = [
                [InlineKeyboardButton(f"Изображение {i+1}", callback_data=f"swap_first_{key}_{i}")]
                for i in range(len(media))
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Выберите первое изображение для замены:", reply_markup=reply_markup)
        else:
            await query.message.reply_text("🛑 Запись не найдена.")
    else:
        await query.message.reply_text("🛑 Пользователь не найден.")


async def select_first_image(update: Update, context: CallbackContext) -> None:
    """Обрабатываем выбор первого изображения."""
    query = update.callback_query
    await query.answer()

    if query and query.data.startswith("swap_first_"):
        data_parts = query.data.split('_')
        # Собираем ключ пользователя и сообщение
        user_id = data_parts[2]
        user_message = "_".join(data_parts[3:-1])
        first_index = int(data_parts[-1])
        context.user_data['swap_key'] = f"{user_id}_{user_message}"
        context.user_data['first_index'] = first_index
    else:
        await query.message.reply_text("🛑 Неверный формат данных.")
        return

    key = context.user_data['swap_key']

    global media_group_storage
    # Загружаем данные из Firebase
    media_group_storage = load_publications_from_firebase()

    # Проверяем наличие user_id в media_group_storage
    if user_id in media_group_storage:
        user_publications = media_group_storage[user_id]
        # Проверяем наличие записи по ключу
        if key in user_publications:
            media_group = user_publications[key]
            # Проверяем, является ли media_group словарём с ключом 'media'
            media = media_group.get("media") if isinstance(media_group, dict) else None
        else:
            await query.message.reply_text("🛑 Запись не найдена.")
            return
    else:
        await query.message.reply_text("🛑 Пользователь не найден.")
        return

    if not media or len(media) < 2:
        await query.message.reply_text("🛑 Недостаточно изображений для замены.")
        return

    # Создаём кнопки для выбора второго изображения (исключая уже выбранное)
    keyboard = [
        [InlineKeyboardButton(f"Изображение {i+1}", callback_data=f"swap_second_{key}_{i}")]
        for i in range(len(media))
        if i != context.user_data['first_index']
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Обновляем сообщение вместо отправки нового
    await query.edit_message_text("Выберите второе изображение для замены:", reply_markup=reply_markup)





async def select_second_image(update: Update, context: CallbackContext) -> None:
    """Обрабатываем выбор второго изображения и выполняем замену."""
    query = update.callback_query
    await query.answer()

    if query and query.data.startswith("swap_second_"):
        # Разделяем данные
        data_parts = query.data.split('_')
        user_id = data_parts[2]
        user_message = "_".join(data_parts[3:-1])
        second_index = int(data_parts[-1])
        first_index = context.user_data.get('first_index')

        if first_index is None:
            await query.message.reply_text("🛑 Сначала выберите первое изображение.")
            return

        # Формируем ключ
        key = f"{user_id}_{user_message}"
    else:
        await query.message.reply_text("🛑 Неверный формат данных.")
        return

    # Логируем ключ и индексы

    global media_group_storage
    # Загружаем данные из Firebase
    media_group_storage = load_publications_from_firebase()

    # Проверяем наличие user_id в media_group_storage
    if user_id in media_group_storage:
        user_publications = media_group_storage[user_id]
        # Проверяем наличие записи по ключу
        if key in user_publications:
            media_group = user_publications[key]
            # Проверяем, является ли media_group словарём с ключом 'media'
            media = media_group.get("media") if isinstance(media_group, dict) else None
        else:
            await query.message.reply_text("🛑 Запись не найдена.")
            return
    else:
        await query.message.reply_text("🛑 Пользователь не найден в хранилище.")
        return

    # Проверка структуры данных
    if not media or not isinstance(media, list) or len(media) < 2:
        await query.message.reply_text("🛑 Недостаточно изображений для замены.")
        return

    # Проверяем индексы
    if first_index >= len(media) or second_index >= len(media):
        await query.message.reply_text("🛑 Ошибка индексов.")
        return


    # Сохраняем начальные значения caption и parse_mode первого изображения
    first_caption = media[0].get('caption')
    first_parse_mode = media[0].get('parse_mode')

    # Меняем изображения местами
    media[first_index], media[second_index] = media[second_index], media[first_index]

    # Восстанавливаем caption и parse_mode для первого изображения
    media[0]['caption'] = first_caption
    media[0]['parse_mode'] = first_parse_mode

    # Убираем caption и parse_mode у остальных изображений
    for item in media[1:]:
        item['caption'] = None
        item['parse_mode'] = None

    # Сохраняем изменения обратно в хранилище
    user_publications[key]['media'] = media
    save_media_group_data(media_group_storage, user_id)

    # Формируем медиагруппу для отображения
    media_group_preview = []
    for media_data in media:
        if 'file_id' in media_data:
            media_group_preview.append(
                InputMediaPhoto(
                    media=media_data['file_id'],
                    caption=media_data.get('caption', ''),
                    parse_mode=media_data.get('parse_mode', None)
                )
            )
    await query.message.delete()
    # Отправляем медиагруппу
    if media_group_preview:
        await context.bot.send_media_group(
            chat_id=query.message.chat_id,
            media=media_group_preview
        )

    # Отправляем информацию о записи с кнопками
    await query.message.reply_text(
        text="✅ Изображения успешно заменены и пост обновлен.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Пост ТГ", callback_data=f"publish_{key}"),
                InlineKeyboardButton("Пост ВК", callback_data=f"vkpub_{key}"),
                InlineKeyboardButton("Удалить", callback_data=f"erase_{key}")
            ],
            [
                InlineKeyboardButton("🌠 Предложить этот пост в Анемон 🌠", callback_data=f"share_{key}")
            ],            
            [
                InlineKeyboardButton("🔄 Случайно перемешать 🔄", callback_data=f"shuffle_{key}")
            ],
            [
                InlineKeyboardButton("🎨 Сортировать по палитре 🎨", callback_data=f"palettesort_{key}")
            ],
            [
                InlineKeyboardButton("📔 Сохранить в папку 📔", callback_data=f"snooze_with_tag_{key}")
            ],                                    
            [
                InlineKeyboardButton("Поменять 2 изображения местами", callback_data=f"swapimages_{key}")
            ],
            [
                InlineKeyboardButton("❌ Удалить 1 изображение ❌", callback_data=f"filedelete_{key}")
            ],
            [
                InlineKeyboardButton("🗂 Посмотреть папки 🗂", callback_data="scheduled_by_tag")
            ],                                 
        ])
    )









async def filedelete_image(update: Update, context: CallbackContext) -> None:
    """Начинаем процесс удаления изображения."""
    query = update.callback_query
    await query.answer()


    # Проверяем формат callback_data
    if query and query.data.startswith("filedelete_"):
        data_parts = query.data.split('_')
        user_id = data_parts[1]
        user_message = "_".join(data_parts[2:])
        key = f"{user_id}_{user_message}"
    else:
        await query.message.reply_text("🛑 Неверный формат данных.")
        return
    global media_group_storage
    # Загружаем данные из Firebase
    media_group_storage = load_publications_from_firebase()

    # Проверяем наличие user_id в media_group_storage
    if user_id in media_group_storage:
        user_publications = media_group_storage[user_id]

        # Проверяем наличие ключа
        if key in user_publications:
            media_group = user_publications[key]

            # Проверяем структуру media_group
            if isinstance(media_group, dict) and 'media' in media_group:
                media = media_group['media']  # Извлекаем список media
            else:
                await query.message.reply_text("🛑 Некорректный формат данных.")
                return

            if len(media) < 1:
                await query.message.reply_text("🛑 Нет изображений для удаления.")
                return

            # Создаём кнопки для выбора изображения для удаления
            keyboard = [
                [InlineKeyboardButton(f"Изображение {i+1}", callback_data=f"fileselect_{user_id}_{user_message}_{i}")]
                for i in range(len(media))
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Выберите изображение для удаления:", reply_markup=reply_markup)
        else:
            await query.message.reply_text("🛑 Запись не найдена.")
    else:
        await query.message.reply_text("🛑 Пользователь не найден.")


async def fileselect_image_to_delete(update: Update, context: CallbackContext) -> None:
    """Обрабатываем выбор изображения для удаления и выполняем удаление."""
    query = update.callback_query
    await query.answer()

    # Проверяем формат callback_data
    if query and query.data.startswith("fileselect_"):
        data_parts = query.data.split('_')
        user_id = data_parts[1]
        user_message = "_".join(data_parts[2:-1])
        index = int(data_parts[-1])  # Последняя часть — индекс изображения
        key = f"{user_id}_{user_message}"
    else:
        await query.message.reply_text("🛑 Неверный формат данных.")
        return

    global media_group_storage
    # Загружаем данные из Firebase
    media_group_storage = load_publications_from_firebase()
    media_group = media_group_storage.get(user_id, {}).get(key)

    # Проверяем наличие данных
    if not media_group:
        await query.message.reply_text("🛑 Данные не найдены.")
        return

    # Проверяем структуру данных
    if isinstance(media_group, dict) and 'media' in media_group:
        media = media_group['media']
    elif isinstance(media_group, list):
        media = media_group
    else:
        await query.message.reply_text("🛑 Некорректный формат данных.")
        return

    # Проверяем индекс
    if not (0 <= index < len(media)):
        await query.message.reply_text("🛑 Ошибка индекса.")
        return

    # Удаляем изображение
    removed_image = media.pop(index)

    # Переносим caption и parse_mode к первому изображению, если удаляется первое
    if index == 0 and media:
        media[0]['caption'] = removed_image.get('caption', '')
        media[0]['parse_mode'] = removed_image.get('parse_mode', None)

    # Сохраняем обновления в Firebase
    if isinstance(media_group_storage[user_id][key], dict):
        media_group_storage[user_id][key]['media'] = media
    else:
        media_group_storage[user_id][key] = media
    save_media_group_data(media_group_storage, user_id)

    # Формируем превью медиагруппы
    media_group_preview = [
        InputMediaPhoto(
            media=item['file_id'],
            caption=item.get('caption', ''),
            parse_mode=item.get('parse_mode', None)
        ) for item in media
    ]

    # Отправляем медиагруппу
    if media_group_preview:
        await context.bot.send_media_group(
            chat_id=query.message.chat_id,
            media=media_group_preview
        )
    else:
        await query.message.reply_text("Медиагруппа пуста. Все изображения удалены.")

    # Формируем ответ с информацией об удалённом изображении
    json_removed_image = json.dumps(removed_image, ensure_ascii=False, indent=4)
    await query.message.reply_text(
        text=f"✅ Изображение успешно удалено и пост обновлен.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Пост ТГ", callback_data=f"publish_{key}"),
                InlineKeyboardButton("Пост ВК", callback_data=f"vkpub_{key}"),
                InlineKeyboardButton("Удалить", callback_data=f"erase_{key}")
            ],
            [
                InlineKeyboardButton("🌠 Предложить этот пост в Анемон 🌠", callback_data=f"share_{key}")
            ],            
            [
                InlineKeyboardButton("🔄 Случайно перемешать 🔄", callback_data=f"shuffle_{key}")
            ],
            [
                InlineKeyboardButton("🎨 Сортировать по палитре 🎨", callback_data=f"palettesort_{key}")
            ],
            [
                InlineKeyboardButton("📔 Сохранить в папку 📔", callback_data=f"snooze_with_tag_{key}")
            ],
            [
                InlineKeyboardButton("Поменять 2 изображения местами", callback_data=f"swapimages_{key}")
            ],
            [
                InlineKeyboardButton("❌ Удалить 1 изображение ❌", callback_data=f"filedelete_{key}")
            ],
            [
                InlineKeyboardButton("🗂 Посмотреть папки 🗂", callback_data="scheduled_by_tag")
            ],      
        ]),
        parse_mode='HTML'
    )









async def handle_view_scheduled(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    MAX_CAPTION_LENGTH = 1024
    # Разделяем callback_data
    if '_' in query.data:
        _, key = query.data.split('_', 1)
    else:
        await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
        return
    
    global media_group_storage
    # Загружаем данные из файла
    media_group_storage = load_publications_from_firebase()
    
    # ID текущего пользователя
    current_user_id = str(update.effective_user.id)
    
    # Проверяем, что данные есть для текущего пользователя
    if current_user_id in media_group_storage:
        user_publications = media_group_storage[current_user_id]
        data = user_publications.get(key)
        if data:
            try:
                # Если данные - это строка, преобразуем в словарь
                if isinstance(data, str):
                    data = json.loads(data)
                
                if isinstance(data, dict) and 'media' in data:
                    media = data['media']
                    media_group = []
                    captions_only = []
                    
                    if isinstance(media, list):
                        for media_data in media:
                            if 'file_id' in media_data:
                                file_id = media_data['file_id']
                                # Проверяем, является ли это URL или file_id
                                if file_id.startswith("http"):
                                    media_type = "url"
                                else:
                                    media_type = "file_id"
                                
                                caption = media_data.get('caption', '')
                                parse_mode = media_data.get('parse_mode', None)
                                
                                # Проверяем длину caption
                                if len(caption) > MAX_CAPTION_LENGTH:
                                    # Если caption слишком длинный, отправляем его отдельно
                                    caption_to_send = ''
                                else:
                                    caption_to_send = caption
                                
                                # Отправляем файл как документ (если это GIF) или фото
                                if file_id.endswith('.gif') or media_type == "url" and file_id.lower().endswith('.gif'):
                                    media_group.append(
                                        InputMediaDocument(
                                            media=file_id,
                                            caption=caption_to_send,
                                            parse_mode=parse_mode
                                        )
                                    )
                                else:
                                    media_group.append(
                                        InputMediaPhoto(
                                            media=file_id,
                                            caption=caption_to_send,
                                            parse_mode=parse_mode
                                        )
                                    )
                            else:
                                if 'caption' in media_data:
                                    captions_only.append(media_data['caption'])

                    elif isinstance(media, dict):
                        for _, media_data in media.items():
                            if 'file_id' in media_data:
                                file_id = media_data['file_id']
                                if file_id.startswith("http"):
                                    media_type = "url"
                                else:
                                    media_type = "file_id"
                                
                                caption = media_data.get('caption', '')
                                parse_mode = media_data.get('parse_mode', None)
                                
                                # Проверяем длину caption
                                if len(caption) > MAX_CAPTION_LENGTH:
                                    # Если caption слишком длинный, отправляем его отдельно
                                    caption_to_send = ''
                                else:
                                    caption_to_send = caption
                                
                                if file_id.endswith('.gif') or media_type == "url" and file_id.lower().endswith('.gif'):
                                    media_group.append(
                                        InputMediaDocument(
                                            media=file_id,
                                            caption=caption_to_send,
                                            parse_mode=parse_mode
                                        )
                                    )
                                else:
                                    media_group.append(
                                        InputMediaPhoto(
                                            media=file_id,
                                            caption=caption_to_send,
                                            parse_mode=parse_mode
                                        )
                                    )
                            else:
                                if 'caption' in media_data:
                                    captions_only.append(media_data['caption'])
                    
                    # Отправка медиа-группы
                    if media_group:
                        await context.bot.send_media_group(
                            chat_id=query.message.chat_id,
                            media=media_group
                        )
                    
                    # Отправка подписей без изображений
                    for caption in captions_only:
                        await query.message.reply_text(
                            text=caption,
                            parse_mode='HTML'
                        )
                    
                    # Отправка caption, если он был слишком длинным
                    for media_data in media:
                        caption = media_data.get('caption', '')
                        if len(caption) > MAX_CAPTION_LENGTH:
                            await query.message.reply_text(
                                text=caption,
                                parse_mode=media_data.get('parse_mode', None)
                            )
                    
                    # Отправляем информацию о записи с кнопками
                    await send_scheduled_post_buttons(query, key, data)
                else:
                    await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
            except json.JSONDecodeError as e:
                await query.message.reply_text(f"🚫 Ошибка преобразования данных: {e}")
        else:
            await query.message.reply_text("🚫 Запись не найдена.")




async def send_scheduled_post_buttons(query, key, data):
    """Отправляет сообщение с кнопками управления публикацией."""
    await query.message.reply_text(
        text=f"Папка: {data.get('scheduled', 'Не указана')}\n\nКоличество медиа в посте: {len(data.get('media', []))}\n\nПри нажатии кнопки \"Редактировать пост\" вы можете отсортировать или удалить изображения, а так же поменять подпись. ",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Пост ТГ", callback_data=f"publish_{key}"),
                InlineKeyboardButton("Пост ВК", callback_data=f"vkpub_{key}"),
                InlineKeyboardButton("Удалить", callback_data=f"yrrasetag_{key}")
            ],
            [
                InlineKeyboardButton("🌠 Предложить этот пост в Анемон 🌠", callback_data=f"share_{key}")
            ],
            [
                InlineKeyboardButton("📝 Редактировать пост 📝", callback_data=f"editpost_{key}")
            ],                
            [
                InlineKeyboardButton("📔 Сменить папку 📔", callback_data=f"snooze_with_tag_{key}")
            ],
            [
                InlineKeyboardButton("🌃 Опубликовать в общую папку 🌃", callback_data=f"sharefromuserpublic_{key}")
            ],
            [
                InlineKeyboardButton("🏙 Общие публикации 🏙", callback_data="view_shared")
            ],
            [
                InlineKeyboardButton("🗂 Посмотреть мои папки 🗂", callback_data="scheduled_by_tag")
            ]
        ])
    )

async def handle_edit_post(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if '_' in query.data:
        _, key = query.data.split('_', 1)
    else:
        await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
        return

    await query.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Случайно перемешать 🔄", callback_data=f"shuffle_{key}")
            ],
            [
                InlineKeyboardButton("🎨 Сортировать по палитре 🎨", callback_data=f"palettesort_{key}")
            ],
            [
                InlineKeyboardButton("Поменять 2 изображения местами", callback_data=f"swapimages_{key}")
            ],
            [
                InlineKeyboardButton("❌ Удалить 1 изображение ❌", callback_data=f"filedelete_{key}")
            ],
            [
                InlineKeyboardButton("✏️ Заменить подпись ✏️", callback_data=f"caption_{key}")
            ],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data=f"backtomain_{key}")
            ]
        ])
    )

async def handle_back_to_main(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    if '_' in query.data:
        _, key = query.data.split('_', 1)
    else:
        await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
        return

    # Загружаем актуальные данные
    media_group_storage = load_publications_from_firebase()
    current_user_id = str(update.effective_user.id)
    if current_user_id in media_group_storage:
        user_publications = media_group_storage[current_user_id]
        data = user_publications.get(key)
        if data:
            # Используем edit_message_text для замены сообщения
            await query.message.edit_text(
                text=f"Папка: {data.get('scheduled', 'Не указана')}\n\nКоличество медиа в посте: {len(data.get('media', []))}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("Пост ТГ", callback_data=f"publish_{key}"),
                        InlineKeyboardButton("Пост ВК", callback_data=f"vkpub_{key}"),
                        InlineKeyboardButton("Удалить", callback_data=f"yrrasetag_{key}")
                    ],
                    [
                        InlineKeyboardButton("🌠 Предложить этот пост в Анемон 🌠", callback_data=f"share_{key}")
                    ],
                    [
                        InlineKeyboardButton("📝 Редактировать пост 📝", callback_data=f"editpost_{key}")
                    ],                   
                    [
                        InlineKeyboardButton("📔 Сменить папку 📔", callback_data=f"snooze_with_tag_{key}")
                    ],
                    [
                        InlineKeyboardButton("🌃 Опубликовать в общем доступе 🌃", callback_data=f"sharefromuserpublic_{key}")
                    ],
                    [
                        InlineKeyboardButton("🏙 Общие публикации 🏙", callback_data="view_shared")
                    ],
                    [
                        InlineKeyboardButton("🗂 Посмотреть мои папки 🗂", callback_data="scheduled_by_tag")
                    ],

                ])
            )
        else:
            await query.message.reply_text("🚫 Запись не найдена.")
    else:
        await query.message.reply_text("🚫 Пользователь не найден в базе данных.")




import random

async def handle_shuffle_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Ответ пользователю, что нажатие обработано

    # Проверяем формат callback_data
    if query and query.data.startswith("shuffle_"):
        data_parts = query.data.split('_', 1)
        key = data_parts[1] if len(data_parts) > 1 else None
    else:
        await query.message.reply_text("\u274c Ошибка: Некорректный формат данных.")
        return

    global media_group_storage
    # Загружаем данные из Firebase
    media_group_storage = load_publications_from_firebase()

    # Проверяем наличие ключа в хранилище
    user_id, user_message = key.split('_', 1) if '_' in key else (None, None)
    if user_id in media_group_storage:
        user_publications = media_group_storage[user_id]

        if key in user_publications:
            media_group = user_publications[key]

            # Проверяем структуру media_group
            if isinstance(media_group, dict) and 'media' in media_group:
                media = media_group['media']
            else:
                await query.message.reply_text("\u274c Некорректный формат данных.")
                return

            if not isinstance(media, list) or len(media) < 1:
                await query.message.reply_text("\u274c Нет изображений для перемешивания.")
                return

            # Сохраняем caption и parse_mode первого элемента
            first_caption = media[0].get('caption')
            first_parse_mode = media[0].get('parse_mode')

            # Перемешиваем media
            random.shuffle(media)

            # Устанавливаем сохранённые caption и parse_mode для первого элемента
            media[0]['caption'] = first_caption
            media[0]['parse_mode'] = first_parse_mode

            # Сбрасываем caption и parse_mode у остальных
            for item in media[1:]:
                item['caption'] = None
                item['parse_mode'] = None

            # Создаём медиагруппу для отправки
            media_group = [
                InputMediaPhoto(
                    media=item['file_id'],
                    caption=item.get('caption', ''),
                    parse_mode=item.get('parse_mode')
                ) for item in media if 'file_id' in item
            ]

            # Отправляем медиагруппу пользователю
            if media_group:
                await context.bot.send_media_group(
                    chat_id=query.message.chat_id,
                    media=media_group
                )

            # Обновляем данные в хранилище
            media_group_storage[user_id][key]['media'] = media
            save_media_group_data(media_group_storage, user_id)

            # Отправляем сообщение с кнопками
            await query.message.reply_text(
                text=f"🔄 Изображения перемешаны:\n\nКоличество медиа: {len(media)}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("Пост ТГ", callback_data=f"publish_{key}"),
                        InlineKeyboardButton("Пост ВК", callback_data=f"vkpub_{key}"),
                        InlineKeyboardButton("Удалить", callback_data=f"erase_{key}")
                    ],
                    [
                        InlineKeyboardButton("🌠 Предложить этот пост в Анемон 🌠", callback_data=f"share_{key}")
                    ],                    
                    [
                        InlineKeyboardButton("🔄 Случайно перемешать ещё раз 🔄", callback_data=f"shuffle_{key}")
                    ],
                    [
                        InlineKeyboardButton("🎨 Сортировать по палитре 🎨", callback_data=f"palettesort_{key}")
                    ],
                    [
                        InlineKeyboardButton("📔 Сохранить в папку 📔", callback_data=f"snooze_with_tag_{key}")
                    ],                                                    
                    [
                        InlineKeyboardButton("Поменять 2 изображения местами", callback_data=f"swapimages_{key}")
                    ],
                    [
                        InlineKeyboardButton("❌ Удалить 1 изображение ❌", callback_data=f"filedelete_{key}")
                    ],
                    [
                        InlineKeyboardButton("🗂 Посмотреть папки 🗂", callback_data="scheduled_by_tag")
                    ],                                                
                ])
            )
        else:
            await query.message.reply_text("🚫 Ошибка: 'media' не найдено или некорректного формата.")

    else:
        await query.message.reply_text("🚫 Запись не найдена.")

import requests
from PIL import Image
from io import BytesIO
import numpy as np
from colorsys import rgb_to_hsv





async def download_image(session, url):
    async with session.get(url) as response:
        if response.status == 200:
            data = await response.read()
            return Image.open(BytesIO(data))
        else:
            raise Exception(f"Failed to download image: {url}")

async def download_images(image_urls):
    async with aiohttp.ClientSession() as session:
        tasks = [download_image(session, url) for url in image_urls]
        return await asyncio.gather(*tasks)
    






SORT_OPTIONS = [
    ("`🖤-Тёмный       `", "dark"),
    ("`🤍-Светлый      `", "light"),
    ("`🌈-Насыщенные    `", "saturated"),
    ("`🩶-Серые         `", "desaturated"),
    ("`❤️-Красный       `", "red"),
    ("`🧡-Оранжевый     `", "orange"),
    ("`💛-Жёлтый        `", "yellow"),
    ("`💚-Зелёный       `", "green"),
    ("`🩵-Голубой       `", "cyan"),
    ("`💙-Синий         `", "blue"),
    ("`💜-Фиолетовый    `", "purple"),
    ("`От тёплых к холодным`", "warm")
]



def analyze_image_colors(image, criterion):
    """
    Анализирует изображение и возвращает:
    - Процентное соотношение темных, средних и ярких пикселей.
    - Процентное соотношение серых, средней насыщенности и насыщенных пикселей.
    - Процентное соотношение основных цветов (красный, оранжевый, желтый, зеленый, голубой, синий, фиолетовый).
    """
    # Преобразуем изображение в RGB, изменяем размер для ускорения обработки
    img = image.convert('RGB').resize((50, 50))
    
    # Преобразуем изображение в массив numpy
    arr = np.array(img).reshape(-1, 3)
    
    # Конвертируем пиксели из RGB в HSV
    hsv_pixels = [rgb_to_hsv(r / 255, g / 255, b / 255) for r, g, b in arr]

    total_pixels = len(hsv_pixels)

    # Анализ яркости
    brightness = [v for _, _, v in hsv_pixels]
    dark_pixels = sum(1 for v in brightness if v < 0.33)
    medium_pixels = sum(1 for v in brightness if 0.33 <= v < 0.75)
    bright_pixels = sum(1 for v in brightness if v >= 0.75)
    total_brightness = sum(brightness) / len(brightness)  # Средняя яркость
    total_bright = 1 - total_brightness  # Инвертируем для диапазона от 0 (ярко) до 1 (темно)

    brightness_distribution = {
        "dark": dark_pixels / total_pixels,
        "medium": medium_pixels / total_pixels,
        "bright": bright_pixels / total_pixels,
        "total_bright": total_bright
    }

    # Анализ насыщенности
    saturation = [s for _, s, _ in hsv_pixels]
    gray_pixels = sum(1 for s in saturation if s < 0.3)
    medium_saturation_pixels = sum(1 for s in saturation if 0.3 <= s < 0.75)
    high_saturation_pixels = sum(1 for s in saturation if s >= 0.75)

    saturation_distribution = {
        "gray": gray_pixels / total_pixels,
        "medium": medium_saturation_pixels / total_pixels,
        "high": high_saturation_pixels / total_pixels,
    }

    # Анализ оттенков
    hue_distribution = {
        "red": [0, 0, 0, 0, 0, 0],  # [hv, mv, lv, hs, ms, ls]
        "orange": [0, 0, 0, 0, 0, 0],
        "yellow": [0, 0, 0, 0, 0, 0],
        "green": [0, 0, 0, 0, 0, 0],
        "cyan": [0, 0, 0, 0, 0, 0],
        "blue": [0, 0, 0, 0, 0, 0],
        "purple": [0, 0, 0, 0, 0, 0],
    }
    color_boundaries = {
        "red": (350 / 360, 10 / 360),
        "orange": (10/ 360, 40 / 360),
        "yellow": (40 / 360, 60 / 360),  # Верхняя граница для жёлтого = 100°
        "green": (60 / 360, 160 / 360),  # Нижняя граница для зелёного = 100°
        "cyan": (160 / 360, 190 / 360),
        "blue": (190 / 360, 250 / 360),
        "purple": (250 / 360, 350 / 360),
    }

    overlap_margin = 10 / 360  # Граница перекрытия в градусах (5°)

    for h, s, v in hsv_pixels:
        for color, (lower, upper) in color_boundaries.items():
            is_in_range = lower <= h < upper or (lower > upper and (h >= lower or h < upper))
            is_in_overlap = (lower - overlap_margin <= h < lower) or (upper <= h < upper + overlap_margin)

            if is_in_range or is_in_overlap:
                index = 0 if v >= 0.66 else 1 if v >= 0.33 else 2
                hue_distribution[color][index] += 1

                sat_index = 3 if s >= 0.5 else 4 if s >= 0.2 else 5
                hue_distribution[color][sat_index] += 1

    hue_distribution = {
        color: {
            "hv": round(100 * hv / total_pixels, 2),
            "mv": round(100 * mv / total_pixels, 2),
            "lv": round(100 * lv / total_pixels, 2),
            "hs": round(100 * hs / total_pixels, 2),
            "ms": round(100 * ms / total_pixels, 2),
            "ls": round(100 * ls / total_pixels, 2),
        }
        for color, (hv, mv, lv, hs, ms, ls) in hue_distribution.items()
    }

    # Расчёт веса
    for color, data in hue_distribution.items():
        # Логируем интересующие значения
        brightness_weight = (
            -3.0 * brightness_distribution["dark"] +
            2.0 * brightness_distribution["medium"] +
            0.5 * brightness_distribution["bright"]
        )
        saturation_weight = (
            -3.0 * saturation_distribution["gray"] +
            1.0 * saturation_distribution["medium"] +
            3.0 * saturation_distribution["high"]
        )
        if brightness_distribution["bright"] > 0.8:
            saturation_weight += 1.5 * saturation_distribution["gray"]
            data["ls"], data["ms"] = -0.2 * data["ls"], 3.0 * data["ms"]
        if saturation_distribution["gray"] > 0.85:
            if brightness_distribution["dark"] > 0.3 and brightness_distribution["bright"] < 0.7:
                data["hs"], data["ms"], data["ls"] = (
                    16.0 * data["hs"],
                    15.0 * data["ms"],
                    0.5 * data["ls"]
                )
        data["tw"] = round(max(0, (
            5.0 * data["hs"] + 3.0 * data["ms"] - data["ls"] +
            2 * data["mv"] - 2 * data["lv"] +
            10.0 * (brightness_weight + saturation_weight)
        )), 2)

    # Проверка, если все значения tw равны 0
    # Проверка, если все значения tw равны 0
    if all(data["tw"] == 0 for data in hue_distribution.values()):
        for color, data in hue_distribution.items():
            # Собираем значения hs, ms, ls
            values = [data["hs"], data["ms"], data["ls"]]
            
            # Проверяем наличие положительных значений
            positive_values = [v for v in values if v > 0]
            
            if positive_values:
                # Если есть положительные значения, берём максимальное из них
                data["tw"] = max(positive_values)
            else:
                # Если все значения отрицательные, берём наименьшее по модулю (наибольшее отрицательное) и делаем его положительным
                data["tw"] = abs(min(values))

    return brightness_distribution, saturation_distribution, hue_distribution

def hue_finele(hue_distribution, criterion):
    """
    Вычисляет итоговый оттенок (hue) изображения на основе данных распределения оттенков.

    :param hue_distribution: Словарь с данными о распределении оттенков.
    :param criterion: Критерий, к которому будет ближе финальный оттенок.
    :return: Финальное значение оттенка (hue) изображения.
    """
    # Отбираем топ-3 цвета по значению tw
    top_colors = sorted(
        ((color, data["tw"]) for color, data in hue_distribution.items() if data["tw"] > 0),
        key=lambda x: x[1],
        reverse=True
    )[:3]


    if len(top_colors) < 1:
        return None  # Если нет данных о цветах, возвращаем None

    # Определение hue для каждого цвета
    hue_positions = {
        "red": 0,
        "orange": 30,
        "yellow": 60,
        "green": 130,
        "cyan": 180,
        "blue": 230,
        "purple": 280
    }

    # Проверка и обработка criterion
    if criterion in ["dark", "light"]:

        hue_criterion = None  # Устанавливаем в None, чтобы избежать ошибок
    elif criterion in ["saturated", "desaturated", "warm"]:

        hue_criterion = hue_positions["red"]
    else:
        if criterion not in hue_positions:
            raise ValueError(f"🚫 Неверный критерий сортировки: {criterion}")
        hue_criterion = hue_positions[criterion]


    # Проверяем разницу между первыми двумя цветами
    if hue_criterion is not None and len(top_colors) > 1 and (
        abs(top_colors[0][1] - top_colors[1][1]) <= 20 or top_colors[1][1] > 150
    ):
        # Определяем ближайший к hue_criterion
        color1, value1 = top_colors[0]
        color2, value2 = top_colors[1]
        hue1 = hue_positions[color1]
        hue2 = hue_positions[color2]

        # Вычисляем расстояния до hue_criterion
        dist1 = abs((hue1 - hue_criterion) % 360)
        dist2 = abs((hue2 - hue_criterion) % 360)
        if dist1 > 180:
            dist1 = 360 - dist1
        if dist2 > 180:
            dist2 = 360 - dist2

        # Определяем базовый цвет по близости к hue_criterion
        if dist1 <= dist2:
            base_color, base_value = color1, value1
            secondary_color = (color2, value2)
        else:
            base_color, base_value = color2, value2
            secondary_color = (color1, value1)

        # Перемещаем второй цвет в логику обработки дополнительных цветов
        additional_colors = [secondary_color] + top_colors[2:]
    else:
        base_color, base_value = top_colors[0]
        additional_colors = top_colors[1:]

    base_hue = hue_positions[base_color]

    # Учитываем вес базового цвета на основе значения tw
    base_weight = base_value / 1000  # Нормализуем вес в диапазоне [0, 1]


    # Обработка дополнительных цветов
    adjustments = []
    for color, value in additional_colors:
        if color in hue_positions:
            delta_hue = (hue_positions[color] - base_hue) % 360
            if delta_hue > 180:
                delta_hue -= 360  # Приведение к диапазону [-180, 180]

            # Определяем делитель для расчёта shift_degree
            divisor = 100 if value > base_value + 100 else 10

            # Рассчитываем градус смещения с учетом tw
            shift_degree = (value / divisor) * (1 - base_weight * 0.35)  # Вес базового цвета уменьшает влияние других цветов
            adjustments.append((delta_hue, shift_degree))

    # Если оба смещения направлены в одну сторону, учитываем только первое
    if len(adjustments) > 1:
        if all(adj[0] > 0 for adj in adjustments) or all(adj[0] < 0 for adj in adjustments):
            adjustments = [max(adjustments, key=lambda x: abs(x[1]))]

    # Применяем корректировку
    final_hue_adjustment = sum(delta * (weight / abs(delta)) for delta, weight in adjustments)
    final_hue = (base_hue + final_hue_adjustment) % 360
    return round(final_hue, 2)






import math

def calculate_normalized_brightness(brightness_distribution, saturation_distribution):
    # Веса для распределений яркости
    brightness_weights = {
        "dark": 0.3,       # Уменьшаем итоговое значение
        "medium": 0.2,      # Нейтральное влияние
        "bright": -0.1      # Увеличиваем итоговое значение
    }
    # Веса для распределений насыщенности
    saturation_weights = {
        "gray": -0.1,        # Увеличиваем итоговое значение (считаем серость ярче)
        "medium": 0.2,      # Нейтральное влияние
        "high": 0.3        # Уменьшаем итоговое значение (высокая насыщенность воспринимается темнее)
    }

    # Рассчитываем взвешенную сумму яркости
    weighted_brightness = sum(
        brightness_distribution[key] * weight
        for key, weight in brightness_weights.items()
    )
    # Рассчитываем взвешенную сумму насыщенности
    weighted_saturation = sum(
        saturation_distribution[key] * weight
        for key, weight in saturation_weights.items()
    )

    # Сумма всех весов
    total_weights_sum = sum(brightness_weights.values()) + sum(saturation_weights.values())

    # Итоговая нормализованная яркость
    raw_brightness = (brightness_distribution["total_bright"] + weighted_brightness + weighted_saturation) * total_weights_sum

    # Применяем логистическую функцию для экспоненциальной нормализации
    def logistic_function(x):
        return 1 / (1 + math.exp(-x))

    # Ограничиваем значение в пределах от 0 до 1
    normalized_brightness = logistic_function(raw_brightness)
    normalized_brightness = max(0, min(1, normalized_brightness))

    return normalized_brightness



# Сортирует изображения по яркости
async def sort_images_by_priority(media, criterion):
    """
    Сортирует изображения по яркости: от светлого к тёмному (light) или наоборот (dark).
    """
    # Подготовка списка URL
    image_urls = [item['file_id'] for item in media if 'file_id' in item]

    # Скачивание изображений асинхронно
    try:
        downloaded_images = await download_images(image_urls)  # Используем await здесь
    except Exception as e:
        raise RuntimeError(f"Error downloading images: {e}")

    # Анализируем изображения и определяем hue для каждого
    analyzed_images = []

    for item, image in zip(media, downloaded_images):
        if image is not None:
            brightness_distribution, saturation_distribution, hue_distribution = analyze_image_colors(image, criterion)


            top_colors = sorted(
                ((color, data["tw"]) for color, data in hue_distribution.items() if data["tw"] > 0),
                key=lambda x: x[1],
                reverse=True
            )[:3]


            color_weights = {
                'yellow': -0.02,
                'blue': 0.01,
                'green': -0.003,
                'cyan': -0.005,
                'red': 0.002,
                'purple': 0.005,
                'orange': -0.007
            }


            brightness_distribution, saturation_distribution, _ = analyze_image_colors(image, criterion)
            normalized_brightness = calculate_normalized_brightness(
                brightness_distribution, saturation_distribution
            )
          
            # Корректировка по цветам
            color_adjustment = 0
            total_weight = sum(weight for _, weight in top_colors)
            for color, weight in top_colors:
                if color in color_weights:
                    influence = color_weights[color] * (weight / total_weight)
                    color_adjustment += influence

            # Ограничение влияния цветов на диапазон [-0.2, +0.2]
            color_adjustment = max(min(color_adjustment, 0.2), -0.2)

            # Влияние серых пикселей
            gray_ratio = saturation_distribution['gray']
            middle_ratio = saturation_distribution['medium']
            if (gray_ratio > 0.85 or middle_ratio > 0.8) and brightness_distribution['bright'] > 0.85:
                # Если много серых пикселей или средняя насыщенность при высокой яркости, усиливаем яркость
                color_adjustment *= (1 - gray_ratio)  # Уменьшаем влияние цветовой корректировки
                normalized_brightness += 0.2 * gray_ratio  # Усиливаем базовую яркость

            # Итоговая яркость
            finale_brightness = max(min(normalized_brightness + color_adjustment, 1), 0)

            if criterion == 'light':
                # Обратная сортировка для 'dark'
                finale_brightness = 1 - finale_brightness


            # Добавляем данные изображения и его итоговую яркость
            analyzed_images.append((item, finale_brightness))

    # Сортировка по убыванию итоговой яркости
    sorted_images = sorted(analyzed_images, key=lambda x: x[1], reverse=True)

    return [item[0] for item in sorted_images]






# сортировка по цветам
async def sort_images_by_hue(media, criterion):
    """
    Сортирует изображения по оттенкам (hue), используя критерий для начального порядка.
    
    :param media: Список словарей с медиа-данными, включая URL изображений.
    :param criterion: Критерий цвета для первого изображения (например, 'red', 'blue', и т.д.).
    :return: Список отсортированных идентификаторов файлов.
    """
    # Подготовка списка URL
    image_urls = [item['file_id'] for item in media if 'file_id' in item]

    # Скачивание изображений асинхронно
    try:
        downloaded_images = await download_images(image_urls)  # Используем await здесь
    except Exception as e:
        raise RuntimeError(f"Error downloading images: {e}")
    
    # Анализируем изображения и определяем hue для каждого
    analyzed_images = []
    for item, image in zip(media, downloaded_images):
        if image is not None:
            hue_distribution = analyze_image_colors(image, criterion)[2]  # Передаем Image напрямую
            final_hue = hue_finele(hue_distribution, criterion)
            if final_hue is not None:
                analyzed_images.append((item, final_hue))


    # Проверка результатов анализа
    if not analyzed_images:
        raise ValueError("🚫 Hue-анализ изображений не дал результатов.")

    # Определяем начальный hue для сортировки на основе критерия
    hue_positions = {
        "red": 0,
        "orange": 30,
        "yellow": 60,
        "green": 130,
        "cyan": 180,
        "blue": 230,
        "purple": 280
    }
    if criterion not in hue_positions:
        raise ValueError(f"🚫 Неверный критерий сортировки: {criterion}")
    
    base_hue = hue_positions[criterion]

    # Функция сортировки по разнице углов
    # Функция для расчёта абсолютной разницы углов
    def hue_distance(hue1, hue2):
        return min(abs(hue1 - hue2), 360 - abs(hue1 - hue2))

    # Находим ближайшее изображение к base_hue
    closest_image = min(analyzed_images, key=lambda img: hue_distance(img[1], base_hue))
    sorted_images = [closest_image]  # Начинаем с ближайшего изображения

    # Удаляем ближайшее изображение из списка
    remaining_images = [img for img in analyzed_images if img != closest_image]

    # Будем добавлять следующее изображение, которое будет ближе всего к последнему selected final_hue
    last_hue = closest_image[1]

    while remaining_images:
        # Выбираем следующее изображение, которое наиболее близко к последнему выбранному final_hue
        next_image = min(remaining_images, key=lambda img: hue_distance(img[1], last_hue))
        sorted_images.append(next_image)
        
        # Обновляем последний выбранный hue
        last_hue = next_image[1]
        
        # Убираем это изображение из оставшихся
        remaining_images = [img for img in remaining_images if img != next_image]

    # Возвращаем отсортированные идентификаторы файлов
    return [item[0] for item in sorted_images]


import math
def gaussian_weight(hue, target, sigma):
    return math.exp(-((hue - target) ** 2) / (2 * sigma ** 2))
# сортировка по насыщенности
async def sort_images_by_color_priority(media, criterion):
    """
    Сортирует изображения по насыщенности: от насыщенного и светлого к тёмному (light) или наоборот (dark).
    """
    # Подготовка списка URL
    image_urls = [item['file_id'] for item in media if 'file_id' in item]

    # Скачивание изображений асинхронно
    try:
        downloaded_images = await download_images(image_urls)  # Используем await здесь
    except Exception as e:
        raise RuntimeError(f"Error downloading images: {e}")

    # Анализируем изображения и определяем насыщенность для каждого
    analyzed_images = []

    for item, image in zip(media, downloaded_images):
        if image is not None:
            # Анализ изображения
            brightness_distribution, saturation_distribution, hue_distribution = analyze_image_colors(image, criterion)
            final_hue = hue_finele(hue_distribution, criterion)



            # Вычисляем averaged_saturation
            gray_weight = -0.8  # Серым придаём больший вес
            medium_weight = 4.4  # Средние пиксели имеют меньший вес
            high_weight = 10.7  # Насыщенные пиксели имеют больший вес

            brightness_boost_factor = brightness_distribution['bright']  # Используем яркость напрямую
            if brightness_boost_factor > 0:
                medium_weight *= 1.5 + brightness_boost_factor 
                high_weight *= 2 + brightness_boost_factor 
            else:
                # Для низкой яркости можно оставить исходные значения или уменьшить веса
                medium_weight *= 0.9
                high_weight *= 0.9
                       
            averaged_saturation = (
                saturation_distribution['gray'] * gray_weight +
                saturation_distribution['medium'] * medium_weight +
                saturation_distribution['high'] * high_weight
            ) / (gray_weight + medium_weight + high_weight)

            # Корректируем averaged_saturation в зависимости от яркости
            bright_boost = 1.2  # Усиление при ярких пикселях
            middle_boost = 1.1  # Усиление при средних пикселях            
            dark_damp = 0.1  # Ослабление при тёмных пикселях

            # Дополнительный коэффициент нелинейного ослабления для "dark"
            dark_penalty_scale = 2.0  # Множитель для усиления влияния высокой "dark"
            dark_adjustment = brightness_distribution['dark'] ** dark_penalty_scale

            brightness_factor = ((
                brightness_distribution['bright'] * bright_boost +
                brightness_distribution['medium'] * middle_boost +
                brightness_distribution['dark'] * (1 - dark_damp) -
                dark_adjustment  # Учитываем нелинейное влияние "dark"
            ) / (bright_boost + middle_boost + dark_damp)) - (
                ((brightness_distribution['bright'] * 2) + brightness_distribution['medium'] + brightness_distribution['dark']) / 6.5
            )


            # Суммируем значения для учета их в одной переменной
            combined_value = (saturation_distribution['gray']) + (brightness_distribution['dark']) - (saturation_distribution['medium'] / 2) - (saturation_distribution['high'] / 2) 

            # Используем сдвиг для того, чтобы снижение начиналось при значении примерно 1
            shift_start = 1  # Начало сильного сдвига
            shift_factor = 4  # Сила сдвига, можно настроить            
            final_brightness_factor = brightness_factor / (1 + math.exp((combined_value - shift_start) * shift_factor))
            # Ограничиваем итоговую насыщенность в пределах [0, 1]
         
            averaged_saturation = max(0, min(1, averaged_saturation + final_brightness_factor))


            # Усиление для теплых и холодных оттенков
            warm_hue_boost = 0.04
            cold_hue_damp = 0.04
            max_adjustment = 0.1

            # Стандартное отклонение для гауссовой функции (ширина изменения)
            sigma = 30  # Чем меньше значение, тем резче спад влияния

            # Рассчитываем вес в зависимости от final_hue
            if (0 <= final_hue <= 140) or (330 <= final_hue <= 360):  # Тёплые оттенки
                weight_90 = gaussian_weight(final_hue, 90, sigma) if final_hue <= 140 else 0
                weight_350 = gaussian_weight(final_hue, 350, sigma) if final_hue >= 330 else 0
                weight = max(weight_90, weight_350)  # Выбираем наибольшее влияние
                adjustment = warm_hue_boost * weight
                finale_Saturation = averaged_saturation + min(max_adjustment, adjustment)

            elif 140 < final_hue < 330:  # Холодные оттенки
                weight = gaussian_weight(final_hue, 240, sigma)
                adjustment = cold_hue_damp * weight
                finale_Saturation = averaged_saturation - min(max_adjustment, adjustment)

            else:  # Предохранитель для значений вне диапазона
                finale_Saturation = averaged_saturation

            # Ограничиваем значение finale_Saturation в пределах допустимого диапазона
            finale_Saturation = max(0, min(1, finale_Saturation))

            # Ограничиваем результат в пределах [0, 1]
            finale_Saturation = max(0, min(1, finale_Saturation))  

            if criterion == 'desaturated':
                # Обратная сортировка для 'dark'
                finale_Saturation = 1 - finale_Saturation
            # Добавляем данные изображения и его итоговую насыщенность
            analyzed_images.append((item, finale_Saturation))

    # Сортировка по убыванию итоговой насыщенности
    sorted_images = sorted(analyzed_images, key=lambda x: x[1], reverse=True)

    return [item[0] for item in sorted_images]





# сортировка по теплоте
async def sort_images_by_warm(media, criterion):
    image_urls = [item['file_id'] for item in media if 'file_id' in item]

    try:
        downloaded_images = await download_images(image_urls)
    except Exception as e:
        raise RuntimeError(f"Error downloading images: {e}")

    analyzed_images = []

    for item, image in zip(media, downloaded_images):
        if image is not None:
            # Анализ изображения
            brightness_distribution, saturation_distribution, hue_distribution = analyze_image_colors(image, criterion)

            # Нормализация
            normalized_brightness = (
                0.2 * brightness_distribution['dark'] +
                0.5 * brightness_distribution['medium'] +
                0.8 * brightness_distribution['bright']
            )

            normalized_saturation = (
                0.1 * saturation_distribution['gray'] +
                0.6 * saturation_distribution['medium'] +
                0.9 * saturation_distribution['high']
            )

            warm_colors = ['red', 'orange', 'yellow']
            cold_colors = ['green', 'cyan', 'blue', 'purple']

            warm_tw = sum(hue_distribution[color]['tw'] for color in warm_colors)
            cold_tw = sum(hue_distribution[color]['tw'] for color in cold_colors)
            total_tw = sum(hue_distribution[color]['tw'] for color in hue_distribution)

            final_warm = (warm_tw - cold_tw) / total_tw if total_tw > 0 else 0

            # Итоговая метрика
            score = (
                0.6 * final_warm +  # Влияние цветов
                0.3 * normalized_brightness +  # Влияние яркости
                0.1 * (1 - normalized_saturation)  # Влияние насыщенности
            )

            analyzed_images.append((item, score))

    # Сортировка по убыванию итогового score
    sorted_images = sorted(analyzed_images, key=lambda x: x[1], reverse=True)

    return [item[0] for item in sorted_images]







async def handle_palettesort(update, context):
    query = update.callback_query
    await query.answer()

    # Проверяем формат callback_data
    if query.data and '_' in query.data:
        _, user_id, user_message = query.data.split('_', 2)
        key = f"{user_id}_{user_message}"
    else:
        await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
        return


    global media_group_storage
    # Загружаем данные из Firebase
    media_group_storage = load_publications_from_firebase()

    if user_id in media_group_storage and key in media_group_storage[user_id]:
        data = media_group_storage[user_id][key]

        # Предлагаем выбор начального критерия сортировки
        buttons = [[InlineKeyboardButton(label, callback_data=f"sort_{user_id}_{user_message}_{option}")]
                   for label, option in SORT_OPTIONS]
        await query.message.reply_text(
            "Выберите желаемый цвет первого изображения для сортировки:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await query.message.reply_text("🚫 Запись не найдена.")


async def handle_palettesort(update, context):
    query = update.callback_query
    await query.answer()

    # Проверяем формат callback_data
    if query.data and '_' in query.data:
        _, user_id, user_message = query.data.split('_', 2)
        key = f"{user_id}_{user_message}"
    else:
        await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
        return



    # Загружаем данные из Firebase
    global media_group_storage
    media_group_storage = load_publications_from_firebase()

    if user_id in media_group_storage and key in media_group_storage[user_id]:
        data = media_group_storage[user_id][key]

        # Предлагаем выбор начального критерия сортировки
        buttons = [[InlineKeyboardButton(label, callback_data=f"sort_{user_id}_{user_message}_{option}")]
                   for label, option in SORT_OPTIONS]
        await query.message.reply_text(
            "Выберите желаемый цвет первого изображения для сортировки:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await query.message.reply_text("🚫 Запись не найдена.")


async def sort_by_criteria(update, context):
    query = update.callback_query
    await query.answer()

    # Проверяем формат callback_data
    if query.data and '_' in query.data:
        parts = query.data.split('_')
        if len(parts) >= 4:
            _, user_id, user_message, criterion = parts[0], parts[1], '_'.join(parts[2:-1]), parts[-1]
            key = f"{user_id}_{user_message}"
        else:
            await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
            return
    else:
        await query.message.reply_text("🚫 Ошибка: Некорректный формат данных.")
        return



    global media_group_storage
    media_group_storage = load_publications_from_firebase()

    if user_id in media_group_storage and key in media_group_storage[user_id]:
        data = media_group_storage[user_id][key]

        try:
            if isinstance(data, str):
                data = json.loads(data)

            media = None
            if isinstance(data, list):
                media = data
            elif isinstance(data, dict) and 'media' in data:
                media = data['media']

            if media and isinstance(media, list):
                # Отправка сообщения о начале сортировки
                progress_message = await query.message.reply_text(
                    text=f"Сортировка начата. Выбранный критерий: {criterion.capitalize()}\n\n"
                )

                # Сортировка всего списка media
                if criterion in {"dark", "light"}:
                    sorted_media = await sort_images_by_priority(media, criterion)
                elif criterion in {"saturated", "desaturated"}:
                    sorted_media = await sort_images_by_color_priority(media, criterion)
                elif criterion == "warm":
                    sorted_media = await sort_images_by_warm(media, criterion)
                else:
                    sorted_media = await sort_images_by_hue(media, criterion)

                # Завершение обновления прогресса

                # Остальная логика остаётся прежней
                first_caption = media[0].get('caption')
                first_parse_mode = media[0].get('parse_mode')

                sorted_media[0]['caption'] = first_caption
                sorted_media[0]['parse_mode'] = first_parse_mode

                for item in sorted_media[1:]:
                    item['caption'] = None
                    item['parse_mode'] = None

                media_group = [
                    InputMediaPhoto(
                        media=item['file_id'],
                        caption=item.get('caption', ''),
                        parse_mode=item.get('parse_mode', None)
                    ) for item in sorted_media if 'file_id' in item
                ]

                if media_group:
                    await context.bot.send_media_group(
                        chat_id=query.message.chat_id,
                        media=media_group
                    )

                # Сохраняем данные с учетом их типа
                if isinstance(data, list):
                    media_group_storage[user_id][key] = {"media": sorted_media}
                else:
                    data['media'] = sorted_media
                    media_group_storage[user_id][key] = data  # Сохраняем остальные поля

                save_media_group_data(media_group_storage, user_id)

                await query.message.reply_text(
                    text=f"✅ Изображения отсортированы:\n\nКритерий: {criterion}, Количество медиа: {len(sorted_media)}",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("Пост ТГ", callback_data=f"publish_{key}"),
                            InlineKeyboardButton("Пост ВК", callback_data=f"vkpub_{key}"),
                            InlineKeyboardButton("Удалить", callback_data=f"erase_{key}")
                        ],
                        [
                            InlineKeyboardButton("🌠 Предложить этот пост в Анемон 🌠", callback_data=f"share_{key}")
                        ],                        
                        [
                            InlineKeyboardButton("🔄 Случайно перемешать 🔄", callback_data=f"shuffle_{key}")
                        ],
                        [
                            InlineKeyboardButton("🎨 Сортировать по палитре 🎨", callback_data=f"palettesort_{key}")
                        ],
                        [
                            InlineKeyboardButton("📔 Сохранить в папку 📔", callback_data=f"snooze_with_tag_{key}")
                        ],                                                          
                        [
                            InlineKeyboardButton("Поменять 2 изображения местами", callback_data=f"swapimages_{key}")
                        ],
                        [
                            InlineKeyboardButton("❌ Удалить 1 изображение ❌", callback_data=f"filedelete_{key}")
                        ],
                        [
                            InlineKeyboardButton("🗂 Посмотреть папки 🗂", callback_data="scheduled_by_tag")
                        ],                            
                    ])
                )
            else:
                await query.message.reply_text("🚫 Ошибка: 'media' не найдено или некорректного формата.")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            await query.message.reply_text(f"🚫 Ошибка обработки данных: {e}")
    else:
        await query.message.reply_text("🚫 Запись не найдена.")



import requests
from vk_api import VkApi
from vk_api.utils import get_random_id






def extract_text_before_first_link(caption: str) -> str:
    """
    Извлекает текст из подписи до первой гиперссылки и удаляет указанные HTML-теги,
    оставляя их содержимое.
    """
    # Удаляем указанные HTML-теги, оставляя их содержимое
    tags_to_remove = [
        r"</?b>",                       # <b> и </b>
        r"</?i>",                       # <i> и </i>
        r"</?u>",                       # <u> и </u>
        r"</?s>",                       # <s> и </s>
        r"</?span\s+class=\"tg-spoiler\">",  # <span class="tg-spoiler"> и </span>
        r"</?code>",                    # <code> и </code>
    ]
    
    # Объединяем паттерны в одно регулярное выражение
    combined_pattern = "|".join(tags_to_remove)
    
    # Удаляем указанные теги, оставляя их содержимое
    cleaned_caption = re.sub(combined_pattern, "", caption, flags=re.DOTALL)
    
    # Извлекаем текст до первой гиперссылки
    match = re.split(r'<a\s+href="[^"]+">', cleaned_caption, maxsplit=1)
    
    if match:
        return match[0].strip()  # Возвращаем текст до первого <a>, удаляя лишние пробелы
    return caption  # Если ссылки нет, возвращаем оригинальную подпись
def format_caption_for_vk(caption: str) -> str:
    """
    Форматирует caption для публикации в VK.
    1. Удаляет ссылки на Telegraph.
    2. Упорядочивает ссылки в формате:
       Ссылки:
       • название - ссылка
    3. Если ссылки отсутствуют или остался только текст, возвращает его без изменений.
    """

    # Удаляем ссылки на Telegraph
    caption = re.sub(r'<a\s+href="https://telegra.ph/[^"]+">[^<]+</a>', '', caption)

    # Извлекаем все ссылки
    links = re.findall(r'<a\s+href="([^"]+)">([^<]+)</a>', caption)
    
    # Формируем текст для ссылок, исключая пустые или некорректные ссылки
    links_text = ""
    if links:
        valid_links = [f"• {text.strip()} - {url.strip()}" for url, text in links if text.strip() and url.strip()]
        if valid_links:
            links_text = "Ссылки:\n" + "\n".join(valid_links)

    # Убираем ссылки из текста
    caption_without_links = re.sub(r'<a\s+href="[^"]+">[^<]+</a>', '', caption).strip()

    # Удаляем лишние символы "•", оставшиеся без текста
    caption_without_links = re.sub(r'\s*•\s*', ' ', caption_without_links).strip()

    # Если нет ссылок и остался только текст, вернуть его
    if not links_text:
        return caption_without_links.strip()

    # Формируем итоговый caption
    formatted_caption = caption_without_links.strip()
    if formatted_caption:
        formatted_caption += "\n\n"  # Добавляем отступ перед "Ссылки:"
    formatted_caption += links_text

    # Убираем лишние пустые строки
    formatted_caption = re.sub(r'\n\s*\n', '\n', formatted_caption).strip()

    return formatted_caption
    


async def handle_vk_keys_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    message_text = update.message.text

    try:
        # Ожидается формат: <owner_id> <token>
        owner_id, token = map(str.strip, message_text.split(maxsplit=1))
        save_vk_keys_to_firebase(user_id, owner_id, token)
        del waiting_for_vk[user_id]  # Убираем из состояния ожидания
        await update.message.reply_text("✅ Данные для публикации в ВК успешно сохранены.")
    except ValueError:
        await update.message.reply_text("🚫 Ошибка: Укажите ID группы и токен через пробел.")
    except Exception as e:
        await update.message.reply_text(f"🚫 Ошибка сохранения данных: {e}")






async def handle_vkpub_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query

    await query.answer()  # Ответ пользователю, что нажатие обработано
    loading_message = await query.message.reply_text("📤 Пост переносится в ВК, ожидайте...")

    if not query.data.startswith("vkpub_"):
        await loading_message.edit_text("🚫 Неверный формат callback данных.")
        return

    # Извлекаем user_id и message_id из callback_data
    _, user_id_str, message_id_str = query.data.split('_', maxsplit=2)
    user_id = int(user_id_str)
    message_id = int(message_id_str)
    key = f"{user_id}_{message_id}"
    global media_group_storage
    # Загружаем данные медиагруппы из Firebase
    media_group_storage = load_publications_from_firebase()
    user_publications = media_group_storage.get(str(user_id), {})
    media_group_data = user_publications.get(key)

    if not media_group_data:
        await loading_message.edit_text("🚫 Ошибка: Данные о медиагруппе не найдены.")
        return

    # Проверка формата данных медиагруппы
    media_items = media_group_data.get("media", [])
    if not media_items or not isinstance(media_items, list):
        await loading_message.edit_text("🚫 Ошибка: Медиагруппа пуста или имеет некорректный формат.")
        return

    # Извлекаем ссылки на изображения
    image_urls = [item.get("file_id") for item in media_items if "file_id" in item]
    if not image_urls:
        await loading_message.edit_text("🚫 Ошибка: Ссылки на изображения отсутствуют.")
        return

    # Загружаем токен и owner_id пользователя из Firebase
    vk_keys_ref = db.reference(f'users_publications/vk_keys/{user_id}')
    vk_keys = vk_keys_ref.get()
    if not vk_keys:
        await loading_message.edit_text(
            "В данный момент у вас не настроена публикация в вашу ВК группу. "
            "Для этого вам нужно получить два значения - ID вашей вк группы и токен.\n\n "
            'Токен вы можете получить тут: vkhost.github.io\n'
            'Для этого перейдите по указанной ссылке и следуйте инструкциям указанным там, в качестве приложения выберите VKадмин\n\n'
            'ID группы можно узнать из адресной строки, из настроек группы. либо тут regvk.com/id/\n\n'
            'Когда у вас будут и ID и токен, отправьте их сюда разделив пробелом или новой строкой.\nТак:\n'
            '<pre>IDгруппы токен</pre>\n'
            'Или так:\n'
            '<pre>IDгруппы\n'
            'токен</pre>'                                    
            ,
            parse_mode="HTML"
        )
        if user_id not in waiting_for_vk:
            waiting_for_vk[user_id] = True         
        return

    token = vk_keys.get("token")
    owner_id = vk_keys.get("owner_id")
    if not token or not owner_id:
        await loading_message.edit_text("🚫 Ошибка: Некорректные данные для ВК. Проверьте настройки.")
        return

    # Авторизация в VK API
    vk_session = VkApi(token=token)
    vk = vk_session.get_api()



    # Загрузка изображений в ВК
    uploaded_photos = []
    # Извлекаем заголовок и обрабатываем caption
    first_caption = media_items[0].get("caption", "")
    cleaned_caption = extract_text_before_first_link(first_caption)
    formatted_caption = format_caption_for_vk(first_caption)
   

    try:
        for url in image_urls:
            photo = upload_photo_to_vk(vk, url, owner_id, formatted_caption) 
            uploaded_photos.append(f"photo{photo['owner_id']}_{photo['id']}")
    except Exception as e:
        await loading_message.edit_text(f"🚫 Ошибка загрузки изображений в ВК: {e}")
        return

    # Публикация поста
    try:
        # Проверяем значение owner_id
        if int(owner_id) > 0:
            owner_id = -int(owner_id)

        vk.wall.post(
            owner_id=int(owner_id),  # ID группы
            from_group=1,
            message=cleaned_caption,
            attachments=",".join(uploaded_photos),
            random_id=get_random_id()
        )

        await loading_message.edit_text("✅ Пост успешно опубликован в ВКонтакте")
    except Exception as e:
        await loading_message.edit_text(f"🚫 Ошибка публикации поста в ВК: {e}")



def upload_photo_to_vk(vk, image_url, group_id, caption):
    # Загружаем изображение на сервер ВКонтакте
    upload_url = vk.photos.getWallUploadServer(group_id=group_id)['upload_url']

    image_data = requests.get(image_url).content
    response = requests.post(upload_url, files={'photo': ('image.jpg', image_data)}).json()
    saved_photo = vk.photos.saveWallPhoto(
        group_id=group_id,
        photo=response['photo'],
        server=response['server'],
        hash=response['hash'],
        caption=caption  # Используем caption как описание фотографии
    )[0]
   
    return saved_photo
















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
            
# Функция для разбиения списка изображений на группы по 10
def chunk_images(images, chunk_size=10):
    for i in range(0, len(images), chunk_size):
        yield images[i:i + chunk_size]

TELEGRAM_API_TIMEOUT = 20  # Увеличьте время ожидания        



async def send_mode(update: Update, context: CallbackContext) -> None:
    """Включение режима дублирования сообщений."""
    user_id = update.message.from_user.id
    if user_id not in users_in_send_mode:
        users_in_send_mode[user_id] = True    
    await update.message.reply_text('🔄 Режим прямой связи включен. Все последующие сообщения будут дублироваться администрации. Для завершения режима введите /fin')
    
async def fin_mode(update: Update, context: CallbackContext) -> None:
    """Выключение режима дублирования сообщений и возврат к изначальной логике."""

    try:     
        user_id = update.effective_user.id

        await update.message.reply_text('✅ Режим пересылки сообщений администрации отключен. Бот вернулся к своему основному режиму работы.')

    except Exception as e:
        await update.message.reply_text(f"🚫 Ошибка сохранения данных: {e}")
    finally:
        del users_in_send_mode[user_id]
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

async def ignore_pinned_message(update: Update, context: CallbackContext):
    # Ничего не делаем, просто игнорируем событие закрепления
    pass


def main() -> None:
    load_context_from_firebase()  # Загружаем историю чатов в user_contexts
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Настройка ConversationHandler для основной логики
    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('edit', edit_article),            
            MessageHandler(filters.TEXT & ~filters.COMMAND, main_logic)  # Основная логика
        ],
        states={
            ASKING_FOR_ARTIST_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_artist_link)],
            ASKING_FOR_AUTHOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_author_name)],
            EDITING_FRAGMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_text)],
            ASKING_FOR_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, handle_new_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
            ],
        },
        fallbacks=[MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message)],
        per_user=True
    )

    search_handler = ConversationHandler(
        entry_points=[CommandHandler('search', start_search)],
        states={
            ASKING_FOR_FILE: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, handle_file),
                MessageHandler(filters.ALL & ~filters.COMMAND, unknown_search_message),
            ],
        },
        fallbacks=[
            CommandHandler('fin_search', finish_search),
            CommandHandler('restart', restart),  # Добавлен обработчик для /restart
        ],
        per_user=True,
        allow_reentry=True
    )

    ocr_handler = ConversationHandler(
        entry_points=[CommandHandler('ocr', start_ocr), CallbackQueryHandler(text_rec_with_gpt, pattern='^text_rec$')],
        states={
            ASKING_FOR_FILE: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, handle_file),
                MessageHandler(filters.ALL & ~filters.COMMAND, unknown_ocr_message),
            ],
            ASKING_FOR_FOLLOWUP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_followup_question),            ],        
        },
        fallbacks=[
            CommandHandler('fin_ocr', finish_ocr),
            CommandHandler('restart', restart),  # Добавлен обработчик для /restart
        ],
        per_user=True,
        allow_reentry=True
    )

    gpt_handler = ConversationHandler(
        entry_points=[CommandHandler('gpt', run_gpt), CommandHandler('set_role', handle_set_role_button), CommandHandler('short_help_gpt', handle_short_gpt_help)],
        states={
            ASKING_FOR_ROLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_role_input),
            ],
            ASKING_FOR_FILE: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, handle_file),
                MessageHandler(filters.ALL & ~filters.COMMAND, unknown_ocr_message),
            ],
        },
        fallbacks=[
            CommandHandler('fin_gpt', stop_gpt),
            CommandHandler('restart', restart),  # Добавлен обработчик для /restart
        ],
        per_user=True,
        allow_reentry=True
    )

    application.add_handler(MessageHandler(filters.StatusUpdate.PINNED_MESSAGE, ignore_pinned_message))
    # Добавляем обработчики команд
    application.add_handler(CallbackQueryHandler(handle_edit_button, pattern='edit_article'))
    application.add_handler(CallbackQueryHandler(handle_delete_button, pattern='delete_last'))
    application.add_handler(CallbackQueryHandler(handle_edit_delete, pattern='^edit_|^delete_'))
    application.add_handler(CallbackQueryHandler(handle_preview_button, pattern='preview_article'))
    application.add_handler(CallbackQueryHandler(handle_create_article_button, pattern='create_article'))
    application.add_handler(CallbackQueryHandler(handle_help_text_button, pattern='help_command'))
    application.add_handler(CallbackQueryHandler(handle_restart_button, pattern='restart'))
    application.add_handler(CallbackQueryHandler(handle_page_change, pattern='^page_')) 
    application.add_handler(CallbackQueryHandler(handle_publish_button, pattern='^publish_'))
    application.add_handler(CallbackQueryHandler(ai_or_not, pattern='ai_or_not'))
    application.add_handler(CallbackQueryHandler(finish_search, pattern='finish_search')) 
    application.add_handler(CallbackQueryHandler(finish_ocr, pattern='finish_ocr'))
    application.add_handler(CallbackQueryHandler(stop_gpt, pattern='stop_gpt'))      
    application.add_handler(CallbackQueryHandler(start_search, pattern='start_search'))
    application.add_handler(CallbackQueryHandler(start_ocr, pattern='start_ocr'))
    application.add_handler(CallbackQueryHandler(button_ocr, pattern='recognize_text'))
    application.add_handler(CallbackQueryHandler(button_ocr, pattern='recognize_plant'))
    application.add_handler(CallbackQueryHandler(button_more_plants_handler, pattern='plant_\\d+'))
    application.add_handler(CallbackQueryHandler(gpt_plants_help_handler, pattern='^gpt_plants_help$'))
    application.add_handler(CallbackQueryHandler(gpt_plants_more_handler, pattern='^gpt_plants_more$'))
    application.add_handler(CallbackQueryHandler(text_rec_with_gpt, pattern='text_rec_with_gpt$'))
    application.add_handler(CallbackQueryHandler(text_plant_help_with_gpt, pattern='text_plant_help_with_gpt$'))    
    application.add_handler(CallbackQueryHandler(regenerate_image, pattern=r"^regenerate_"))
    application.add_handler(CallbackQueryHandler(examples_table_handler, pattern='^examples_table$'))
    application.add_handler(CallbackQueryHandler(handle_view_shared, pattern="^view_shared$"))
    application.add_handler(CallbackQueryHandler(handle_select_scheduled, pattern=r"^view_shared_"))
    application.add_handler(CallbackQueryHandler(handle_view_post, pattern=r"^viewneuralpost_\d+_.+$"))
    application.add_handler(CallbackQueryHandler(handle_neuralpublic_button, pattern="^neuralpublic_"))
    application.add_handler(CallbackQueryHandler(handle_shared_tag_selection, pattern="^sharedtag_"))
    application.add_handler(CallbackQueryHandler(handle_sharefromuser_publication, pattern=r"^sharefromuserpublic_\d+_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_edit_post, pattern=r"^editpost_\d+_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_back_to_main, pattern=r"^backtomain_\d+_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_add_favorite, pattern=r"^favorite_\d+_\d+_\d+$"))

    
    
    application.add_handler(CallbackQueryHandler(run_gpt, pattern='run_gpt')) 
    application.add_handler(CallbackQueryHandler(reset_dialog, pattern='^reset_dialog$')) 
    application.add_handler(CallbackQueryHandler(handle_set_role_button, pattern='^set_role_button$'))  
    application.add_handler(CallbackQueryHandler(handle_followup_question, pattern='^ask_followup'))    
    application.add_handler(CallbackQueryHandler(handle_short_gpt_help, pattern='^short_help_gpt$'))                 
    application.add_handler(CallbackQueryHandler(handle_vkpub_button, pattern=r'^vkpub_'))
    application.add_handler(CallbackQueryHandler(filedelete_image, pattern=r'^filedelete_'))
    application.add_handler(CallbackQueryHandler(fileselect_image_to_delete, pattern=r'^fileselect_'))
    application.add_handler(CallbackQueryHandler(handle_role_select, pattern='^role_select$'))
    application.add_handler(CallbackQueryHandler(handle_role_selected, pattern='^(newroleselect_|defaultrole_)'))
    application.add_handler(CallbackQueryHandler(handle_delete_role, pattern=r"^clear_role_"))  
    application.add_handler(CallbackQueryHandler(mainhelp_callback, pattern="osnhelp"))
    application.add_handler(CallbackQueryHandler(handle_share_button, pattern='^share_'))
    application.add_handler(CallbackQueryHandler(mushrooms_gpt, pattern='mushrooms_gpt$'))    

    application.add_handler(CallbackQueryHandler(yrrase_scheduled, pattern="yrrasetag_"))
      
    # Начало процесса замены
    application.add_handler(CallbackQueryHandler(swap_images, pattern=r'^swapimages_'))
    application.add_handler(CallbackQueryHandler(delete_all_by_tag, pattern=r"^tagdelete_"))
    # Выбор первого изображения
    application.add_handler(CallbackQueryHandler(select_first_image, pattern=r'^swap_first_'))

    # Выбор второго изображения
    application.add_handler(CallbackQueryHandler(select_second_image, pattern=r'^swap_second_'))
    # Обработчик для кнопки "Отложить"

    application.add_handler(CallbackQueryHandler(handle_snooze_with_tag_button, pattern=r"^snooze_with_tag_\d+_\d+$"))  
    application.add_handler(CallbackQueryHandler(handle_tag_selection, pattern=r"^tag_"))
    application.add_handler(CallbackQueryHandler(handle_replace_caption, pattern=r"caption_"))
    application.add_handler(CallbackQueryHandler(handle_save_button, pattern=r"^save_\d+_\d+$"))

    application.add_handler(CallbackQueryHandler(select_style, pattern="choose_style"))
    application.add_handler(CallbackQueryHandler(category_handler, pattern="^category_"))
    application.add_handler(CallbackQueryHandler(model_handler, pattern="^model_"))
    application.add_handler(CallbackQueryHandler(cancel_handler, pattern="^cancelmodel"))

    
    application.add_handler(CommandHandler("scheduledmark", handle_scheduled_tags))
    application.add_handler(CallbackQueryHandler(handle_scheduled_tags, pattern="^scheduled_by_tag$"))
    application.add_handler(CallbackQueryHandler(show_scheduled_by_tag, pattern="^filter_tag_"))
    # Обработчик для команды /scheduled (показать список отложенных записей)

    application.add_handler(CallbackQueryHandler(handle_shuffle_button, pattern=r"^shuffle_\d+_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_palettesort, pattern=r"^palettesort_\d+_\d+$"))
    application.add_handler(CallbackQueryHandler(sort_by_criteria, pattern=r"^sort_\w+_\w+$"))


    # Обработчик для просмотра конкретной отложенной записи
    application.add_handler(CallbackQueryHandler(handle_view_scheduled, pattern=r'^view_[\w_]+$'))    
    application.add_handler(CommandHandler("sendall", sendall))    
    application.add_handler(CommandHandler("style", choose_style))   
    application.add_handler(CommandHandler('set_role', set_role ))          
    application.add_handler(CommandHandler('send', send_mode))
    application.add_handler(CommandHandler('fin', fin_mode))
    application.add_handler(CommandHandler('restart', restart))
    application.add_handler(CommandHandler('rerestart', rerestart))    
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('publish', publish))
    application.add_handler(CommandHandler('preview', preview_article))  # Добавляем обработчик для /preview
    application.add_handler(CommandHandler('delete', delete_last))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, duplicate_message))  # Обработчик дублирования сообщений


    # Добавляем обработчики для команд /search и /fin_search
    application.add_handler(search_handler)
    application.add_handler(CommandHandler('fin_search', finish_search))  # Обработчик команды /fin_search

    # Добавляем обработчики для команд /ocr и /fin_ocr
    application.add_handler(ocr_handler)
    application.add_handler(CommandHandler('fin_ocr', finish_ocr)) 

    # Добавляем обработчики для команд /gpt и /fin_gpt
    application.add_handler(gpt_handler)
    application.add_handler(CommandHandler('fin_gpt', stop_gpt))     

    # Добавляем основной conversation_handler
    application.add_handler(conversation_handler)

    logger.info("Bot started and polling...")  
    keep_alive()#запускаем flask-сервер в отдельном потоке. Подробнее ниже...
    application.run_polling() #запуск бота    

if __name__ == '__main__':
    main()
