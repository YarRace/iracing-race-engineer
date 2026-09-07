"""Каждый импорт из кода объявлен в requirements.txt.

ЗАЧЕМ. Pillow стоял на машине Ярослава и не стоял на раннере. Прогон падал
на сборке картинок — за три шага от настоящей причины, — и я трижды чинил
не то: сначала кодировку, потом коды возврата, потом браузер. Настоящий
ответ был в одну строчку: пакет не объявлен.

То же самое ждёт первого человека, который поставит программу по
инструкции. У него не упадёт ничего — просто кнопка руля молча перестанет
работать, потому что pygame ставился «сам» вместе с чем-то другим.

ЧТО ЗДЕСЬ ВАЖНО. Проверяется код, который РАБОТАЕТ у пользователя: `src`,
`overlay`, инструменты и файлы в корне. Опыты в `spikes/` не проверяются —
они на то и опыты.
"""
import ast
import pathlib
import sys
from importlib.metadata import packages_distributions

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Папки, которые ставит и запускает пользователь.
SCAN = ["src", "overlay", "tools"]

# Не проверяем — с причиной у каждого.
EXCLUDE = {
    "spikes": "опыты, в программу не входят",
    "tools/transcribe.py": "расшифровка видео — мой инструмент, не часть программы",
    "tools/build_exe.py": "PyInstaller нужен только сборке релиза, он ставится в release.yml",
}

# Импорты, которых в requirements быть НЕ должно, и почему.
OPTIONAL = {
    "nvidia": "CUDA-DLL приходят пакетами nvidia-*, если пользователь их ставил; "
              "без них Whisper просто идёт на процессоре",
}


def _files():
    out = []
    for d in SCAN:
        out += sorted((ROOT / d).rglob("*.py"))
    out += sorted(ROOT.glob("*.py"))
    keep = []
    for f in out:
        rel = f.relative_to(ROOT).as_posix()
        if any(rel == e or rel.startswith(e + "/") for e in EXCLUDE):
            continue
        if "__pycache__" in rel:
            continue
        keep.append(f)
    return keep


def _local_names():
    """Имена, которые импортируются как свои, а не из pip."""
    names = {"tests", "conftest"}
    for p in ROOT.iterdir():
        if p.is_dir() and (p / "__init__.py").exists():
            names.add(p.name)
        elif p.suffix == ".py":
            names.add(p.stem)
    for d in ("src", "overlay", "tools"):
        for p in (ROOT / d).iterdir() if (ROOT / d).exists() else []:
            names.add(p.stem if p.suffix == ".py" else p.name)
    return names


def _imports():
    """Имя стороннего модуля -> файлы, где он импортирован."""
    local = _local_names()
    found = {}
    for f in _files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names = [a.name.split(".")[0] for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.level == 0:
                names = [(n.module or "").split(".")[0]]
            else:
                continue
            for m in names:
                if m and m not in local and m not in sys.stdlib_module_names:
                    found.setdefault(m, set()).add(f.relative_to(ROOT).as_posix())
    return found


def _declared():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    out = set()
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if line:
            # uvicorn[standard] — имя пакета до квадратной скобки
            out.add(line.split("[")[0].split("=")[0].split(">")[0]
                    .strip().lower().replace("_", "-"))
    return out


def test_every_import_is_declared():
    declared = _declared()
    dists = packages_distributions()
    missing = []
    for mod, where in sorted(_imports().items()):
        if mod in OPTIONAL:
            continue
        # Имя модуля и имя пакета часто разные: PIL ставится как pillow,
        # irsdk — как pyirsdk. Спрашиваем у самого Python, кто его принёс.
        owners = {d.lower().replace("_", "-") for d in dists.get(mod, [])}
        if owners & declared or mod.lower().replace("_", "-") in declared:
            continue
        missing.append(f"{mod} (импортируют: {', '.join(sorted(where))})"
                       f" — ставится пакетом {' или '.join(sorted(owners)) or '?'}")
    assert not missing, (
        "не объявлены в requirements.txt:\n  " + "\n  ".join(missing))


def test_the_optional_ones_are_still_optional():
    """Список необязательных не должен тихо разрастаться."""
    for mod, reason in OPTIONAL.items():
        assert reason and len(reason) > 20, f"{mod}: причина не написана"
    assert len(OPTIONAL) <= 3, "необязательных стало много — это уже не исключения"


def test_pillow_and_pygame_are_declared():
    """Именно эти двое уже ломались молча — pillow на прогоне, pygame у людей."""
    declared = _declared()
    for name in ("pillow", "pygame"):
        assert name in declared, f"{name} убрали из requirements.txt"
