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
# ВАЖНО (подтверждено реальным стинтом, Task 7): для Cadillac GTP carcass-каналы —
# это ПЕРИОДИЧЕСКИЙ СНАПШОТ, а не непрерывная телеметрия: за стинт каждый канал даёт
# ~1 значение (последнее измерение). Значения осмысленные (spread/bias/баланс считаются
# корректно), но динамики прогрева внутри круга нет — это ограничение данных SDK.
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

# --- Стратегические каналы (топливо/остаток гонки/износ шин) ---
# Отдельно от SCALAR, чтобы не менять контракт нормализованного кадра метрик.
STRATEGY_SCALAR = {
    "fuel": "FuelLevel",                  # литры в баке (live)
    "laps_remain": "SessionLapsRemain",   # кругов до конца (32767 = без лимита)
    "time_remain": "SessionTimeRemain",   # секунд до конца сессии
    "fuel_per_hour": "FuelUsePerHour",    # мгновенный расход (л/час)
    "lap": "Lap", "t": "SessionTime", "on_pit": "OnPitRoad",
}
# Износ шин: 3 точки на угол (L/M/R протектора), 1.0 = новые, 0.0 = стёрты (live).
TIRE_WEAR = {
    "LF": ("LFwearL", "LFwearM", "LFwearR"),
    "RF": ("RFwearL", "RFwearM", "RFwearR"),
    "LR": ("LRwearL", "LRwearM", "LRwearR"),
    "RR": ("RRwearL", "RRwearM", "RRwearR"),
}
# Ёмкость бака — из DriverInfo: ir["DriverInfo"]["DriverCarFuelMaxLtr"] (89.0 для Cadillac GTP).
DRIVER_FUEL_MAX = "DriverCarFuelMaxLtr"

# Повреждения: iRacing НЕ отдаёт карту по зонам кузова — только время ремонта (сек)
# и статус фаст-ремонта. PitRepairLeft > 0 ⇒ машина побита и требует ремонта в боксе.
DAMAGE_SCALAR = {
    "repair_sec": "PitRepairLeft",            # обязательный ремонт, сек (только если damage вкл.)
    "opt_repair_sec": "PitOptRepairLeft",     # опциональный ремонт, сек
    "fast_repair_available": "FastRepairAvailable",
    "fast_repair_used": "FastRepairUsed",
    "incidents": "PlayerCarMyIncidentCount",  # мои инциденты (x-очки)
    "team_incidents": "PlayerCarTeamIncidentCount",  # инциденты ВСЕЙ команды (эндуранс)
}

# --- Гоночные «помощники» (тайминг, флаги, машина, погода) ---
RACE_SCALAR = {
    "lap": "Lap",
    "cur_lap_time": "LapCurrentLapTime",      # текущий круг, сек (live)
    "last_lap_time": "LapLastLapTime",        # последний завершённый круг
    "best_lap_time": "LapBestLapTime",        # лучший круг сессии
    "delta_best": "LapDeltaToBestLap",        # дельта к лучшему, сек (+медленнее/-быстрее)
    "delta_optimal": "LapDeltaToOptimalLap",  # дельта к оптимальному
    "position": "PlayerCarPosition",
    "class_position": "PlayerCarClassPosition",
    "rpm": "RPM",
    "shift_pct": "ShiftIndicatorPct",         # 0..1 заполнение шифт-лампы
    "shift_rpm": "PlayerCarSLShiftRPM",       # обороты переключения
    "blink_rpm": "PlayerCarSLBlinkRPM",       # обороты «мигай и переключайся»
    "abs_active": "BrakeABSactive",
    "session_flags": "SessionFlags",          # битовая маска флагов трассы
    "engine_warnings": "EngineWarnings",      # битовая маска предупреждений
    "wind_vel": "WindVel",                    # м/с
    "wind_dir": "WindDir",                    # рад
    "humidity": "RelativeHumidity",           # 0..1
    "skies": "Skies",                         # 0=ясно..3=пасмурно
    "track_wetness": "TrackWetness",          # 1=сухо..7
    "energy_pct": "EnergyERSBatteryPct",      # заряд гибридной батареи 0..1 (GTP)
    "deploy_pct": "EnergyMGU_KLapDeployPct",  # деплой энергии за круг 0..1
    "on_pit": "OnPitRoad",
    "car_left_right": "CarLeftRight",         # споттер: 0 чисто,1 слева,2 справа,3 обе,4 2слева,5 2справа
}
# Для gap до соперников — массивы по индексам машин + свой индекс из DriverInfo.
RACE_ARRAYS = {
    "pos": "CarIdxPosition", "lap_dist": "CarIdxLapDistPct", "est_time": "CarIdxEstTime",
}
DRIVER_CAR_IDX = "DriverCarIdx"  # ir["DriverInfo"]["DriverCarIdx"] — индекс своей машины
