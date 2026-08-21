from overlay.config import Config


def test_enabled_and_geometry_roundtrip(tmp_path):
    path = str(tmp_path / "overlay.json")
    c = Config(path)
    assert c.is_enabled("fuel") is False          # по умолчанию выключено
    c.set_enabled("fuel", True)
    c.set_geometry("fuel", 100, 200, 220, 130)
    c.set_edit_mode(True)
    c.set_widget_opt("fuel", "bg", 0.4)
    c.set_widget_opt("fuel", "accent", "#3ea6ff")
    # перечитали с диска — состояние сохранилось
    c2 = Config(path)
    assert c2.is_enabled("fuel") is True
    assert c2.geometry("fuel") == (100, 200, 220, 130)
    assert c2.edit_mode() is True
    assert c2.geometry("unknown") is None
    assert c2.widget_opt("fuel", "bg") == 0.4
    assert c2.widget_opt("fuel", "accent") == "#3ea6ff"
    assert c2.widget_opt("fuel", "font", 1.0) == 1.0          # дефолт, если не задано
    assert c2.widget_opt("other", "bg", 0.78) == 0.78         # дефолт для незнакомого виджета
    c2.clear_widget_opts("fuel")
    assert Config(path).widget_opt("fuel", "bg", 0.78) == 0.78  # сброшено


def test_profiles_snapshot_switch_and_autosync(tmp_path):
    path = str(tmp_path / "ov.json")
    c = Config(path)
    c.set_enabled("fuel", True)
    c.set_opacity(0.8)
    c.save_profile("Solo")                              # снимок: fuel on, opacity 0.8
    assert c.active_profile() == "Solo" and "Solo" in c.profiles()
    c.set_enabled("gforce", True)                       # авто-синхрон в активный (Solo)
    c.save_profile("Endur")                             # новый профиль из текущего
    c.set_enabled("fuel", False)                        # меняем только Endur
    assert c.is_enabled("fuel") is False
    assert c.load_profile("Solo") is True               # вернулись на Solo — его раскладка
    assert c.is_enabled("fuel") is True and c.is_enabled("gforce") is True
    assert c.opacity() == 0.8
    c.load_profile("Endur")                             # Endur сохранил своё
    assert c.is_enabled("fuel") is False
    c.delete_profile("Endur")
    assert "Endur" not in c.profiles()
    assert "Solo" in Config(path).profiles()            # профили переживают перезапуск


def test_load_ignores_broken_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ not json", encoding="utf-8")
    c = Config(str(path))                          # не падает на битом файле
    assert c.is_enabled("x") is False
    assert c.edit_mode() is False
