from overlay.config import Config


def test_enabled_and_geometry_roundtrip(tmp_path):
    path = str(tmp_path / "overlay.json")
    c = Config(path)
    assert c.is_enabled("fuel") is False          # по умолчанию выключено
    c.set_enabled("fuel", True)
    c.set_geometry("fuel", 100, 200, 220, 130)
    c.set_locked(True)
    # перечитали с диска — состояние сохранилось
    c2 = Config(path)
    assert c2.is_enabled("fuel") is True
    assert c2.geometry("fuel") == (100, 200, 220, 130)
    assert c2.locked() is True
    assert c2.geometry("unknown") is None


def test_load_ignores_broken_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ not json", encoding="utf-8")
    c = Config(str(path))                          # не падает на битом файле
    assert c.is_enabled("x") is False
    assert c.locked() is False
