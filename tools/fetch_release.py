"""Опись опубликованного релиза — чтобы страница Get it знала, что есть.

ЗАЧЕМ. Страница честно говорила «скачивать пока нечего», и это было
правдой. Как только релиз опубликован, та же честность требует
обратного — дать ссылку. Но статический сайт собирается заранее и сам
узнать об этом не может.

Здесь и узнаёт: спрашиваем у GitHub, есть ли ОПУБЛИКОВАННЫЙ релиз, и
кладём короткую опись в `docs/release.json`. Дальше её читает
`site.load_release()` — и живая страница, и собранная.

ЧТО ВАЖНО В УСТРОЙСТВЕ.

  • Черновик и предрелиз пропускаем. Черновик видит только владелец, а
    страницу читают все: ссылка на него — это 404 в одно нажатие.
  • Нет релизов — файл УДАЛЯЕМ. Иначе страница будет обещать то, чего
    больше нет.
  • Сети нет — файл НЕ ТРОГАЕМ и выходим с кодом 2. Отсутствие интернета
    на машине сборки не повод стирать рабочую страницу; код 2
    `refresh_assets` считает предупреждением, а не поломкой.
  • Токен не нужен: список релизов открытого репозитория отдаётся всем.

Запуск:
    python tools/fetch_release.py
    python tools/fetch_release.py --repo owner/name
"""
import argparse
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

# Имена, которые мы кладём в релиз. Чужие файлы (исходники, которые GitHub
# прикладывает сам) на страницу не выносим — их там ждут меньше всего.
OURS = (".zip",)


def fetch(repo, timeout=20):
    """Последний опубликованный релиз или None. Бросает при отсутствии сети."""
    url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = json.load(r)
    for rel in data:                       # сверху — самые свежие
        if rel.get("draft") or rel.get("prerelease"):
            continue
        assets = [{"name": a["name"],
                   "size": a.get("size", 0),
                   "url": a["browser_download_url"]}
                  for a in rel.get("assets", [])
                  if a["name"].endswith(OURS)]
        if not assets:
            continue
        return {"tag": rel.get("tag_name", ""),
                "url": rel.get("html_url", ""),
                "published": (rel.get("published_at") or "")[:10],
                "assets": assets}
    return None


def main():
    from ci_status import repo_from_url

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", help="owner/name; по умолчанию — из origin")
    ap.add_argument("--out", default=str(ROOT / "docs" / "release.json"))
    a = ap.parse_args()

    repo = a.repo or repo_from_url(subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True).stdout)
    out = pathlib.Path(a.out)

    try:
        rel = fetch(repo)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  не спросить у GitHub ({type(exc).__name__}) — "
              f"оставляю {out.name} как есть")
        return 2

    if rel is None:
        if out.exists():
            out.unlink()
            print("  опубликованных релизов нет — опись удалена")
        else:
            print("  опубликованных релизов нет — страница скажет об этом честно")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rel, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"  релиз {rel['tag']} от {rel['published']}: "
          f"{len(rel['assets'])} файл(ов) → {out}")
    for x in rel["assets"]:
        print(f"      {x['name']:<32}{x['size'] / 1048576:>7.0f} МБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
