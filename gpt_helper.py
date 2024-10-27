import logging
import io
from collections import deque
import google.generativeai as genai
from PIL import Image

# Google API Key и модель Gemini
GOOGLE_API_KEY = "AIzaSyD4_LesVhVi57HbA1fHX3rbUC_Voxv-beU"
MODEL_NAME = "gemini-1.5-flash"

# Конфигурация логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Настройка Google Generative AI
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

# Хранилище сообщений для контекста диалога
dialog_context = {}
MAX_CONTEXT_LENGTH = 30

def add_to_context(user_id, message):
    """Добавляет сообщение в контекст пользователя."""
    if user_id not in dialog_context:
        dialog_context[user_id] = deque(maxlen=MAX_CONTEXT_LENGTH)
    dialog_context[user_id].append(message)

def get_full_context(user_id):
    """Получает полный контекст диалога для пользователя."""
    return "\n".join(dialog_context.get(user_id, []))

def generate_gemini_response(user_id, query=None, image=None, use_context=True):
    """Создает запрос для модели Gemini на основе контекста и отправляет изображение, если оно есть."""
    # Если контекст не нужен, используем только текущий запрос
    input_data = [query] if query else []

    # Если контекст нужен, добавляем его в запрос
    if use_context:
        full_context = get_full_context(user_id)
        input_data.insert(0, full_context)

    if image:
        input_data.append(image)

    try:
        response = model.generate_content(input_data)
        response_text = getattr(response, 'text', 'Ошибка: не удалось получить ответ').strip()
        return response_text
    except Exception as e:
        logging.error(f"Ошибка при генерации ответа: {e}")
        return "Ошибка при обработке запроса. Попробуйте снова."

def limit_response_length(text):
    """Обрезает текст, если он слишком длинный для отправки в Telegram."""
    MAX_MESSAGE_LENGTH = 4096
    return text[:MAX_MESSAGE_LENGTH - 3] + '...' if len(text) > MAX_MESSAGE_LENGTH else text
