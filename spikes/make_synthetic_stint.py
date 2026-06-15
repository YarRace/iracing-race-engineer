"""ВРЕМЕННЫЙ генератор синтетической фикстуры стинта для оффлайн-разработки.

Создаёт tests/fixtures/sample_stint.jsonl по контракту нормализованного кадра,
чтобы разблокировать Задачи 15/16/19 без сима. РЕАЛЬНАЯ фикстура запишется
живым live-циклом в Задаче 7 и заменит этот файл.

Кадры имитируют 3 круга: разгон/торможение/повороты, лёгкий перегрев передка и
внутренних кромок (для осмысленных метрик). Детерминирован (без random).
"""
import json, math

OUT = "tests/fixtures/sample_stint.jsonl"
FPS = 60
LAP_SECONDS = 100          # ~100 c на круг
LAPS = 3
TRACK_TEMP = 39.82
AIR_TEMP = 25.57

def corner_temps(base, inner_bias, load):
    # tl=внутр. кромка, tm=середина, tr=внешняя. load 0..1 поднимает общую t.
    t = base + 25 * load
    return (round(t + inner_bias, 1), round(t, 1), round(t - inner_bias, 1))

frames = []
t = 0.0
fuel = 89.0
for lap in range(1, LAPS + 1):
    n = LAP_SECONDS * FPS
    for i in range(n):
        phase = i / n                      # 0..1 по кругу
        # синтетический «трек»: 4 поворота
        corner = math.sin(phase * math.pi * 4)
        steer = 0.5 * corner
        braking = max(0.0, -math.cos(phase * math.pi * 4)) * 0.8
        throttle = max(0.0, math.cos(phase * math.pi * 4)) * 0.9
        speed = 40 + 35 * (1 - abs(corner))          # медленнее в поворотах
        lat = 12 * corner
        yaw = 0.7 * steer * (speed / 60)             # «здоровый» отклик (neutral)
        load = abs(corner)
        # перед горячее зада, внутренние кромки горячее (избыток развала)
        tires = {
            "LF": dict(zip(("tl", "tm", "tr"), corner_temps(82, 7, load))),
            "RF": dict(zip(("tl", "tm", "tr"), corner_temps(82, 7, load))),
            "LR": dict(zip(("tl", "tm", "tr"), corner_temps(74, 3, load))),
            "RR": dict(zip(("tl", "tm", "tr"), corner_temps(74, 3, load))),
        }
        shocks = {"LF": 0.030 - 0.01 * load, "RF": 0.030 - 0.01 * load,
                  "LR": 0.045 - 0.01 * load, "RR": 0.045 - 0.01 * load}
        fuel -= 0.0007
        frames.append({
            "t": round(t, 3), "lap": lap, "lap_dist_pct": round(phase, 4),
            "speed": round(speed, 2), "throttle": round(throttle, 3), "brake": round(braking, 3),
            "steer": round(steer, 4), "lat_accel": round(lat, 3),
            "long_accel": round(-braking * 10 + throttle * 5, 3), "yaw_rate": round(yaw, 4),
            "gear": min(7, 2 + int(speed / 18)), "fuel": round(fuel, 2),
            "tires": {c: {k: round(v, 1) for k, v in d.items()} for c, d in tires.items()},
            "shock_defl": {c: round(v, 4) for c, v in shocks.items()},
            "track_temp": TRACK_TEMP, "air_temp": AIR_TEMP,
        })
        t += 1.0 / FPS

with open(OUT, "w", encoding="utf-8") as f:
    for fr in frames:
        f.write(json.dumps(fr) + "\n")
print(f"Готово: {len(frames)} кадров, {LAPS} круга → {OUT}")
