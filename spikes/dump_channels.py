import irsdk, time, json

ir = irsdk.IRSDK()
assert ir.startup(), "iRacing не запущен / SDK не доступен"
time.sleep(0.5)

# Все доступные телеметрийные каналы и их текущие значения
keys = sorted(ir._var_headers_dict.keys())
with open("spikes/OUT_channels.txt", "w", encoding="utf-8") as f:
    for k in keys:
        f.write(f"{k} = {ir[k]}\n")
    f.write("\n\n=== WeekendInfo ===\n")
    f.write(json.dumps(ir["WeekendInfo"], indent=2, ensure_ascii=False))
    f.write("\n\n=== DriverInfo (active car) ===\n")
    f.write(json.dumps(ir["DriverInfo"], indent=2, ensure_ascii=False))
print(f"Готово: {len(keys)} каналов → spikes/OUT_channels.txt")
ir.shutdown()
