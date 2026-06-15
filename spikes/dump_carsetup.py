"""SPIKE (Задачи 3/4): дамп текущего сетапа машины из живого SDK.

Современный .sto — закрытый бинарь, парсить нельзя. Зато ir["CarSetup"] отдаёт
весь сетап открыто. Этот скрипт сохраняет его в spikes/OUT_carsetup.json — основа
для sto_reader (Task 8) и фикстуры tests/fixtures/sample_setup.json.
"""
import irsdk, time, json

ir = irsdk.IRSDK()
assert ir.startup(), "iRacing не запущен / SDK не доступен"
time.sleep(0.3)

cs = ir["CarSetup"]
assert cs is not None, "CarSetup отсутствует — сесть в машину/гараж"
with open("spikes/OUT_carsetup.json", "w", encoding="utf-8") as f:
    json.dump(cs, f, indent=2, ensure_ascii=False)
print(f"Готово: секции {list(cs.keys())} → spikes/OUT_carsetup.json")
ir.shutdown()
