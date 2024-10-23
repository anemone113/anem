from flask import Flask
from flask import request
from flask_cors import CORS  # Импортируем CORS
from threading import Thread
import time
import requests

app = Flask('')
CORS(app, resources={r"/*": {"origins": "https://anemone.onrender.com"}})  # Настройка CORS

@app.route('/')
def home():
    return "I'm alive"

def run():
    app.run(host='0.0.0.0', port=80)

def keep_alive():
    t = Thread(target=run)
    t.start()
