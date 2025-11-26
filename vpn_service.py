import asyncio
import aiohttp
import base64
import re
import random
import json
import logging
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import qrcode
from io import BytesIO
# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ И КОНСТАНТЫ ---

# Поисковик
HAS_DDGS = False
try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        HAS_DDGS = True
    except ImportError:
        logger.warning("Модуль duckduckgo_search не найден. Умный поиск отключен.")

BASE_DIR = Path.cwd()
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
SUB_FILE_PATH = STATIC_DIR / "sub.txt"

# Белый список SNI (твои + друга)
RUSSIA_SNI = [
    "1l-api.mail.ru", "1l-go.mail.ru", "1l-hit.mail.ru", "1l-s2s.mail.ru", "1l-view.mail.ru",
    "1l.mail.ru", "1link.mail.ru", "2018.mail.ru", "2019.mail.ru", "2020.mail.ru", "2021.mail.ru",
    "23feb.mail.ru", "2gis.com", "2gis.ru", "300.ya.ru", "3475482542.mc.yandex.ru", "742231.ms.ok.ru",
    "8mar.mail.ru", "8march.mail.ru", "9may.mail.ru", "a.auth-nsdi.ru", "a.res-nsdi.ru", "aa.mail.ru",
    "adm.digital.gov.ru", "adm.mp.rzd.ru", "admin.cs7777.vk.ru", "admin.tau.vk.ru", "afisha.mail.ru",
    "agent.mail.ru", "akashi.vk-portal.net", "alfabank.ru", "alpha3.minigames.mail.ru", "alpha4.minigames.mail.ru",
    "amigo.mail.ru", "analytics.predict.mail.ru", "analytics.vk.ru", "an.yandex.ru", "answer.mail.ru",
    "answers.mail.ru", "api.2gis.ru", "api.browser.yandex.com", "api.browser.yandex.ru", "api.cs7777.vk.ru",
    "api.events.plus.yandex.net", "api.max.ru", "api.ok.ru", "api.photo.2gis.com", "api.predict.mail.ru",
    "api.reviews.2gis.com", "api.s3.yandex.net", "api.tau.vk.ru", "api.uxfeedback.yandex.net", "api-maps.yandex.ru",
    "api.vk.ru", "api.plus.kinopoisk.ru", "apps.research.mail.ru", "authdl.mail.ru", "auto.mail.ru", "auto.ru",
    "autodiscover.corp.mail.ru", "autodiscover.ord.ozon.ru", "avatars.mds.yandex.com", "avatars.mds.yandex.net",
    "avito.ru", "avito.st", "away.cs7777.vk.ru", "away.tau.vk.ru", "azt.mail.ru", "b.auth-nsdi.ru", "b.res-nsdi.ru",
    "bank.ozon.ru", "banners-website.wildberries.ru", "bb.mail.ru", "bd.mail.ru", "beko.dom.mail.ru", "bender.mail.ru",
    "beta.mail.ru", "bfds.sberbank.ru", "biz.mail.ru", "bitva.mail.ru", "blackfriday.mail.ru", "blog.mail.ru",
    "bot.gosuslugi.ru", "botapi.max.ru", "bratva-mr.mail.ru", "bro-bg-store.s3.yandex.com", "bro-bg-store.s3.yandex.net",
    "bro-bg-store.s3.yandex.ru", "brontp-pre.yandex.ru", "browser.mail.ru", "browser.yandex.com", "browser.yandex.ru",
    "calendar.mail.ru", "capsula.mail.ru", "cargo.rzd.ru", "cars.mail.ru", "catalog.api.2gis.com", "cdn.connect.mail.ru",
    "cdn.lemanapro.ru", "cdn.newyear.mail.ru", "cdn.s3.yandex.net", "cdn.tbank.ru", "cdn.yandex.ru", "cf.mail.ru",
    "chat-prod.wildberries.ru", "chat3.vtb.ru", "cloud.cdn.yandex.com", "cloud.cdn.yandex.net", "cloud.cdn.yandex.ru",
    "cloud.vk.com", "cloud.vk.ru", "cloudcdn-ams19.cdn.yandex.net", "cloudcdn-m9-10.cdn.yandex.net", "cloudcdn-m9-12.cdn.yandex.net",
    "cloudcdn-m9-13.cdn.yandex.net", "cloudcdn-m9-14.cdn.yandex.net", "cloudcdn-m9-15.cdn.yandex.net", "cloudcdn-m9-2.cdn.yandex.net",
    "cloudcdn-m9-3.cdn.yandex.net", "cloudcdn-m9-4.cdn.yandex.net", "cloudcdn-m9-5.cdn.yandex.net", "cloudcdn-m9-6.cdn.yandex.net",
    "cloudcdn-m9-7.cdn.yandex.net", "cloudcdn-m9-9.cdn.yandex.net", "cms-res-web.online.sberbank.ru", "cobma.mail.ru",
    "cobmo.mail.ru", "code.mail.ru", "codefest.mail.ru", "collections.yandex.com", "collections.yandex.ru", "comba.mail.ru",
    "combatt.mail.ru", "commba.mail.ru", "company.rzd.ru", "compute.mail.ru", "connect.cs7777.vk.ru", "contacts.rzd.ru",
    "contract.gosuslugi.ru", "corp.mail.ru", "cpg.money.mail.ru", "crowdtest.payment-widget-smarttv.plus.tst.kinopoisk.ru",
    "crowdtest.payment-widget.plus.tst.kinopoisk.ru", "csp.yandex.net", "cs.avito.ru", "ctlog.mail.ru", "ctlog2023.mail.ru",
    "ctlog2024.mail.ru", "cto.mail.ru", "cups.mail.ru", "da-preprod.biz.mail.ru", "da.biz.mail.ru", "data.amigo.mail.ru",
    "dating.ok.ru", "deti.mail.ru", "dev.max.ru", "dev1.mail.ru", "dev2.mail.ru", "dev3.mail.ru", "dev.cs7777.vk.ru",
    "dev.tau.vk.ru", "digital.gov.ru", "disk.2gis.com", "disk.rzd.ru", "dmp.dmpkit.lemanapro.ru", "dn.mail.ru", "dnd.wb.ru",
    "doc.mail.ru", "dobro.mail.ru", "dom.mail.ru", "download.max.ru", "dragonpals.mail.ru", "dr.yandex.net", "dr2.yandex.net",
    "ds.mail.ru", "duck.mail.ru", "dzen.ru", "e.mail.ru", "education.mail.ru", "egress.yandex.net", "eh.vk.com",
    "ekmp-a-51.rzd.ru", "enterprise.api-maps.yandex.ru", "esa-res.online.sberbank.ru", "esc.predict.mail.ru", "esia.gosuslugi.ru",
    "et.mail.ru", "expert.vk.ru", "external-api.mediabilling.kinopoisk.ru", "external-api.plus.kinopoisk.ru", "favicon.yandex.com",
    "favicon.yandex.net", "favicon.yandex.ru", "fe.mail.ru", "filekeeper-vod.2gis.com", "finance.mail.ru", "finance.wb.ru",
    "five.predict.mail.ru", "foto.mail.ru", "frontend.vh.yandex.ru", "fw.wb.ru", "games-bamboo.mail.ru", "games-fisheye.mail.ru",
    "games.mail.ru", "genesis.mail.ru", "geo-apart.predict.mail.ru", "gibdd.mail.ru", "golos.mail.ru", "go.mail.ru",
    "gosuslugi.ru", "gosweb.gosuslugi.ru", "goya.rutube.ru", "gpb.finance.mail.ru", "graphql-web.kinopoisk.ru", "graphql.kinopoisk.ru",
    "gu-st.ru", "hd.kinopoisk.ru", "health.mail.ru", "help.mcs.mail.ru", "help.max.ru", "hi-tech.mail.ru", "horo.mail.ru",
    "hrc.tbank.ru", "hs.mail.ru", "http-check-headers.yandex.ru", "i.max.ru", "i0.photo.2gis.com", "i1.photo.2gis.com",
    "i2.photo.2gis.com", "i3.photo.2gis.com", "i4.photo.2gis.com", "i5.photo.2gis.com", "i6.photo.2gis.com", "i7.photo.2gis.com",
    "i8.photo.2gis.com", "i9.photo.2gis.com", "id.cs7777.vk.ru", "id.sber.ru", "id.tbank.ru", "id.tau.vk.ru", "id.vk.ru",
    "imgproxy.cdn-tinkoff.ru", "imperia.mail.ru", "informer.yandex.ru", "internet.mail.ru", "invest.ozon.ru", "it.mail.ru",
    "izbirkom.ru", "jam.api.2gis.com", "jd.mail.ru", "jitsi.wb.ru", "journey.mail.ru", "juggermobile.mail.ru", "junior.mail.ru",
    "keys.api.2gis.com", "kicker.mail.ru", "kino.mail.ru", "kingdomrift.mail.ru", "kiks.yandex.com", "kiks.yandex.ru",
    "knights.mail.ru", "kobma.mail.ru", "kobmo.mail.ru", "komba.mail.ru", "kommba.mail.ru", "kombo.mail.ru", "konflikt.mail.ru",
    "kombu.mail.ru", "lady.mail.ru", "landing.mail.ru", "la.mail.ru", "le.tbank.ru", "learning.ozon.ru", "legal.max.ru",
    "legendofheroes.mail.ru", "legenda.mail.ru", "lemanapro.ru", "link.max.ru", "link.mp.rzd.ru", "live.ok.ru", "lk.gosuslugi.ru",
    "loa.mail.ru", "login.cs7777.vk.ru", "login.tau.vk.ru", "login.vk.com", "login.vk.ru", "lotro.mail.ru", "love.mail.ru",
    "m.47news.ru", "m.ok.ru", "m.vk.ru", "m.vkvideo.cs7777.vk.ru", "ma.kinopoisk.ru", "mailer.mail.ru", "mailexpress.mail.ru",
    "man.mail.ru", "map.gosuslugi.ru", "mapgl.2gis.com", "maps.mail.ru", "marusia.mail.ru", "max.ru", "mcs.mail.ru",
    "me.cs7777.vk.ru", "media-golos.mail.ru", "media.mail.ru", "mediafeeds.yandex.com", "mediafeeds.yandex.ru", "mediapro.mail.ru",
    "merch-cpg.money.mail.ru", "metrics.alfabank.ru", "microapps.kinopoisk.ru", "miniapp.internal.myteam.mail.ru", "minigames.mail.ru",
    "mobfarm.mail.ru", "money.mail.ru", "mosqa.mail.ru", "mozilla.mail.ru", "mp.rzd.ru", "ms.cs7777.vk.ru", "msk.t2.ru",
    "music.vk.ru", "my.mail.ru", "my.rzd.ru", "myteam.mail.ru", "nebogame.mail.ru", "net.mail.ru", "neuro.translate.yandex.ru",
    "new.mail.ru", "newyear.mail.ru", "newyear2018.mail.ru", "news.mail.ru", "nonstandard.sales.mail.ru", "notes.mail.ru",
    "novorossiya.gosuslugi.ru", "oauth.cs7777.vk.ru", "oauth.tau.vk.ru", "oauth2.cs7777.vk.ru", "octavius.mail.ru",
    "oneclick-payment.kinopoisk.ru", "online.sberbank.ru", "operator.mail.ru", "ord.ozon.ru", "ord.vk.ru", "otvet.mail.ru",
    "otveti.mail.ru", "otvety.mail.ru", "ova.ozon.ru", "owa.ozon.ru", "park.mail.ru", "partners.gosuslugi.ru", "partners.lemanapro.ru",
    "pay.ozon.ru", "pay.mail.ru", "payment-widget-smarttv.plus.kinopoisk.ru", "payment-widget.kinopoisk.ru", "payment-widget.plus.kinopoisk.ru",
    "panzar.mail.ru", "pernatsk.mail.ru", "pets.mail.ru", "pic.rutubelist.ru", "pl-res.online.sberbank.ru", "pochtabank.mail.ru",
    "pogoda.mail.ru", "pokerist.mail.ru", "polis.mail.ru", "pos.gosuslugi.ru", "pp.mail.ru", "pptest.userapi.com", "predict.mail.ru",
    "preview.rutube.ru", "primeworld.mail.ru", "privacy-cs.mail.ru", "prodvizhenie.rzd.ru", "ptd.predict.mail.ru", "public-api.reviews.2gis.com",
    "public.infra.mail.ru", "pubg.mail.ru", "pulse.mp.rzd.ru", "pulse.mail.ru", "push.vk.ru", "pw.mail.ru", "quantum.mail.ru",
    "queuev4.vk.com", "quiz.kinopoisk.ru", "r.vk.ru", "rate.mail.ru", "rebus.calls.mail.ru", "rebus.octavius.mail.ru",
    "receive-sentry.lmru.tech", "reseach.mail.ru", "rev.mail.ru", "riot.mail.ru", "rl.mail.ru", "rm.mail.ru", "rs.mail.ru",
    "rutube.ru", "rzd.ru", "s.vtb.ru", "s3.babel.mail.ru", "s3.mail.ru", "s3.media-mobs.mail.ru", "s3.t2.ru", "s3.yandex.net",
    "sales.mail.ru", "sangels.mail.ru", "sba.yandex.com", "sba.yandex.net", "sba.yandex.ru", "sberbank.ru", "sdk.money.mail.ru",
    "secure-cloud.rzd.ru", "secure.ozon.ru", "secure.rzd.ru", "securepay.ozon.ru", "security.mail.ru", "seller.ozon.ru",
    "service.amigo.mail.ru", "sfd.gosuslugi.ru", "shadowbound.mail.ru", "sntr.avito.ru", "socdwar.mail.ru", "sochi-park.predict.mail.ru",
    "souz.mail.ru", "sphere.mail.ru", "speller.yandex.net", "sport.mail.ru", "sso-app4.vtb.ru", "sso-app5.vtb.ru", "sso.auto.ru",
    "sso.dzen.ru", "sso.kinopoisk.ru", "ssp.rutube.ru", "st-im.kinopoisk.ru", "st.kinopoisk.ru", "st.max.ru", "st.okcdn.ru",
    "st.ozone.ru", "st-ok.cdn-vk.ru", "staging-analytics.predict.mail.ru", "staging-esc.predict.mail.ru", "staging-sochi-park.predict.mail.ru",
    "stand.aoc.mail.ru", "stand.bb.mail.ru", "stand.cb.mail.ru", "stand.la.mail.ru", "stand.pw.mail.ru", "static-mon.yandex.net",
    "static.dl.mail.ru", "static.lemanapro.ru", "static.operator.mail.ru", "static.rutube.ru", "stats.avito.ru", "stats.vk-portal.net",
    "status.mcs.mail.ru", "strm-rad-23.strm.yandex.net", "strm.yandex.net", "strm.yandex.ru", "stream.mail.ru", "street-combats.mail.ru",
    "styles.api.2gis.com", "suggest.dzen.ru", "suggest.sso.dzen.ru", "sun6-20.userapi.com", "sun6-21.userapi.com", "sun6-22.userapi.com",
    "sun9-101.userapi.com", "sun9-38.userapi.com", "support.biz.mail.ru", "support.mcs.mail.ru", "support.tech.mail.ru", "surveys.yandex.ru",
    "sync.browser.yandex.net", "target.vk.ru", "tamtam.ok.ru", "tbh.mail.ru", "team.mail.ru", "team.rzd.ru", "tech.mail.ru",
    "tera.mail.ru", "ticket.rzd.ru", "tickets.widget.kinopoisk.ru", "tidaltrek.mail.ru", "tiles.maps.mail.ru", "tile0.maps.2gis.com",
    "tile1.maps.2gis.com", "tile2.maps.2gis.com", "tile3.maps.2gis.com", "tile4.maps.2gis.com", "tmgame.mail.ru", "todo.mail.ru",
    "top-fwz1.mail.ru", "touch.kinopoisk.ru", "townwars.mail.ru", "travel.rzd.ru", "travel.yastatic.net", "travel.yandex.ru",
    "trk.mail.ru", "ttbh.mail.ru", "tv.mail.ru", "typewriter.mail.ru", "u.corp.mail.ru", "ufo.mail.ru", "ui.cs7777.vk.ru",
    "ui.tau.vk.ru", "uslugi.yandex.ru", "uxfeedback-cdn.s3.yandex.net", "uxfeedback.yandex.ru", "vk-portal.net", "vk.ru",
    "vkdoc.mail.ru", "vkvideo.cs7777.vk.ru", "voina.mail.ru", "voter.gosuslugi.ru", "vt-1.ozone.ru", "warface.mail.ru",
    "warheaven.mail.ru", "wartune.mail.ru", "wap.yandex.com", "wap.yandex.ru", "wb.ru", "weblink.predict.mail.ru", "web.max.ru",
    "webagent.mail.ru", "webstore.mail.ru", "welcome.mail.ru", "welcome.rzd.ru", "wf.mail.ru", "wh-cpg.money.mail.ru",
    "whatsnew.mail.ru", "widgets.kinopoisk.ru", "wok.mail.ru", "ws-api.oneme.ru", "ws.seller.ozon.ru", "www.avito.ru",
    "www.avito.st", "www.biz.mail.ru", "www.cikrf.ru", "www.gosuslugi.ru", "www.kinopoisk.ru", "www.mail.ru", "www.mcs.mail.ru",
    "www.ozon.ru", "www.pubg.mail.ru", "www.rzd.ru", "www.sberbank.ru", "www.t2.ru", "www.vtb.ru", "www.wf.mail.ru",
    "xapi.ozon.ru", "yabs.yandex.ru", "ya.ru", "yandex.com", "yandex.net", "yandex.ru", "yastatic.net",
    "zen-yabro-morda.mediascope.mc.yandex.ru", "zen.yandex.com", "zen.yandex.net", "zen.yandex.ru"
]


# ВЕРНУЛ СТАТИЧЕСКИЕ ИСТОЧНИКИ (Это база, без них грустно)
STATIC_SOURCES = [
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_SS+All_RUS.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/Vless-Reality-White-Lists-Rus-Cable.txt",
    "https://github.com/igareck/vpn-configs-for-russia/raw/refs/heads/main/Vless-Reality-White-Lists-Rus-Cable.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE_DELETED.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt",
    "https://raw.githubusercontent.com/MrPooyaX/VpnsFucking/main/Shenzo.txt",
    "https://raw.githubusercontent.com/anaer/Sub/main/clash.yaml",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/Eternity.txt",
    "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Eternity.txt",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2",
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/ts-sf/fly/main/v2",
    "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt",
    "https://raw.githubusercontent.com/tbbatbb/Proxy/master/dist/v2ray.config.txt",
    "https://raw.githubusercontent.com/v2ray-links/v2ray-free/master/v2ray",
    "https://raw.githubusercontent.com/mksshare/MKSS/main/sub/v2ray",
    "https://raw.githubusercontent.com/snakem982/Proxies/main/all_nodes.txt",
    "https://raw.githubusercontent.com/Everyday-VPN/Everyday-VPN/main/subscription/v2ray.txt",
    "https://raw.githubusercontent.com/xiyaowong/freeFQ/main/v2ray",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray",
    "https://raw.githubusercontent.com/officialputuid/v2ray-look/main/v2ray/v2ray",
    "https://raw.githubusercontent.com/learnhard-cn/free_proxy_ss/main/v2ray/v2ray_sub.txt",
    "https://raw.githubusercontent.com/Alvin9999/new-pac/master/v2ray/v2ray",
    "https://raw.githubusercontent.com/ssrsub/ssr/master/Clash.yml",
    "https://raw.githubusercontent.com/oslook/clash-freenode/main/clash.yaml",
    "https://raw.githubusercontent.com/runcody/proxies/main/proxies.txt",
    "https://raw.githubusercontent.com/yqqy/V2ray-Configs/main/V2ray-Configs/base64.txt",
    "https://raw.githubusercontent.com/AlienLimited/V2ray-Configs/main/base64.txt",
    "https://raw.githubusercontent.com/ufor/Clash/main/Clash",
    "https://raw.githubusercontent.com/erickrodriguezs/v2ray-setup/master/v2ray_config.json",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/main/Long_term_subscription_num",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
    "https://raw.githubusercontent.com/2dust/v2rayN/master/v2rayN/bin/Debug/config.json",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/protocols/reality",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/protocols/vless",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/protocols/vmess",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/protocols/trojan",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/protocols/shadowsocks",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/protocols/hysteria",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/protocols/tuic",
    "https://raw.githubusercontent.com/chf2/clash/main/clash.yaml",
    "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub",
    "https://raw.githubusercontent.com/aiboboxx/clashfree/main/clash.yml",
    "https://raw.githubusercontent.com/xvvb/proxy/main/proxy.txt",
]

HTTP_PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/Userv5/Proxy-List-Daily/main/proxy_list_http.txt",
]

SEARCH_DORKS = [
    'site:pastebin.com "vless://" 2025', 'site:pastebin.com "vmess://" free',
    'site:pastebin.com "trojan://" 2025', 'site:pastebin.com "ss://" 2025',
    'site:rentry.co "vless://" 2025', 'site:rentry.co "hysteria2://" config',
    'site:justpaste.it "v2ray" 2025', 'site:controlc.com "vmess"',
    'site:paste.ee "vless://" 2025', 'site:privatebin.net "v2ray"',
    'site:ghostbin.com "vmess"', 'site:telegra.ph "vless://"',
    'site:graph.org "vmess://"', 'site:notion.site "vless" config',
    'site:hackmd.io "vmess" list', 'site:md.sh "vless"',
    'site:hf.space "vless://"', 'site:hf.co "vmess://"',
    'site:vercel.app "vless://"', 'site:vercel.app "vmess://"',
    'site:onrender.com "vmess://"', 'site:onrender.com "vless://"',
    'site:railway.app "vless://"', 'site:herokuapp.com "vmess://"',
    'site:glitch.me "vless://"', 'site:replit.com "vless://"',
    'site:replit.com "vmess://"', 'site:run.app "vless://"',
    'site:workers.dev "vless://"', 'site:pages.dev "vless://"',
    'site:b4a.app "vless://"', 'site:fly.dev "vmess://"',
    'site:github.com "vless://" russia', 'site:github.com "vless://" free 2025',
    'site:gist.github.com "vless://" 2025', 'site:gitlab.com "vless://" public',
    'site:bitbucket.org "vmess://" list', 'site:raw.githubusercontent.com "vless://"',
    'site:codesandbox.io "vless://"', 'site:libraries.io "v2ray"',
    'site:t.me "vless://" -inurl:post', 'site:t.me "vmess://" -inurl:post',
    'site:t.me "hysteria2://" 2025', 'site:t.me "tuic://" config',
    'site:vk.com "vless://" 2025', 'site:youtube.com "vless://" description',
    'site:twitter.com "vless://" 2025', 'site:reddit.com "vless://" free',
    'intext:"vless://" "reality" "pbk" 2025', 'intext:"vmess://" "ws" "tls" 2025',
    'intext:"hysteria2://" "password" 2025', 'intext:"hy2://" "2025" free',
    'intext:"tuic://" "uuid" 2025', 'intext:"trojan://" "sni" 2025',
    'intext:"wireguard://" "privatekey" 2025', 'intext:"wg://" "endpoint" 2025',
    'inurl:subscribe "v2ray" 2025', 'inurl:sub "vless" list',
    '"v2ray" "russia" "bypass" 2025', '"vless" "iran" "free" 2025',
    '"sing-box" "config" "json" 2025', '"clash" "meta" "yaml" 2025'
]

AUTHORS_GIT = ['aiboboxx', 'freefq', 'Pawdroid', 'v2ray-links', 'mksshare', 'snakem982', 'LalatinaHub', 'ts-sf'] #Авторы для поиска
FILES_GIT = ['config.txt', 'v2ray.txt', 'sub.txt', 'subscribe', 'list.txt', 'clash.yaml'] #Возможные файлы

class VpnManager:
    proxies = []

    @staticmethod
    def get_dynamic_sources():
        """Генерация ссылок по дате (из кода друга)"""
        d = datetime.now().strftime('%Y/%m/%Y%m%d')
        return [f"https://nodefree.org/dy/{d}.txt"]

    @staticmethod
    async def get_proxies(session):
        logger.info("Сбор прокси...")
        try:
            tasks = [session.get(u, timeout=4) for u in HTTP_PROXY_SOURCES]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            found = set()
            for res in results:
                if isinstance(res, aiohttp.ClientResponse) and res.status == 200:
                    text = await res.text()
                    found.update(re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+', text))
            VpnManager.proxies = [f"http://{p}" for p in list(found)[:150]]
            logger.info(f"Найдено прокси: {len(VpnManager.proxies)}")
        except Exception as e:
            logger.error(f"Ошибка прокси: {e}")

    @staticmethod
    def search_links():
        links = set()
        # 1. GitHub (статические авторы)
        for a in AUTHORS_GIT:
            for b in [f"https://raw.githubusercontent.com/{a}/v2ray/main", f"https://raw.githubusercontent.com/{a}/free/main"]:
                for f in FILES_GIT: links.add(f"{b}/{f}")
        
        # 2. DuckDuckGo (осторожно, может не работать на серверах)
        if HAS_DDGS and VpnManager.proxies:
            logger.info("Запуск DuckDuckGo поиска...")
            pool = VpnManager.proxies
            random.shuffle(SEARCH_DORKS)
            for q in SEARCH_DORKS[:2]: # Мало запросов чтобы не банили
                try:
                    current_proxy = random.choice(pool)
                    with DDGS(proxy=current_proxy, timeout=10) as ddgs:
                        res = ddgs.text(q, max_results=5)
                        if res:
                            for r in res: links.add(r['href'])
                except Exception:
                    continue
        return list(links)

    @staticmethod
    def parse_config(link: str):
        """Исправленный парсер (логика друга)"""
        try:
            link = link.strip()
            if not link: return None

            # --- ЛОГИКА ДЛЯ VMESS (Base64 JSON) ---
            if link.startswith("vmess://"):
                try:
                    b64 = link[8:]
                    b64 += "=" * ((4 - len(b64) % 4) % 4)
                    data = base64.b64decode(b64).decode("utf-8", errors="ignore")
                    j = json.loads(data)
                    # Ищем SNI в разных полях
                    sni = (j.get("sni") or j.get("host") or j.get("add") or "").lower()
                    return {"host": j.get("add"), "port": int(j.get("port") or 443), "sni": sni, "raw": link}
                except: return None

            # --- ЛОГИКА ДЛЯ VLESS/TROJAN (URL Params) ---
            try:
                u = urlparse(link)
            except: return None
            
            q = parse_qs(u.query)
            sni = (q.get("sni", [q.get("host", [""])[0]])[0] or u.hostname or "").lower()
            
            # Reality fallback для SNI
            if not sni and u.scheme == "vless":
                sni = (q.get("security", [""])[0] == "reality" and q.get("sni", [""])[0]) or ""
            
            port = u.port or 443
            if not u.hostname: return None
            
            return {"host": u.hostname, "port": port, "sni": sni, "raw": link}
        except: return None

    @staticmethod
    async def check_port(host, port):
        """Проверка соединения"""
        try:
            conn = asyncio.open_connection(host, port)
            r, w = await asyncio.wait_for(conn, timeout=2) # Таймаут поменьше для скорости
            w.close()
            await w.wait_closed()
            return True
        except: return False

async def run_vpn_update():
    """Основная функция обновления"""
    logger.info(">>> Начало обновления VPN списков")
    
    conn = aiohttp.TCPConnector(limit=100, ssl=False)
    async with aiohttp.ClientSession(connector=conn) as session:
        # 1. Сбор прокси (нужны для поиска)
        await VpnManager.get_proxies(session)
        
        # 2. Сбор всех источников ссылок
        found_sources = await asyncio.to_thread(VpnManager.search_links)
        # Объединяем: Статика + По дате + Найденное поиском
        all_sources = list(set(STATIC_SOURCES + VpnManager.get_dynamic_sources() + found_sources))
        
        logger.info(f"Источников для скачивания: {len(all_sources)}")
        
        # 3. Скачивание контента
        tasks = [session.get(url, timeout=15) for url in all_sources]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        raw_text = ""
        for r in responses:
            if isinstance(r, aiohttp.ClientResponse) and r.status == 200:
                try:
                    content = await r.text()
                    # Пробуем раскодировать весь файл (часто подписки приходят в base64)
                    try:
                        decoded = base64.b64decode(content + "===", validate=False).decode("utf-8", errors="ignore")
                        # Если раскодировалось и похоже на конфиги, берем декод, иначе оригинал
                        if "://" in decoded:
                            raw_text += "\n" + decoded
                        else:
                            raw_text += "\n" + content
                    except: 
                        raw_text += "\n" + content
                except: pass

        # 4. Поиск ключей регуляркой
        logger.info("Парсинг ключей...")
        pattern = re.compile(r"(vmess://[\w\+\-/=]+|vless://[^\s\"'<>()]+|trojan://[^\s\"'<>()]+)", re.I)
        found_links = set(pattern.findall(raw_text))
        
        configs_to_check = []
        seen_keys = set()
        
        for link in found_links:
            cfg = VpnManager.parse_config(link)
            if not cfg or not cfg["sni"]: continue
            
            # Проверка на дубликаты (host:port)
            key = f"{cfg['host']}:{cfg['port']}"
            if key in seen_keys: continue
            seen_keys.add(key)
            
            # Фильтрация по SNI (Белый список)
            # any() проверяет, содержится ли любой из разрешенных доменов в SNI конфига
            if any(d in cfg["sni"] for d in RUSSIA_SNI):
                configs_to_check.append(cfg)

        logger.info(f"Найдено {len(configs_to_check)} потенциальных RU-конфигов. Начинаем проверку портов...")
        
        # 5. Проверка доступности (Async worker)
        alive_configs = []
        # Ограничим проверку 500 конфигами, чтобы не положить сервер и уложиться в тайминги
        configs_to_check = configs_to_check[:500] 
        sem = asyncio.Semaphore(100) # 100 одновременных проверок

        async def worker(cfg):
            async with sem:
                if await VpnManager.check_port(cfg["host"], cfg["port"]):
                    alive_configs.append(cfg["raw"])

        await asyncio.gather(*[worker(c) for c in configs_to_check])

        # 6. Сохранение
        if alive_configs:
            logger.info(f"Успех! Рабочих конфигов: {len(alive_configs)}")
            content = "\n".join(alive_configs)
            # Кодируем в Base64 для клиентов (стандартный формат подписки)
            b64_sub = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            
            with open(SUB_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(b64_sub)
            return len(alive_configs)
        else:
            logger.warning("Рабочие конфиги не найдены (0 шт).")
            return 0


def create_qr_code(data):
    """Генерирует QR код в памяти"""
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    bio = BytesIO()
    img.save(bio)
    bio.seek(0)
    return bio            