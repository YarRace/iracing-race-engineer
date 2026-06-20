#!/usr/bin/env python3
"""Переводчик реального времени.

Верх: слушает ВЕСЬ звук ПК (англ. речь собеседника) → распознаёт → переводит на
русский. Низ: пишешь ИЛИ диктуешь голосом по-русски → выдаёт английский (и копирует
в буфер), чтобы ответить англоязычному собеседнику.

STT — локальный faster-whisper (CPU, общая модель). Перевод — GoogleTranslator.
Запуск: python translator.py
"""
import os
import sys
import threading


def _add_nvidia_dll_dirs():
    """Подсунуть CUDA-DLL из pip-пакетов nvidia-* в путь поиска (для GPU Whisper)."""
    try:
        import nvidia
        bases = list(getattr(nvidia, "__path__", []))
    except Exception:
        return
    for base in bases:
        try:
            subs = os.listdir(base)
        except Exception:
            continue
        for name in subs:
            d = os.path.join(base, name, "bin")
            if os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except Exception:
                    pass
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


_add_nvidia_dll_dirs()

import numpy as np
import httpx
import soundcard as sc
from deep_translator import GoogleTranslator

OLLAMA = os.environ.get("IRE_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("IRE_OLLAMA_MODEL", "qwen2.5:7b")
from faster_whisper import WhisperModel
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QTextEdit, QLineEdit, QPushButton, QLabel, QComboBox)

RATE = 16000
# CPU, чтобы НЕ грузить видеокарту и не лагать iRacing. medium — точность/скорость.
MODEL_NAME = os.environ.get("TRANSLATOR_WHISPER", "medium")
DEVICE = os.environ.get("TRANSLATOR_DEVICE", "cpu")


def translate(text, src, dst):
    try:
        return GoogleTranslator(source=src, target=dst).translate(text)
    except Exception:
        return "(ошибка перевода)"


# Простой английский через Ollama включается ТОЛЬКО env TRANSLATOR_SIMPLE=1
# (Ollama грузит видеокарту → может лагать iRacing; по умолчанию выключено).
SIMPLE_EN = os.environ.get("TRANSLATOR_SIMPLE", "0") == "1"


def translate_simple_en(ru):
    """Русский → ПРОСТОЙ разговорный английский через Ollama. keep_alive=0 — модель
    не висит в видеопамяти. Если выключено/недоступно — обычный перевод Google."""
    if not SIMPLE_EN:
        return translate(ru, "ru", "en")
    try:
        r = httpx.post(f"{OLLAMA}/api/chat", json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content":
                 "Translate the user's Russian into SIMPLE spoken English. Use short, "
                 "common, easy words (A2 level), natural and friendly. Keep it brief. "
                 "Output ONLY the English translation, nothing else."},
                {"role": "user", "content": ru},
            ],
            "stream": False, "keep_alive": 0,           # не держим модель в VRAM
            "options": {"temperature": 0.3, "num_predict": 120},
        }, timeout=30)
        r.raise_for_status()
        out = r.json()["message"]["content"].strip().strip('"')
        return out or translate(ru, "ru", "en")
    except Exception:
        return translate(ru, "ru", "en")


class Engine(QObject):
    """Общая модель + слушатель звука ПК (EN) + диктовка с микрофона (RU)."""
    incoming = Signal(str, str)        # (english, russian)
    dictated = Signal(str)             # распознанный русский текст
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self.model = None
        self.listening = False
        self.mic_recording = False
        self._mic_buf = []
        self.source_name = None        # какое аудиоустройство слушать (loopback)

    def load(self):
        self.status.emit(f"Загружаю распознавание ({MODEL_NAME}, {DEVICE})…")
        ct = "float16" if DEVICE == "cuda" else "int8"
        try:
            self.model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=ct,
                                      cpu_threads=max(4, os.cpu_count() or 8))
            list(self.model.transcribe(np.zeros(RATE, dtype=np.float32), language="en")[0])
            self.status.emit(f"Готово ({DEVICE.upper()}). Нажми «Слушать» или «Сказать».")
        except Exception as e:
            self.status.emit(f"Ошибка модели: {e}")

    def _stt(self, audio, lang):
        if self.model is None:
            return ""
        # нормализация громкости — усиливаем тихий звук для точного распознавания
        peak = float(np.abs(audio).max())
        if peak > 0:
            audio = audio / peak * 0.95
        segs, _ = self.model.transcribe(audio, language=lang, beam_size=5,
                                        vad_filter=True, condition_on_previous_text=False)
        return "".join(s.text for s in segs).strip()

    # --- слушатель звука ПК (английский → русский), нарезка по паузам ---
    def start_listen(self):
        self.listening = True
        threading.Thread(target=self._listen, daemon=True).start()

    def stop_listen(self):
        self.listening = False

    def _listen(self):
        while self.model is None and self.listening:
            threading.Event().wait(0.2)
        try:
            name = self.source_name or str(sc.default_speaker().name)
            mic = sc.get_microphone(id=name, include_loopback=True)
        except Exception as e:
            self.status.emit(f"Нет доступа к звуку: {e}")
            return
        short = (self.source_name or "по умолчанию")[:26]
        self.status.emit(f"Слушаю: {short}…")
        STEP, SIL, END, MINS, MAXB = RATE // 2, 0.0018, 2, 2, 40
        buf, sp, sil = [], 0, 0

        def flush():
            if len(buf) < MINS:
                return
            audio = np.clip(np.concatenate(buf).reshape(-1).astype(np.float32), -1, 1)
            en = self._stt(audio, "en")
            if len(en) >= 2:
                self.incoming.emit(en, translate(en, "en", "ru"))

        with mic.recorder(samplerate=RATE, channels=1) as rec:
            while self.listening:
                a = rec.record(numframes=STEP).reshape(-1).astype(np.float32)
                if np.abs(a).mean() > SIL:
                    buf.append(a); sp += 1; sil = 0
                elif sp > 0:
                    buf.append(a); sil += 1
                    if sil >= END:
                        flush(); buf, sp, sil = [], 0, 0
                if len(buf) >= MAXB:
                    flush(); buf, sp, sil = [], 0, 0

    # --- диктовка с микрофона (русский → в поле ввода) ---
    def toggle_mic(self):
        if self.mic_recording:
            self.mic_recording = False                # стоп → распознаём в потоке
        else:
            self.mic_recording = True
            threading.Thread(target=self._mic, daemon=True).start()

    def _mic(self):
        try:
            micdev = sc.default_microphone()
        except Exception as e:
            self.status.emit(f"Нет микрофона: {e}")
            self.mic_recording = False
            return
        self.status.emit("Говори…")
        frames = []
        with micdev.recorder(samplerate=RATE, channels=1) as rec:
            while self.mic_recording:
                frames.append(rec.record(numframes=RATE // 4).reshape(-1).astype(np.float32))
        if not frames:
            return
        audio = np.clip(np.concatenate(frames), -1, 1)
        ru = self._stt(audio, "ru")
        self.status.emit("Слушаю звук ПК…" if self.listening else "Готово.")
        if ru:
            self.dictated.emit(ru)


class App(QWidget):
    out_ready = Signal(str)

    def __init__(self):
        super().__init__()
        self.out_ready.connect(self._show_out)
        self.setWindowTitle("Переводчик реального времени")
        # поверх всех окон, но остаётся обычным окном (можно свернуть/закрыть)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(470, 600)
        self.setStyleSheet("background:#15181d;color:#e8eaed;font-family:Segoe UI;")
        lay = QVBoxLayout(self)

        lay.addWidget(self._lbl("Источник звука (куда выведен Discord):", 12))
        self.source = QComboBox()
        self.source.setStyleSheet("background:#0d0f12;border:1px solid #2a2f38;border-radius:8px;padding:6px;font-size:13px;")
        self._fill_sources()
        self.source.currentIndexChanged.connect(self._pick_source)
        lay.addWidget(self.source)

        lay.addWidget(self._lbl("Собеседник (EN → RU):", 13))
        self.incoming = QTextEdit(readOnly=True)
        self.incoming.setStyleSheet("background:#0d0f12;border:1px solid #2a2f38;border-radius:8px;font-size:15px;")
        lay.addWidget(self.incoming, 3)
        self.listen_btn = self._btn("▶ Слушать звук ПК", self.toggle_listen)
        lay.addWidget(self.listen_btn)
        self.status = self._lbl("", 11, "#9099a6")
        lay.addWidget(self.status)

        lay.addWidget(self._lbl("Твой ответ (RU → EN):", 13))
        row = QHBoxLayout()
        self.input_ru = QLineEdit()
        self.input_ru.setPlaceholderText("Напиши или продиктуй по-русски, затем Enter…")
        self.input_ru.setStyleSheet("background:#0d0f12;border:1px solid #2a2f38;border-radius:8px;padding:8px;font-size:15px;")
        self.input_ru.returnPressed.connect(self.translate_out)
        row.addWidget(self.input_ru, 4)
        self.mic_btn = self._btn("🎤 Сказать", self.toggle_mic)
        row.addWidget(self.mic_btn, 1)
        lay.addLayout(row)

        self.output_en = QTextEdit(readOnly=True)
        self.output_en.setStyleSheet("background:#11301c;border:1px solid #1f5a35;border-radius:8px;font-size:16px;color:#fff;")
        self.output_en.setMaximumHeight(110)
        lay.addWidget(self.output_en)
        lay.addWidget(self._btn("⧉ Копировать английский",
                                lambda: QGuiApplication.clipboard().setText(self.output_en.toPlainText())))

        lay.addWidget(self._lbl("Перевести текст (EN → RU):", 13))
        self.input_en = QLineEdit()
        self.input_en.setPlaceholderText("Вставь английский текст и нажми Enter…")
        self.input_en.setStyleSheet("background:#0d0f12;border:1px solid #2a2f38;border-radius:8px;padding:8px;font-size:15px;")
        self.input_en.returnPressed.connect(self.translate_in)
        lay.addWidget(self.input_en)
        self.output_ru2 = QTextEdit(readOnly=True)
        self.output_ru2.setStyleSheet("background:#11223a;border:1px solid #1f3f5a;border-radius:8px;font-size:16px;color:#fff;")
        self.output_ru2.setMaximumHeight(90)
        lay.addWidget(self.output_ru2)

        self.eng = Engine()
        self.eng.incoming.connect(self.on_incoming)
        self.eng.dictated.connect(self.on_dictated)
        self.eng.status.connect(self.status.setText)
        threading.Thread(target=self.eng.load, daemon=True).start()

    def _lbl(self, t, s, c="#9099a6"):
        l = QLabel(t); l.setFont(QFont("Segoe UI", s)); l.setStyleSheet(f"color:{c};"); return l

    def _fill_sources(self):
        self.source.addItem("По умолчанию (весь звук ПК)", None)
        try:
            for m in sc.all_microphones(include_loopback=True):
                if m.isloopback:
                    self.source.addItem(m.name, m.name)
        except Exception:
            pass

    def _pick_source(self):
        if not hasattr(self, "eng"):
            return
        self.eng.source_name = self.source.currentData()
        if self.eng.listening:                          # перезапустить слушатель на новом источнике
            self.eng.stop_listen(); self.eng.start_listen()

    def _btn(self, t, fn):
        b = QPushButton(t); b.clicked.connect(fn)
        b.setStyleSheet("background:#1b1f26;border:1px solid #2a2f38;border-radius:8px;padding:8px;font-size:14px;")
        return b

    def toggle_listen(self):
        if self.eng.listening:
            self.eng.stop_listen(); self.listen_btn.setText("▶ Слушать звук ПК")
        else:
            self.eng.start_listen(); self.listen_btn.setText("⏹ Стоп")

    def toggle_mic(self):
        self.eng.toggle_mic()
        self.mic_btn.setText("⏹ Стоп" if self.eng.mic_recording else "🎤 Сказать")

    def on_incoming(self, en, ru):
        self.incoming.append(f"<span style='color:#9099a6;font-size:12px'>{en}</span><br>{ru}<br>")
        sb = self.incoming.verticalScrollBar(); sb.setValue(sb.maximum())

    def on_dictated(self, ru):
        self.mic_btn.setText("🎤 Сказать")
        self.input_ru.setText(ru)                      # вставили — проверь и нажми Enter
        self.input_ru.setFocus()

    def translate_out(self):
        ru = self.input_ru.text().strip()
        if not ru:
            return
        self.output_en.setPlainText("…")
        threading.Thread(target=self._do_out, args=(ru,), daemon=True).start()
        self.input_ru.clear()

    def _do_out(self, ru):
        self.out_ready.emit(translate_simple_en(ru))   # простой разговорный английский

    def _show_out(self, en):
        self.output_en.setPlainText(en)
        QGuiApplication.clipboard().setText(en)

    def translate_in(self):
        en = self.input_en.text().strip()
        if not en:
            return
        self.output_ru2.setPlainText(translate(en, "en", "ru"))
        self.input_en.clear()


def main():
    app = QApplication(sys.argv)
    w = App(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
