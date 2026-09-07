"""Что там с прогоном на GitHub — и ПОЧЕМУ он упал.

ЗАЧЕМ. Журнал прогона отдаётся только владельцу репозитория: запрос к
/actions/jobs/<id>/logs отвечает 403 даже для открытого репозитория. Из-за
этого причину падения приходилось угадывать по имени упавшего шага — я
угадал трижды подряд и трижды мимо (кодировка, коды возврата, браузер), а
настоящей причиной был незаявленный Pillow.

Аннотации, в отличие от журнала, открыты всем. `refresh_assets` кладёт
туда настоящий текст ошибки, а этот скрипт его достаёт. Первый же запуск
назвал причину целиком, с именем файла и строкой.

Токен не нужен: всё через открытый API. Поэтому же есть предел по числу
запросов — при ожидании скрипт спрашивает раз в 25 секунд.

Запуск:
    python tools/ci_status.py               последние прогоны
    python tools/ci_status.py --sha abc1234 только по коммиту
    python tools/ci_status.py --wait        дождаться конца и показать причину
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.github.com/repos/{}"
# Предупреждение, которое GitHub вешает на каждый прогон и которое к делу
# не относится: показывать его каждый раз значит прятать настоящую ошибку.
NOISE = ("Node.js 20 is deprecated",)


def repo_from_url(url):
    """«владелец/имя» из адреса origin. Чистая функция — её и проверяем."""
    return (url.strip().removesuffix(".git")
            .replace("git@github.com:", "github.com/")
            .split("github.com/")[-1].strip("/"))


def repo():
    """Владелец/имя из origin — чтобы не зашивать адрес в скрипт."""
    return repo_from_url(subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True).stdout)


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("  403 — либо предел запросов, либо закрытая часть API.")
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sha", help="только прогоны по этому коммиту")
    ap.add_argument("--wait", action="store_true",
                    help="ждать, пока прогоны закончатся")
    ap.add_argument("--limit", type=int, default=6)
    a = ap.parse_args()

    base = API.format(repo())
    sha = a.sha or (subprocess.run(["git", "rev-parse", "HEAD"],
                                   capture_output=True, text=True).stdout.strip()
                    if a.wait else None)

    while True:
        runs = get(f"{base}/actions/runs?per_page={max(a.limit, 10)}")["workflow_runs"]
        if sha:
            runs = [r for r in runs if r["head_sha"].startswith(sha)]
        if not a.wait or (runs and all(r["status"] == "completed" for r in runs)):
            break
        left = [r["name"] for r in runs if r["status"] != "completed"]
        print(f"  ждём: {', '.join(left) or 'прогон ещё не появился'}")
        time.sleep(25)

    if not runs:
        print(f"  Прогонов по {sha or 'этому репозиторию'} нет.\n"
              "  Если коммит только что запушен — подожди минуту. Если в его\n"
              "  сообщении есть пометка пропуска, прогона не будет вовсе.")
        return 1

    bad = 0
    for r in runs[:a.limit]:
        mark = {"success": "ok  ", "failure": "СБОЙ", None: "идёт"}.get(
            r["conclusion"], r["conclusion"] or "?")
        print(f"\n  {mark} {r['name']:<9} {r['head_sha'][:7]}  {r['created_at']}")
        if r["conclusion"] != "failure":
            continue
        bad += 1
        for j in get(f"{base}/actions/runs/{r['id']}/jobs")["jobs"]:
            for s in j["steps"]:
                if s["conclusion"] not in ("success", "skipped", None):
                    print(f"       упал шаг: {s['name']}")
            for an in get(f"{base}/check-runs/{j['id']}/annotations"):
                msg = an.get("message") or ""
                if an["annotation_level"] == "notice" or any(n in msg for n in NOISE):
                    continue
                title = (an.get("title") or "").strip()
                if title:
                    print(f"       {title}:")
                for line in msg.splitlines():
                    print(f"         {line}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
