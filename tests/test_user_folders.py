"""Папки, куда человек кладёт свои файлы, создаются сами и объясняют себя.

Логотипы марок и фото трасс подхватываются по имени файла — и это ровно
та возможность, о которой не узнаёт никто: пустой папки нет, а в
документацию к оверлею не заглядывают, пока что-нибудь не сломается.
"""
import pathlib

import pytest

from ire import paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "user_root", lambda: tmp_path)
    return tmp_path


def test_both_folders_appear_with_a_note_inside(home):
    paths.ensure_user_folders()
    for name in ("logos", "trackphotos"):
        note = home / "data" / name / "README.txt"
        assert note.exists(), name
        assert len(note.read_text(encoding="utf-8")) > 200, f"{name}: записка пустая"


def test_an_existing_note_is_never_overwritten(home):
    d = home / "data" / "logos"
    d.mkdir(parents=True)
    (d / "README.txt").write_text("моя записка", encoding="utf-8")
    paths.ensure_user_folders()
    assert (d / "README.txt").read_text(encoding="utf-8") == "моя записка"


def test_running_twice_changes_nothing(home):
    paths.ensure_user_folders()
    before = {f: f.read_bytes() for f in (home / "data").rglob("*")if f.is_file()}
    paths.ensure_user_folders()
    after = {f: f.read_bytes() for f in (home / "data").rglob("*") if f.is_file()}
    assert before == after


def test_a_read_only_disk_does_not_stop_the_program(home, monkeypatch):
    """Из-за папки для картинок программа падать не должна."""
    def boom(*a, **k):
        raise OSError("только чтение")

    monkeypatch.setattr(pathlib.Path, "mkdir", boom)
    assert paths.ensure_user_folders() == []


def test_the_notes_are_in_english():
    """Их читает пользователь, а интерфейс у нас английский."""
    for name, note in paths._NOTES.items():
        cyr = [c for c in note if "а" <= c.lower() <= "я"]
        assert not cyr, f"{name}: русский текст в записке для пользователя"


def test_the_note_names_the_loose_matching():
    """Главное, что человек должен понять: имя файла можно не угадывать."""
    assert "matched loosely" in paths._NOTES["trackphotos"]
    assert "matched loosely" in paths._NOTES["logos"]


@pytest.mark.parametrize("entry", ["run.py", "overlay_app.py"])
def test_both_entry_points_create_them(entry):
    src = (pathlib.Path(__file__).resolve().parents[1] / entry).read_text(
        encoding="utf-8")
    assert "ensure_user_folders()" in src, f"{entry} не создаёт папки"
