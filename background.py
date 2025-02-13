from flask import Flask, request, make_response
from threading import Thread
import time
import requests
app = Flask('')

@app.route('/')
def home():
    return "I'm alive"

@app.route('/map')
def show_map():
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
        <iframe width="100%" height="100%" frameborder="0" allowfullscreen 
            allow="geolocation" 
            src="//umap.openstreetmap.fr/ru/map/anemone_1177482?scaleControl=true&miniMap=false&scrollWheelZoom=true&zoomControl=true&editMode=disabled&moreControl=true&searchControl=null&tilelayersControl=null&embedControl=false&datalayersControl=true&onLoadPanel=none&captionBar=false&captionMenus=true&measureControl=true&datalayers=ad0d1cbb-4dd3-4476-8111-c8a40f97126b%2Ca5a444be-fdb5-44aa-81a7-2a0c4b889705&locateControl=true&starControl=false#9/55.6147/37.3123">
        </iframe>
        <p>
            <a href="//umap.openstreetmap.fr/ru/map/anemone_1177482?scaleControl=true&miniMap=false&scrollWheelZoom=true&zoomControl=true&editMode=disabled&moreControl=true&searchControl=null&tilelayersControl=null&embedControl=false&datalayersControl=true&onLoadPanel=none&captionBar=false&captionMenus=true&measureControl=true&datalayers=ad0d1cbb-4dd3-4476-8111-c8a40f97126b%2Ca5a444be-fdb5-44aa-81a7-2a0c4b889705&locateControl=true&starControl=false#9/55.6147/37.3123">
                Смотреть в полноэкранном режиме
            </a>
        </p>
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
