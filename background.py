from flask import Flask
from flask import request
from threading import Thread
import time
import requests
app = Flask('')
@app.route('/')
def home():
    return "I'm alive"

@app.route('/map')
def show_map():
    return '''
    <html>
    <head>
        <title>Карта</title>
    </head>
    <body>
        <iframe width="100%" height="500px" frameborder="0" allowfullscreen allow="geolocation"
        src="https://umap.openstreetmap.fr/ru/map/?scaleControl=false&miniMap=false&scrollWheelZoom=true&zoomControl=true&editMode=disabled&moreControl=true&searchControl=null&tilelayersControl=null&embedControl=null&datalayersControl=true&onLoadPanel=none&captionBar=false&captionMenus=true"></iframe>
        <p><a href="https://umap.openstreetmap.fr/ru/map/?scaleControl=false&miniMap=false&scrollWheelZoom=true&zoomControl=true&editMode=disabled&moreControl=true&searchControl=null&tilelayersControl=null&embedControl=null&datalayersControl=true&onLoadPanel=none&captionBar=false&captionMenus=true">Смотреть в полноэкранном режиме</a></p>
    </body>
    </html>
    '''
def run():
  app.run(host='0.0.0.0', port=80)
def keep_alive():
  t = Thread(target=run)
  t.start()
