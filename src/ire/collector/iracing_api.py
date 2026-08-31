"""Официальный iRacing Data API: iRating, лицензия, история гонок.

Garage 61 отдаёт круги и имя пилота, но НЕ отдаёт iRating и лицензию —
это данные самого iRacing. Ярослав хочет, чтобы инженер подставлял их сам:
«человек загрузит инженера, и он уже будет брать информацию с базы данных
iRacing его аккаунта — как его зовут и рейтинг».

Как здесь устроен вход, и почему именно так:

  • пароль НИКОГДА не проходит через код в открытом виде. iRacing ждёт
    base64 от SHA-256 по строке `пароль + email в нижнем регистре` —
    считаем хеш на месте и отправляем только его;
  • данные для входа берутся из `data/iracing_auth.json`, который
    заполняет ЧЕЛОВЕК. Папка data/ в .gitignore, в чат ничего не уходит,
    в логах ничего не печатается;
  • cookie-сессия кладётся на диск и переиспользуется: iRacing ограничивает
    частоту входов и на частые попытки отвечает 429, а иногда требует
    капчу — и тогда вход возможен ТОЛЬКО руками через сайт.

ВАЖНО, проверено 31.08.2026 на живом сервере: документированный вход
`POST /auth` БОЛЬШЕ НЕ РАБОТАЕТ. nginx отвечает 405 ещё до приложения —
на этом пути теперь лежит страница входа на JavaScript, и POST там
запрещён. Проверено, что дело не в нас и не в сети:

    GET  /data/doc  -> 401 от приложения (значит хост тот и живой)
    POST /data/doc  -> 401 от приложения (значит POST проходит насквозь)
    GET  /auth      -> 200 nginx, HTML-страница
    POST /auth      -> 405 nginx

То есть iRacing перевёл вход на форму в браузере. Разбирать их JS-бандл,
чтобы найти новый адрес и обойти изменившийся вход, мы не будем: это
именно обход механизма, который они намеренно поменяли.

Модуль оставлен рабочим целиком — кроме шага входа. Как только станет
известен новый адрес (из их документации или от них самих), меняется одна
константа AUTH_PATH, и всё остальное поедет. Пока же имя пилота и его
рейтинг у Garage 61 всё равно есть — на главной строка не пустая.

Файл `data/iracing_auth.json`:
    {"email": "you@example.com", "password": "…"}
"""
from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from ire import paths

BASE = "https://members-ng.iracing.com"
AUTH_PATH = "/auth"                # см. предупреждение выше: сейчас отвечает 405
TIMEOUT = 20
CACHE_TTL = 3600            # iRating меняется после гонки, не каждую минуту


def _dir():
    d = paths.data_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def credentials():
    """Логин и пароль из файла, который заполняет человек. Пустое — если нет."""
    try:
        raw = (_dir() / "iracing_auth.json").read_text(encoding="utf-8-sig")
        d = json.loads(raw)
        return str(d.get("email", "")).strip(), str(d.get("password", ""))
    except (OSError, ValueError):
        return "", ""


def available():
    email, password = credentials()
    return bool(email and password)


def _hash(email, password):
    """То, что iRacing ждёт вместо пароля: base64(sha256(пароль + email)).

    Почта — в нижнем регистре, это часть их правила. Сам пароль дальше
    этой функции не уходит никуда.
    """
    digest = hashlib.sha256((password + email.lower()).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


class Client:
    """Сессия к iRacing. Cookie переживает перезапуск — вход дорогой."""

    def __init__(self):
        self.jar = http.cookiejar.MozillaCookieJar(str(_dir() / "iracing_cookies.txt"))
        try:
            self.jar.load(ignore_discard=True)
        except (OSError, http.cookiejar.LoadError):
            pass
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [("User-Agent", "iracing-race-engineer/1.0"),
                                  ("Accept", "application/json")]
        self.error = ""

    def _save(self):
        try:
            self.jar.save(ignore_discard=True)
        except OSError:
            pass

    def login(self):
        email, password = credentials()
        if not (email and password):
            self.error = ("no credentials — create data/iracing_auth.json with "
                          '{"email": "...", "password": "..."}')
            return False
        body = json.dumps({"email": email,
                           "password": _hash(email, password)}).encode("utf-8")
        req = urllib.request.Request(BASE + AUTH_PATH, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                self.error = ("iRacing is rate-limiting the login — wait a few "
                              "minutes")
            elif e.code == 405:
                # Не «что-то пошло не так»: путь входа у них изменился, и об
                # этом надо сказать прямо, иначе человек будет искать ошибку
                # в своём пароле, которого проблема не касается вовсе.
                self.error = ("iRacing no longer accepts the documented login "
                              "endpoint (405) — they moved sign-in to a "
                              "browser form. Nothing to fix on your side.")
            else:
                self.error = f"iRacing answered {e.code}"
            return False
        except Exception as e:                                # noqa: BLE001
            self.error = str(e)
            return False

        if data.get("verificationRequired") or data.get("captcha"):
            # Обходить проверку мы не будем и не должны: она для того и есть.
            self.error = ("iRacing asks for a CAPTCHA — sign in once at "
                          "members.iracing.com in a browser, then try again")
            return False
        if not data.get("authcode"):
            self.error = data.get("message") or "login rejected"
            return False
        self._save()
        return True

    def get(self, path, **params):
        """GET к API. Ответ у них двухступенчатый: сначала ссылка, потом данные.

        Почти все эндпоинты отвечают не данными, а `{"link": "..."}` на S3.
        Наивный клиент возвращает эту ссылку как результат и «работает»,
        пока кто-нибудь не спросит, где числа.
        """
        url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        try:
            with self.opener.open(urllib.request.Request(url), timeout=TIMEOUT) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):                    # сессия протухла — войти заново
                if self.login():
                    return self.get(path, **params)
            self.error = f"{e.code}"
            return None
        except Exception as e:                                # noqa: BLE001
            self.error = str(e)
            return None

        link = data.get("link") if isinstance(data, dict) else None
        if link:
            try:
                with self.opener.open(link, timeout=TIMEOUT) as r2:
                    return json.loads(r2.read())
            except Exception as e:                            # noqa: BLE001
                self.error = str(e)
                return None
        return data


def profile(force=False):
    """Имя, iRating и лицензия по категориям. Кэш на час.

    Возвращает всегда СЛОВАРЬ с полем ok — вызывающему не нужно ловить
    исключения, чтобы нарисовать одну строку в интерфейсе.
    """
    cache = _dir() / "iracing_profile.json"
    if not force:
        try:
            if time.time() - cache.stat().st_mtime < CACHE_TTL:
                return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    if not available():
        return {"ok": False, "reason": "no credentials — create "
                                       "data/iracing_auth.json"}

    c = Client()
    info = c.get("/data/member/info")
    if not info:
        if not c.login():
            return {"ok": False, "reason": c.error}
        info = c.get("/data/member/info")
    if not info:
        return {"ok": False, "reason": c.error or "no answer from iRacing"}

    lic = []
    for x in info.get("licenses") or []:
        lic.append({
            "category": x.get("category_name") or x.get("category"),
            "irating": x.get("irating"),
            "licence": f"{x.get('group_name', '')} {x.get('safety_rating', '')}".strip(),
        })
    out = {"ok": True,
           "name": info.get("display_name"),
           "cust_id": info.get("cust_id"),
           "club": info.get("club_name"),
           "licenses": lic}
    try:
        cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out


def irating(category="sports_car"):
    """iRating в одной категории — то, что подставляется в интерфейс."""
    p = profile()
    if not p.get("ok"):
        return None
    want = category.replace("_", " ").lower()
    for x in p.get("licenses") or []:
        if want in str(x.get("category", "")).lower():
            return x.get("irating")
    return None
