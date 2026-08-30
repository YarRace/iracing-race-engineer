"""Ресурсы сборки и данные пользователя — два РАЗНЫХ каталога.

Пока проект жил только в исходниках, это был один и тот же путь, и разницы
никто не видел. В собранном .exe она появляется, и ошибка получается тихой:
приложение поднимается, страницу отдаёт, а стили к ней — 500, потому что
tokens.css искали не по тому пути. Именно так и вышло при первой сборке.

Второй, более дорогой промах — положить данные пользователя ВНУТРЬ сборки.
Тогда обновление программы стирает историю кругов, карты трасс и всю
настройку оверлея. Проверяем оба правила.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ire import paths                                            # noqa: E402


def test_from_sources_both_roots_are_the_repo():
    """Из исходников поведение не меняется — иначе тесты врали бы про сборку."""
    assert not paths.frozen()
    assert paths.res_root() == ROOT
    assert paths.user_root() == ROOT


def test_frozen_splits_resources_from_user_data(monkeypatch, tmp_path):
    """В .exe ресурсы лежат в _internal, а данные — рядом с самим .exe."""
    meipass = tmp_path / "app" / "_internal"
    exe = tmp_path / "app" / "RaceEngineer.exe"
    meipass.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    assert paths.res_root() == meipass
    assert paths.user_root() == exe.parent
    assert paths.res_root() != paths.user_root(), \
        "слитые каталоги — обновление сотрёт историю кругов"
    assert paths.data_dir() == exe.parent / "data"
    assert paths.data_dir().is_dir()                  # создаётся при первом запуске


def test_build_maps_every_resource_the_code_asks_for():
    """Пути в сборщике обязаны совпадать с тем, что ищет код.

    Разъезд не роняет запуск — он даёт 500 на стилях и пустую витрину,
    и искать причину приходится не там, где она проявилась.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import build_exe

    dests = {d for _, d in build_exe.DATAS}
    for need in ("src/ire/dashboard/static", "docs/widgets", "docs/news", "data"):
        assert need in dests, f"сборка не кладёт {need}"

    # то же самое с другой стороны: код ищет ровно эти места
    from ire.dashboard import server, site
    assert server.STATIC.replace("\\", "/").endswith("src/ire/dashboard/static")
    assert server.DOCS.replace("\\", "/").endswith("docs")
    assert site.ROOT == paths.res_root()


def test_user_data_is_never_bundled():
    """История, круги и раскладка принадлежат человеку, а не сборке."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build_exe

    for src, _ in build_exe.DATAS:
        assert src != "data", "вся папка data/ уехала в сборку"
        assert "history.db" not in src
        assert "overlay_config" not in src
        assert "/laps" not in src and "trackmaps" not in src
