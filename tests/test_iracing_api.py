"""Официальный iRacing Data API: iRating и лицензия.

Сети здесь нет: тесты проверяют то, что можно сломать молча — формулу
хеша пароля, двухступенчатый ответ через ссылку и поведение при капче.

Пароль в тестах выдуманный. Настоящий лежит в data/iracing_auth.json,
который заполняет человек, и в код не попадает никогда.
"""
import base64
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ire.collector import iracing_api as api                     # noqa: E402


def test_password_is_hashed_the_way_iracing_expects():
    """base64(sha256(пароль + почта в НИЖНЕМ регистре)). Ошибись в регистре —
    и вход отвечает «неверный пароль», хотя пароль верный."""
    want = base64.b64encode(
        hashlib.sha256(b"secret123me@example.com").digest()).decode()
    assert api._hash("Me@Example.COM", "secret123") == want


def test_the_plain_password_never_leaves_the_hash_function():
    h = api._hash("me@example.com", "secret123")
    assert "secret123" not in h


def test_no_credentials_is_a_clean_answer_not_an_exception(tmp_path, monkeypatch):
    """Инженер зовёт это на живом цикле. Ловить исключения ради одной
    строки в интерфейсе никто не должен."""
    monkeypatch.setattr(api, "_dir", lambda: tmp_path)
    assert api.available() is False
    p = api.profile(force=True)
    assert p["ok"] is False and "credentials" in p["reason"]
    assert api.irating() is None


def test_credentials_are_read_from_the_file_the_person_fills(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_dir", lambda: tmp_path)
    (tmp_path / "iracing_auth.json").write_text(
        json.dumps({"email": " Me@Example.com ", "password": "pw"}),
        encoding="utf-8")
    email, pw = api.credentials()
    assert email == "Me@Example.com" and pw == "pw"
    assert api.available() is True


def test_a_broken_credentials_file_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_dir", lambda: tmp_path)
    (tmp_path / "iracing_auth.json").write_text("не json", encoding="utf-8")
    assert api.credentials() == ("", "")
    assert api.available() is False


def test_captcha_is_reported_not_worked_around(tmp_path, monkeypatch):
    """Капча стоит для того, чтобы её не обходили. Наше дело — сказать
    человеку, что надо один раз зайти на сайт руками."""
    monkeypatch.setattr(api, "_dir", lambda: tmp_path)
    (tmp_path / "iracing_auth.json").write_text(
        json.dumps({"email": "a@b.c", "password": "pw"}), encoding="utf-8")

    class FakeResp:
        def __init__(self, payload):
            self._p = json.dumps(payload).encode()
        def read(self):
            return self._p
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    c = api.Client()
    c.opener.open = lambda *a, **k: FakeResp({"verificationRequired": True})
    assert c.login() is False
    assert "CAPTCHA" in c.error
    assert "browser" in c.error


def test_the_two_step_link_answer_is_followed(tmp_path, monkeypatch):
    """Почти все эндпоинты отвечают не данными, а ссылкой на S3. Наивный
    клиент вернул бы ссылку как результат и «работал» бы до первого вопроса,
    где числа."""
    monkeypatch.setattr(api, "_dir", lambda: tmp_path)

    class FakeResp:
        def __init__(self, payload):
            self._p = json.dumps(payload).encode()
        def read(self):
            return self._p
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    calls = []

    def fake_open(req, timeout=0):
        url = req if isinstance(req, str) else req.full_url
        calls.append(url)
        if "members-ng" in url:
            return FakeResp({"link": "https://s3.example/data.json"})
        return FakeResp({"display_name": "Yaroslav", "cust_id": 1,
                         "licenses": [{"category_name": "Sports Car",
                                       "irating": 2450, "group_name": "A",
                                       "safety_rating": 3.5}]})

    c = api.Client()
    c.opener.open = fake_open
    got = c.get("/data/member/info")
    assert len(calls) == 2, "по ссылке не сходили"
    assert got["display_name"] == "Yaroslav"


def test_profile_shapes_licences_for_the_interface(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_dir", lambda: tmp_path)
    (tmp_path / "iracing_auth.json").write_text(
        json.dumps({"email": "a@b.c", "password": "pw"}), encoding="utf-8")

    monkeypatch.setattr(api.Client, "get", lambda self, path, **kw: {
        "display_name": "Yaroslav Chizhov", "cust_id": 42, "club_name": "Russia",
        "licenses": [{"category_name": "Sports Car", "irating": 2450,
                      "group_name": "A", "safety_rating": 3.51},
                     {"category_name": "Formula Car", "irating": 1800,
                      "group_name": "B", "safety_rating": 2.9}]})
    p = api.profile(force=True)
    assert p["ok"] and p["name"] == "Yaroslav Chizhov"
    assert {x["category"] for x in p["licenses"]} == {"Sports Car", "Formula Car"}
    assert p["licenses"][0]["licence"] == "A 3.51"
    assert api.irating("sports_car") == 2450
    assert api.irating("oval") is None


def test_a_changed_login_endpoint_is_named_not_blamed_on_the_password(tmp_path, monkeypatch):
    """31.08.2026 iRacing перевёл вход на форму в браузере: POST /auth даёт
    405 от nginx, ещё до приложения. Написать в такой ситуации «что-то пошло
    не так» — отправить человека искать ошибку в своём пароле, которого
    проблема не касается вовсе.
    """
    import urllib.error
    monkeypatch.setattr(api, "_dir", lambda: tmp_path)
    (tmp_path / "iracing_auth.json").write_text(
        json.dumps({"email": "a@b.c", "password": "pw"}), encoding="utf-8")

    c = api.Client()

    def boom(*a, **k):
        raise urllib.error.HTTPError("u", 405, "Not Allowed", {}, None)

    c.opener.open = boom
    assert c.login() is False
    assert "405" in c.error
    assert "Nothing to fix on your side" in c.error
    assert "password" not in c.error.lower()


def test_rate_limiting_is_told_apart_from_a_wrong_password(tmp_path, monkeypatch):
    import urllib.error
    monkeypatch.setattr(api, "_dir", lambda: tmp_path)
    (tmp_path / "iracing_auth.json").write_text(
        json.dumps({"email": "a@b.c", "password": "pw"}), encoding="utf-8")
    c = api.Client()

    def boom(*a, **k):
        raise urllib.error.HTTPError("u", 429, "Too Many", {}, None)

    c.opener.open = boom
    assert c.login() is False
    assert "rate-limiting" in c.error


def test_the_garage61_rating_is_never_called_irating(tmp_path, monkeypatch):
    """Garage 61 отдаёт driverRating — число другой природы, чем iRating.
    Подписать его словом «iRating» значило бы соврать в одну строчку ровно
    там, где человек сравнивает себя с другими.

    Проверяется ПОВЕДЕНИЕ, а не соседний текст в файле: первая версия этого
    теста смотрела на окно исходника и ловила соседнюю ветку, где про
    настоящий iRating написано законно.
    """
    import os
    import time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import pytest
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    sys.path.insert(0, str(ROOT))
    import ire.paths as P
    monkeypatch.setattr(P, "data_dir", lambda: tmp_path)
    import app as A
    from ire.collector import garage61 as G

    monkeypatch.setattr(api, "available", lambda: False)      # официальный закрыт
    monkeypatch.setattr(G, "my_rating", lambda *a, **k: {
        "rating": 3287, "name": "Ярослав Чижов", "when": "2026-08-21",
        "source": "Garage 61 driver rating"})
    monkeypatch.setattr(A.Engineer, "start", lambda self: None)

    w = A.App()
    try:
        w.home._draw_who()
        for _ in range(200):
            if getattr(w.home, "_who_text", ""):
                break
            time.sleep(0.02)
        text = getattr(w.home, "_who_text", "")
    finally:
        w.close()

    assert "3287" in text, f"рейтинг не показан вовсе: {text!r}"
    assert "Garage 61" in text, f"не сказано, откуда число: {text!r}"
    assert "iRating" not in text and " iR" not in text,         f"рейтинг Garage 61 подписан как iRating: {text!r}"
