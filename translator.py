#!/usr/bin/env python3
"""Переводчик реального времени.

Верх: слушает ВЕСЬ звук ПК (англ. речь собеседника) → распознаёт → переводит на
русский, показывает текст. Низ: пишешь по-русски → выдаёт английский (и копирует
в буфер), чтобы ответить англоязычному собеседнику.

STT — локальный faster-whisper (CPU). Перевод — GoogleTranslator (нужен интернет).
Запуск: python translator.py
"""
import sys
import threading

import numpy as np
import soundcard as sc
from deep_translator import GoogleTranslator
from faster_whisper import WhisperModel
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QTextEdit, QLineEdit, QPushButton, QLabel)

CHUNK_SEC = 4
RATE = 16000


class Listener(QObject):
    """Фоновый слушатель звука ПК: chunk → Whisper(en) → перевод(ru) → сигнал."""
    line = Signal(str, str)        # (english, russian)
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.running = False

    def _run(self):
        self.status.emit("Загружаю распознавание…")
        try:
            model = WhisperModel("small", device="cpu", compute_type="int8",
                                 cpu_threads=max(4, __import__("os").cpu_count() or 8))
        except Exception as e:
            self.status.emit(f"Ошибка модели: {e}")
            return
        try:
            spk = sc.default_speaker()
            mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
        except Exception as e:
            self.status.emit(f"Нет доступа к звуку: {e}")
            return
        self.status.emit("Слушаю звук ПК…")
        with mic.recorder(samplerate=RATE, channels=1) as rec:
            while self.running:
                data = rec.record(numframes=RATE * CHUNK_SEC)
                audio = np.clip(data.reshape(-1).astype(np.float32), -1, 1)
                if np.abs(audio).mean() < 0.0015:       # тишина — пропускаем
                    continue
                try:
                    segs, _ = model.transcribe(audio, language="en", beam_size=1,
                                               vad_filter=True, condition_on_previous_text=False)
                    en = "".join(s.text for s in segs).strip()
                except Exception:
                    continue
                if len(en) < 2:
                    continue
                try:
                    ru = GoogleTranslator(source="en", target="ru").translate(en)
                except Exception:
                    ru = "(ошибка перевода)"
                self.line.emit(en, ru)


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Переводчик реального времени")
        self.resize(460, 560)
        self.setStyleSheet("background:#15181d;color:#e8eaed;font-family:Segoe UI;")
        lay = QVBoxLayout(self)

        lay.addWidget(self._label("Собеседник (EN → RU):", 13))
        self.incoming = QTextEdit(readOnly=True)
        self.incoming.setStyleSheet("background:#0d0f12;border:1px solid #2a2f38;border-radius:8px;font-size:15px;")
        lay.addWidget(self.incoming, 3)

        self.listen_btn = QPushButton("▶ Слушать звук ПК")
        self.listen_btn.setStyleSheet("background:#1b1f26;border:1px solid #2a2f38;border-radius:8px;padding:8px;font-size:14px;")
        self.listen_btn.clicked.connect(self.toggle_listen)
        lay.addWidget(self.listen_btn)
        self.status = self._label("", 11, "#9099a6")
        lay.addWidget(self.status)

        lay.addWidget(self._label("Твой ответ (RU → EN):", 13))
        self.input_ru = QLineEdit()
        self.input_ru.setPlaceholderText("Напиши по-русски и нажми Enter…")
        self.input_ru.setStyleSheet("background:#0d0f12;border:1px solid #2a2f38;border-radius:8px;padding:8px;font-size:15px;")
        self.input_ru.returnPressed.connect(self.translate_out)
        lay.addWidget(self.input_ru)

        self.output_en = QTextEdit(readOnly=True)
        self.output_en.setStyleSheet("background:#11301c;border:1px solid #1f5a35;border-radius:8px;font-size:16px;color:#fff;")
        self.output_en.setMaximumHeight(110)
        lay.addWidget(self.output_en)
        copy = QPushButton("⧉ Копировать английский")
        copy.setStyleSheet("background:#1b1f26;border:1px solid #2a2f38;border-radius:8px;padding:7px;")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.output_en.toPlainText()))
        lay.addWidget(copy)

        self.listener = Listener()
        self.listener.line.connect(self.on_incoming)
        self.listener.status.connect(lambda s: self.status.setText(s))

    def _label(self, text, size, color="#9099a6"):
        l = QLabel(text); f = QFont("Segoe UI", size); l.setFont(f)
        l.setStyleSheet(f"color:{color};"); return l

    def toggle_listen(self):
        if self.listener.running:
            self.listener.stop()
            self.listen_btn.setText("▶ Слушать звук ПК")
            self.status.setText("Остановлено")
        else:
            self.listener.start()
            self.listen_btn.setText("⏹ Стоп")

    def on_incoming(self, en, ru):
        self.incoming.append(f"<span style='color:#9099a6;font-size:12px'>{en}</span><br>{ru}<br>")
        self.incoming.verticalScrollBar().setValue(self.incoming.verticalScrollBar().maximum())

    def translate_out(self):
        ru = self.input_ru.text().strip()
        if not ru:
            return
        try:
            en = GoogleTranslator(source="ru", target="en").translate(ru)
        except Exception as e:
            en = f"(ошибка: {e})"
        self.output_en.setPlainText(en)
        QGuiApplication.clipboard().setText(en)        # сразу в буфер
        self.input_ru.clear()


def main():
    app = QApplication(sys.argv)
    w = App()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
