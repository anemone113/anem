import logging
import io
from collections import deque
import google.generativeai as genai
from PIL import Image
import base64
import json

# Google API Key и модель Gemini
GOOGLE_API_KEY = "AIzaSyB5UCCya5hXDO2q3n-K5tQY4FzWSB4dVQY"

model_config = {
    "temperature": 0.3,          # Высокая температура для увеличения креативности
    "max_output_tokens": 10000,    # Длинный ответ
    "top_p": 0.4,               # Более широкий диапазон вероятностей для выбора токенов
    "top_k": 4,                # Большой выбор токенов для разнообразия
}
# Конфигурация логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Настройка Google Generative AI
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash', generation_config=model_config)

# Хранилище для историй диалогов пользователей
user_contexts = {}

def generate_image_description(user_id, image):
    """Создает текстовое описание изображения и добавляет его в контекст пользователя."""
    # Преобразуем изображение в base64 для отправки в модель
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='JPEG')
    img_byte_arr = img_byte_arr.getvalue()
    image_b64 = base64.b64encode(img_byte_arr).decode('utf-8')

    # Формируем запрос для генерации описания
    input_data = [
        {"text": "Опиши изображение максимально подробно насколько это возможно. Выдели в текстовом виде все детали изображения. На русском языке."},
        {"mime_type": "image/jpeg", "data": image_b64}
    ]

    try:
        # Запрос на генерацию описания через модель
        response = model.generate_content({"parts": input_data})
        
        if hasattr(response, 'parts') and response.parts:
            description = response.parts[0].text.strip()
            add_to_context(user_id, description, message_type="image_description")  # Сохранение в контексте
            return description
        else:
            logging.warning("Ответ от модели не содержит текстового компонента для описания.")
            return "Не удалось сгенерировать описание изображения."
    except Exception as e:
        logging.error(f"Ошибка при генерации описания изображения: {e}")
        return "Ошибка при обработке изображения. Попробуйте снова."

def get_relevant_context(user_id):
    """Получает явный контекст для пользователя."""
    context = user_contexts.get(user_id, deque(maxlen=50))
    
    # Создаём более компактный контекст, избегая повторов
    unique_context = []
    seen_messages = set()
    for msg in context:
        if msg not in seen_messages:
            seen_messages.add(msg)
            unique_context.append(msg)

    # Формируем явный контекст
    explicit_context = [
        "Вы играете роль телеграм чат-бота помощника. Используй разметку markdown_v2 для ответов",
        "На чётко заданные вопросы старайся давать менее расплывчатые ответы, по возможности не используй уточнения о том что ты не являешься профессионалом  и прочее такое, отвечай по существу вопроса и давай лично свою оценку, с минимумом поправок на разные точки зрения ",        
        "У этого чата есть история сообщений.",
        "Используйте этот контекст для ответов по необходимости.",
        "Старайся отвечать по возможности и по необходимости подробно",  
        "Старайся поддерживать тот стиль общения которым с тобой общается собеседник"      
    ]
    
    return '\n'.join(explicit_context + unique_context)

def add_to_context(user_id, message, message_type):
    """Добавляет сообщение в контекст пользователя, избегая повторов."""
    if user_id not in user_contexts:
        user_contexts[user_id] = deque(maxlen=50)  # Максимум 50 сообщений
    
    # Проверка на наличие повтора
    if f"{message_type}: {message}" not in user_contexts[user_id]:
        user_contexts[user_id].append(f"{message_type}: {message}")



def generate_gemini_response(user_id, query=None, text=None, image=None, use_context=True):
    input_data = [{"text": "Отвечай на русском языке, если не указано иное."}]
    
    if use_context:
        relevant_context = get_relevant_context(user_id)
        if relevant_context:
            input_data.append({"text": relevant_context})

    if query:
        input_data.append({"text": query})
        if use_context:
            add_to_context(user_id, query, message_type="user_message")

    if text:
        input_data.append({"text": text})
        if use_context:
            add_to_context(user_id, text, message_type="file_content")

    if image:
        # Генерация и сохранение описания изображения
        description = generate_image_description(user_id, image)
        input_data.append({"text": description})  # Включаем описание в контекст
        if use_context:
            add_to_context(user_id, description, message_type="image_description")

    logging.info(f"Отправка данных в Gemini: {json.dumps(input_data, ensure_ascii=False)}")

    try:
        response = model.generate_content({"parts": input_data})
        
        if hasattr(response, 'parts') and response.parts:
            response_text = response.parts[0].text.strip()
            if use_context:
                add_to_context(user_id, response_text, message_type="bot_response")

            if image:
                # Сохраняем полный ответ как описание изображения
                add_to_context(user_id, response_text, message_type="image_full_description")

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
