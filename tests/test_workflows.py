"""Прогоны на GitHub: чего в них не должно быть.

Проверять здесь особенно нечего — YAML не выполняется тестом. Но два
случая уже стоили недели незамеченной поломки, и оба видны глазами в
тексте файла.
"""
import pathlib
import re
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
FLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def _text(name):
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_the_workflows_are_valid_yaml():
    assert FLOWS, "не нашёл ни одного прогона"
    for f in FLOWS:
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert d.get("jobs"), f"{f.name}: нет заданий"


def test_git_add_never_names_an_ignored_path():
    """`git add` на игноримый путь падает и НЕ ДОБАВЛЯЕТ НИЧЕГО.

    Именно это и случилось: в списке стоял `data/catalog.json`, папка
    data/ в .gitignore, add возвращал 1, `|| true` глотал ошибку, а
    следом `git diff --cached --quiet` показывал пустоту. Шаг печатал
    «коммитить нечего» на каждом прогоне, и автосборка витрины не
    сработала ни разу.
    """
    bad = []
    for f in FLOWS:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("git add "):
                continue
            for path in line[len("git add "):].split():
                if path.startswith(("-", "2>", "|", "&")):
                    continue
                r = subprocess.run(["git", "check-ignore", "-q", path],
                                   cwd=ROOT, capture_output=True)
                if r.returncode == 0:
                    bad.append(f"{f.name}: {path} — в .gitignore")
    assert not bad, "\n  ".join(["git add на игноримый путь:"] + bad)


def test_a_failing_git_add_is_not_swallowed():
    for f in FLOWS:
        for line in f.read_text(encoding="utf-8").splitlines():
            if "git add " in line:
                assert "|| true" not in line, (
                    f"{f.name}: `|| true` прячет провалившийся add — "
                    "ровно так поломка и жила незамеченной")


def test_the_deprecated_node20_actions_are_gone():
    """actions/checkout@v4 и setup-python@v5 висят на Node 20.

    GitHub уже принудительно гоняет их на Node 24 и пишет об этом
    предупреждением в каждом прогоне; в какой-то момент это станет
    ошибкой.
    """
    old = re.compile(r"actions/(checkout@v[1-4]|setup-python@v[1-5])\b")
    for f in FLOWS:
        found = old.findall(f.read_text(encoding="utf-8"))
        assert not found, f"{f.name}: устаревшие действия — {', '.join(found)}"


def test_the_russian_output_has_somewhere_to_go():
    """Вывод инструментов русский, консоль раннера — cp437.

    Без PYTHONIOENCODING первая же печатная строка роняла шаг с
    UnicodeEncodeError, ещё до тестов.
    """
    for f in FLOWS:
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        env = d.get("env") or {}
        assert str(env.get("PYTHONIOENCODING", "")).lower() == "utf-8", (
            f"{f.name}: нет PYTHONIOENCODING — русский вывод уронит шаг")


def test_the_repo_is_read_from_origin_not_hardcoded():
    """tools/ci_status.py должен работать и после переименования репозитория."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from ci_status import repo_from_url

    for url in ("https://github.com/YarRace/iracing-race-engineer.git",
                "https://github.com/YarRace/iracing-race-engineer",
                "git@github.com:YarRace/iracing-race-engineer.git",
                "  https://github.com/YarRace/iracing-race-engineer/  \n"):
        assert repo_from_url(url) == "YarRace/iracing-race-engineer", url
