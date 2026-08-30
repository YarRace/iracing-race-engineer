import pytest

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


# ── сброс виджета к заводским ───────────────────────────────────────────────

def test_reset_widget_clears_look_and_geometry(tmp_path):
    """Одного сброса оформления мало: растянутый виджет остаётся растянутым,
    и «сброс» выглядит наполовину сделанным."""
    c = Config(str(tmp_path / "cfg.json"))
    c.set_widget_opt("fuel", "bg", 0.2)
    c.set_geometry("fuel", 100, 200, 500, 400)
    c.set_widget_opt("delta", "bg", 0.9)          # соседа не трогаем

    c.reset_widget("fuel")
    assert c.widget_opt("fuel", "bg") is None
    assert c.geometry("fuel") is None
    assert c.widget_opt("delta", "bg") == 0.9


def test_reset_widget_survives_an_untouched_widget(tmp_path):
    c = Config(str(tmp_path / "cfg.json"))
    c.reset_widget("never-configured")            # не падает и не создаёт мусор
    assert c.widget_opt("never-configured", "bg") is None


# ── обмен раскладками одним файлом ──────────────────────────────────────────

def test_layout_round_trip_through_a_file(tmp_path):
    """Перенос на второй компьютер: выгрузили — загрузили — то же самое."""
    src = Config(str(tmp_path / "a.json"))
    src.set_enabled("fuel", True)
    src.set_geometry("fuel", 10, 20, 230, 220)
    src.set_widget_opt("fuel", "bg", 0.5)
    src.set_opacity(0.7)
    src.set_favourite("fuel", True)
    src.save_widget_preset("fuel", "race")

    out = tmp_path / "my-layout.json"
    assert src.export_layout(str(out))
    assert out.exists()

    dst = Config(str(tmp_path / "b.json"))
    name = dst.import_layout(str(out))
    assert dst.is_enabled("fuel")
    assert dst.geometry("fuel") == (10, 20, 230, 220)
    assert dst.widget_opt("fuel", "bg") == 0.5
    assert abs(dst.opacity() - 0.7) < 1e-9
    assert dst.is_favourite("fuel")
    assert "race" in dst.widget_presets("fuel")
    assert name in dst.profiles() and dst.active_profile() == name


def test_import_refuses_a_foreign_file(tmp_path):
    """Молча принять чужой JSON — значит потерять свою раскладку без слов."""
    bad = tmp_path / "notes.json"
    bad.write_text('{"hello": "world"}', encoding="utf-8")
    c = Config(str(tmp_path / "cfg.json"))
    c.set_enabled("fuel", True)
    with pytest.raises(ValueError):
        c.import_layout(str(bad))
    assert c.is_enabled("fuel"), "раскладку не должно было тронуть"


def test_import_keeps_my_own_widget_presets(tmp_path):
    """Пресеты сливаются, а не заменяются: свои наработки не выбрасываем."""
    src = Config(str(tmp_path / "a.json"))
    src.set_widget_opt("fuel", "bg", 0.5)
    src.save_widget_preset("fuel", "from-file")
    out = tmp_path / "l.json"
    src.export_layout(str(out))

    dst = Config(str(tmp_path / "b.json"))
    dst.set_widget_opt("delta", "bg", 0.1)
    dst.save_widget_preset("delta", "mine")
    dst.import_layout(str(out))
    assert "mine" in dst.widget_presets("delta")
    assert "from-file" in dst.widget_presets("fuel")


def test_exported_file_is_readable_by_a_human(tmp_path):
    """Файл переносят руками — он должен открываться в блокноте и читаться."""
    import json as _json
    c = Config(str(tmp_path / "cfg.json"))
    c.set_enabled("fuel", True)
    out = tmp_path / "l.json"
    c.export_layout(str(out))
    text = out.read_text(encoding="utf-8")
    assert "\n" in text, "одна строка на весь файл — не для чтения"
    d = _json.loads(text)
    assert d["format"] == Config.EXPORT_FORMAT and d["version"] == 1
