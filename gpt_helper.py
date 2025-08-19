import logging
import io
from collections import deque
from PIL import Image
import base64
import json
import os
import firebase_admin
from firebase_admin import credentials, db
import random
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
    Tool
)
import aiohttp
from google.genai.types import CreateCachedContentConfig, GenerateContentConfig, Part
import re
import time
import tempfile
import os
import requests
import pathlib
from io import BytesIO
from PIL import Image
import asyncio
from telegram.ext import CallbackContext, ContextTypes
from telegram import Update
from tempfile import NamedTemporaryFile
# Google API Key и модель Gemini
GOOGLE_API_KEY = "AIzaSyDJHKC-x6tY6TdOkyg5QC45V1HH8o3VgiI"

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



def save_ozon_tracking_to_firebase(user_id: int, item_data: dict):
    """Сохраняет товар для отслеживания в Firebase."""
    try:
        user_ref = db.reference(f"ozon_prices/{user_id}/tracked_items")
        current_items = user_ref.get() or []

        # Опционально: Предотвращение дублирования URL или обновление существующих
        existing_item_index = -1
        for i, existing_item in enumerate(current_items):
            if existing_item.get("url") == item_data["url"]:
                existing_item_index = i
                break
        
        if existing_item_index != -1:
            # Обновляем существующий элемент
            # Заменяем старые данные отслеживания новыми для того же URL
            current_items[existing_item_index] = item_data 
            logger.info(f"Обновлен товар {item_data['url']} для пользователя {user_id}")
        else:
            # Добавляем новый элемент
            current_items.append(item_data)
            logger.info(f"Добавлен новый товар {item_data['url']} для пользователя {user_id}")

        user_ref.set(current_items) # Сохраняем весь список обратно
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении отслеживания Ozon в Firebase: {e}")
        return False


def load_ozon_tracking_from_firebase(user_id: int):
    """Загружает все отслеживаемые товары Ozon для пользователя из Firebase."""
    try:
        user_ref = db.reference(f"ozon_prices/{user_id}/tracked_items")
        tracked_items = user_ref.get()

        if tracked_items is None:
            logger.info(f"Нет отслеживаемых товаров для пользователя {user_id}")
            return []
        
        logger.info(f"Загружено {len(tracked_items)} товаров для пользователя {user_id}")
        return tracked_items
    except Exception as e:
        logger.error(f"Ошибка при загрузке отслеживаемых товаров Ozon из Firebase: {e}")
        return []

def load_ozon_product_firebase(user_id: int, product_id: str):
    """Возвращает конкретный отслеживаемый товар по product_id для пользователя из Firebase."""
    try:
        user_ref = db.reference(f"ozon_prices/{user_id}/tracked_items/")
        tracked_items = user_ref.get()

        if not tracked_items:
            logger.info(f"Нет отслеживаемых товаров для пользователя {user_id}")
            return None

        for item in tracked_items:
            if item.get("item_id") == product_id:
                logger.info(f"Товар с ID {product_id} найден для пользователя {user_id}")
                return item

        logger.info(f"Товар с ID {product_id} не найден у пользователя {user_id}")
        return None

    except Exception as e:
        logger.error(f"Ошибка при загрузке товара Ozon из Firebase: {e}")
        return None


def delete_ozon_product_firebase(user_id: int, product_id: str) -> bool:
    """Удаляет конкретный отслеживаемый товар по product_id для пользователя из Firebase."""
    try:
        user_ref = db.reference(f"ozon_prices/{user_id}/tracked_items/")
        tracked_items = user_ref.get()

        if not tracked_items:
            logger.info(f"Нет отслеживаемых товаров для пользователя {user_id}")
            return False

        # Оставим только те товары, у которых item_id не равен product_id
        updated_items = [item for item in tracked_items if item.get("item_id") != product_id]

        # Обновим список в Firebase
        user_ref.set(updated_items)
        logger.info(f"Товар с ID {product_id} удалён для пользователя {user_id}")
        return True

    except Exception as e:
        logger.error(f"Ошибка при удалении товара Ozon из Firebase: {e}")
        return False


def update_ozon_tracking_item(user_id: str, item_id: str, updated_fields: dict) -> bool:
    try:
        from firebase_admin import db
        user_ref = db.reference(f"ozon_prices/{user_id}/tracked_items")
        current_items = user_ref.get() or []

        updated = False
        for item in current_items:
            if item.get("item_id") == item_id:
                item.update(updated_fields)  # Обновляем только нужные поля
                updated = True
                break

        if updated:
            user_ref.set(current_items)  # Сохраняем обратно весь список
            return True
        else:
            logger.warning(f"Товар с item_id={item_id} не найден у пользователя {user_id}")
            return False
    except Exception as e:
        logger.exception(f"Ошибка при обновлении отслеживаемого товара: {e}")
        return False


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
                user_contexts[int(user_id)] = deque(context_list, maxlen=150)

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
def save_publications_to_firebase(user_id, message_id, new_data):
    """Загружает актуальные данные перед сохранением, чтобы избежать перезаписи."""
    try:
        # Ссылка на путь пользователя и сообщения
        path = f"users_publications/{user_id}/{message_id}"
        ref = db.reference(path)

        # Получаем актуальные данные
        current_data = ref.get() or {}

        # Осторожное слияние: обновляем только те поля, где значение не None
        merged_data = current_data.copy()
        for k, v in new_data.items():
            if v is not None:
                merged_data[k] = v

        # Сохраняем обновлённые данные
        ref.set(merged_data)

    except Exception as e:
        logging.error(f"Ошибка при сохранении публикации {user_id}_{message_id} в Firebase: {e}")


def save_inline_query_to_firebase(user_id: int, query: str, response: str):
    """Сохраняет последний запрос и ответ пользователя (до 10 штук)"""
    try:
        ref = db.reference(f"neuro_search/{user_id}")
        current_data = ref.get() or []

        # Удаляем дубликаты по query
        current_data = [item for item in current_data if item.get("query") != query]

        # Добавляем новый запрос в начало списка
        current_data.insert(0, {"query": query, "response": response})

        # Ограничиваем 10 последними
        if len(current_data) > 10:
            current_data = current_data[:10]

        ref.set(current_data)
    except Exception as e:
        logging.error(f"Ошибка при сохранении inline запроса в Firebase: {e}")
def load_user_inline_queries(user_id: int) -> list[dict]:
    """Загружает последние 10 inline-запросов пользователя."""
    try:
        ref = db.reference(f"neuro_search/{user_id}")
        return ref.get() or []
    except Exception as e:
        logging.error(f"Ошибка при загрузке inline-запросов пользователя {user_id}: {e}")
        return []



def load_shared_publications():
    """Загружает общие публикации из Firebase."""
    try:
        ref = db.reference('shared_publications')
        return ref.get() or {}
    except Exception as e:
        logging.error(f"Ошибка при загрузке общих публикаций: {e}")
        return {}


def load_entire_database():
    """Загружает всю базу данных из Firebase."""
    try:
        ref = db.reference('/')
        return ref.get() or {}
    except Exception as e:
        logging.error(f"Ошибка при загрузке базы данных: {e}")
        return {}

def save_to_shared_publications(user_id: int, key: str, data: dict) -> None:
    ref = db.reference(f"shared_publications/{user_id}/{key}")
    ref.set(data)


def save_to_user_plants(user_id: int, scientific_name: str, data: dict) -> None:
    """Сохраняет информацию о растении в Firebase."""
    try:
        ref = db.reference(f"user_plants/{user_id}/{scientific_name}")
        ref.set(data)
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных о растении: {e}")

def save_to_user_mapplants(user_id: int, name: str, data: dict) -> None:
    """Сохраняет информацию о растении в Firebase."""
    try:
        # Разделяем данные на общие и уникальные
        common_data = {
            "Full_text": data.get("Full_text"),
            "Type": data.get("Type")
        }
        user_specific_data = {
            "coordinates": data.get("coordinates"),
            "img_url": data.get("img_url"),
            "user_full_text": data.get("user_full_text")
        }

        # Сохраняем общие данные в plants_info
        info_ref = db.reference(f"plants_info/{name}")
        info_ref.update(common_data)

        # Генерируем уникальный ключ для новой записи
        record_key = db.reference(f"map_plants/{user_id}/{name}").push().key

        # Добавляем уникальную запись для пользователя
        user_ref = db.reference(f"map_plants/{user_id}/{name}/{record_key}")
        user_ref.set(user_specific_data)

        logging.info(f"Добавлена новая запись для растения '{name}' у пользователя {user_id}.")
        return record_key
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных о растении: {e}")

def load_all_plants_data() -> dict:
    """Загружает данные о всех растениях всех пользователей из Firebase."""
    try:
        map_plants_ref = db.reference("map_plants")
        plants_info_ref = db.reference("plants_info")
        map_plants_data = map_plants_ref.get() or {}
        plants_info_data = plants_info_ref.get() or {}

        # Добавляем общую информацию к данным пользователей
        for user_id, plants in map_plants_data.items():
            for plant_name, records in plants.items():
                if plant_name in plants_info_data:
                    for record_key, record_data in records.items():
                        record_data.update(plants_info_data[plant_name])

        return map_plants_data
    except Exception as e:
        logging.error(f"Ошибка при загрузке данных о растениях: {e}")
        return {}




def update_to_user_mapplants(user_id: int, name: str, new_name: str, new_data: dict) -> None:
    """Переименовывает растение пользователя, обновляя существующие данные."""
    try:
        # Получаем ссылку на старое растение
        old_ref = db.reference(f"map_plants/{user_id}/{name}")
        old_data = old_ref.get() or {}
        
        if not old_data:
            logging.warning(f"Растение '{name}' не найдено у пользователя {user_id}.")
            return

        # Проверяем, существует ли new_name в plants_info
        info_ref = db.reference(f"plants_info/{new_name}")
        existing_info = info_ref.get() or {}

        # Если new_name отсутствует в plants_info, добавляем его
        if not existing_info:
            common_data = {
                "Full_text": new_data.get("Full_text"),
                "Type": new_data.get("Type")
            }
            info_ref.update(common_data)
            logging.info(f"Добавлена новая общая информация для растения '{new_name}'.")
        else:
            logging.info(f"Общая информация для растения '{new_name}' уже существует.")

        # Генерируем уникальный record_key для новой записи
        new_record_ref = db.reference(f"map_plants/{user_id}/{new_name}").push()
        record_key = new_record_ref.key

        # Подготавливаем новые пользовательские данные
        user_specific_data = {
            "coordinates": new_data.get("coordinates", old_data.get("coordinates")),
            "img_url": new_data.get("img_url", old_data.get("img_url"))
        }

        # Добавляем новую запись для new_name
        new_record_ref.set(user_specific_data)
        logging.info(f"Добавлена новая запись для растения '{new_name}' у пользователя {user_id}.")

        # Удаляем старую запись с name
        old_ref.delete()
        logging.info(f"Старая запись для растения '{name}' удалена у пользователя {user_id}.")

    except Exception as e:
        logging.error(f"Ошибка при обновлении данных о растении: {e}")


def delete_user_plant_record(user_id: int, name: str, record_key: str) -> None:
    """Удаляет конкретную запись о растении пользователя."""
    try:
        ref = db.reference(f"map_plants/{user_id}/{name}/{record_key}")
        if not ref.get():
            logging.warning(f"Запись '{record_key}' для растения '{name}' не найдена у пользователя {user_id}.")
            return
        ref.delete()
        logging.info(f"Запись '{record_key}' для растения '{name}' у пользователя {user_id} удалена.")
    except Exception as e:
        logging.error(f"Ошибка при удалении записи о растении: {e}")


def mark_watering(user_id: int) -> None:
    """Добавляет дату и время полива в Firebase."""
    try:
        ref = db.reference(f"user_plants/{user_id}/water_plants")
        current_time = datetime.now().strftime("%d.%m.%y %H:%M")

        # Получаем текущие записи, если они есть
        existing_records = ref.get()
        if existing_records is None:
            existing_records = []

        # Добавляем новую запись
        existing_records.append(current_time)
        ref.set(existing_records)

    except Exception as e:
        logging.error(f"Ошибка при добавлении даты полива: {e}")


def load_water_plants(user_id: int) -> list:
    """Загружает список дат поливки пользователя из Firebase."""
    try:
        ref = db.reference(f"user_plants/{user_id}/water_plants")
        water_plants = ref.get() or []
        return water_plants
    except Exception as e:
        logging.error(f"Ошибка при загрузке данных о поливке: {e}")
        return []




# Функция для получения всех токенов из Firebase
def get_all_tokens() -> list:
    try:
        ref_tokens = db.reference('Tokens/All_tokens')
        all_tokens = ref_tokens.get()
        if all_tokens:
            logging.info("Загружены API-ключи из Firebase")
            return all_tokens
        else:
            logging.warning("В Firebase нет API-ключей, используем локальные")
            return []
    except Exception as e:
        logging.error(f"Ошибка при получении токенов из Firebase: {e}")
        return []

# Функция для установки списка всех токенов
def set_all_tokens(tokens: list):
    try:
        ref_tokens = db.reference('Tokens/All_tokens')
        ref_tokens.set(tokens)
        logging.info("Обновлены API-ключи в Firebase")
    except Exception as e:
        logging.error(f"Ошибка при сохранении токенов в Firebase: {e}")

# Функция для получения последнего успешного токена
def get_last_successful_token() -> str:
    try:
        ref_last_token = db.reference('Tokens/LAST_SUCCESSFUL_TOKEN')
        last_token = ref_last_token.get()
        if last_token:
            logging.info(f"Последний успешный API-ключ: {last_token}")
            return last_token
        else:
            logging.warning("В Firebase нет последнего успешного API-ключа")
            return None
    except Exception as e:
        logging.error(f"Ошибка при получении последнего успешного API-ключа: {e}")
        return None

# Функция для установки последнего успешного токена
def set_last_successful_token(token: str):
    try:
        ref_last_token = db.reference('Tokens/LAST_SUCCESSFUL_TOKEN')
        ref_last_token.set(token)
        logging.info(f"Сохранен последний успешный API-ключ: {token}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении последнего успешного API-ключа: {e}")












def load_user_plants(user_id: int) -> dict:
    """Загружает информацию о растениях пользователя из Firebase, исключая water_plants."""
    try:
        ref = db.reference(f"user_plants/{user_id}")
        data = ref.get() or {}
        return {key: value for key, value in data.items() if key != "water_plants"}
    except Exception as e:
        logging.error(f"Ошибка при загрузке данных о растениях: {e}")
        return {}

def delete_user_plant(user_id: int, scientific_name: str) -> None:
    """Удаляет информацию о конкретном растении пользователя из Firebase."""
    try:
        ref = db.reference(f"user_plants/{user_id}/{scientific_name}")
        if ref.get():
            ref.delete()
            logging.info(f"Растение '{scientific_name}' удалено для пользователя {user_id}.")
        else:
            logging.warning(f"Растение '{scientific_name}' не найдено у пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при удалении растения '{scientific_name}': {e}")

def copy_to_shared_publications(user_id: int, key: str) -> bool:
    """Копирует публикацию из users_publications в shared_publications."""
    ref_users = db.reference(f"users_publications/{user_id}/{key}")
    ref_shared = db.reference(f"shared_publications/{user_id}/{key}")

    data = ref_users.get()
    if data:
        ref_shared.set(data)  # Копируем данные в shared_publications
        return True
    return False
from html import unescape
async def notify_owner_favorited(context: CallbackContext, owner_id: int, post_data: dict):
    """Отправляет владельцу уведомление о добавлении его поста в избранное при достижении 3+ пользователей."""
    try:
        caption = post_data["media"][0]["caption"]
        logger.info(f"caption: {caption}")        
        caption = re.sub(r"<.*?>", "", caption)  # Убираем HTML-теги
        caption = unescape(caption)  # Декодируем HTML-сущности
        caption = re.split(r"\bseed\b", caption, flags=re.IGNORECASE)[0]  # Обрезаем по "seed"
        caption = re.sub(r"^\d+,\s*", "", caption)  # Убираем числа в начале строки
        
        # Обрезаем caption до ближайшего пробела перед 23 символами
        if len(caption) > 26:
            cutoff = caption[:26].rfind(" ")
            caption = caption[:cutoff] if cutoff != -1 else caption[:26]
        
        message_text = f"🎉 Поздравляем, вашу публикацию «{caption}» добавили в избранное 3 или более человек!"

        # Отправляем сообщение владельцу
        await context.bot.send_message(chat_id=owner_id, text=message_text)
    
    except Exception as e:
        logger.info(f"Ошибка при отправке уведомления владельцу: {e}")


def add_to_favorites(user_id: int, owner_id: int, post_id: str, context: CallbackContext) -> bool:
    """Добавляет или удаляет публикацию из избранного пользователя."""
    ref = db.reference(f"shared_publications/{owner_id}/{post_id}/favorites")
    favorites = ref.get() or []

    if user_id in favorites:
        favorites.remove(user_id)  # Удаляем из избранного
        ref.set(favorites)
        return False  # Удалён
    else:
        favorites.append(user_id)  # Добавляем в избранное
        ref.set(favorites)

        # Загружаем данные о посте и проверяем количество избранных
        publications = load_shared_publications()
        post_data = publications.get(owner_id, {}).get(post_id)
        logger.info(f"post_data {post_data} ")

        if post_data and len(favorites) >= 3:  # Проверяем, достигло ли число 3+
            asyncio.create_task(notify_owner_favorited(context, owner_id, post_data))

        return True  # Добавлен




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
            
            # Если у пользователя больше нет публикаций, удаляем его из базы полностью
            if not current_data[user_id]:
                del current_data[user_id]

                # Явное удаление узла пользователя в Firebase
                ref = db.reference(f'users_publications/{user_id}')
                ref.delete()  # Полностью удаляет данные пользователя

            else:
                # Обновляем базу только если у пользователя остались записи
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

def save_twitter_keys_to_firebase(user_id: int, api_key: str, api_secret: str, access_token: str, access_token_secret: str) -> None:
    """
    Сохраняет ключи API и токены доступа для публикации в Twitter в Firebase.
    """
    try:
        ref = db.reference(f'users_publications/twitter_keys/{user_id}')
        ref.set({
            "api_key": api_key,
            "api_secret": api_secret,
            "access_token": access_token,
            "access_token_secret": access_token_secret,
        })
        logging.info(f"Twitter API ключи успешно сохранены для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении Twitter API ключей: {e}")
        raise  # Передаем ошибку выше для обработки в вызывающей функции


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


def get_user_model(user_id: int) -> str:
    """Возвращает модель пользователя из Firebase или значение по умолчанию."""
    try:
        ref_models = db.reference(f'user_models/{user_id}')
        user_model = ref_models.get()

        if user_model:
            logging.info(f"Модель для пользователя {user_id}: {user_model}")
            return user_model
        else:
            logging.warning(f"Модель для пользователя {user_id} не найдена. Используется значение по умолчанию.")
            return "imagen3"
    except Exception as e:
        logging.error(f"Ошибка при загрузке модели для пользователя {user_id}: {e}")
        return "imagen3"

def set_user_model(user_id: int, model: str):
    """Устанавливает пользовательскую модель и сохраняет её в Firebase."""
    try:
        ref_models = db.reference(f'user_models/{user_id}')
        ref_models.set(model)
        logging.info(f"Модель пользователя {user_id} обновлена на: {model}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении модели в Firebase: {e}")
        
def get_user_preset(user_id: int) -> str:
    """Возвращает выбранный пресет пользователя из Firebase или значение по умолчанию."""
    try:
        ref_preset = db.reference(f'user_presets/{user_id}')
        user_preset = ref_preset.get()
        if user_preset:
            logging.info(f"Пресет для пользователя {user_id}: {user_preset}")
            return user_preset
        else:
            logging.warning(f"Пресет для пользователя {user_id} не найден. Используется значение по умолчанию.")
            return "Нет"
    except Exception as e:
        logging.error(f"Ошибка при загрузке пресета для пользователя {user_id}: {e}")
        return "Нет"

def set_user_preset(user_id: int, preset: str):
    """Устанавливает пользовательский пресет и сохраняет его в Firebase."""
    try:
        ref_preset = db.reference(f'user_presets/{user_id}')
        ref_preset.set(preset)
        logging.info(f"Пресет пользователя {user_id} обновлен на: {preset}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении пресета в Firebase: {e}")

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
    user_roles[user_id].pop("default_role", None)
    user_roles[user_id].pop("game_role", None)  # Удаляем default_role, если он существует

    save_context_to_firebase(user_id)  # Сохраняем изменения в Firebase





async def generate_image_description(user_id, image_path, query=None, use_context=True):
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если у пользователя есть игровая роль, она имеет приоритет над дефолтной
    game_role_key = user_roles_data.get("game_role")
    if game_role_key and game_role_key in GAME_ROLES:
        selected_role = GAME_ROLES[game_role_key]["full_description"]

    # Если пользователь выбрал новую роль, она имеет наивысший приоритет
    if "selected_role" in user_roles_data:
        selected_role = user_roles_data["selected_role"]

    # Если нет ни роли по умолчанию, ни пользовательской роли
    if not selected_role:
        selected_role = "Ты обычный вариант модели Gemini реализованный в виде телеграм бота, помогаешь пользователю выполнять различные задачи и выполняешь его поручения. В боте есть кнопка выбор роли, сообщи об этом пользователю если он поинтересуется. Так же ты умеешь рисовать и дорисовывать изображения. Для того чтобы ты что-то нарисовал, тебе нужно прислать сообщение которое начинается со слово \"Нарисуй\". Чтобы ты изменил, обработал или дорисовал изображение, тебе нужно отправить исходное сообщение с подписью начинающейся с \"Дорисуй\", так же сообщи об этом пользователю если он будет спрашивать."

    # Формируем system_instruction с user_role и relevant_context
    relevant_context = await get_relevant_context(user_id)
    # Исключаем дубли текущего сообщения в relevant_context
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()


    # Формируем system_instruction с user_role и relevant_context
    relevant_context = await get_relevant_context(user_id) if use_context else ""
       
    system_instruction = (
        f"Ты чат-бот играющий роль: {selected_role}. Эту роль задал тебе пользователь и ты должен строго её придерживаться. "
    )

    # Исключаем дубли текущего сообщения в relevant_context
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()

    # Формируем контекст с текущим запросом
    context = (
        f"Предыдущий контекст вашего диалога: {relevant_context if relevant_context else 'отсутствует.'}"        
        f"Собеседник прислал тебе изображение "     
        f" С подписью:\n{query}"
        if query else
        " Отреагируй на это изображение в контексте чата"
    )


    try:
        # Загрузка изображения в Gemini
        try:
            image_file = client.files.upload(file=pathlib.Path(image_path))
        except Exception as e:
            logger.error(f"Ошибка при загрузке изображения: {e}")
            return "Не удалось загрузить изображение."

        logger.info(f"Изображение загружено: {image_file.uri}")

        # Настройки безопасности
        safety_settings = [
            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
        ]

        # Генерация ответа от модели Gemini
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=image_file.uri,
                            mime_type=image_file.mime_type
                        ),
                        types.Part(text=f"Пользователь прислал изображение: {context}\n"),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,                
                temperature=1.0,
                top_p=0.9,
                top_k=40,
                #max_output_tokens=5000,
                #presence_penalty=0.6,
                #frequency_penalty=0.6,
                safety_settings=safety_settings
            )
        ) 
        # Проверяем наличие ответа
        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()

            return response_text
        else:
            logger.warning("Gemini не вернул ответ на запрос для изображения.")
            return "Извините, я не смог распознать изображение."

    except Exception as e:
        logger.error("Ошибка при распознавании изображения: %s", e)
        return "Произошла ошибка при обработке изображения. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'image_path' in locals() and os.path.exists(image_path):
            try:
                os.remove(image_path)
                logger.info(f"Временный файл удален: {image_path}")
            except Exception as e:
                logger.error(f"Ошибка при удалении временного файла: {e}")


async def get_relevant_context(user_id):
    """Получает контекст для пользователя."""
    context = user_contexts.get(user_id, deque(maxlen=150))
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
        user_contexts[user_id] = deque(maxlen=150)  # Максимум 150 сообщений
    
    # Добавляем 3 часа к текущему времени
    timestamp = (datetime.now() + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{timestamp} | {message_type}: {message}"
    
    if entry not in user_contexts[user_id]:
        user_contexts[user_id].append(entry)



async def generate_gemini_inline_response(query: str) -> str:
    """Генерирует краткий ответ от Gemini для инлайн-запроса."""
    system_instruction = (
        "Ты умная и лаконичная нейросеть для вывода быстрых ответов в инлайн-телеграм боте. Отвечай кратко, по сути запроса и по существу, избегая вводных фраз и лишних размышлений. Длинные ответы давай только когда это действительно требуется"
    )

    context = (
        f"Текущий запрос:\n{query}"
    )

    try:
        google_search_tool = Tool(
            google_search=GoogleSearch()
        )        
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash-lite-preview-06-17',
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=1.3,
                top_p=0.95,
                top_k=20,
                tools=[google_search_tool],                
                max_output_tokens=7000,
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                ]
            )
        )
        if response.candidates and response.candidates[0].content.parts:
            full_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text
            ).strip()
            return full_text
        else:
            return "Извините, не удалось получить ответ."
    except Exception as e:
        logger.error("Ошибка в generate_gemini_inline_response: %s", e)
        return "Произошла ошибка. Попробуйте позже."



async def generate_animation_response(video_file_path, user_id, query=None):
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если у пользователя есть игровая роль, она имеет приоритет над дефолтной
    game_role_key = user_roles_data.get("game_role")
    if game_role_key and game_role_key in GAME_ROLES:
        selected_role = GAME_ROLES[game_role_key]["full_description"]

    # Если пользователь выбрал новую роль, она имеет наивысший приоритет
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
    command_text = (
        f"Ты в чате играешь роль: {selected_role}. "
        f"Предыдущий контекст вашего диалога: {relevant_context if relevant_context else 'отсутствует.'}"        
        f"Собеседник прислал тебе гиф-анимацию, ответь на эту анимацию в контексте беседы, либо просто опиши её "             
    )


    try:

        # Проверяем существование файла
        if not os.path.exists(video_file_path):
            return "Видео недоступно. Попробуйте снова."

        # Загрузка файла через API Gemini
        video_path = pathlib.Path(video_file_path)

        try:
            video_file = client.files.upload(file=video_path)
        except Exception as e:
            return "Не удалось загрузить видео. Попробуйте снова."

        # Ожидание обработки видео
        while video_file.state == "PROCESSING":
            await asyncio.sleep(10)
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
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
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
                #presence_penalty=0.5,
                #frequency_penalty=0.5,
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
        bot_response = ''.join(part.text for part in response.candidates[0].content.parts if part.text).strip()

                             
        return bot_response

    except FileNotFoundError as fnf_error:
        logging.error(f"Файл не найден: {fnf_error}")
        return "Видео не найдено. Проверьте путь к файлу."

    except Exception as e:
        logging.error("Ошибка при обработке видео с Gemini:", exc_info=True)
        return "Ошибка при обработке видео. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'video_file_path' in locals() and os.path.exists(video_file_path):
            try:
                os.remove(video_file_path)
                logger.info(f"Временный файл удален: {video_file_path}")
            except Exception as e:
                logger.error(f"Ошибка при удалении временного файла: {e}")





async def generate_video_response(video_file_path, user_id, query=None):
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если у пользователя есть игровая роль, она имеет приоритет над дефолтной
    game_role_key = user_roles_data.get("game_role")
    if game_role_key and game_role_key in GAME_ROLES:
        selected_role = GAME_ROLES[game_role_key]["full_description"]

    # Если пользователь выбрал новую роль, она имеет наивысший приоритет
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



    try:

        try:
            video_file = client.files.upload(file=pathlib.Path(video_file_path))
        except Exception as e:
            logger.error(f"Ошибка при загрузке изображения: {e}")
            return "Не удалось загрузить изображение."


        # Ожидание обработки видео
        while video_file.state == "PROCESSING":

            await asyncio.sleep(10)
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
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
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
                #presence_penalty=0.5,
                #frequency_penalty=0.5,
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
        bot_response = ''.join(part.text for part in response.candidates[0].content.parts if part.text).strip()
                  
        return bot_response

    except FileNotFoundError as fnf_error:
        logging.error(f"Файл не найден: {fnf_error}")
        return "Видео не найдено. Проверьте путь к файлу."

    except Exception as e:
        logging.error("Ошибка при обработке видео с Gemini:", exc_info=True)
        return "Ошибка при обработке видео. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'video_file_path' in locals() and os.path.exists(video_file_path):
            try:
                os.remove(video_file_path)
                logger.info(f"Временный файл удален: {video_file_path}")
            except Exception as e:
                logger.error(f"Ошибка при удалении временного файла: {e}")

async def generate_document_response(document_path, user_id, query=None):
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если у пользователя есть игровая роль, она имеет приоритет над дефолтной
    game_role_key = user_roles_data.get("game_role")
    if game_role_key and game_role_key in GAME_ROLES:
        selected_role = GAME_ROLES[game_role_key]["full_description"]

    # Если пользователь выбрал новую роль, она имеет наивысший приоритет
    if "selected_role" in user_roles_data:
        selected_role = user_roles_data["selected_role"]


    # Если нет ни роли по умолчанию, ни пользовательской роли
    if not selected_role:
        selected_role = "роль не выбрана, попроси пользователя придумать или выбрать роль"

    relevant_context = await get_relevant_context(user_id)
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()

    context = (
        f"Ты телеграм чат-бот, сейчас ты играешь роль {selected_role}. Собеседник прислал тебе документ с подписью:\n{query}"
        f"Предыдущий контекст вашей переписки:\n{relevant_context}"            
    )

    command_text = context 



    try:
        if not os.path.exists(document_path):
            logging.error(f"Файл {document_path} не существует.")
            return "Документ недоступен. Попробуйте снова."

        file_extension = os.path.splitext(document_path)[1].lower()
        logging.info(f"file_extension: {file_extension}")


        document_path_obj = pathlib.Path(document_path)
        try:
            file_upload = client.files.upload(file=document_path_obj)
        except Exception as e:
            print(f"Error uploading file: {e}")
            return None

        google_search_tool = Tool(google_search=GoogleSearch())
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
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
                command_text
            ],
            config=types.GenerateContentConfig(
                temperature=1.4,
                #max_output_tokens=10000,                
                top_p=0.95,
                top_k=25,
                #presence_penalty=0.7,
               # frequency_penalty=0.7,
                tools=[google_search_tool],
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')
                ]
            )
        )
        if not response.candidates or not response.candidates[0].content.parts:
            return "Извините, я не могу обработать этот документ."

        bot_response = ''.join(part.text for part in response.candidates[0].content.parts if part.text).strip()

        return bot_response

    except FileNotFoundError as fnf_error:
        logging.info(f"Файл не найден: {fnf_error}")
        return "Документ не найден. Проверьте путь к файлу."

    except Exception as e:
        logging.info("Ошибка при обработке документа с Gemini:", exc_info=True)
        return "Ошибка при обработке документа. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'document_path' in locals() and os.path.exists(document_path):
            try:
                os.remove(document_path)
                logger.info(f"Временный файл удален: {document_path}")
            except Exception as e:
                logger.error(f"Ошибка при удалении временного файла: {e}")



async def generate_audio_response(audio_file_path, user_id, query=None):
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если у пользователя есть игровая роль, она имеет приоритет над дефолтной
    game_role_key = user_roles_data.get("game_role")
    if game_role_key and game_role_key in GAME_ROLES:
        selected_role = GAME_ROLES[game_role_key]["full_description"]

    # Если пользователь выбрал новую роль, она имеет наивысший приоритет
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
    command_text = context if query else "Распознай текст в аудио. Если текста нет или распознать его не удалось то опиши содержимое."




    try:

        try:
            audio_file = client.files.upload(file=pathlib.Path(audio_file_path))
        except Exception as e:
            logger.error(f"Ошибка при загрузке изображения: {e}")
            return "Не удалось загрузить изображение."

        if not command_text:
            command_text = "распознай текст либо опиши содержание аудио, если текста нет."



        # Генерация ответа через Gemini
        google_search_tool = Tool(
            google_search=GoogleSearch()
        )      
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=audio_file.uri,
                            mime_type=audio_file.mime_type
                        )
                    ]
                ),
                command_text  # Здесь будет ваш текст команды
            ],
            config=types.GenerateContentConfig(
                temperature=1.4,
                top_p=0.95,
                top_k=25,
                #max_output_tokens=30000,
                #presence_penalty=0.7,
                #frequency_penalty=0.7,
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
        logger.info("Ответ от Gemini: %s", response)
        # Извлечение текста ответа
        bot_response = ''.join(part.text for part in response.candidates[0].content.parts if part.text).strip()
        logger.info("Ответ от Gemini: %s", bot_response)              
        return bot_response

    except FileNotFoundError as fnf_error:
        logging.info(f"Файл не найден: {fnf_error}")
        return "Аудиофайл не найден. Проверьте путь к файлу."

    except Exception as e:
        logging.info("Ошибка при обработке аудиофайла с Gemini:", exc_info=True)
        return "Ошибка при обработке аудиофайла. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'audio_file_path' in locals() and os.path.exists(audio_file_path):
            try:
                os.remove(audio_file_path)
                logger.info(f"Временный файл удален: {audio_file_path}")
            except Exception as e:
                logger.error(f"Ошибка при удалении временного файла: {e}")








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
    "Role12": {
        "short_name": "Ремонтник",
        "full_description": "Ты эксперт по бытовому ремонту. Ты помогаешь пользователю справляться с повседневными проблемами: починить кран, устранить течь, заменить розетку или починить дверь. Ты даешь подробные, понятные инструкции и советы, как правильно и безопасно выполнить ремонтные работы в доме. Ты также подсказываешь, какие инструменты и материалы лучше использовать."
    },
    "Role13": {
        "short_name": "Историк",
        "full_description": "Ты знаток истории. Ты рассказываешь пользователю о ключевых событиях прошлого, объясняешь их причины и последствия, помогаешь понимать исторические процессы. Ты знаешь много интересных фактов и можешь анализировать историю с разных точек зрения. Ты также помогаешь разбираться в исторических источниках и оценивать их достоверность."
    },
    "Role14": {
        "short_name": "Ботаник",
        "full_description": "Ты эксперт в области ботаники. Ты помогаешь пользователю разбираться в растениях, их строении, классификации и среде обитания. Ты даешь советы по уходу за растениями, их размножению и защите от болезней. Ты также знаешь о лекарственных и ядовитых растениях, их свойствах и использовании в медицине и кулинарии."
    },
    "Role15": {
        "short_name": "Грибник",
        "full_description": "Ты знаток грибов. Ты помогаешь пользователю определять съедобные и ядовитые грибы, рассказываешь, где и когда их лучше собирать. Ты объясняешь, как правильно обрабатывать грибы, чтобы они были безопасными для употребления. Ты также знаешь интересные факты о грибах и их роли в экосистеме."
    },
    "Role16": {
        "short_name": "Зоопсихолог",
        "full_description": "Ты специалист по поведению животных. Ты помогаешь пользователю понимать эмоции и поступки домашних питомцев, решать проблемы с их поведением и налаживать гармоничные отношения между человеком и животным. Ты даешь советы по адаптации животных, обучению и коррекции нежелательного поведения."
    },
    "Role17": {
        "short_name": "Ветеринар",
        "full_description": "Ты опытный ветеринар. Ты помогаешь пользователю разбираться в здоровье домашних животных, распознавать симптомы болезней и давать советы по уходу. Ты объясняешь, когда нужно срочно обратиться к врачу и какие профилактические меры помогут питомцу оставаться здоровым. Ты также даешь рекомендации по питанию, вакцинации и содержанию животных."
    },    
    "Role19": {
        "short_name": "Терапевт",
        "full_description": "Ты терапевт, твоя цель - задавать уточняющие вопросы касательно здоровья собеседника стараясь таким образом максимально сузить список возможных болезней. Сначала ты даёшь короткие общие предположения и задаёшь много вопросов, когда возможных вариантов остаётся мало, даёшь подробное описание возможных болезней или недугов."
    },
    "Role20": {
        "short_name": "Компьютерщик",
        "full_description": "Ты мастер по ремонту компьютеров. Сначала ты задаёшь собеседнику вопросы касательно проблемы с компьютером или оборудованием стараясь сузить список возможных проблем, затем когда список сужен стараешься объяснить причину проблему и решить её если это возможно"
    },     
}

GAME_ROLES = {
    "Role100": {
        "short_name": "Акинатор",
        "full_description": "Ты ведущий игры. Пользователь загадывает известного персонажа, "
                            "ты же должен минимальным количеством вопросов отгадать, кого загадал пользователь. "
                            "Ты можешь задавать ровно один вопрос в каждом своём сообщении и ждать ответа пользователя на него. "
                            "Отвечать на твои вопросы пользователь может только \"да\", \"нет\", \"не знаю\". "
                            "В конечном счёте твоя цель - сначала задавать максимально общие вопросы, "
                            "чтобы сузить круг поиска насколько это возможно, и уже потом выдавать конкретные предположения. "
                            "Ты можешь только задавать вопрос, ровно один вопрос в каждом твоём сообщении. "
                            "Затем, когда у тебя будет достаточно сведений, пытаться выдвигать предложения. Ничего более. "
                            "Не используй конструкции вроде \"Бот ответил\" или timestamp с указанием времени, это служебная информация которая нужна только для истории чата ",
        "alert": "Вы загадываете персонажа, существо, реального человека. а бот пытается его отгадать\n\nДля использования игровых ролей рекомендуется сбросить историю диалога чтобы бот меньше путался"                     
    }, 
    "Role101": {
        "short_name": "Викторина",
        "full_description": "Ты — ведущий викторины, игры 'Кто хочет стать миллионером'. "
                            "Загадываешь игроку вопрос и предлагаешь 4 варианта ответа. За раз ты должен загадать ровно один вопрос и ждать пока игрок даст ответ на него, не подсказывая и не давая верный ответ. "
                            "Если игрок угадал верно, то загадываешь новый вопрос, сложнее прошлого и тоже даёшь 4 варианта ответа. "
                            "Всего 20 уровней сложности, где 1 - самые простые вопросы, 20 - самые сложные. "
                            "Если пользователь ответил неправильно, то ты называешь верный ответ, а прогресс сбрасывается на первый уровень сложности. "
                            "Старайся не повторяться в тематике вопросов. "        
                            "Не используй конструкции вроде \"Бот ответил\" или timestamp с указанием времени, это служебная информация которая нужна только для истории чата",
        "alert": "Бот даёт вопрос и 4 варианта ответа, вы выбираете один из них. Всего 20 уровней сложности, при ошибке прогресс сбрасывается.\n\nРекомендуется сбросить историю диалога чтобы бот меньше путался."                            
    },
    "Role102": {
        "short_name": "Своя игра",
        "full_description": "Ты — ведущий игры по аналогии с Jeopardy! или 'Своя игра'. "
                            "При первом обращении к тебе ты выдаёшь список тем вопросов в количестве 10 штук. "
                            "Пользователь называет тему и стоимость. "
                            "Всего есть 10 уровней сложности - 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, "
                            "где 100 - самые простые, 1000 - самые сложные. "
                            "Если пользователь верно отвечает на вопрос, ты начисляешь ему эти баллы, если ошибается - вычитаешь. "
                            "В конце каждого своего сообщения, после вопроса, присылай счёт игрока и оставшийся список тем. "                            
                            "Если пользователь пишет тебе слово 'заново', то счёт сбрасывается, и ты присылаешь новый список тем. "
                            "Старайся не повторять слишком похожие вопросы, например об одной и той же личности или одной и той же стране, за исключением случаев если это требует заданная тема. "        
                            "Не используй конструкции вроде \"Бот ответил\" или timestamp с указанием времени, это служебная информация которая нужна только для истории чата ",
        "alert": "Бот даёт 10 тем, у каждой темы 10 уровней сложности равных стоимости 100, 200, 300 итд. Вы выбираете тему и стоимость. В случае верного ответа очки начисляются, в случае ошибки вычитаются"                            
    },
    "Role103": {
        "short_name": "Что? Где? Когда?",
        "full_description": "Ты — ведущий игры 'Что? Где? Когда?'. "
                            "Твоя цель - задавать сложные логические вопросы. "
                            "Вопросы должны быть действительно сложными, но при этом к ответу на них должна быть возможность "
                            "прийти путём логических размышлений. "
                            "Собеседник называет ответы, ты говоришь, верный это ответ или нет. "
                            "Не используй конструкции вроде \"Бот ответил\" или timestamp с указанием времени, это служебная информация которая нужна только для истории чата",
        "alert": "Бот задаёт сложный вопрос к ответу на который обычно можно прийти логически\n\nДля использования игровых ролей рекомендуется сбросить историю диалога чтобы бот меньше путался"                            
    },  
    "Role104": {
        "short_name": "Правда или ложь",
        "full_description": "Ты — ведущий игры 'Правда или ложь'. "
                            "Твоя цель - придумывать утверждения, а собеседник должен отгадать, правдиво ли твоё утверждение или нет. Ты должен прислать ровно одно утверждение и ждать ответа игрока. Не должен сам писать правдиво оно или нет, это должен отгадать игрок. "
                            "Это могут быть как правдивые утверждения и факты, которые звучат странно или неправдоподобно, "
                            "так и наоборот - вполне реалистичные утверждения, которые являются ложью. "            
                            "Получив ответ игрока, сообщаешь ему верно он угадал или нет, а так же комментируешь своё предыдущее утверждение лаконичной и уместной репликой. Затем даёшь новое утверждение. " 
                            "Не давай слишком много утверждений одного типа подряд, старайся рандомно чередовать ложные и правдивые утверждения. Не страшно если 2, 3, 4 или даже 5 раз подряд будут например ложные, однако затем всё же должно последовать правдивое. Либо же смена может быть более частой, опять же выбирай рандомно. "                                                                     
                            "Не используй конструкции вроде \"Бот ответил\" или timestamp с указанием времени, это служебная информация которая нужна только для истории чата ",
        "alert": "Бот даёт утверждение вы отвечаете ему правда это или ложь\n\nДля использования игровых ролей рекомендуется сбросить историю диалога чтобы бот меньше путался"                            
    },   
    "role105": {
        "short_name": "Бредогенератор",
        "full_description": "Ты — ведущий игры 'Бредогенератор'. "
                            "Твоя цель - придумать необычное, на первый взгляд нелогичное, странное, бредово звучащее предложение. "
                            "Это может быть какое-то утверждение, описание события или что-то ещё. "
                            "Собеседник же должн логически объяснить то, что ты придумал, и сделать это наиболее правдоподобно. "
                            "Не используй конструкции вроде \"Бот ответил\" или timestamp с указанием времени, это служебная информация, которая нужна только для истории чата.",
        "alert": "Бот выдаёт очень странное утверждение, ваша задача придумать правдоподобное объяснение этого утверждения\n\nРекомендуется сбросить историю диалога чтобы бот меньше путался"                            
    },  
    "role106": {
        "short_name": "Крокодил",
        "full_description": "Ты — ведущий игры 'Крокодил'. "
                            "Текущее слово: {word}. Не называй его пользователю, он должен отгадать его сам, в этом и есть суть игры. "
                            "Собеседник отгадывает это слово, а ты отвечаешь 'да', 'нет' или 'не совсем'. Ты ни в коем случае не должен называть это слово, собеседник должен назвать его(либо очень близкое) сам"
                            "Обогащай свои сообщения короткими, не более 10-12 слов, комментариями или реакциями касательно предположений пользователя, делающими игру интереснее, разнообразнее и веселее. Не используй при этом смайлики. Но это не должны быть подсказки или что-то что явно указывает на заданное слово"        
                            "Однако если собеседник сам просит о подсказке, то можешь дать её, но не слишком явную и очевидную. Если собеседник говорит что сдаётся то можешь назвать слово."
                            "Не используй конструкции вроде \"Бот ответил\" или timestamp с указанием времени, это служебная информация которая нужна только для истории чата"
                            "Чтобы слово обновилось на новое пользователь должен отправить тебе одно из слов \"Дальше\" или \"Сбросить\", сообщи ему об этом если он будет спрашивать или не понимать"                            ,
        "alert": "Бот загадывает слово, вы должно отгадать это слово задавая боту вопросы на которые он может отвечать только Да или Нет. Для того чтобы бот загадал новое слово, отправьте ему \"Дальше\" или \"Сдаюсь\""                            
    },                      
}



chat_words = {}

async def generate_gemini_response(user_id, query=None, use_context=True):
    # Проверяем, выбрана ли роль по умолчанию или пользовательская роль
    user_roles_data = user_roles.get(user_id, {})
    selected_role = None

    # Проверяем наличие роли по умолчанию
    default_role_key = user_roles_data.get("default_role")
    if default_role_key and default_role_key in DEFAULT_ROLES:
        selected_role = DEFAULT_ROLES[default_role_key]["full_description"]

    # Если у пользователя есть игровая роль, она имеет приоритет над дефолтной
    game_role_key = user_roles_data.get("game_role")
    if game_role_key and game_role_key in GAME_ROLES:
        selected_role = GAME_ROLES[game_role_key]["full_description"]

    # Если пользователь выбрал новую роль, она имеет наивысший приоритет
    if "selected_role" in user_roles_data:
        selected_role = user_roles_data["selected_role"]

    # Если нет ни роли по умолчанию, ни пользовательской роли
    if not selected_role:
        selected_role = "Ты обычный вариант модели Gemini реализованный в виде телеграм бота, помогаешь пользователю выполнять различные задачи и выполняешь его поручения. В боте есть кнопка выбор роли, сообщи об этом пользователю если он поинтересуется. Так же ты умеешь рисовать и дорисовывать изображения. Для того чтобы ты что-то нарисовал, тебе нужно прислать сообщение которое начинается со слово \"Нарисуй\". Чтобы ты изменил, обработал или дорисовал изображение, тебе нужно отправить исходное сообщение с подписью начинающейся с \"Дорисуй\", так же сообщи об этом пользователю если он будет спрашивать."

    # Проверяем, выбрана ли роль "Крокодил"
    if game_role_key == "role106":
        chat_id = user_id  # или другой идентификатор чата
        if query and query.lower() in ["дальше", "сбросить"]:
            generated_text = await generate_word(chat_id)
            word = extract_random_word(generated_text)
            chat_words[chat_id] = word  # Обновляем слово
            response_text = "Слово изменено. Желательно(но не обязательно) сбросить при этом историю диалога чтобы бот меньше путался. Задавайте ваш вопрос касательно нового слова"
            return response_text           
        elif chat_id not in chat_words:
            generated_text = await generate_word(chat_id)
            word = extract_random_word(generated_text)
            chat_words[chat_id] = word  # Первоначальное слово
        else:
            word = chat_words[chat_id]  # Используем текущее слово

        selected_role = GAME_ROLES[game_role_key]["full_description"].format(word=word)

    # Формируем system_instruction с user_role и relevant_context
    relevant_context = await get_relevant_context(user_id) if use_context else ""
    system_instruction = (
        f"Ты чат-бот играющий роль: {selected_role}. Эту роль задал тебе пользователь и ты должен строго её придерживаться. "
        f"Конструкции вроде bot_response или user_send_text служат только для структурирования истории диалога, ни в коем случае не используй их в своих ответах"              
    )

    logging.info(f"system_instruction: {system_instruction}")
    # Исключаем дубли текущего сообщения в relevant_context
    if query and relevant_context:
        relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()

    # Формируем контекст с текущим запросом
    context = (
        f"Текущий запрос:\n{query}"   
        f"Сосредоточь особенное внимание именно на текущем запросе, контекст используй только по необходимости, когда это уместно"         
        f"Предыдущий контекст вашего диалога: {relevant_context if relevant_context else 'отсутствует.'}. "        
    )

    logger.info(f"context {context}")


    attempts = 3  # Количество попыток
    for attempt in range(attempts):
        try:
            # Создаём клиент с правильным ключом
            google_search_tool = Tool(
                google_search=GoogleSearch()
            )
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=context,  # Здесь передаётся переменная context
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,                
                    temperature=1.4,
                    top_p=0.95,
                    top_k=25,
                    #max_output_tokens=4500,
                    #presence_penalty=0.7,
                    #frequency_penalty=0.7,
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
            logging.info(f"response: {response}")
            if response.candidates and response.candidates[0].content.parts:
                response_text = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if part.text and not getattr(part, "thought", False)
                ).strip()



                return response_text
            else:
                logging.warning("Ответ от модели не содержит текстового компонента.")
                return "Извините, я не могу ответить на этот запрос."

        except Exception as e:
            logging.error(f"Ошибка при генерации ответа (попытка {attempt + 1}/{attempts}): {e}")
            if attempt < attempts - 1:
                await asyncio.sleep(4)  # Ожидание перед повторной попыткой

    return "Ошибка при обработке запроса. Попробуйте снова позже."


def limit_response_length(text):
    """Обрезает текст, если он слишком длинный для отправки в Telegram."""
    MAX_MESSAGE_LENGTH = 4096
    return text[:MAX_MESSAGE_LENGTH - 3] + '...' if len(text) > MAX_MESSAGE_LENGTH else text





async def generate_composition_comparison_response(user_id, images, query):
    """Сравнивает составы продуктов/вещей на фото и даёт совет по выбору."""
    system_instruction = (
        "Ты эксперт по анализу составов продуктов и вещей. "
        "Твоя задача: сравни составы на фото и дай краткий совет, что выбрать лучше и почему. "
        "Если продукты принципиально разные и их сравнивать некорректно – честно скажи об этом пользователю. "
        "Пиши очень лаконично, только полезные факты для выбора, без лишней информации, речевых оборотов и воды. "
        "Максимум 200 слов. "
        "Используй html-разметку, но исключительно ту что доступна в телеграм (<b>, <i>, <br>) если это улучшает читаемость."
    )

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)

        # Загружаем все изображения
        image_parts = []
        for image in images:
            with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                image.save(temp_file, format="JPEG")
                image_path = temp_file.name

            image_file = client.files.upload(file=pathlib.Path(image_path))
            image_parts.append(
                types.Part.from_uri(file_uri=image_file.uri, mime_type=image_file.mime_type)
            )

            os.remove(image_path)

        # Собираем запрос
        contents = [
            types.Content(
                role="user",
                parts=image_parts + [types.Part(text=f"Комментарий пользователя: {query}" if query else "")]
            )
        ]

        # Запрос к модели
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                ]
            )
        )

        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()
            return response_text or "Не удалось сравнить составы."
        else:
            return "Не удалось сравнить составы."

    except Exception as e:
        logging.error(f"Ошибка при анализе составов: {e}")
        return "Ошибка при обработке изображений. Попробуйте снова."



async def generate_mushrooms_multi_response(user_id, images, query):
    """Генерирует описание гриба на основе одного или нескольких изображений."""
    system_instruction = (
        "Определи что это за гриб (или грибы). Кратко расскажи о них, "
        "где растут и чаще всего встречаются, как выглядят, какие-то особенности, "
        "съедобны или нет, другую важную информацию. Если у тебя есть несколько вариантов – перечисли их. "
        "Если необходимо, используй html-разметку, доступную в Telegram. "
        "Суммарная длина текста не должна быть выше 300 слов."
    )

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())

        # Загружаем все изображения
        image_parts = []
        for image in images:
            with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                image.save(temp_file, format="JPEG")
                image_path = temp_file.name

            image_file = client.files.upload(file=pathlib.Path(image_path))
            image_parts.append(
                types.Part.from_uri(file_uri=image_file.uri, mime_type=image_file.mime_type)
            )

            # сразу удаляем локальный файл
            os.remove(image_path)

        # Собираем запрос
        contents = [
            types.Content(
                role="user",
                parts=image_parts + [types.Part(text=f"Уточнение от пользователя касательно гриба: {query}" if query else "")]
            )
        ]

        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=1.0,
                top_p=0.9,
                top_k=40,
                tools=[google_search_tool],
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                ]
            )
        )

        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()
            return response_text
        else:
            return "Не удалось определить гриб."

    except Exception as e:
        logging.error(f"Ошибка при анализе изображений: {e}")
        return "Ошибка при обработке изображений. Попробуйте снова."

async def generate_products_response(user_id, images, query):
    """
    Сравнивает продукты на одном или нескольких изображениях и советует лучший.
    """
    system_instruction = (
        "Твоя задача — помочь пользователю сделать выбор. "
        "Определи все товары или продукты на предоставленных фото. Используя информацию из интернета и отзывы, "
        "сравни их между собой. Посоветуй лучший из них. "
        "Если фото несколько, сравнивай товары со всех фотографий. "
        "Если на фото много товаров из разных категорий, выбери наиболее вероятную категорию для сравнения. "
        "Если все товары из разных категорий или по ним нет информации, укажи, что сравнение невозможно. "
        "Ответ должен быть очень кратким и лаконичным: просто лучший товар и почему он лучше (например, лучший состав, отзывы, качество)."
    )

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())

        # Загружаем все изображения
        image_parts = []
        for image in images:
            with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                image.save(temp_file, format="JPEG")
                image_path = temp_file.name

            image_file = client.files.upload(file=pathlib.Path(image_path))
            image_parts.append(
                types.Part.from_uri(file_uri=image_file.uri, mime_type=image_file.mime_type)
            )

            # Сразу удаляем локальный файл
            os.remove(image_path)

        # Собираем запрос
        prompt_text = "Сравни эти товары."
        if query:
            prompt_text += f" Особое внимание удели: {query}"
            
        contents = [
            types.Content(
                role="user",
                parts=image_parts + [types.Part(text=prompt_text)]
            )
        ]

        response = await client.aio.models.generate_content(
            model='gemini-1.5-flash', # Используем актуальную модель
            contents=contents,
            generation_config=types.GenerationConfig(
                temperature=0.5, # Температура чуть ниже для более фактического ответа
            ),
            system_instruction=system_instruction,
            tools=[google_search_tool],
            safety_settings=[
                types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
            ]
        )

        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if hasattr(part, "text") and part.text and not getattr(part, "thought", False)
            ).strip()
            return response_text
        else:
            return "Не удалось сравнить товары."

    except Exception as e:
        logging.error(f"Ошибка при анализе изображений товаров: {e}")
        return "Ошибка при обработке изображений. Попробуйте снова."


async def generate_calories_response(user_id, images, query):
    """Оценивает примерное количество калорий на фото с едой и даёт полезную информацию."""
    system_instruction = (
        "Ты нутрициолог и спортивный консультант. "
        "Твоя задача — кратко и по существу проанализировать фото с едой.\n\n"
        "Отвечай структурировано по пунктам:\n"
        "1. Определи продукты на фото (каждый отдельно).\n"
        "2. Укажи примерное количество калорий для каждого продукта.\n"
        "3. Дай итоговую сумму калорий всего блюда или нескольких блюд, набора продуктов.\n"
        "4. Добавь краткую оценку пользы/вреда с точки зрения здоровья.\n"
        "5. Скажи, сколько примерно минут/часов нужно тренироваться (ходьба, бег или фитнес), чтобы сжечь эту еду.\n"
        "6. Дай одно-два полезных замечания или лайфхака (например, чем можно заменить для меньшей калорийности).\n\n"
        "⚠️ Важно: пиши лаконично, без лишней воды. Используй короткие предложения, списки или таблицы.\n"
        "Если несколько фото — анализируй их все.\n"
        "Если что-то определить невозможно, пиши честно: «неопределимо»."
        "Используй html-разметку, но исключительно ту что доступна в телеграм (<b>, <i>, <br>) если это улучшает читаемость."        
    )

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())

        # Загружаем все изображения
        image_parts = []
        for image in images:
            with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                image.save(temp_file, format="JPEG")
                image_path = temp_file.name

            image_file = client.files.upload(file=pathlib.Path(image_path))
            image_parts.append(
                types.Part.from_uri(file_uri=image_file.uri, mime_type=image_file.mime_type)
            )

            os.remove(image_path)

        # Собираем запрос
        contents = [
            types.Content(
                role="user",
                parts=image_parts + [types.Part(text=f"Комментарий пользователя: {query}" if query else "")]
            )
        ]

        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.8,
                top_p=0.9,
                top_k=40,
                tools=[google_search_tool],
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                ]
            )
        )

        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()
            return response_text
        else:
            return "Не удалось оценить калорийность."

    except Exception as e:
        logging.error(f"Ошибка при анализе изображений: {e}")
        return "Ошибка при обработке изображений. Попробуйте снова."



async def generate_mapplants_response(user_id, image):
    """Генерирует текстовое описание проблемы с растением на основе изображения."""

    # Формируем статичный контекст для запроса
    context = (
        "Распознай растение на фото, по следующим пунктам:\n"
        "0) Что это. Гриб, растение, дерево, ягода. Этот пункт начни с фразы \"0)Это: \" В ответе напиши только одно слово из перечисленных, если ничего не подходит то напиши \"распознать не вышло\"\n"
        "1) Русскоязычные названия, от самого популярного до самых редких, если есть. Этот пункт начни с фразы \"1)Русские названия: \" В ответе перечисли только название или названия без лишних пояснений\n"
        "2) Общая краткая информация и описание, как выглядит, не длиннее 30 слов. Этот пункт начни с фразы \"2)Общая информация: \"\n"
        "3) Где обычно растёт, на какой территории и в какой местности, не длиннее 15 слов. Этот пункт начни с фразы \"3)Произрастает: \"\n"
        "4) Где и как применяется, ядовит или нет, не длиннее 20 слов. Этот пункт начни с фразы \"4)Применение: \"\n"
        "5) Дополнительная важная или интересная информация по этому растению, если есть. Этот пункт начни с фразы \"5)Дополнительно: \"\n\n"
        "Строго придерживайся заданного формата ответа, это нужно для того, чтобы корректно работал код программы.\n"
        "Никакого лишнего текста кроме заданных пунктов не пиши.\n"        
    )
    try:
        # Сохраняем изображение во временный файл
        with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            image_path = temp_file.name
            image.save(temp_file, format="JPEG")

        logging.info(f"Сохранено временное изображение: {image_path}")

        # Инициализация клиента Gemini
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())

        # Загрузка изображения
        try:
            image_file = client.files.upload(file=pathlib.Path(image_path))
        except Exception as e:
            logging.error(f"Ошибка при загрузке изображения: {e}")
            return "Не удалось загрузить изображение."

        logging.info(f"Изображение загружено: {image_file.uri}")
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
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=image_file.uri,
                            mime_type=image_file.mime_type
                        ),
                        types.Part(text=f"{context}\n"),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=1.0,
                top_p=0.9,
                top_k=40,
                #max_output_tokens=2000,
                #presence_penalty=0.6,
                #frequency_penalty=0.6,
                tools=[google_search_tool],
                safety_settings=safety_settings
            )
        )

        # Проверяем наличие ответа
        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()

            return response_text
        else:
            logging.warning("Gemini не вернул ответ на запрос для изображения.")
            return "Не удалось определить проблему растения."

    except Exception as e:
        logging.info(f"Ошибка при генерации описания проблемы растения: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'image_path' in locals() and os.path.exists(image_path):
            try:
                os.remove(image_path)
                logging.info(f"Временный файл удален: {image_path}")
            except Exception as e:
                logging.error(f"Ошибка при удалении временного файла: {e}")



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
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=context,  # Здесь передаётся переменная context
                config=types.GenerateContentConfig(               
                    temperature=1.4,
                    top_p=0.95,
                    top_k=25,
                    #max_output_tokens=2000,
                    #presence_penalty=0.7,
                    #frequency_penalty=0.7,
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
                response = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if part.text and not getattr(part, "thought", False)
                ).strip()
            
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
            # Сохраняем изображение во временный файл
            with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                image_path = temp_file.name
                image.save(temp_file, format="JPEG")

            logging.info(f"Сохранено временное изображение: {image_path}")

            # Инициализация клиента Gemini
            client = genai.Client(api_key=GOOGLE_API_KEY)
            google_search_tool = Tool(google_search=GoogleSearch())

            # Загрузка изображения
            try:
                image_file = client.files.upload(file=pathlib.Path(image_path))
            except Exception as e:
                logging.error(f"Ошибка при загрузке изображения: {e}")
                return "Не удалось загрузить изображение."
                
            safety_settings = [
                types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
            ]

            # Создание клиента и генерация ответа от модели
            client = genai.Client(api_key=GOOGLE_API_KEY)
            google_search_tool = Tool(google_search=GoogleSearch())        
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_uri(
                                file_uri=image_file.uri,
                                mime_type=image_file.mime_type
                            ),
                            types.Part(text=f"{context}\n"),
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=1.0,
                    top_p=0.9,
                    top_k=40,
                    #max_output_tokens=3000,
                    #presence_penalty=0.6,
                    #frequency_penalty=0.6,
                    tools=[google_search_tool],
                    safety_settings=safety_settings
                )
            )

            # Проверяем наличие ответа
            if response.candidates and response.candidates[0].content.parts:
                response_text = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if part.text and not getattr(part, "thought", False)
                ).strip()

                return response_text
            else:
                logging.warning("Gemini не вернул ответ на запрос для изображения.")
                return "Не удалось определить текст."

        except Exception as e:
            logging.info(f"Ошибка при генерации описания проблемы растения: {e}")
            return "Ошибка при обработке изображения. Попробуйте снова."
        finally:
            # Удаляем временный файл
            if 'image_path' in locals() and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logging.info(f"Временный файл удален: {image_path}")
                except Exception as e:
                    logging.error(f"Ошибка при удалении временного файла: {e}")
    else:
        return "Неверный запрос. Укажите изображение или текст для обработки."


async def generate_plant_issue_response(user_id, image, caption=None):
    """Генерирует текстовое описание проблемы с растением на основе изображения."""

    # Формируем статичный контекст для запроса
    context = ("Определи, что за проблема с растением (болезнь, вредители и т.д.) и предложи решение, ответ напиши на русском. Если необходимо используй html разметку доступную в telegram.")
    # Если есть подпись, добавляем её в запрос
    if caption:
        context += f"\n\nПользователь уточнил: {caption}"

    try:
        # Сохраняем изображение во временный файл
        with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            image_path = temp_file.name
            image.save(temp_file, format="JPEG")

        logging.info(f"Сохранено временное изображение: {image_path}")

        # Инициализация клиента Gemini
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())

        # Загрузка изображения
        try:
            image_file = client.files.upload(file=pathlib.Path(image_path))
        except Exception as e:
            logging.error(f"Ошибка при загрузке изображения: {e}")
            return "Не удалось загрузить изображение."

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
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=image_file.uri,
                            mime_type=image_file.mime_type
                        ),
                        types.Part(text=f"{context}\n"),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=1.0,
                top_p=0.9,
                top_k=40,
                #max_output_tokens=2000,
                #presence_penalty=0.6,
                #frequency_penalty=0.6,
                tools=[google_search_tool],
                safety_settings=safety_settings
            )
        )

        # Проверяем наличие ответа
        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()

            return response_text
        else:
            logging.warning("Gemini не вернул ответ на запрос для изображения.")
            return "Не удалось определить проблему растения."

    except Exception as e:
        logging.info(f"Ошибка при генерации описания проблемы растения: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'image_path' in locals() and os.path.exists(image_path):
            try:
                os.remove(image_path)
                logging.info(f"Временный файл удален: {image_path}")
            except Exception as e:
                logging.error(f"Ошибка при удалении временного файла: {e}")


async def response_animal(user_id, image, caption=None):
    """Определяет животное по фото и выдает краткую справку о нём."""

    # Формируем статичный контекст для запроса
    context = (
        "Определи, какое это животное (включая птиц, насекомых и иных живых существ) по изображению. "
        "Дай краткое описание на русском языке: его отличительные черты, среду обитания, чем питается, "
        "и интересные факты. Ответ сделай информативным, но кратким. "
        "Если необходимо, используй html-разметку, доступную в Telegram (например <b>, <i>, <u>, <a>)."
    )
    # Если есть подпись, добавляем её в запрос
    if caption:
        context += f"\n\nПользователь уточнил: {caption}"

    try:
        # Сохраняем изображение во временный файл
        with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            image_path = temp_file.name
            image.save(temp_file, format="JPEG")

        logging.info(f"Сохранено временное изображение: {image_path}")

        # Инициализация клиента Gemini
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())

        # Загрузка изображения
        try:
            image_file = client.files.upload(file=pathlib.Path(image_path))
        except Exception as e:
            logging.error(f"Ошибка при загрузке изображения: {e}")
            return "Не удалось загрузить изображение."

        # Настройки безопасности
        safety_settings = [
            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
        ]

        # Создание клиента и генерация ответа от модели
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=image_file.uri,
                            mime_type=image_file.mime_type
                        ),
                        types.Part(text=f"{context}\n"),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=1.0,
                top_p=0.9,
                top_k=40,
                tools=[google_search_tool],
                safety_settings=safety_settings
            )
        )

        # Проверяем наличие ответа
        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()

            return response_text
        else:
            logging.warning("Gemini не вернул ответ на запрос для изображения животного.")
            return "Не удалось определить животное."

    except Exception as e:
        logging.info(f"Ошибка при генерации описания животного: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'image_path' in locals() and os.path.exists(image_path):
            try:
                os.remove(image_path)
                logging.info(f"Временный файл удален: {image_path}")
            except Exception as e:
                logging.error(f"Ошибка при удалении временного файла: {e}")



async def response_ingredients(user_id, image):
    """Анализирует состав продукта или изделия по фото и выдает структурированный отчет."""

    # Формируем статичный контекст для запроса
    context = (
        "Проанализируй состав продукта или изделия по изображению с научной и обоснованной точки зрения. "
        "Используй актуальные научные данные и заслуживающие доверия источники. "
        "Будь по возможности предельно кратким и лаконичным, пиши только существенную и полезную информацию чтобы твой ответ можно было быстро прочитать, постарайся уместить весь ответ в 300 слов, максимум 400. "       
        "Твой ответ должен быть четко структурирован по следующим пунктам. "
        "Если какой-то пункт неприменим (например, продукт нельзя рассматривать с точки зрения пользы), укажи это.\n\n"
        "<b>1. Общая краткая характеристика:</b> Что это за продукт или изделие?\n"
        "<b>2. Анализ состава:</b> Разбери каждый компонент. Укажи его функцию (например, консервант, краситель, эмульгатор). Если компонент может быть вреден, вызывать аллергию или имеет другие важные особенности, отметь это.\n"
        "<b>3. Потенциальная польза:</b> Опиши возможную пользу данного продукта, если он съедобен то пользу для здоровья, основываясь на компонентах.\n"
        "<b>4. Потенциальный вред:</b> Опиши возможные риски и вред  связанные с данным продуктом, если он съедобен то например при чрезмерном употреблении или для определенных групп людей.\n"
        "<b>5. Общее качество продукта:</b> На основе анализа состава, дай общую оценку качества продукта (например, натуральный состав, много искусственных добавок и т.д.).\n"
        "<b>6. Выводы:</b> Сделай краткий итоговый вывод о продукте, стоит ли его покупать/употреблять.\n\n"
        "Ответ должен быть объективным и информативным. Используй html-разметку Telegram для форматирования (<b>, <i>, <u>)."
    )

    try:
        # Сохраняем изображение во временный файл
        with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            image_path = temp_file.name
            image.save(temp_file, format="JPEG")

        logging.info(f"Сохранено временное изображение: {image_path}")

        # Инициализация клиента Gemini
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())

        # Загрузка изображения
        try:
            image_file = client.files.upload(file=pathlib.Path(image_path))
        except Exception as e:
            logging.error(f"Ошибка при загрузке изображения: {e}")
            return "Не удалось загрузить изображение."

        # Настройки безопасности
        safety_settings = [
            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
        ]

        # Генерация ответа
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=image_file.uri,
                            mime_type=image_file.mime_type
                        ),
                        types.Part(text=f"{context}\n"),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.8,
                top_p=0.9,
                top_k=40,
                tools=[google_search_tool],
                safety_settings=safety_settings
            )
        )

        # Проверяем наличие текста в ответе
        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()
            return response_text
        else:
            logging.warning("Gemini не вернул ответ на запрос для анализа состава.")
            return "Не удалось проанализировать состав продукта."

    except Exception as e:
        logging.info(f"Ошибка при генерации анализа состава: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'image_path' in locals() and os.path.exists(image_path):
            try:
                os.remove(image_path)
                logging.info(f"Временный файл удален: {image_path}")
            except Exception as e:
                logging.error(f"Ошибка при удалении временного файла: {e}")


async def generate_barcode_response(user_id, image=None, query=None):
    context = "Найди в интернете отзывы об этом продукте и пришли в ответ краткую сводку о найденных положительных и отрицательных отзывах. Ответ разбей по категориям: \"0)Название товара: \" \n\n \"1)Оценка: */5 (с точностью до сотых) \nОбщее краткое впечатление: \" (не длиннее 35 слов, оценку сформулируй на основании полученных данных где 5 - наилучший товар)\n\n \"2)Положительные отзывы: \" что хвалят и почему(не длиннее 50 слов)\n\n \"3)Отрицательные отзывы: \" Чем недовольны и почему, постарайся выделить наиболее существенные претензии(не длиннее 70 слов)\n\n Строго придерживайся заданного формата ответа, это нужно для того, чтобы корректно работал код программы."
    try:
        # Сохраняем изображение во временный файл
        with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            image_path = temp_file.name
            image.save(temp_file, format="JPEG")

        logging.info(f"Сохранено временное изображение: {image_path}")

        # Инициализация клиента Gemini
        client = genai.Client(api_key=GOOGLE_API_KEY)
        google_search_tool = Tool(google_search=GoogleSearch())

        # Загрузка изображения
        try:
            image_file = client.files.upload(file=pathlib.Path(image_path))
        except Exception as e:
            logging.error(f"Ошибка при загрузке изображения: {e}")
            return "Не удалось загрузить изображение."
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
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=image_file.uri,
                            mime_type=image_file.mime_type
                        ),
                        types.Part(text=f"{context}\n"),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=1.0,
                top_p=0.9,
                top_k=40,
                #max_output_tokens=1000,
                #presence_penalty=0.6,
                #frequency_penalty=0.6,
                tools=[google_search_tool],
                safety_settings=safety_settings
            )
        )
        # Проверяем наличие ответа
        if response.candidates and response.candidates[0].content.parts:
            response_text = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()

            return response_text
        else:
            logging.warning("Gemini не вернул ответ на запрос для штрихкод.")
            return "Не удалось распознать штрихкод."

    except Exception as e:
        logging.info(f"Ошибка при генерации описания проблемы растения: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."
    finally:
        # Удаляем временный файл
        if 'image_path' in locals() and os.path.exists(image_path):
            try:
                os.remove(image_path)
                logging.info(f"Временный файл удален: {image_path}")
            except Exception as e:
                logging.error(f"Ошибка при удалении временного файла: {e}")

async def generate_barcode_analysis(user_id, query=None):
    """Генерирует текстовое описание проблемы с растением на основе текста."""

    # Если передан текстовый запрос
    if query:
        system_instruction = (
            f"На основании предоставленной информации определи название данного продукта. В ответ напиши только название и ничего более кроме названия."   
            f"Если информации недостаточно то сообщи об этом"            
        )
        context = (         
                f"Текущая доступная информация о продукте: {query}"    
        )

        try:
            # Создаём клиент с правильным ключом
            client = genai.Client(api_key=GOOGLE_API_KEY)
            google_search_tool = Tool(google_search=GoogleSearch()) 
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=context,  # Здесь передаётся переменная context
                config=types.GenerateContentConfig( 
                    system_instruction=system_instruction,                              
                    temperature=1.4,
                    top_p=0.95,
                    top_k=25,
                    #max_output_tokens=2000,
                    #presence_penalty=0.7,
                    #frequency_penalty=0.7,
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
                response = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if part.text and not getattr(part, "thought", False)
                ).strip()
          
                return response
            else:
                logging.warning("Ответ от модели не содержит текстового компонента.")
                return "Извините, ошибка обработки."
        except Exception as e:
            logging.error(f"Ошибка при генерации ответа: {e}")
            return "Ошибка при обработке запроса. Попробуйте снова."  


async def generate_barcode_otzyvy(user_id, query=None):
    """Генерирует текстовое описание проблемы с растением на основе текста."""

    # Если передан текстовый запрос
    if query:
        logging.info(f"query: {query}")          
        context = (         
                f"Найди в интернете отзывы о продукте {query}"    
        )

        try:
            # Создаём клиент с правильным ключом
            client = genai.Client(api_key=GOOGLE_API_KEY)
            google_search_tool = Tool(google_search=GoogleSearch()) 
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=context,  # Здесь передаётся переменная context
                config=types.GenerateContentConfig(                             
                    temperature=1.4,
                    top_p=0.95,
                    top_k=25,
                    #max_output_tokens=2000,
                    #presence_penalty=0.7,
                    #frequency_penalty=0.7,
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
                response = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if part.text and not getattr(part, "thought", False)
                ).strip()
                logging.info(f"response: {response}")            
                return response
            else:
                logging.warning("Ответ от модели не содержит текстового компонента.")
                return "Извините, ошибка обработки."
        except Exception as e:
            logging.error(f"Ошибка при генерации ответа: {e}")
            return "Ошибка при обработке запроса. Попробуйте снова."  


async def generate_plant_help_response(user_id, query=None):
    """Генерирует текстовое описание проблемы с растением на основе текста."""

    # Если передан текстовый запрос
    if query:
        # Формируем контекст с текущим запросом
        context = (         
                f"Запрос:\n{query}"     
        )
        logging.info(f"context: {context}")
        try:
            # Создаём клиент с правильным ключом
            client = genai.Client(api_key=GOOGLE_API_KEY)
            google_search_tool = Tool(google_search=GoogleSearch()) 
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=context,  # Здесь передаётся переменная context
                config=types.GenerateContentConfig(               
                    temperature=1.4,
                    top_p=0.95,
                    top_k=25,
                    #max_output_tokens=2000,
                    #presence_penalty=0.7,
                    #frequency_penalty=0.7,
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
            logging.info(f"response: {response}")       
            if response.candidates and response.candidates[0].content.parts:
                response = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if part.text and not getattr(part, "thought", False)
                ).strip()
            
                return response
            else:
                logging.warning("Ответ от модели не содержит текстового компонента.")
                return "Извините, я не могу ответить на этот запрос."
        except Exception as e:
            logging.error(f"Ошибка при генерации ответа: {e}")
            return "Ошибка при обработке запроса. Попробуйте снова."  



async def translate_promt_with_gemini(user_id, query=None):
    if query:
        # Проверяем наличие кириллических символов
        contains_cyrillic = bool(re.search("[а-яА-Я]", query))

        logger.info(f"Содержит кириллицу: {contains_cyrillic}")

        # Если кириллицы нет, возвращаем текст без изменений
        if not contains_cyrillic:
            return query

        # Если текст не на английском, переводим его
        context = (
            f"Ты бот для перевода промптов с русского на английский. Переведи запрос в качестве промпта для генерации изображения на английский язык. "
            f"В ответ пришли исключительно готовый промт на английском языке и ничего более. Это важно для того чтобы код корректно сработал. "
            f"Даже если запрос странный и не определённый, то переведи его и верни перевод. "
            f"Текущий запрос:\n{query}"
        )

        max_retries = 2  # Максимальное количество повторных попыток
        retry_delay = 3  # Задержка между попытками в секундах

        for attempt in range(max_retries + 1):  # Первая попытка + две повторные
            try:
                # Создаём клиент с правильным ключом
                client = genai.Client(api_key=GOOGLE_API_KEY)
                google_search_tool = Tool(google_search=GoogleSearch()) 
                response = await client.aio.models.generate_content(
                    model='gemini-2.5-flash-lite',
                    contents=context,  # Здесь передаётся переменная context
                    config=types.GenerateContentConfig(               
                        temperature=1.4,
                        top_p=0.95,
                        top_k=25,
                        #max_output_tokens=2000,
                        #presence_penalty=0.7,
                        #frequency_penalty=0.7,
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
                    response = "".join(
                        part.text for part in response.candidates[0].content.parts
                        if part.text and not getattr(part, "thought", False)
                    ).strip()
                
                    return response
                else:
                    logging.warning("Ответ от модели не содержит текстового компонента.")
                    return "Извините, я не могу ответить на этот запрос."

            except Exception as e:
                logging.error(f"Ошибка при генерации ответа (попытка {attempt + 1}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay)  # Ждём перед следующей попыткой
                else:
                    return "Ошибка при обработке запроса. Попробуйте снова."




async def generate_word(chat_id):

    context = (
        f"Твоя цель - сгенерировать 100 слов подходящая для игры в крокодил. Это должны быть как простые слова, так и какие-нибудь интересные слова которые достаточно сложно отгадать, но они должны быть общеизвестными. Они могут быть из любой области науки, культуры, общества, интернета и тд"
        f"Старайся избегать глаголов и имён собственных. "     
        f"Избегай повторов и схожих по смыслу слов. "            
        f"Эти слова должны быть знакомы большинству людей. "           
        f"В ответ пришли список слов в следующем формате: 1: слово1 2: слово2 3: слово3 и тд"     
    )
    try:
        # Создаём клиент с правильным ключом
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=context,  # Здесь передаётся переменная context
            config=types.GenerateContentConfig(
                temperature=1.7,
                top_p=0.9,
                top_k=40,
                #max_output_tokens=2500,
                #presence_penalty=1.0,
                #frequency_penalty=0.8,
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
            bot_response = "".join(
                part.text for part in response.candidates[0].content.parts
                if part.text and not getattr(part, "thought", False)
            ).strip()
            logger.info("Ответ от Gemini: %s", bot_response)
            return bot_response
        else:
            logger.warning("Gemini не вернул ответ на запрос.")
            # Проверяем, есть ли какие-либо дополнительные данные в response
            if hasattr(response, '__dict__'):
                logger.info("Содержимое response: %s", response.__dict__)
            else:
                logger.info("response не содержит атрибута __dict__. Тип объекта: %s", type(response))
            
            return "Извините, я не могу ответить на этот запрос."
    except Exception as e:
        logger.error("Ошибка при генерации ответа от Gemini: %s", e)
        return "Ошибка при обработке запроса. Попробуйте снова."

def extract_random_word(text: str) -> str:
    """Извлекает случайное слово из сгенерированного списка."""
    words = re.findall(r"\d+:\s*([\w-]+)", text)  # Ищем слова после номеров
    if not words:
        return "Ошибка генерации"
    return random.choice(words)





async def Generate_gemini_image(prompt):
    context = (
        f"{prompt}" 
    )        
    try:

        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=context,
            config=types.GenerateContentConfig(
                temperature=1,
                top_p=0.95,
                top_k=40,
                #max_output_tokens=10000,
                response_modalities=[
                    "image",
                    "text",
                ],
                safety_settings=[
                    types.SafetySetting(
                        category="HARM_CATEGORY_HARASSMENT",
                        threshold="BLOCK_NONE",  # Block none
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_HATE_SPEECH",
                        threshold="BLOCK_NONE",  # Block none
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        threshold="BLOCK_NONE",  # Block none
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_DANGEROUS_CONTENT",
                        threshold="BLOCK_NONE",  # Block none
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_CIVIC_INTEGRITY",
                        threshold="BLOCK_NONE",  # Block none
                    ),
                ],
                response_mime_type="text/plain",
            ),
        )

        captions = []
        image_urls = []
        for part in response.candidates[0].content.parts:
            # Текст и изображения могут быть в разных частях
            if part.text is not None:
                clean_caption = part.text.replace('\n', ' ').strip()[:1000]
                captions.append(clean_caption)

            if part.inline_data is not None:
                image = Image.open(BytesIO(part.inline_data.data))
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                    image.save(temp_file.name, format="PNG")
                    image_urls.append(temp_file.name)

        # Выводим данные для парсинга
        for i, url in enumerate(image_urls):
            print(f"===IMAGE_START==={i}===")
            print(url)
            print(f"===IMAGE_END==={i}===")

        for i, caption in enumerate(captions):
            print(f"===CAPTION_START==={i}===")
            print(caption)
            print(f"===CAPTION_END==={i}===")

        return captions, image_urls

    except Exception as e:
        logger.error(f"Ошибка при генерации изображения: {e}")
        return None, None 



async def generate_inpaint_gemini(image_file_path: str, instructions: str):
    """
    Загружает изображение в Google и отправляет его в Gemini для обработки.

    :param image_file_path: Локальный путь к изображению.
    :param instructions: Текстовая инструкция для обработки.
    :return: Байтовые данные обработанного изображения и текстовый ответ (если есть).
    """
    try:
        if not instructions:
            instructions = "Придумай как сделать это изображение интереснее."

        # Проверяем, существует ли файл
        if not os.path.exists(image_file_path):
            logger.error(f"Файл {image_file_path} не существует.")
            return None, "Ошибка: изображение не найдено."

        # Загружаем изображение в Google Gemini
        image_path = pathlib.Path(image_file_path)
        logger.info(f"Uploading image file: {image_path}")

        client = genai.Client(api_key=GOOGLE_API_KEY)

        try:
            image_file = client.files.upload(file=image_path)
            logger.info(f"image_file: {image_file}")            
        except Exception as e:
            logger.error(f"Ошибка при загрузке изображения: {e}")
            return None, "Не удалось загрузить изображение."

        logger.info(f"Image uploaded: {image_file.uri}")

        # Отправляем изображение в Gemini
        safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        ]

        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=image_file.uri,
                            mime_type=image_file.mime_type
                        ),
                        types.Part(text=instructions),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=1.0,
                top_p=0.95,
                top_k=40,
                response_modalities=["image", "text"],
                safety_settings=safety_settings,
            ),
        )


        if not response.candidates:
            logging.warning("Gemini вернул пустой список кандидатов.")
            return None, None

        first_candidate = response.candidates[0]
        if not hasattr(first_candidate, "content") or not first_candidate.content:
            logging.warning("Ответ Gemini не содержит контента.")
            return None, None
        
        if not hasattr(first_candidate.content, "parts") or not first_candidate.content.parts:
            logging.warning("Ответ Gemini не содержит частей контента.")
            return None, None

        captions = []
        image_urls = []
        for part in response.candidates[0].content.parts:
            # Текст и изображения могут быть в разных частях
            if part.text is not None:
                clean_caption = part.text.replace('\n', ' ').strip()[:1000]
                captions.append(clean_caption)

            if part.inline_data is not None:
                image = Image.open(BytesIO(part.inline_data.data))
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                    image.save(temp_file.name, format="PNG")
                    image_urls.append(temp_file.name)

        # Выводим данные для парсинга
        for i, url in enumerate(image_urls):
            print(f"===IMAGE_START==={i}===")
            print(url)
            print(f"===IMAGE_END==={i}===")

        for i, caption in enumerate(captions):
            print(f"===CAPTION_START==={i}===")
            print(caption)
            print(f"===CAPTION_END==={i}===")
        logger.info(f"image_urls: {image_urls}")
        return captions, image_urls

    except Exception as e:
        logger.error("Ошибка при обработке изображения с Gemini:", exc_info=True)
        return None, "Ошибка при обработке изображения."

