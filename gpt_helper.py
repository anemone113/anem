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

# Google API Key и модель Gemini
GOOGLE_API_KEY = "AIzaSyAEwA5U0CYCYiqjNZv451WlcAo2N6AbPMU"

genai.configure(api_key=GOOGLE_API_KEY)
model_config = {
    "temperature": 1.4,
    "max_output_tokens": 3000,
    "top_p": 0.9,
    "top_k": 25,
    "frequency_penalty": 0.7,
    "presence_penalty": 0.7
}

# Конфигурация логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Настройка Google Generative AI
safety_settings = [
    {
        'category': 'HARM_CATEGORY_HARASSMENT',
        'threshold': 'BLOCK_NONE',
    },
    {
        'category': 'HARM_CATEGORY_HATE_SPEECH',
        'threshold': 'BLOCK_NONE',
    },
    {
        'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT',
        'threshold': 'BLOCK_NONE',
    },
    {
        'category': 'HARM_CATEGORY_DANGEROUS_CONTENT',
        'threshold': 'BLOCK_NONE',
    },
]

model = genai.GenerativeModel('gemini-1.5-flash-002',
                                  generation_config=model_config,
                                  safety_settings=safety_settings
                                  )

# Инициализация Firebase
cred = credentials.Certificate('/etc/secrets/firebase-key.json')  # Путь к вашему JSON файлу
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://anemone-60bbf-default-rtdb.europe-west1.firebasedatabase.app/'  # Замените на URL вашей базы данных
})

# Хранилище для историй диалогов пользователей
user_contexts = {}

user_roles = {}

user_presets = {} 

user_models = {}

def load_context_from_firebase():
    """Загружает user_contexts, user_roles, пресеты и модели из Firebase."""
    global user_contexts, user_roles, user_presets, user_models
    try:
        ref_context = db.reference('user_contexts')
        ref_roles = db.reference('user_roles')
        ref_presets = db.reference('user_presets')
        ref_models = db.reference('user_models')

        # Загружаем контексты
        json_context = ref_context.get()
        if json_context:
            for user_id, context_list in json_context.items():
                user_contexts[int(user_id)] = deque(context_list, maxlen=500)

        # Загружаем роли
        json_roles = ref_roles.get()
        if json_roles:
            for user_id, role in json_roles.items():
                user_roles[int(user_id)] = role

        # Загружаем пресеты
        json_presets = ref_presets.get()
        if json_presets:
            user_presets.update({int(user_id): preset for user_id, preset in json_presets.items()})

        # Загружаем модели
        json_models = ref_models.get()
        if json_models:
            user_models.update({int(user_id): model for user_id, model in json_models.items()})

        logging.info("Контекст, роли, пресеты и модели успешно загружены из Firebase.")
    except Exception as e:
        logging.error(f"Ошибка при загрузке данных из Firebase: {e}")

def save_context_to_firebase():
    """Сохраняет user_contexts, user_roles, пресеты и модели в Firebase."""
    try:
        # Преобразуем deques в списки для сохранения в Firebase
        json_context = {user_id: list(context) for user_id, context in user_contexts.items()}
        ref_context = db.reference('user_contexts')
        ref_context.set(json_context)

        # Сохраняем роли
        ref_roles = db.reference('user_roles')
        ref_roles.set(user_roles)

        # Сохраняем пресеты
        ref_presets = db.reference('user_presets')
        ref_presets.set(user_presets)

        # Сохраняем модели
        ref_models = db.reference('user_models')
        ref_models.set(user_models)

        logging.info("Контекст, роли, пресеты и модели успешно сохранены в Firebase.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных в Firebase: {e}")

def get_user_preset(user_id: int) -> str:
    try:
        # Обращаемся к ветке Firebase, где хранятся пресеты
        ref_presets = db.reference('user_presets')
        user_presets = ref_presets.get()

        # Преобразуем user_id в строку, т.к. ключи Firebase обычно строки
        user_preset = user_presets.get(str(user_id))

        if user_preset:
            logging.info(f"Пресет для пользователя {user_id}: {user_preset}")
            return user_preset
        else:
            logging.warning(f"Пресет для пользователя {user_id} не найден. Используется значение по умолчанию.")
            return "None"
    except Exception as e:
        logging.error(f"Ошибка при загрузке пресета для пользователя {user_id}: {e}")
        return "None"


def set_user_presets(user_id, preset):
    """Устанавливает пользовательский пресет и сохраняет его в Firebase."""
    user_presets[user_id] = preset
    try:
        # Сохраняем пресеты в Firebase
        ref_presets = db.reference('user_presets')
        ref_presets.set({str(uid): p for uid, p in user_presets.items()})
        logging.info(f"Пресет пользователя {user_id} обновлён на: {preset}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении пресета в Firebase: {e}")

def get_user_model(user_id: int) -> str:
    """Возвращает модель пользователя из Firebase или значение по умолчанию."""
    try:
        ref_models = db.reference('user_models')
        user_models = ref_models.get()
        user_model = user_models.get(str(user_id))

        if user_model:
            logging.info(f"Модель для пользователя {user_id}: {user_model}")
            return user_model
        else:
            logging.warning(f"Модель для пользователя {user_id} не найдена. Используется значение по умолчанию.")
            return "animagineXLV3_v30.safetensors [75f2f05b]"
    except Exception as e:
        logging.error(f"Ошибка при загрузке модели для пользователя {user_id}: {e}")
        return "animagineXLV3_v30.safetensors [75f2f05b]"

def set_user_model(user_id, model):
    """Устанавливает пользовательскую модель и сохраняет её в Firebase."""
    user_models[user_id] = model
    try:
        ref_models = db.reference('user_models')
        ref_models.set({str(uid): m for uid, m in user_models.items()})
        logging.info(f"Модель пользователя {user_id} обновлена на: {model}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении модели в Firebase: {e}")

def set_user_role(user_id, role_text):
    """Устанавливает пользовательскую роль и сохраняет её в Firebase."""
    user_roles[user_id] = role_text
    save_context_to_firebase()  # Сохраняем новую роль
    logging.info(f"Роль пользователя {user_id} обновлена на: {role_text}")        

def generate_image_description(user_id, image):
    """Создает текстовое описание изображения и добавляет его в контекст пользователя."""
    # Преобразуем изображение в base64 для отправки в модель
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='JPEG')
    img_byte_arr = img_byte_arr.getvalue()
    image_b64 = base64.b64encode(img_byte_arr).decode('utf-8')

    # Формируем запрос для генерации описания
    input_data = [
        {"text": f"Описание на русском языке:"},
        {"mime_type": "image/jpeg", "data": image_b64}
    ]

    # Настройки безопасности для фильтрации вредоносного контента
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    try:
        # Запрос на генерацию описания через модель с настройками безопасности
        response = model.generate_content(
            {"parts": input_data},
            safety_settings=safety_settings
        )

        if hasattr(response, 'parts') and response.parts:
            description = response.parts[0].text.strip()
            logging.info(f"Сгенерировано описание для пользователя {user_id}: {description}")  # Логирование сгенерированного описания
            return description
        else:
            logging.warning("Ответ от модели не содержит текстового компонента для описания.")
            return "Не удалось сгенерировать описание изображения."
    except Exception as e:
        logging.error(f"Ошибка при генерации описания изображения: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."
        
def get_relevant_context(user_id):
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
    
    return '\n'.join([user_role] + unique_context)

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

def get_clean_response_text(response_text):
    """Удаляет метку времени и тип сообщения для отображения пользователю."""
    # Убираем метку времени и тип сообщения, если они есть
    parts = response_text.split('|', 1)
    if len(parts) > 1:
        clean_text = parts[1].split(':', 1)[-1].strip()  # Убираем тип сообщения
        return clean_text
    return response_text



def generate_gemini_response(user_id, query=None, text=None, image=None, use_context=True):
    user_role = user_roles.get(user_id, "")    
    input_data = [
        {"text": f"Тебе нужно придерживаться роль которая будет задана тебе далее, используй контекст беседы так же доступный тебе далее, отвечай на русском языке. Текущая роль: {user_role}"}
    ]

    logging.debug(f"Начало функции generate_gemini_response. user_id={user_id}, query={query}, text={text}, image={'есть' if image else 'нет'}, use_context={use_context}")

    # Добавляем контекст, если требуется
    if use_context:
        relevant_context = get_relevant_context(user_id)
        
        if query:
            # Исключаем из контекста дубли текущего сообщения
            relevant_context = relevant_context.replace(f"user_message: {query}", "").strip()
        
        if relevant_context:
            input_data.append({"text": f"История диалога: {relevant_context}"})
            logging.debug(f"Добавлен релевантный контекст: {relevant_context}")
        else:
            logging.debug("Релевантный контекст отсутствует.")

    # Добавляем запрос пользователя
    if query:
        input_data.append({"text": f"Текущий запрос пользователя: {query}"})
        if use_context:
            add_to_context(user_id, query, message_type="user_message")
        logging.debug(f"Добавлен запрос в input_data: {query}")

    # Добавляем текст, если передан
    if text:
        input_data.append({"text": text})
        if use_context:
            add_to_context(user_id, text, message_type="file_content")
        logging.debug(f"Добавлен текст в input_data: {text}")

    if image:
        # Генерация и сохранение описания изображения
        description = generate_image_description(user_id, image)  # Генерация описания изображения
        input_data.append({"text": description})
        if use_context:
            add_to_context(user_id, description, message_type="image_description")  # Добавляем описание изображения в контекст
        logging.debug(f"Добавлено описание изображения в input_data: {description}")


    logging.info(f"Отправка данных в Gemini: {json.dumps(input_data, ensure_ascii=False)}")

    # Настройки безопасности для фильтрации вредоносного контента
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    
    logging.debug(f"Настройки безопасности: {safety_settings}")

    try:
        # Запрос на генерацию ответа через модель
        response = model.generate_content(
            {"parts": input_data},
            safety_settings=safety_settings
        )
        logging.debug(f"Получен ответ от модели: {response}")
        
        if hasattr(response, 'parts') and response.parts:
            response_text = response.parts[0].text.strip()
            if use_context:
                add_to_context(user_id, response_text, message_type="bot_response")  # Добавляем ответ в контекст
                logging.debug(f"Ответ добавлен в контекст: {response_text}")
            
            save_context_to_firebase()
            logging.debug("Контекст успешно сохранен в Firebase.")
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


def generate_plant_issue_response(user_id, image):
    """Генерирует текстовое описание проблемы с растением на основе изображения."""
    
    # Преобразование изображения в base64 для передачи в модель
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG')
        img_byte_arr = img_byte_arr.getvalue()
        image_b64 = base64.b64encode(img_byte_arr).decode('utf-8')
        
        # Формируем данные для модели
        input_data = [
            {"text": "Определи, что за проблема с растением (болезнь, вредители и т.д.) и предложи решение, ответ напиши на русском:"},
            {"mime_type": "image/jpeg", "data": image_b64}
        ]
        logging.debug("Сформирован запрос для определения проблемы с растением.")

    except Exception as e:
        logging.error(f"Ошибка при преобразовании изображения: {e}")
        return "Ошибка при обработке изображения."

    # Настройки безопасности для модели
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    try:
        # Отправка данных в модель для генерации описания
        response = model.generate_content(
            {"parts": input_data},
            safety_settings=safety_settings
        )

        # Проверка на наличие ответа и возврат описания
        if hasattr(response, 'parts') and response.parts:
            description = response.parts[0].text.strip()
            logging.info(f"Сгенерировано описание проблемы с растением для пользователя {user_id}: {description}")
            return description

        else:
            logging.warning("Ответ от модели не содержит текстового компонента для описания проблемы растения.")
            return "Не удалось сгенерировать описание проблемы растения."

    except Exception as e:
        logging.error(f"Ошибка при генерации описания проблемы растения: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."



def generate_text_rec_response(user_id, image=None, query=None):
    """Генерирует текстовое описание проблемы с растением на основе изображения или текста."""
    
    # Если передан текстовый запрос
    if query:
        logging.debug(f"Получен текстовый запрос от пользователя {user_id}: {query}")
        try:
            # Подготовка данных для текстового запроса
            input_data = [{"text": query}]
            # Отправляем запрос в модель
            response = model.generate_content({"parts": input_data})
            
            # Проверка и возврат ответа
            if hasattr(response, 'parts') and response.parts:
                return response.parts[0].text.strip()
            else:
                logging.warning("Ответ от модели не содержит текстового компонента.")
                return "Не удалось сгенерировать ответ на текстовый запрос."

        except Exception as e:
            logging.error(f"Ошибка при обработке текста: {e}")
            return "Ошибка при обработке текста. Попробуйте снова."
    
    # Если передано изображение
    elif image:
        try:
            # Преобразуем изображение в base64 для передачи в модель
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='JPEG')
            img_byte_arr = img_byte_arr.getvalue()
            image_b64 = base64.b64encode(img_byte_arr).decode('utf-8')
            
            # Подготовка данных для модели
            input_data = [
                {"text": "Постарайся полностью распознать текст на изображении и в ответе прислать его. Текст может быть на любом языке, но в основном на русском, английском, японском, китайском и корейском. Ответ присылай на языке оргигинала. Либо в случае если у тебя не получилось распознать текст, то напиши что текст распознать не вышло"},
                {"mime_type": "image/jpeg", "data": image_b64}
            ]
            logging.debug("Сформирован запрос для определения проблемы с растением.")
            
            # Настройки безопасности для модели
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]

            # Отправка данных в модель для генерации описания
            response = model.generate_content(
                {"parts": input_data},
                safety_settings=safety_settings
            )

            # Проверка на наличие ответа и возврат описания
            if hasattr(response, 'parts') and response.parts:
                description = response.parts[0].text.strip()
                logging.info(f"Сгенерировано описание проблемы с растением для пользователя {user_id}: {description}")
                return description
            else:
                logging.warning("Ответ от модели не содержит текстового компонента для описания проблемы растения.")
                return "Не удалось сгенерировать описание проблемы растения."

        except Exception as e:
            logging.error(f"Ошибка при генерации описания проблемы растения: {e}")
            return "Ошибка при обработке изображения. Попробуйте снова."

    else:
        return "Неверный запрос. Укажите изображение или текст для обработки."


async def translate_to_english(user_id, prompt):
    """
    Переводит текст на английский язык с использованием модели Gemini.
    
    :param user_id: ID пользователя, для которого выполняется перевод.
    :param prompt: Текст на русском языке для перевода.
    :return: Переведённый текст или сообщение об ошибке.
    """
    try:
        # Формируем данные для модели
        input_data = [
            {
                "text": f"Преобразуй этот текст в промт для генерации изображений и переведи на английский язык, в ответ пришли только готовый переведённый промт и ничего больше:\n{prompt}"
            }
        ]
        logging.info(f"Полученный текст: {prompt}")

        # Настройки безопасности для модели

        # Отправка данных в модель для перевода текста
        response = await model.generate_content_async(
            {"parts": input_data}
        )
        safety = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {   "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            },
        ] 
        # Проверка на наличие ответа и возврат перевода
        if response and hasattr(response, 'parts') and response.parts:
            translated_text = response.parts[0].text.strip()
            logging.info(f"Сгенерирован перевод текста для пользователя {user_id}: {translated_text}")
            return translated_text
        else:
            logging.warning("Ответ от модели не содержит текстового компонента для перевода.")
            return "Не удалось перевести текст. Попробуйте снова."

    except Exception as e:
        logging.error(f"Ошибка при переводе текста для пользователя {user_id}: {e}")
        return "Произошла ошибка при обработке запроса. Попробуйте снова."



def generate_plant_help_response(user_id, query=None):
    """Генерирует текстовое описание проблемы с растением на основе текста."""

    # Если передан текстовый запрос
    if query:
        logging.debug(f"Получен текстовый запрос от пользователя {user_id}: {query}")
        try:
            # Подготовка данных для текстового запроса
            input_data = [{"text": query}]
            # Отправляем запрос в модель
            response = model.generate_content({"parts": input_data})
            
            # Проверка и возврат ответа
            if hasattr(response, 'parts') and response.parts:
                return response.parts[0].text.strip()
            else:
                logging.warning("Ответ от модели не содержит текстового компонента.")
                return "Не удалось сгенерировать ответ на текстовый запрос."

        except Exception as e:
            logging.error(f"Ошибка при обработке текста: {e}")
            return "Ошибка при обработке текста. Попробуйте снова."

    else:
        return "Неверный запрос. Укажите текст для обработки."
