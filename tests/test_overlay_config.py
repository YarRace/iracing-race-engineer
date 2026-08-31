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


def test_a_saved_set_is_a_snapshot_you_can_come_back_to(tmp_path):
    """Набор — снимок на момент сохранения, а не зеркало текущей раскладки.

    Зеркалом он был раньше, и это молча уничтожало сохранённое: собрал
    «Endurance night», один раз подвигал виджеты под спринт — и набора нет.
    """
    path = str(tmp_path / "ov.json")
    c = Config(path)
    c.set_enabled("fuel", True)
    c.set_opacity(0.8)
    c.save_profile("Solo")                              # снимок: fuel on, opacity 0.8
    assert c.active_profile() == "Solo" and "Solo" in c.profiles()

    c.set_enabled("gforce", True)                       # правим ТЕКУЩЕЕ, не набор
    c.save_profile("Endur")                             # новый набор из текущего
    c.set_enabled("fuel", False)

    assert c.load_profile("Solo") is True
    assert c.is_enabled("fuel") is True
    assert c.is_enabled("gforce") is False, "Solo подтянул то, чего в нём не было"
    assert c.opacity() == 0.8

    c.load_profile("Endur")
    assert c.is_enabled("fuel") is True, "Endur сохранял fuel включённым"
    assert c.is_enabled("gforce") is True

    c.delete_profile("Endur")
    assert "Endur" not in c.profiles()
    assert "Solo" in Config(path).profiles()            # наборы переживают перезапуск


def test_moving_widgets_does_not_quietly_destroy_the_set_you_are_on(tmp_path):
    """Тот самый случай, ради которого всё и менялось: подвигал экран под
    сегодняшнюю гонку — набор обязан остаться таким, каким его сохранили."""
    path = str(tmp_path / "ov.json")
    c = Config(path)
    c.set_enabled("fuel", True)
    c.set_geometry("fuel", 100, 200, 300, 120)
    c.save_profile("Endurance night")

    c.set_geometry("fuel", 1500, 40, 300, 120)          # сдвинули под спринт
    c.set_enabled("fuel", False)                        # и вовсе убрали

    assert c.load_profile("Endurance night") is True
    assert c.is_enabled("fuel") is True
    assert c.geometry("fuel")[:2] == (100, 200), "набор перезаписан движением виджета"


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


# ── сброс всего и автоснимки ────────────────────────────────────────────────

def test_reset_all_clears_the_look_but_not_the_choices(tmp_path):
    """«Сбросить вид» и «забыть, чем я пользуюсь» — разные желания."""
    c = Config(str(tmp_path / "cfg.json"))
    c.set_enabled("fuel", True)
    c.set_favourite("fuel", True)
    c.set_widget_opt("fuel", "bg", 0.2)
    c.set_geometry("fuel", 5, 6, 700, 500)
    c.set_opacity(0.4)
    c.save_widget_preset("fuel", "race")
    c.save_profile("mine")

    c.reset_all()
    assert c.widget_opt("fuel", "bg") is None       # вид — стёрт
    assert c.geometry("fuel") is None
    assert c.opacity() == 1.0
    assert c.is_enabled("fuel")                     # выбор — на месте
    assert c.is_favourite("fuel")
    assert "race" in c.widget_presets("fuel")
    assert "mine" in c.profiles()


def test_backup_writes_one_file_per_day(tmp_path):
    """Файл на запуск дал бы триста снимков за месяц и ни одного нужного."""
    c = Config(str(tmp_path / "cfg.json"))
    c.set_enabled("fuel", True)
    first = c.backup_layout(today="2026-08-30")
    c.set_enabled("delta", True)
    again = c.backup_layout(today="2026-08-30")
    assert first == again

    d = tmp_path / Config.BACKUP_DIR
    assert [f.name for f in d.glob("*.json")] == ["layout-2026-08-30.json"]
    # переписан свежим состоянием, а не оставлен утренним
    restored = Config(str(tmp_path / "r.json"))
    restored.import_layout(first)
    assert restored.is_enabled("delta")


def test_backup_keeps_only_the_last_days(tmp_path):
    c = Config(str(tmp_path / "cfg.json"))
    for day in range(1, Config.BACKUP_KEEP + 4):
        c.backup_layout(today=f"2026-08-{day:02d}")
    kept = sorted(f.name for f in (tmp_path / Config.BACKUP_DIR).glob("*.json"))
    assert len(kept) == Config.BACKUP_KEEP
    assert kept[0] == "layout-2026-08-04.json"      # самые старые подрезаны
    assert kept[-1] == f"layout-2026-08-{Config.BACKUP_KEEP + 3:02d}.json"


def test_backup_never_raises(tmp_path, monkeypatch):
    """Уронить выход из приложения из-за резервной копии нельзя."""
    c = Config(str(tmp_path / "cfg.json"))
    monkeypatch.setattr("os.makedirs",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("нет места")))
    assert c.backup_layout() == ""
