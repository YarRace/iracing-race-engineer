"""Фильтр биржи Кворка: показать только те задания, на которые стоит откликаться.

Разведка 24.08.2026 (140 заданий с 20 страниц) дала три правила, которые
экономят время сильнее любого поиска по ключевым словам:

  1. «Нанято, %» смотреть РАНЬШЕ цены. Ниже 30% — почти всегда время впустую:
     заказчик собирает предложения и пропадает. В выборке попадался человек
     с 0% при 40 размещённых проектах.

  2. Меньше 5 откликов — идти, больше 20 — нет. Заданий с <5 откликов было
     203 из ~540 открытых: это и есть окно. Там, где 30–60 откликов, письмо
     просто не прочитают.

  3. Считать цену за ЕДИНИЦУ. «5 000 ₽» звучит прилично, пока не прочитаешь,
     что это за 500 карточек. Скрипт вытаскивает из описания числа вида
     «N карточек» и считает цену за штуку — самый частый способ вляпаться.

Биржа отдаёт данные внутри страницы одним JSON (ключ wantsListData), который
рисует Vue уже в браузере. Поэтому парсим не разметку, а этот JSON: разметка
меняется от релиза к релизу, структура данных — заметно реже.

Ничего никуда не отправляет и не откликается: только читает публичный список
и печатает отобранное. Авторизация не нужна.

Запуск:
    python tools/kwork_scan.py                  # правила по умолчанию
    python tools/kwork_scan.py --pages 40       # глубже по списку
    python tools/kwork_scan.py --min-hire 50    # только надёжные заказчики
    python tools/kwork_scan.py --all            # без фильтра, посмотреть всё
    python tools/kwork_scan.py --keywords "логотип,баннер"
"""
import argparse
import gzip
import io
import re
import sys
import time
import urllib.error
import urllib.request

URL = "https://kwork.ru/projects"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# Ниши Ярослава. Специально узкие: широкое «дизайн» затягивает вёрстку сайтов
# и 3D, куда он не пойдёт, и отчёт превращается в шум.
KEYWORDS = [
    "карточк", "инфограф", "маркетплейс", "wildberries", "вайлдберриз",
    "ozon", "озон", "яндекс маркет", "rich-контент", "рич-контент",
    "описани", "копирайт", "продающ", "текст для сайт", "тексты для сайт",
    "лендинг", "презентац", "баннер", "обложк",
]

# Слова, по которым задание отбрасывается, даже если ключевое слово совпало.
# Все до одного — из реальной выборки: «рассылка коммерческих предложений»
# ловилась на «предложени», обзвон — на «продающ».
STOP = [
    "рассылк", "обзвон", "холодн", "звонк", "оператор", "менеджер по продаж",
    "яндекс директ", "директолог", "таргетолог", "seo-продвижен",
    "накрутк", "отзыв", "подписчик", "лайк",
    # Продажа чужих услуг, а не работа руками: такие задания перечисляют
    # «инфографика, карточки, логотипы» списком того, что надо ПРОДАТЬ,
    # и ловятся на ключевые слова первыми.
    "поиск клиент", "найти клиент", "привлечен", "лидогенерац", "лидов",
    "менеджер по работе", "продажник",
    # Техобслуживание кабинета продавца — не дизайн и не текст. Ловится на
    # слово «маркетплейс» и забивает выдачу: 29.08 шесть из шести совпадений
    # оказались именно такими, причём пять от одного заказчика.
    "настройка кабинет", "настроить кабинет", "настройка постав", "сопровожден",
    "fbs", "fbo", "yml", "парсер", "выгрузк", "интеграц", "api ",
    "рекламн", "таргет", "директ",
]

# Сколько единиц работы обещано: «100 карточек», «на 50 товаров», «5 слайдов».
UNITS = re.compile(
    r"(\d{2,6})\s*(?:шт|штук|карточ\w*|товар\w*|позиц\w*|слайд\w*|страниц\w*|"
    r"артикул\w*|наименован\w*)", re.I)

# Одно задание в embedded JSON. Порядок ключей у Кворка стабилен; если он
# поменяется, скрипт молча найдёт 0 заданий — на это есть проверка в main.
ITEM = re.compile(
    r'"id":(\d+),"status":"active"'
    r'[\s\S]{0,900}?"category_id":"(\d+)","description":"([\s\S]{0,900}?)","files":\['
    r'[\s\S]{0,200}?"kwork_count":(\d+),"lang":"[a-z]+","name":"([\s\S]{0,200}?)",'
    r'"max_days":"(\d+)","priceLimit":"([\d.]+)"'
    r'[\s\S]{0,1500}?"wants_count":"(\d+)","wants_hired_percent":"(\d+)"')


def fetch(page):
    """Одна страница списка. Возвращает текст либо None — сеть не повод падать."""
    url = URL if page == 1 else f"{URL}?page={page}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return raw.decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        print(f"  страница {page}: не открылась ({type(e).__name__})", file=sys.stderr)
        return None


def clean(s):
    """Из JSON-строки в человеческий текст."""
    s = (s.replace('\\r', ' ').replace('\\n', ' ').replace('\\/', '/')
          .replace('\\t', ' ').replace('\\\\', '\\'))
    s = re.sub(r"\[:[0-9a-f]+\]", "", s)                    # эмодзи-заглушки Кворка
    s = (s.replace("&bull;", "•").replace("&mdash;", "—").replace("&ndash;", "–")
          .replace("&laquo;", "«").replace("&raquo;", "»").replace("&nbsp;", " ")
          .replace("&amp;", "&").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", s).strip()


def parse(html):
    """Задания со страницы."""
    html = html.replace('\\"', '"')
    out = []
    for m in ITEM.finditer(html):
        out.append({
            "id": int(m.group(1)),
            "cat": int(m.group(2)),
            "desc": clean(m.group(3)),
            "offers": int(m.group(4)),
            "name": clean(m.group(5)),
            "days": int(m.group(6)),
            "price": int(float(m.group(7))),
            "buyer_projects": int(m.group(8)),
            "hire": int(m.group(9)),
        })
    return out


def units(job):
    """Сколько единиц работы обещано, если это вообще названо числом."""
    best = 0
    for m in UNITS.finditer(job["name"] + " " + job["desc"]):
        n = int(m.group(1))
        if n > best:
            best = n
    return best


def matches(job, keywords):
    text = (job["name"] + " " + job["desc"]).lower()
    if any(s in text for s in STOP):
        return False
    return any(k in text for k in keywords)


def score(job):
    """Чем выше, тем раньше смотреть. Надёжность заказчика весит больше цены:
    заказ на 5000 ₽ у человека с 0% найма стоит ровно ноль."""
    s = job["hire"] * 2.0
    s += max(0, 25 - job["offers"]) * 3.0
    s += min(job["price"], 30000) / 500.0
    per = job["price"] / units(job) if units(job) else 0
    if per and per < 30:                       # 30 ₽ за карточку — уже дно
        s -= 60
    if job["buyer_projects"] <= 1:             # новичок без истории — риск
        s -= 15
    return s


def show(job):
    u = units(job)
    per = f" · {job['price'] / u:.0f} ₽/шт из {u}" if u else ""
    warn = ""
    if u and job["price"] / u < 30:
        warn = "   ⚠ цена за единицу ниже плинтуса"
    elif job["hire"] < 30:
        warn = "   ⚠ заказчик редко нанимает"
    print(f"\n  {job['name']}")
    print(f"    {job['price']} ₽ · откликов {job['offers']} · нанимает {job['hire']}% "
          f"· у него проектов {job['buyer_projects']} · срок {job['days']} дн{per}")
    if warn:
        print(warn)
    print(f"    https://kwork.ru/projects/{job['id']}")
    d = job["desc"]
    print(f"    {d[:200]}{'…' if len(d) > 200 else ''}")


def main():
    ap = argparse.ArgumentParser(description="Фильтр биржи Кворка")
    ap.add_argument("--pages", type=int, default=20, help="сколько страниц пройти")
    ap.add_argument("--min-hire", type=int, default=30, help="минимальный %% найма")
    ap.add_argument("--max-offers", type=int, default=6, help="потолок откликов")
    ap.add_argument("--min-price", type=int, default=0, help="минимальная цена, ₽")
    ap.add_argument("--keywords", default="", help="свои слова через запятую")
    ap.add_argument("--all", action="store_true", help="без фильтров, показать всё")
    ap.add_argument("--limit", type=int, default=15, help="сколько показать")
    a = ap.parse_args()

    kw = [k.strip().lower() for k in a.keywords.split(",") if k.strip()] or KEYWORDS

    print(f"Читаю биржу: {a.pages} страниц…")
    jobs, seen = [], set()
    for p in range(1, a.pages + 1):
        html = fetch(p)
        if not html:
            continue
        for j in parse(html):
            if j["id"] not in seen:
                seen.add(j["id"])
                jobs.append(j)
        time.sleep(0.4)                        # не долбим чужой сервер

    if not jobs:
        print("\nНе нашёл ни одного задания. Скорее всего Кворк поменял формат\n"
              "страницы — тогда надо поправить регулярку ITEM в этом файле.")
        return 1

    print(f"Собрано заданий: {len(jobs)}")

    if a.all:
        good = jobs
    else:
        good = [j for j in jobs
                if matches(j, kw)
                and j["hire"] >= a.min_hire
                and j["offers"] <= a.max_offers
                and j["price"] >= a.min_price]

    print(f"Под твои руки и правила: {len(good)}")
    if not good:
        near = [j for j in jobs if matches(j, kw)]
        print(f"\nПо ключевым словам подходило {len(near)}, но все отсеялись "
              f"фильтрами.\nОслабь: --min-hire 0 --max-offers 20")
        return 0

    good.sort(key=score, reverse=True)
    print("\n" + "─" * 72)
    print("  СНАЧАЛА СМОТРИ ЭТИ")
    print("─" * 72)
    for j in good[:a.limit]:
        show(j)

    print("\n" + "─" * 72)
    print("  Один отклик в день, штучный. Первая фраза каждый раз своя —")
    print("  она доказывает, что ты открывал задание. Шаблон в файле")
    print("  «Ночная работа 24 августа/3. Отклики — шаблон и разбор биржи.md».")
    print("─" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
