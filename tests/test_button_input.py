"""Чистая логика ввода оверлея (без железа): идентификатор привязки и имена."""
from overlay.button_input import input_id, key_name, hat_name


def test_input_id_joybtn_and_legacy():
    new = {"type": "joybtn", "guid": "G", "btn": 4}
    old = {"guid": "G", "btn": 4}                 # старый формат без "type" — та же кнопка
    assert input_id(new) == input_id(old) == ("joybtn", "G", 4)


def test_input_id_distinguishes_types_and_values():
    assert input_id({"type": "key", "vk": 65}) != input_id({"type": "key", "vk": 66})
    up = {"type": "hat", "guid": "G", "hat": 0, "hx": 0, "hy": 1}
    down = {"type": "hat", "guid": "G", "hat": 0, "hx": 0, "hy": -1}
    assert input_id(up) != input_id(down)
    # разные типы с «похожими» полями не путаются
    assert input_id({"type": "key", "vk": 4}) != input_id({"type": "joybtn", "guid": "G", "btn": 4})
    assert input_id(None) is None


def test_names_readable():
    assert key_name(65) == "A"
    assert key_name(0x70) == "F1"
    assert key_name(0x20) == "Space"
    assert hat_name(0, 1) == "▲ up"
    assert hat_name(1, 0) == "▶ right"
