from flask import Flask, request, jsonify, send_from_directory, make_response
from threading import Thread
import os
import logging

app = Flask(__name__, static_folder='static')  # Указываем папку для статики


# --- API ENDPOINTS (Точки для работы с данными) ---

@app.route('/api/timer/get_all', methods=['GET'])
def api_get_timers():
    from gpt_helper import get_user_timers  # импорт внутри функции
    
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "No user_id provided"}), 400
    
    data = get_user_timers(user_id)
    return jsonify(data)


@app.route('/api/timer/create_media', methods=['POST'])
def api_create_media():
    from gpt_helper import add_new_media  # импорт внутри функции

    data = request.json
    user_id = data.get('user_id')
    title = data.get('title')
    m_type = data.get('type', 'movie')
    
    if not user_id or not title:
        return jsonify({"error": "Missing data"}), 400
        
    media_id = add_new_media(user_id, title, m_type)
    if media_id:
        return jsonify({"status": "success", "media_id": media_id})
    else:
        return jsonify({"status": "error"}), 500



@app.route('/api/timer/update_media_title', methods=['POST'])
def api_update_media_title():
    from gpt_helper import update_media_title
    
    data = request.json
    user_id = data.get('user_id')
    media_id = data.get('media_id')
    title = data.get('title')

    if not user_id or not media_id or not title:
        return jsonify({"error": "missing params"}), 400

    ok = update_media_title(user_id, media_id, title)
    return jsonify({"status": "success" if ok else "error"})


@app.route('/api/timer/add_entry', methods=['POST'])
def api_add_entry():
    from gpt_helper import add_timer_entry 

    data = request.json
    
    # ИЗМЕНЕНИЕ: Получаем список file_ids
    # Если фронтенд прислал старый file_id, превращаем его в список
    f_ids = data.get('file_ids', [])
    if not f_ids and data.get('file_id'):
        f_ids = [data.get('file_id')]

    res = add_timer_entry(
        user_id=data.get('user_id'),
        media_id=data.get('media_id'),
        note_text=data.get('text'),
        timestamp=data.get('timestamp'),
        episode=data.get('episode'),
        file_ids=f_ids  # Передаем список
    )
    return jsonify({"status": "success" if res else "error", "key": res})

@app.route('/api/timer/delete', methods=['DELETE'])
def api_delete_media():
    from gpt_helper import delete_media  # импорт внутри функции

    user_id = request.args.get('user_id')
    media_id = request.args.get('media_id')
    
    if delete_media(user_id, media_id):
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 500


# --- WEBAPP ROUTING (Маршруты для веб-приложений) ---

from flask import send_file
from io import BytesIO

# --- НОВЫЕ API ENDPOINTS ---

@app.route('/api/media/upload_image', methods=['POST'])
def api_upload_image():
    from gpt_helper import upload_file_to_telegram
    
    if 'image' not in request.files:
        return jsonify({"error": "No image"}), 400
        
    file = request.files['image']
    user_id = request.form.get('user_id') 
    
    if not user_id:
        return jsonify({"error": "No user_id"}), 400

    # Отправляем фото пользователю в чат
    file_id = upload_file_to_telegram(file, user_id)
    
    if file_id:
        return jsonify({"status": "success", "file_id": file_id})
    return jsonify({"status": "error", "message": "Telegram upload failed"}), 500


@app.route('/api/media/get_image_url', methods=['GET'])
def api_get_image_url():
    # Фронтенд просит ссылку на картинку по file_id
    from gpt_helper import get_telegram_file_link
    file_id = request.args.get('file_id')
    if not file_id:
        return jsonify({"error": "No id"}), 400
        
    link = get_telegram_file_link(file_id) # Функция выше
    if link:
        return jsonify({"url": link})
    return jsonify({"error": "Not found"}), 404



@app.route('/')
def home():
    return "Bot Server is Running. <br> Available apps: /timer-app"


@app.route('/timer-app/', defaults={'path': ''})
@app.route('/timer-app/<path:path>')
def serve_timer_app(path):
    full_path = os.path.join(app.static_folder, path)
    if path != "" and os.path.exists(full_path):
        return send_from_directory(app.static_folder, path)

    return send_from_directory(app.static_folder, 'timer_index.html')

@app.route('/api/timer/update_entry', methods=['POST'])
def api_update_entry():
    from gpt_helper import update_timer_entry
    data = request.json
    
    # ИЗМЕНЕНИЕ: Обработка списка
    f_ids = data.get('file_ids') # Может быть None, если не меняли картинки

    success = update_timer_entry(
        user_id=data.get('user_id'),
        media_id=data.get('media_id'),
        entry_id=data.get('entry_id'),
        text=data.get('text'),
        timestamp=data.get('timestamp'),
        file_ids=f_ids # Передаем в helper
    )
    return jsonify({"status": "success" if success else "error"})


@app.route('/api/timer/delete_entry', methods=['DELETE'])
def api_delete_entry():
    from gpt_helper import delete_timer_entry
    
    user_id = request.args.get('user_id')
    media_id = request.args.get('media_id')
    entry_id = request.args.get('entry_id')
    
    if delete_timer_entry(user_id, media_id, entry_id):
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 500




@app.route('/other-app/', defaults={'path': ''})
@app.route('/other-app/<path:path>')
def serve_other_app(path):
    return "This is a future app placeholder"


# --- SERVER STARTUP ---

def run():
    app.run(host='0.0.0.0', port=80)

def keep_alive():
    t = Thread(target=run)
    t.start()
