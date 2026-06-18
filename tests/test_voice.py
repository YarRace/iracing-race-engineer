import os
from ire.voice.engineer import VoiceEngineer, announce


def test_disabled_voice_is_noop(monkeypatch):
    monkeypatch.setenv("IRE_VOICE", "off")
    v = VoiceEngineer()
    assert v.enabled is False
    v.say("тест")            # не должно падать и ничего не делает
    assert v._q.qsize() == 0


def test_say_dedup_by_key(monkeypatch):
    monkeypatch.setenv("IRE_VOICE", "off")
    v = VoiceEngineer()
    v.enabled = True         # включаем логику очереди без реального TTS-воркера
    v.say("жёлтый", key="flag")
    v.say("жёлтый", key="flag")   # дубль — игнор
    v.say("зелёный", key="flag")  # новое — добавится
    assert v._q.qsize() == 2


def test_announce_flag_and_lowfuel(monkeypatch):
    monkeypatch.setenv("IRE_VOICE", "off")
    v = VoiceEngineer(); v.enabled = True
    announce(v, {"flags": [{"key": "checkered", "label": "клетчатый"}], "warnings": []},
             {"laps_on_fuel": 1.5, "avg_burn": 3.0})
    msgs = [v._q.get() for _ in range(v._q.qsize())]
    assert any("Клетчатый" in m or "финиш" in m for m in msgs)
    assert any("топлива" in m for m in msgs)
