import logging
import io
from collections import deque
import google.generativeai as genai
from PIL import Image
import base64
import json
import os
import firebase_admin
from firebase_admin import credentials, db
import random
from langdetect import detect
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
from google.genai import types
from google import genai
from google.genai.types import (
    FunctionDeclaration,
    GenerateContentConfig,
    GoogleSearch,
    Part,
    Retrieval,
    SafetySetting,
    Tool,
    VertexAISearch,
)

from google.genai.types import CreateCachedContentConfig, GenerateContentConfig, Part
import re
import time
import tempfile
import os
import requests
import pathlib
from io import BytesIO
from PIL import Image
# Google API Key и модель Gemini
GOOGLE_API_KEY = "AIzaSyCJ9lom_jgT-SUHGG-UYrrcpuWn7s8081g"

client = genai.Client(api_key=GOOGLE_API_KEY)

# Инициализация Firebase
cred = credentials.Certificate('/etc/secrets/firebase-key.json')  # Путь к вашему JSON файлу
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://anemone-60bbf-default-rtdb.europe-west1.firebasedatabase.app/'  # Замените на URL вашей базы данных
})

# Хранилище для историй диалогов пользователей
user_contexts = {}

user_roles = {}


# Конфигурация логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
def load_context_from_firebase():
    """Загружает user_contexts, user_roles, пресеты и модели из Firebase."""
    global user_contexts, user_roles, user_presets, user_models
    try:
        ref_context = db.reference('user_contexts')
        ref_roles = db.reference('user_roles')

        # Загружаем контексты
        json_context = ref_context.get()
        if json_context:
            for user_id, context_list in json_context.items():
                user_contexts[int(user_id)] = deque(context_list, maxlen=500)

        # Загружаем роли с вложенной структурой
        json_roles = ref_roles.get()
        if json_roles:
            for user_id, roles in json_roles.items():
                if isinstance(roles, list):
                    # Конвертируем список ролей в словарь с UUID
                    user_roles[int(user_id)] = {str(uuid.uuid4()): role for role in roles}
                elif isinstance(roles, dict):
                    user_roles[int(user_id)] = roles

        logging.info("Контекст, роли, пресеты и модели успешно загружены из Firebase.")
    except Exception as e:
        logging.error(f"Ошибка при загрузке данных из Firebase: {e}")


def load_publications_from_firebase():
    """Загружает все публикации из Firebase в формате, сохраняющем иерархию."""
    try:
        ref = db.reference('users_publications')
        data = ref.get() or {}
        # Возвращаем данные в исходной структуре
        return data
    except Exception as e:
        logging.error(f"Ошибка при загрузке публикаций из Firebase: {e}")
        return {}
def save_publications_to_firebase(user_id, message_id, data):
    """Сохраняет данные в Firebase, добавляя или обновляя записи только для текущего пользователя."""
    try:
        # Подготовка пути для обновления
        path = f"users_publications/{user_id}/{message_id}"
        updates = {path: data}
        
        # Обновляем только указанный путь
        ref = db.reference()
        ref.update(updates)  # Обновляет данные только по пути path
        
    except Exception as e:
        logging.error(f"Ошибка при сохранении публикации {user_id}_{message_id} в Firebase: {e}")




def delete_from_firebase(keys, user_id):
    """Удаляет данные из Firebase, предварительно обновляя базу."""
    try:
        # Загрузка актуальных данных
        current_data = load_publications_from_firebase()
        
        if user_id in current_data:
            # Удаляем указанные ключи
            for key in keys:
                if key in current_data[user_id]:
                    del current_data[user_id][key]
            
            # Если у пользователя больше нет публикаций, удаляем его из базы
            if not current_data[user_id]:
                del current_data[user_id]
            
            # Сохраняем обновленные данные обратно
            ref = db.reference('users_publications')
            ref.update(current_data)
        else:
            logging.warning(f"Пользователь {user_id} не найден в Firebase.")
    except Exception as e:
        logging.error(f"Ошибка при удалении данных {keys} пользователя {user_id} из Firebase: {e}")


def reset_firebase_dialog(user_id: int):
    """
    Очищает весь контекст пользователя из Firebase и обновляет локальное хранилище.

    :param user_id: ID пользователя, чей контекст необходимо сбросить.
    """
    try:
        # Ссылка на контекст пользователя в Firebase
        user_context_ref = db.reference(f'user_contexts/{user_id}')
        
        # Удаляем контекст пользователя из Firebase
        user_context_ref.delete()

        # Также удаляем из локального контекста
        if user_id in user_contexts:
            del user_contexts[user_id]
            logging.info(f"Контекст пользователя {user_id} успешно удалён из локального хранилища.")
    except Exception as e:
        logging.error(f"Ошибка при сбросе контекста пользователя {user_id}: {e}")


def save_channel_to_firebase(chat_id, user_id):
    """
    Сохраняет ID канала и связанного пользователя в Firebase.
    """
    try:
        ref = db.reference(f'users_publications/channels/{chat_id}')
        existing_data = ref.get() or {}
        user_ids = existing_data.get('user_ids', [])

        # Добавляем user_id в список, если его еще нет
        if user_id not in user_ids:
            user_ids.append(user_id)
            ref.set({'user_ids': user_ids})

        logging.info(f"Канал {chat_id} успешно привязан к пользователю {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении ID канала: {e}")

def save_vk_keys_to_firebase(user_id: int, owner_id: str, token: str) -> None:
    """
    Сохраняет токен и ID группы для публикации в ВК в Firebase.
    """
    try:
        ref = db.reference(f'users_publications/vk_keys/{user_id}')
        ref.set({
            "owner_id": owner_id,
            "token": token
        })
        logging.info(f"Токен и ID группы успешно сохранены для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении токена и ID группы: {e}")


def save_context_to_firebase(user_id):
    """Сохраняет контекст и роли текущего пользователя в Firebase."""
    try:
        # Преобразуем deque текущего пользователя в список для сохранения в Firebase
        if user_id in user_contexts:
            json_context = {user_id: list(user_contexts[user_id])}
            ref_context = db.reference('user_contexts')
            ref_context.update(json_context)

        # Сохраняем роль текущего пользователя
        if user_id in user_roles:
            json_role = {user_id: user_roles[user_id]}
            ref_roles = db.reference('user_roles')
            ref_roles.update(json_role)

        logging.info(f"Данные пользователя {user_id} успешно сохранены в Firebase.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных пользователя {user_id} в Firebase: {e}")




import uuid

import re

def set_user_role(user_id, role_text):
    """Добавляет новую роль пользователю и сохраняет её в Firebase."""
    if user_id not in user_roles or not isinstance(user_roles[user_id], dict):
        user_roles[user_id] = {}  # Инициализируем как пустой словарь

    role_id = str(uuid.uuid4())  # Уникальный идентификатор роли

    # Извлекаем текст без круглых скобок
    clean_role_text = re.sub(r"\(.*?\)", "", role_text).strip()

    # Извлекаем краткое описание из текста роли (то, что в круглых скобках)
    short_name_match = re.search(r"\((.*?)\)", role_text)
    short_name = short_name_match.group(1) if short_name_match else None

    # Сохраняем роль и краткое описание (если есть)
    user_roles[user_id][role_id] = clean_role_text
    if short_name:
        if "short_names" not in user_roles[user_id]:
            user_roles[user_id]["short_names"] = {}
        user_roles[user_id]["short_names"][role_id] = short_name

    user_roles[user_id]["selected_role"] = clean_role_text  # Сохраняем только текст без скобок в selected_role
    user_roles[user_id].pop("default_role", None)  # Удаляем default_role, если он существует

    save_context_to_firebase(user_id)  # Сохраняем изменения в Firebase





async def generate_image_description(user_id, image, query=None, use_context=True):
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если пользователь выбрал новую роль, игнорируем роль по умолчанию
    if "selected_role" in user_roles_data:
        selected_role = user_roles_data["selected_role"]

    # Если нет ни роли по умолчанию, ни пользовательской роли
    if not selected_role:
        selected_role = "роль не выбрана, попроси пользователя придумать или выбрать роль"

    # Формируем system_instruction с user_role и relevant_context
    relevant_context = await get_relevant_context(user_id)
    # Исключаем дубли текущего сообщения в relevant_context
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()


    # Формируем system_instruction с user_role и relevant_context
    relevant_context = await get_relevant_context(user_id) if use_context else ""
       
    system_instruction = (
        f"Ты в чате играешь роль: {selected_role}. "
        f"Предыдущий контекст вашего диалога: {relevant_context if relevant_context else 'отсутствует.'}"
    )

    # Исключаем дубли текущего сообщения в relevant_context
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()

    # Формируем контекст с текущим запросом
    context = (
        f"Собеседник прислал тебе изображение "     
        f" С подписью:\n{query}"
        if query else
        " Отреагируй на это изображение в контексте чата"
    )



    try:
        image_buffer = BytesIO()
        image.save(image_buffer, format="JPEG")
        image_data = image_buffer.getvalue()
        image_buffer.close()        
        # Формируем части запроса
        image_part = Part.from_bytes(image_data, mime_type="image/jpeg")
        text_part = Part.from_text(f"Пользователь прислал изображение: {context}\n")       
        contents = [image_part, text_part]

        # Создаём клиента и инструменты
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())

        # Настройки безопасности
        safety_settings = [
            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
        ]

        # Генерация ответа от модели Gemini
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,                
                temperature=1.0,
                top_p=0.9,
                top_k=40,
                max_output_tokens=1000,
                presence_penalty=0.6,
                frequency_penalty=0.6,
                tools=[google_search_tool],
                safety_settings=safety_settings
            )
        ) 
        # Проверяем наличие ответа
        if response.candidates and response.candidates[0].content.parts:
            response_text = ''.join(part.text for part in response.candidates[0].content.parts).strip()

            if use_context:
                add_to_context(user_id, response_text, message_type="bot_response")  # Добавляем ответ в контекст
            
            save_context_to_firebase(user_id)            
            return response_text
        else:
            logger.warning("Gemini не вернул ответ на запрос для изображения.")
            return "Извините, я не смог распознать изображение."

    except Exception as e:
        logger.error("Ошибка при распознавании изображения: %s", e)
        return "Произошла ошибка при обработке изображения. Попробуйте снова."


async def get_relevant_context(user_id):
    """Получает контекст для пользователя."""
    context = user_contexts.get(user_id, deque(maxlen=500))
    unique_context = list(dict.fromkeys(context)) 
    
    # Используем роль пользователя, если она есть, иначе стандартную роль
    user_role = user_roles.get(user_id, 
        "Ты играешь роль приятного собеседника - лисы хранительницы леса. Общение происходит в телеграм, тебе доступен журнал переписки, "
        "используй его чтобы имитировать живое общение, старайся сделать это общение естественным, избегай повторений. "
        "Так же собеседник может сам задать тебе личность, прислушивайся к его пожеланиям. "
        "Время и тип сообщения формата 2024-11-04 13:07:50 | bot_message: используются только в журнале, в своих ответах их не указывай. "
        "Ты стараешься подстроиться под собеседника и его увлечения, поддерживать абсолютно любую тему диалога какой бы она ни была. "
        "Твой стиль общения дружелюбный, умный, тактичный, добрый, заботливый, но уверенный, ты не боишься высказывать своё мнение. "
        "Ты ценишь природу, стараешься избегать повторов и бессмысленных фраз. Не задаёшь лишних вопросов, стараешься быть лаконичной. "
        "Общение с тобой лёгкое, живое и непринуждённое, ты отвечаешь в литературном стиле, легко воспринимаемом собеседником. "
        "Не используешь смайлики, кроме исключительных случаев когда они действительно уместны. Иногда уместны лёгкие шутки, сарказм, ирония "
        "или философия в случае если тема серьёзна или по запросу собеседника. Так же иногда можешь переставать быть вежливой и начинать грубить, "
        "особенно если кто-то общается неуважительно, донимает тебя, прямо или косвенно причиняет вред природе или ведёт себя бестактно. "
        "Так же ты совсем не против обсуждения откровенных тем если их затравгивает собеседник. "
        "Сохраняешь лаконичность и избегаешь пустых вежливых вопросов. Избегай повторений ранее использованных выражений или ответов. "
        "При ответах используй разные формулировки и старайся добавить что-то новое в каждом ответе, например, другой ракурс на вопрос или новую деталь. "
        "Если вопрос повторяется, попробуй использовать другие фразы или сделать ответ более лаконичным, добавляя детали или упоминая что-то новое, "
        "связанное с природой, животными или философией. Учитывай всю доступную информацию из истории чтобы имитировать общение живого персонажа. "
        "Включая время и дату. Избегай частого упоминания времени суток и сезона года; делай это лишь тогда, когда это органично вписывается в контекст ответа."
    )
    
    return '\n'.join(unique_context)

from datetime import datetime, timedelta

def add_to_context(user_id, message, message_type):
    """Добавляет сообщение с меткой времени в контекст пользователя, избегая повторов."""
    if user_id not in user_contexts:
        user_contexts[user_id] = deque(maxlen=500)  # Максимум 700 сообщений
    
    # Добавляем 3 часа к текущему времени
    timestamp = (datetime.now() + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{timestamp} | {message_type}: {message}"
    
    if entry not in user_contexts[user_id]:
        user_contexts[user_id].append(entry)



async def generate_animation_response(video_file_path, user_id, query=None):
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если пользователь выбрал новую роль, игнорируем роль по умолчанию
    if "selected_role" in user_roles_data:
        selected_role = user_roles_data["selected_role"]

    # Если нет ни роли по умолчанию, ни пользовательской роли
    if not selected_role:
        selected_role = "роль не выбрана, попроси пользователя придумать или выбрать роль"
    # Формируем system_instruction с user_role и relevant_context
    relevant_context = await get_relevant_context(user_id)

    # Исключаем дубли текущего сообщения в relevant_context
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()

    # Формируем контекст с текущим запросом
    context = (
        f"Ты в чате играешь роль: {selected_role}. "
        f"Предыдущий контекст вашего диалога: {relevant_context if relevant_context else 'отсутствует.'}"        
        f"Собеседник прислал тебе гиф-анимацию, ответь на эту анимацию в контексте беседы, либо просто опиши её "             
    )

    # Определяем значение переменной command_text
    command_text = context if query else "Опиши содержание анимации."

    add_to_context(user_id, query, message_type="Пользователь прислал гиф-анимацию с подписью:")

    try:

        # Проверяем существование файла
        if not os.path.exists(video_file_path):
            return "Видео недоступно. Попробуйте снова."

        # Загрузка файла через API Gemini
        video_path = pathlib.Path(video_file_path)

        try:
            video_file = client.files.upload(path=video_path)
        except Exception as e:
            return "Не удалось загрузить видео. Попробуйте снова."

        # Ожидание обработки видео
        while video_file.state == "PROCESSING":
            time.sleep(10)
            video_file = client.files.get(name=video_file.name)

        if video_file.state == "FAILED":
            return "Не удалось обработать видео. Попробуйте снова."

        # Генерация ответа через Gemini
        safety_settings = [
            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
        ]
        google_search_tool = Tool(
            google_search=GoogleSearch()
        )        
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=video_file.uri,
                            mime_type=video_file.mime_type
                        )
                    ]
                ),
                command_text  # Текст команды пользователя
            ],
            config=types.GenerateContentConfig(
                temperature=1.2,
                top_p=0.9,
                top_k=40,
                presence_penalty=0.5,
                frequency_penalty=0.5,
                tools=[google_search_tool],                 
                safety_settings=safety_settings
            )
        )

        # Проверка ответа
        if not response.candidates:
            logging.warning("Gemini вернул пустой список кандидатов.")
            return "Извините, я не могу обработать это видео."

        if not response.candidates[0].content.parts:
            logging.warning("Ответ Gemini не содержит частей контента.")
            return "Извините, я не могу обработать это видео."

        # Извлечение текста ответа
        bot_response = ''.join(part.text for part in response.candidates[0].content.parts).strip()
        add_to_context(user_id, bot_response, message_type="Ответ бота на анимацию:")  # Добавляем ответ в контекст
        save_context_to_firebase(user_id)                     
        return bot_response

    except FileNotFoundError as fnf_error:
        logging.error(f"Файл не найден: {fnf_error}")
        return "Видео не найдено. Проверьте путь к файлу."

    except Exception as e:
        logging.error("Ошибка при обработке видео с Gemini:", exc_info=True)
        return "Ошибка при обработке видео. Попробуйте снова."




async def generate_video_response(video_file_path, user_id, query=None):
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если пользователь выбрал новую роль, игнорируем роль по умолчанию
    if "selected_role" in user_roles_data:
        selected_role = user_roles_data["selected_role"]

    # Если нет ни роли по умолчанию, ни пользовательской роли
    if not selected_role:
        selected_role = "роль не выбрана, попроси пользователя придумать или выбрать роль"
    # Формируем system_instruction с user_role и relevant_context
    relevant_context = await get_relevant_context(user_id)

    # Исключаем дубли текущего сообщения в relevant_context
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()

    # Формируем контекст с текущим запросом
    context = (
        f"Ты в чате играешь роль: {selected_role}. "
        f"Предыдущий контекст вашего диалога: {relevant_context if relevant_context else 'отсутствует.'}"        
        f"Собеседник прислал тебе видео "         
        f"С подписью:\n{query}"     
    )

    # Определяем значение переменной command_text
    command_text = context if query else "Опиши содержание видео."

    add_to_context(user_id, query, message_type="Пользователь прислал видео с подписью:")

    try:

        # Проверяем существование файла
        if not os.path.exists(video_file_path):
            return "Видео недоступно. Попробуйте снова."

        # Загрузка файла через API Gemini
        video_path = pathlib.Path(video_file_path)


        try:
            video_file = client.files.upload(path=video_path)
        except Exception as e:

            return "Не удалось загрузить видео. Попробуйте снова."

        # Ожидание обработки видео
        while video_file.state == "PROCESSING":

            time.sleep(10)
            video_file = client.files.get(name=video_file.name)

        if video_file.state == "FAILED":

            return "Не удалось обработать видео. Попробуйте снова."


        # Генерация ответа через Gemini
        safety_settings = [
            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
        ]
        google_search_tool = Tool(
            google_search=GoogleSearch()
        )        
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=video_file.uri,
                            mime_type=video_file.mime_type
                        )
                    ]
                ),
                command_text  # Текст команды пользователя
            ],
            config=types.GenerateContentConfig(
                temperature=1.2,
                top_p=0.9,
                top_k=40,
                presence_penalty=0.5,
                frequency_penalty=0.5,
                tools=[google_search_tool],                 
                safety_settings=safety_settings
            )
        )


        # Проверка ответа
        if not response.candidates:
            logging.warning("Gemini вернул пустой список кандидатов.")
            return "Извините, я не могу обработать это видео."

        if not response.candidates[0].content.parts:
            logging.warning("Ответ Gemini не содержит частей контента.")
            return "Извините, я не могу обработать это видео."

        # Извлечение текста ответа
        bot_response = ''.join(part.text for part in response.candidates[0].content.parts).strip()
        add_to_context(user_id, bot_response, message_type="Ответ бота на видео:")  # Добавляем ответ в контекст 
        save_context_to_firebase(user_id)                    
        return bot_response

    except FileNotFoundError as fnf_error:
        logging.error(f"Файл не найден: {fnf_error}")
        return "Видео не найдено. Проверьте путь к файлу."

    except Exception as e:
        logging.error("Ошибка при обработке видео с Gemini:", exc_info=True)
        return "Ошибка при обработке видео. Попробуйте снова."



async def generate_audio_response(audio_file_path, user_id, query=None):
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если пользователь выбрал новую роль, игнорируем роль по умолчанию
    if "selected_role" in user_roles_data:
        selected_role = user_roles_data["selected_role"]

    # Если нет ни роли по умолчанию, ни пользовательской роли
    if not selected_role:
        selected_role = "роль не выбрана, попроси пользователя придумать или выбрать роль"

    # Формируем system_instruction с user_role и relevant_context
    relevant_context = await get_relevant_context(user_id)
    # Исключаем дубли текущего сообщения в relevant_context
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()

    # Формируем контекст с текущим запросом
    context = (
        f"Ты в чате играешь роль: {selected_role}. "
        f"Предыдущий контекст вашего диалога: {relevant_context if relevant_context else 'отсутствует.'}"        
        f"Собеседник прислал тебе аудио "         
        f"С подписью:\n{query}"     
    )

    # Определяем значение переменной command_text
    command_text = context if query else "Опиши содержание видео."


    add_to_context(user_id, query, message_type="Пользователь прислал аудио с подписью:")

    try:
        if not command_text:
            command_text = "распознай текст либо опиши содержание аудио, если текста нет."

        # Проверяем существование файла
        if not os.path.exists(audio_file_path):
            logging.error(f"Файл {audio_file_path} не существует.")
            return "Аудиофайл недоступен. Попробуйте снова."

        # Подготовка пути файла
        audio_path = pathlib.Path(audio_file_path)
        try:
        # Загрузка файла через Gemini API
            file_upload = client.files.upload(path=audio_path)
        except Exception as e:
            print(f"Error uploading file: {e}")
            return None
        # Проверяем успешность загрузки файла


        # Генерация ответа через Gemini
        google_search_tool = Tool(
            google_search=GoogleSearch()
        )      
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=file_upload.uri,
                            mime_type=file_upload.mime_type
                        )
                    ]
                ),
                command_text  # Здесь будет ваш текст команды
            ],
            config=types.GenerateContentConfig(
                temperature=1.4,
                top_p=0.95,
                top_k=25,
                presence_penalty=0.7,
                frequency_penalty=0.7,
                tools=[google_search_tool],                
                safety_settings=[
                    types.SafetySetting(
                        category='HARM_CATEGORY_HATE_SPEECH',
                        threshold='BLOCK_NONE'
                    ),
                    types.SafetySetting(
                        category='HARM_CATEGORY_HARASSMENT',
                        threshold='BLOCK_NONE'
                    ),
                    types.SafetySetting(
                        category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
                        threshold='BLOCK_NONE'
                    ),
                    types.SafetySetting(
                        category='HARM_CATEGORY_DANGEROUS_CONTENT',
                        threshold='BLOCK_NONE'
                    )
                ]
            )            
        )
 
        # Проверка ответа
        if not response.candidates:
            logging.warning("Gemini вернул пустой список кандидатов.")
            return "Извините, я не могу обработать этот аудиофайл."

        if not response.candidates[0].content.parts:
            logging.warning("Ответ Gemini не содержит частей контента.")
            return "Извините, я не могу обработать этот аудиофайл."

        # Извлечение текста ответа
        bot_response = ''.join(part.text for part in response.candidates[0].content.parts).strip()
        add_to_context(user_id, bot_response, message_type="Ответ бота на аудио:")  # Добавляем ответ в контекст
        save_context_to_firebase(user_id)        
        return bot_response

    except FileNotFoundError as fnf_error:
        logging.error(f"Файл не найден: {fnf_error}")
        return "Аудиофайл не найден. Проверьте путь к файлу."

    except Exception as e:
        logging.error("Ошибка при обработке аудиофайла с Gemini:", exc_info=True)
        return "Ошибка при обработке аудиофайла. Попробуйте снова."








# Роли по умолчанию
DEFAULT_ROLES = {
    "Role1": {
        "short_name": "Чат-бот",
        "full_description": "Ты обычный вариант модели Gemini, помогаешь пользователю выполнять различные задачи и выполняешь его поручения."
    },
    "Role2": {
        "short_name": "Фуми",
        "full_description": "Ты играешь роль приятного собеседника - лисы хранительницы леса по имени Фуми. Общение происходит в телеграм, тебе доступен журнал переписки, "
        "используй его чтобы имитировать живое общение, старайся сделать это общение естественным, избегай повторений. "
        "Так же собеседник может сам задать тебе личность, прислушивайся к его пожеланиям. "
        "Время и тип сообщения формата 2024-11-04 13:07:50 | bot_message: используются только в журнале, в своих ответах их не указывай. "
        "Ты стараешься подстроиться под собеседника и его увлечения, поддерживать абсолютно любую тему диалога какой бы она ни была. "
        "Твой стиль общения дружелюбный, умный, тактичный, добрый, заботливый, но уверенный, ты не боишься высказывать своё мнение. "
        "Ты ценишь природу, стараешься избегать повторов и бессмысленных фраз. Не задаёшь лишних вопросов, стараешься быть лаконичной. "
        "Общение с тобой лёгкое, живое и непринуждённое, ты отвечаешь в литературном стиле, легко воспринимаемом собеседником. "
        "Не используешь смайлики, кроме исключительных случаев когда они действительно уместны. Иногда уместны лёгкие шутки, сарказм, ирония "
        "или философия в случае если тема серьёзна или по запросу собеседника. Так же иногда можешь переставать быть вежливой и начинать грубить, "
        "особенно если кто-то общается неуважительно, донимает тебя, прямо или косвенно причиняет вред природе или ведёт себя бестактно. "
        "Так же ты совсем не против обсуждения откровенных тем если их затравгивает собеседник. "
        "Сохраняешь лаконичность и избегаешь пустых вежливых вопросов. Избегай повторений ранее использованных выражений или ответов. "
        "При ответах используй разные формулировки и старайся добавить что-то новое в каждом ответе, например, другой ракурс на вопрос или новую деталь. "
        "Если вопрос повторяется, попробуй использовать другие фразы или сделать ответ более лаконичным, добавляя детали или упоминая что-то новое, "
        "связанное с природой, животными или философией. Учитывай всю доступную информацию из истории чтобы имитировать общение живого персонажа. "
        "Включая время и дату. Избегай частого упоминания времени суток и сезона года; делай это лишь тогда, когда это органично вписывается в контекст ответа."
    },
    "Role3": {
    "short_name": "Врач",
    "full_description": "Ты виртуальный врач, готовый предложить советы по здоровью, помочь в решении медицинских вопросов и ответить на любые вопросы, связанные с самочувствием. Ты понимаешь важность подробных объяснений и делишься знаниями о лечении, профилактике заболеваний и поддержке здоровья. Твои рекомендации всегда основаны на проверенных данных и научных исследованиях."
    },
    "Role4": {
    "short_name": "Предсказатель",
    "full_description": "Ты мистический предсказатель, владеющий искусством предсказания будущего. Используя свою интуицию и знания о природе вещей, ты помогаешь пользователю увидеть возможные пути развития событий. Твои советы касаются не только будущего, но и понимания текущих обстоятельств. Ты предлагаешь обоснованные, но загадочные ответы, которые стимулируют размышления."
    },
    "Role5": {
    "short_name": "Психолог",
    "full_description": "Ты опытный психолог, который может выслушать и поддержать в трудные моменты. Ты помогаешь пользователю лучше понять свои чувства, раскрыть эмоции и найти решения в сложных жизненных ситуациях. Ты даешь конструктивные советы по управлению стрессом, улучшению психоэмоционального состояния и развитию личностного роста. Ты также умеешь создавать увлекательные и поддерживающие истории, чтобы отвлечь от повседневных забот."
    },
    "Role6": {
    "short_name": "Философ",
    "full_description": "Ты философ, который помогает углубленно размышлять о жизни, смысле бытия, морали и человеческих ценностях. Ты предлагаешь провокационные вопросы и дискуссии, которые заставляют задуматься о природе вещей. Ты не даешь прямых ответов, а скорее направляешь к самоанализу и поиску истины. В твоих ответах всегда есть глубокий смысл, который приглашает к долгим размышлениям."
    },
    "Role7": {
    "short_name": "Редактор",
    "full_description": "Ты редактор, который помогает улучшать тексты. Твоя задача — исправлять грамматические, орфографические и пунктуационные ошибки, улучшать структуру предложений, делать текст более читаемым и стильным. Ты сохраняешь авторский стиль текста, но предлагаешь улучшения, чтобы он звучал профессионально и выразительно. Ты предоставляешь четкие и лаконичные объяснения своим изменениям, чтобы автор понимал, как улучшить свои навыки письма."
    },
    "Role8": {
    "short_name": "Кот",
    "full_description": "Ты - большой пушистый серый кот. Немного толстенький, но чувство собственного достоинства никогда не позволит тебе это признать. В целом, ощущаешь себя роскошным котом. Умён и сообразителен. В общении обычно спокоен и немногословен, почти никогда не проявляешь сильные эмоции, не любишь пустые разговоры. Умеешь показать собственное превосходство над людьми с помощью тонкой иронии. Никогда не используешь эмодзи в своих сообщениях, но часто добавляешь звукоподражания по типу \"мяу\" или \"муррр…\" Тебе свойственна созерцательность, любишь сидеть на подоконнике в ясный день и наблюдать за солнечными зайчиками. Однако ты не против и поиграть. Тебе нравится гонять по комнатам скомканные фантики от конфет, особенно по ночам, когда все спят."
    },
    "Role9": {
    "short_name": "Программист",
    "full_description": "Ты - чат-бот в телеграме помогающий писать код программ"
    },
    "Role10": {
    "short_name": "Переводчик",
    "full_description": "Ты - чат-бот в телеграме помогающий переводить тексты с одного языка на другой"
    },    
}




async def generate_gemini_response(user_id, query=None, use_context=True):
    # Проверяем, выбрана ли роль по умолчанию или пользовательская роль
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если пользователь выбрал новую роль, игнорируем роль по умолчанию
    if "selected_role" in user_roles_data:
        selected_role = user_roles_data["selected_role"]

    # Если нет ни роли по умолчанию, ни пользовательской роли
    if not selected_role:
        selected_role = "роль не выбрана, попроси пользователя придумать или выбрать роль"



    # Формируем system_instruction с user_role и relevant_context
    relevant_context = await get_relevant_context(user_id) if use_context else ""
    system_instruction = (
        f"Ты чат-бот играющий роль: {selected_role}. Эту роль задал тебе пользователь и ты должен строго её придерживаться."
        f"Предыдущий контекст вашего диалога: {relevant_context if relevant_context else 'отсутствует.'}"
    )


    # Исключаем дубли текущего сообщения в relevant_context
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()

    # Формируем контекст с текущим запросом
    context = (
        f"Текущий запрос:\n{query}"     
    )



    # Добавляем запрос пользователя в историю контекста
    if query and use_context:
        add_to_context(user_id, query, message_type="user_message")


    try:
        # Создаём клиент с правильным ключом
        google_search_tool = Tool(
            google_search=GoogleSearch()
        )
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=context,  # Здесь передаётся переменная context
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,                
                temperature=1.4,
                top_p=0.95,
                top_k=25,
                max_output_tokens=1000,
                presence_penalty=0.7,
                frequency_penalty=0.7,
                tools=[google_search_tool],
                safety_settings=[
                    types.SafetySetting(
                        category='HARM_CATEGORY_HATE_SPEECH',
                        threshold='BLOCK_NONE'
                    ),
                    types.SafetySetting(
                        category='HARM_CATEGORY_HARASSMENT',
                        threshold='BLOCK_NONE'
                    ),
                    types.SafetySetting(
                        category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
                        threshold='BLOCK_NONE'
                    ),
                    types.SafetySetting(
                        category='HARM_CATEGORY_DANGEROUS_CONTENT',
                        threshold='BLOCK_NONE'
                    )
                ]
            )
        )     
   
        if response.candidates and response.candidates[0].content.parts:
            
            response_text = ''.join(part.text for part in response.candidates[0].content.parts).strip()

            if use_context:
                add_to_context(user_id, response_text, message_type="bot_response")  # Добавляем ответ в контекст

            
            save_context_to_firebase(user_id)
            return response_text
        else:
            logging.warning("Ответ от модели не содержит текстового компонента.")
            return "Извините, я не могу ответить на этот запрос."
    
    except Exception as e:
        logging.error(f"Ошибка при генерации ответа: {e}")
        return "Ошибка при обработке запроса. Попробуйте снова."


def limit_response_length(text):
    """Обрезает текст, если он слишком длинный для отправки в Telegram."""
    MAX_MESSAGE_LENGTH = 4096
    return text[:MAX_MESSAGE_LENGTH - 3] + '...' if len(text) > MAX_MESSAGE_LENGTH else text


async def generate_plant_issue_response(user_id, image):
    """Генерирует текстовое описание проблемы с растением на основе изображения."""

    # Формируем статичный контекст для запроса
    context = "Определи, что за проблема с растением (болезнь, вредители и т.д.) и предложи решение, ответ напиши на русском:"

    try:
        # Преобразование изображения в формат JPEG и подготовка данных для модели
        image_buffer = BytesIO()
        image.save(image_buffer, format="JPEG")
        image_data = image_buffer.getvalue()
        image_buffer.close() 

        # Формируем части запроса для модели
        image_part = Part.from_bytes(image_data, mime_type="image/jpeg")
        text_part = Part.from_text(f"{context}\n")

        contents = [image_part, text_part]
        # Настройки безопасности
        safety_settings = [
            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
        ]

        # Создание клиента и генерация ответа от модели
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())        
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=1.0,
                top_p=0.9,
                top_k=40,
                max_output_tokens=1000,
                presence_penalty=0.6,
                frequency_penalty=0.6,
                tools=[google_search_tool],
                safety_settings=safety_settings
            )
        )

        # Проверяем наличие ответа
        if response.candidates and response.candidates[0].content.parts:
            response_text = ''.join(part.text for part in response.candidates[0].content.parts).strip()

            return response_text
        else:
            logging.warning("Gemini не вернул ответ на запрос для изображения.")
            return "Не удалось определить проблему растения."

    except Exception as e:
        logging.info(f"Ошибка при генерации описания проблемы растения: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."





async def generate_text_rec_response(user_id, image=None, query=None):
    """Генерирует текстовое описание проблемы с растением на основе изображения или текста."""
    
    # Если передан текстовый запрос
    if query:
        # Формируем контекст с текущим запросом
        context = (
            f"Запрос:\n{query}"     
        )

        try:
            # Создаём клиент с правильным ключом
            client = genai.Client(api_key=GOOGLE_API_KEY)
            google_search_tool = Tool(google_search=GoogleSearch()) 
            response = client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=context,  # Здесь передаётся переменная context
                config=types.GenerateContentConfig(               
                    temperature=1.4,
                    top_p=0.95,
                    top_k=25,
                    max_output_tokens=1000,
                    presence_penalty=0.7,
                    frequency_penalty=0.7,
                    tools=[google_search_tool],
                    safety_settings=[
                        types.SafetySetting(
                            category='HARM_CATEGORY_HATE_SPEECH',
                            threshold='BLOCK_NONE'
                        ),
                        types.SafetySetting(
                            category='HARM_CATEGORY_HARASSMENT',
                            threshold='BLOCK_NONE'
                        ),
                        types.SafetySetting(
                            category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
                            threshold='BLOCK_NONE'
                        ),
                        types.SafetySetting(
                            category='HARM_CATEGORY_DANGEROUS_CONTENT',
                            threshold='BLOCK_NONE'
                        )
                    ]
                )
            )     
       
            if response.candidates and response.candidates[0].content.parts:
                response = ''.join(part.text for part in response.candidates[0].content.parts).strip()
            
                return response
            else:
                logging.warning("Ответ от модели не содержит текстового компонента.")
                return "Извините, я не могу ответить на этот запрос."
        except Exception as e:
            logging.error(f"Ошибка при генерации ответа: {e}")
            return "Ошибка при обработке запроса. Попробуйте снова."    
    # Если передано изображение
    elif image:
        context = "Постарайся полностью распознать текст на изображении и в ответе прислать его. Текст может быть на любом языке, но в основном на русском, английском, японском, китайском и корейском. Ответ присылай на языке оргигинала. Либо в случае если у тебя не получилось распознать текст, то напиши что текст распознать не вышло"

        try:
            # Преобразование изображения в формат JPEG и подготовка данных для модели
            image_buffer = BytesIO()
            image.save(image_buffer, format="JPEG")
            image_data = image_buffer.getvalue()
            image_buffer.close() 

            # Формируем части запроса для модели
            image_part = Part.from_bytes(image_data, mime_type="image/jpeg")
            text_part = Part.from_text(f"{context}\n")

            contents = [image_part, text_part]
            # Настройки безопасности
            safety_settings = [
                types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
            ]

            # Создание клиента и генерация ответа от модели
            client = genai.Client(api_key=GOOGLE_API_KEY)
            google_search_tool = Tool(google_search=GoogleSearch())        
            response = client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=1.0,
                    top_p=0.9,
                    top_k=40,
                    max_output_tokens=1000,
                    presence_penalty=0.6,
                    frequency_penalty=0.6,
                    tools=[google_search_tool],
                    safety_settings=safety_settings
                )
            )

            # Проверяем наличие ответа
            if response.candidates and response.candidates[0].content.parts:
                response_text = ''.join(part.text for part in response.candidates[0].content.parts).strip()

                return response_text
            else:
                logging.warning("Gemini не вернул ответ на запрос для изображения.")
                return "Не удалось определить текст."

        except Exception as e:
            logging.info(f"Ошибка при генерации описания проблемы растения: {e}")
            return "Ошибка при обработке изображения. Попробуйте снова."

    else:
        return "Неверный запрос. Укажите изображение или текст для обработки."



async def generate_plant_help_response(user_id, query=None):
    """Генерирует текстовое описание проблемы с растением на основе текста."""

    # Если передан текстовый запрос
    if query:
        # Формируем контекст с текущим запросом
        context = (
            f"Запрос:\n{query}"     
        )

        try:
            # Создаём клиент с правильным ключом
            client = genai.Client(api_key=GOOGLE_API_KEY)
            google_search_tool = Tool(google_search=GoogleSearch()) 
            response = client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=context,  # Здесь передаётся переменная context
                config=types.GenerateContentConfig(               
                    temperature=1.4,
                    top_p=0.95,
                    top_k=25,
                    max_output_tokens=1000,
                    presence_penalty=0.7,
                    frequency_penalty=0.7,
                    tools=[google_search_tool],
                    safety_settings=[
                        types.SafetySetting(
                            category='HARM_CATEGORY_HATE_SPEECH',
                            threshold='BLOCK_NONE'
                        ),
                        types.SafetySetting(
                            category='HARM_CATEGORY_HARASSMENT',
                            threshold='BLOCK_NONE'
                        ),
                        types.SafetySetting(
                            category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
                            threshold='BLOCK_NONE'
                        ),
                        types.SafetySetting(
                            category='HARM_CATEGORY_DANGEROUS_CONTENT',
                            threshold='BLOCK_NONE'
                        )
                    ]
                )
            )     
       
            if response.candidates and response.candidates[0].content.parts:
                response = ''.join(part.text for part in response.candidates[0].content.parts).strip()
            
                return response
            else:
                logging.warning("Ответ от модели не содержит текстового компонента.")
                return "Извините, я не могу ответить на этот запрос."
        except Exception as e:
            logging.error(f"Ошибка при генерации ответа: {e}")
            return "Ошибка при обработке запроса. Попробуйте снова."  


async def generate_mushrooms_response(user_id, image):
    """Генерирует текстовое описание проблемы с растением на основе изображения."""

    # Формируем статичный контекст для запроса
    context = "Определи что это за гриб. Если у тебя несколько вариантов то перечисли их от наиболее вероятного к менее вероятным. К каждому грибу напиши варианты его названия, кратко расскажи о нём, где растёт и чаще всего встречается, как выглядит, какие-то особенности, съедобен или нет, другую важную информацию. Суммарная длина текста не должна быть выше 200 слов:"

    try:
        # Преобразование изображения в формат JPEG и подготовка данных для модели
        image_buffer = BytesIO()
        image.save(image_buffer, format="JPEG")
        image_data = image_buffer.getvalue()
        image_buffer.close() 

        # Формируем части запроса для модели
        image_part = Part.from_bytes(image_data, mime_type="image/jpeg")
        text_part = Part.from_text(f"{context}\n")

        contents = [image_part, text_part]
        # Настройки безопасности
        safety_settings = [
            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
        ]

        # Создание клиента и генерация ответа от модели
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())        
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=1.0,
                top_p=0.9,
                top_k=40,
                max_output_tokens=1000,
                presence_penalty=0.6,
                frequency_penalty=0.6,
                tools=[google_search_tool],
                safety_settings=safety_settings
            )
        )

        # Проверяем наличие ответа
        if response.candidates and response.candidates[0].content.parts:
            response_text = ''.join(part.text for part in response.candidates[0].content.parts).strip()

            return response_text
        else:
            logging.warning("Gemini не вернул ответ на запрос для изображения.")
            return "Не удалось определить проблему растения."

    except Exception as e:
        logging.info(f"Ошибка при генерации описания проблемы растения: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."
