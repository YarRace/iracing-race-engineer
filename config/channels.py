# Карта: нормализованное поле -> точное имя канала iRacing (подтверждено дампом Task 2)
# Источник: spikes/OUT_channels.txt (349 каналов, Cadillac V-Series.R @ Watkins Glen, live SDK)

SCALAR = {
    "speed": "Speed", "throttle": "Throttle", "brake": "Brake",
    "steer": "SteeringWheelAngle", "lat_accel": "LatAccel",
    "long_accel": "LongAccel", "yaw_rate": "YawRate",
    "gear": "Gear", "fuel": "FuelLevel",
    "lap": "Lap", "lap_dist_pct": "LapDistPct", "t": "SessionTime",
}

# Температуры шин: в дампе присутствует ТОЛЬКО carcass-набор (*tempCL/CM/CR).
# Tread/surface-набор (*tempL/M/R) в этой машине/сессии SDK не отдаёт — поэтому
# используем carcass (CL=left, CM=middle, CR=right). См. отчёт Task 2.
TIRE_TEMP = {
    "LF": ("LFtempCL", "LFtempCM", "LFtempCR"),
    "RF": ("RFtempCL", "RFtempCM", "RFtempCR"),
    "LR": ("LRtempCL", "LRtempCM", "LRtempCR"),
    "RR": ("RRtempCL", "RRtempCM", "RRtempCR"),
}

SHOCK_DEFL = {"LF": "LFshockDefl", "RF": "RFshockDefl", "LR": "LRshockDefl", "RR": "RRshockDefl"}

# Температуры из YAML-секции WeekendInfo (НЕ телеметрийные каналы).
# Путь: ir["WeekendInfo"]["TrackSurfaceTemp"] / ir["WeekendInfo"]["TrackAirTemp"]
# Оба ключа лежат на ВЕРХНЕМ уровне WeekendInfo (не во вложенном WeekendOptions).
# Значения — строки с единицами, например "39.82 C" / "25.57 C" — требуют парсинга.
WEEKEND_TRACK_TEMP = "TrackSurfaceTemp"
WEEKEND_AIR_TEMP = "TrackAirTemp"
