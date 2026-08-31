"""Расшифровка речи из видео — чтобы задачу можно было НАГОВОРИТЬ, а не печатать.

Ярослав записывает экран в OBS и объясняет голосом. Кадры я вижу, звук —
нет. Здесь звук достаётся из файла и превращается в текст с отметками
времени, так что видео и рассказ читаются вместе.

Локально и офлайн: faster-whisper уже стоит в проекте (его использует
`translator.py`), модели лежат в кэше. Никуда ничего не уходит — на записи
экрана бывает видно и почту, и токены, и чужие имена.

Модель по умолчанию `small`: на десятиминутном ролике она отрабатывает
за пару минут и понимает русский. `--model medium` точнее, но втрое дольше;
`large-v3` имеет смысл, только когда запись шумная.

Запуск:
    python tools/transcribe.py "C:\\...\\video.mkv"
    python tools/transcribe.py video.mkv --model medium --out текст.txt
"""
import argparse
import pathlib
import subprocess
import sys
import tempfile


def extract_audio(video, wav):
    """Дорожка в 16 кГц моно — то, что ждёт whisper.

    ffmpeg берём из imageio-ffmpeg: он уже есть в проекте, и не нужно
    требовать от человека ставить ffmpeg отдельно.
    """
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run(
        [exe, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
         "-f", "wav", str(wav)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not pathlib.Path(wav).exists():
        tail = (r.stderr or "").strip().splitlines()[-3:]
        return False, "\n".join(tail)
    return True, ""


def stamp(sec):
    return f"{int(sec // 60):02d}:{int(sec % 60):02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--model", default="small",
                    help="small (быстро) / medium / large-v3 (для шумных записей)")
    ap.add_argument("--lang", default="ru")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    src = pathlib.Path(a.video)
    if not src.exists():
        print(f"  нет файла: {src}")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        wav = pathlib.Path(tmp) / "audio.wav"
        ok, err = extract_audio(src, wav)
        if not ok:
            print("  не удалось достать звук:\n " + err)
            print("  Если в записи нет дорожки микрофона — включи её в OBS.")
            return 1
        if wav.stat().st_size < 4000:
            print("  дорожка пустая — микрофон в записи не включён")
            return 1

        from faster_whisper import WhisperModel
        # int8 на процессоре: качество то же, а память и время заметно меньше
        model = WhisperModel(a.model, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(wav), language=a.lang,
                                          vad_filter=True)

        lines = []
        for s in segments:
            text = s.text.strip()
            if text:
                lines.append(f"[{stamp(s.start)}] {text}")

    body = "\n".join(lines)
    if a.out:
        pathlib.Path(a.out).write_text(body, encoding="utf-8")
        print(f"  сохранено: {a.out}  ({len(lines)} реплик)")
    else:
        print(body)
    if not lines:
        print("  речи не распознано — возможно, микрофон был выключен")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
