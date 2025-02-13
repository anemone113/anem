from flask import Flask, request, make_response
from threading import Thread
import time
import requests
from bot import view_map
app = Flask('')

@app.route('/')
def home():
    return "I'm alive"

@app.route('/map')
def show_map():
    # Получаем URL карты
    umap_url = asyncio.run(view_map())  # Вызываем асинхронную функцию

    return f'''
    <html>
    <head>
        <title>Карта</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <script>
            Telegram.WebApp.ready();
        </script>
    </head>
    <body>
        <iframe width="100%" height="500px" frameborder="0" allowfullscreen src="{umap_url}"></iframe>
    </body>
    </html>
    '''

def run():
    app.run(host='0.0.0.0', port=80)

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == '__main__':
    keep_alive()
