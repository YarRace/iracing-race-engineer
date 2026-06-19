from ire.voice.engineer import spotter_phrase


def test_spotter_announces_on_change():
    assert spotter_phrase(None, 0) is None          # старт, чисто — молчим
    assert spotter_phrase(0, 1) == "Слева"
    assert spotter_phrase(1, 1) is None             # без изменения — молчим
    assert spotter_phrase(1, 2) == "Справа"
    assert spotter_phrase(2, 3) == "С обеих сторон"
    assert spotter_phrase(3, 0) == "Чисто"          # все уехали
    assert spotter_phrase(0, 4) == "Двое слева"
    assert spotter_phrase(0, 5) == "Двое справа"
