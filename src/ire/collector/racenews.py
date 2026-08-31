"""Новости про гонки — только те, что человеку правда интересны.

Ярослав сформулировал правило прямо: «нужно что-то прям популярное и
известное. Не всякое ралли, где победили лося в какой-то Норвегии, и никто
об этом не знает — плохой опыт уже был».

Отсюда устройство: лента не просто собирается из источников, а ФИЛЬТРУЕТСЯ.
Заголовок должен упомянуть что-то узнаваемое — Формулу 1, Ле-Ман, IMSA,
крупную симрейсинговую серию или производителя железа. Всё остальное
отбрасывается молча.

Что берём:
  • симрейсинг — iRacing, ACC, Le Mans Ultimate, rFactor, киберспорт;
  • железо — Fanatec, MOZA, Simagic, Thrustmaster, Logitech, Simucube;
  • настоящие гонки, но только крупные — F1, WEC, IMSA, Ле-Ман, IndyCar,
    NASCAR, Формула E, GT World Challenge.

Ленты читаются как обычный RSS, без внешних библиотек: стандартный
xml.etree разбирает и RSS, и Atom, а тащить в проект feedparser ради
двадцати строк незачем.

Сеть здесь — вспомогательная. Не ответил источник, отдал мусор, лежит
без интернета — лента просто короче, а приложение работает.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from ire import paths

TIMEOUT = 12
CACHE_TTL = 900               # 15 минут: новости не выходят чаще
MAX_PER_FEED = 25

# Источник = (название, адрес, раздел). Раздел нужен, чтобы человек мог
# отфильтровать одно от другого: симрейсинг и настоящие гонки читают
# по-разному, вперемешку это каша.
FEEDS = [
    ("Autosport", "https://www.autosport.com/rss/feed/f1", "F1"),
    ("Motorsport.com", "https://www.motorsport.com/rss/f1/news/", "F1"),
    ("Motorsport.com", "https://www.motorsport.com/rss/wec/news/", "WEC"),
    ("Motorsport.com", "https://www.motorsport.com/rss/imsa/news/", "IMSA"),
    ("Motorsport.com", "https://www.motorsport.com/rss/indycar/news/", "IndyCar"),
    ("Motorsport.com", "https://www.motorsport.com/rss/esports/news/", "Sim racing"),
    ("Traxion", "https://traxion.gg/feed/", "Sim racing"),
    ("Motorsport.com", "https://www.motorsport.com/rss/nascar-cup/news/", "NASCAR"),
    ("Motorsport.com", "https://www.motorsport.com/rss/formula-e/news/", "Formula E"),
]
# OverTake проверен 31.08.2026: по всем четырём обычным адресам ленты
# (/feed, /rss, /news.rss, /news/index.rss) отдаётся страница-заглушка
# на 2.8 КБ без единой записи. Ленты у них нет — не вписываем мёртвый
# источник, чтобы он молча съедал по двенадцать секунд на каждый сбор.

# Узнаваемое. Заголовок без единого такого слова в ленту не попадает —
# это и есть защита от «победили лося в Норвегии».
KNOWN = [
    # симрейсинг и железо
    "iracing", "assetto corsa", "le mans ultimate", "rfactor", "automobilista",
    "gran turismo", "forza", "f1 25", "f1 24", "eaf1", "sim racing", "simracing",
    "esports", "fanatec", "moza", "simagic", "thrustmaster", "logitech",
    "simucube", "asetek", "sim rig", "wheelbase", "direct drive",
    # настоящие гонки — только крупное
    "formula 1", "formula one", " f1 ", "f1:", "grand prix", "verstappen",
    "hamilton", "norris", "leclerc", "russell", "piastri", "alonso", "ferrari",
    "mclaren", "mercedes", "red bull", "aston martin", "williams",
    "le mans", "wec", "hypercar", "imsa", "daytona", "sebring", "petit le mans",
    "indycar", "indy 500", "nascar", "formula e", "gt world challenge",
    "porsche", "bmw m", "cadillac", "toyota gazoo", "peugeot",
]

# Списка «что выбрасывать» здесь нет намеренно. Первая версия его завела —
# и он оказался мёртвым: белый список уже отвечает на вопрос целиком, а обе
# ветки проверки возвращали одно и то же. Правило простое: нет узнаваемого
# имени — новости нет. «Ралли в Норвегии» не пройдёт не потому, что оно
# в чёрном списке, а потому, что в нём некого узнать.


def _dir():
    d = paths.data_dir() / "news"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def interesting(title, summary=""):
    """Стоит ли новость места в ленте.

    Белый список, и только он: заголовок обязан упомянуть что-то узнаваемое.
    Так «Rally winner tests a Formula 1 car» проходит (Формула 1 узнаётся),
    а «Rally win in Norway» — нет, и именно этого просил Ярослав.
    """
    t = f"{title} {summary}".lower()
    return any(k in t for k in KNOWN)


def _text(node, *names):
    for n in names:
        el = node.find(n)
        if el is not None and (el.text or "").strip():
            return html.unescape(el.text.strip())
    return ""


def _strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def parse_feed(xml_text, source="", section=""):
    """RSS или Atom → список новостей. Битый XML — пустой список, не исключение."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    out = []
    items = root.iter("item")
    for it in items:
        title = _text(it, "title")
        link = _text(it, "link")
        summary = _strip_tags(_text(it, "description"))
        when = _text(it, "pubDate")
        if title:
            out.append({"title": title, "link": link, "summary": summary[:280],
                        "when": when, "source": source, "section": section})
    if out:
        return out[:MAX_PER_FEED]

    ns = "{http://www.w3.org/2005/Atom}"
    for it in root.iter(ns + "entry"):
        title = _text(it, ns + "title")
        el = it.find(ns + "link")
        link = el.get("href") if el is not None else ""
        summary = _strip_tags(_text(it, ns + "summary", ns + "content"))
        when = _text(it, ns + "updated", ns + "published")
        if title:
            out.append({"title": title, "link": link or "", "summary": summary[:280],
                        "when": when, "source": source, "section": section})
    return out[:MAX_PER_FEED]


def fetch(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={
        "User-Agent": "iracing-race-engineer/1.0 (+news reader)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:                                        # noqa: BLE001
        return ""


def load(force=False, feeds=None):
    """Свежая лента: собрать, отфильтровать, положить в кэш.

    Кэш нужен не ради скорости, а ради работы без интернета: у Ярослава
    всё идёт через VPN, и туннель отваливается. Показать вчерашние новости
    лучше, чем пустой экран.
    """
    cache = _dir() / "feed.json"
    if not force:
        try:
            if time.time() - cache.stat().st_mtime < CACHE_TTL:
                return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    rows, seen = [], set()
    for source, url, section in (feeds if feeds is not None else FEEDS):
        for n in parse_feed(fetch(url), source, section):
            if not interesting(n["title"], n["summary"]):
                continue
            key = n["title"].lower()[:80]
            if key in seen:                    # одну новость перепечатывают все
                continue
            seen.add(key)
            rows.append(n)

    if not rows:
        try:                                   # сеть молчит — отдаём вчерашнее
            return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    try:
        cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return rows


def sections(rows):
    out = []
    for r in rows or []:
        if r.get("section") and r["section"] not in out:
            out.append(r["section"])
    return out
