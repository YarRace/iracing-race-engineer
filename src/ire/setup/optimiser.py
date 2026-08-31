"""Setup Optimiser: человек говорит, что делает машина, — программа что крутить.

ЧЕМ ЭТО ОТЛИЧАЕТСЯ от того, что уже есть в проекте, — вопрос не праздный,
иначе выйдет третий дубль:

  • `metrics/symptoms.py` определяет снос и занос ПО ТЕЛЕМЕТРИИ, сам;
  • `explainer/explainer.py` объясняет словами и предлагает правки МОДЕЛЬЮ.

Здесь ни того, ни другого. Ответ строится по ощущениям человека и остаётся
ОДИНАКОВЫМ от запуска к запуску — это его главное свойство. Он нужен там,
где телеметрии нет вовсе: первый заезд, чужая машина, запись не велась. И
там, где ответ модели проверить нечем, а крутить надо сейчас.

ПРО НАПРАВЛЕНИЯ. В этом проекте уже находили перевёрнутый совет по развалу
(коммит a5cc9ff), и это ошибка хуже отсутствия инструмента: человек уезжает
в гараж и делает противоположное. Поэтому:

  • у каждой правки написано, ПОЧЕМУ она так работает;
  • правки, в направлении которых нет уверенности, не выдаются вовсе — они
    перечислены отдельно, с причиной. Список короче, зато ему можно верить;
  • развала здесь нет НАМЕРЕННО: его сторона зависит от того, по какую
    сторону оптимума мы сейчас, а это измеряется — и уже измеряется Tyre
    Tool по кромкам протектора. По ощущениям развал не советуется никогда.
"""
from __future__ import annotations

import re

# ── вопросы ─────────────────────────────────────────────────────────────────
# Вопрос, на который нечем ответить в таблице правок, хуже отсутствия вопроса:
# человек отвечает, и ничего не меняется. Поэтому здесь только те, чей ответ
# действительно разводит советы.
QUESTIONS = [
    {"id": "phase", "required": True, "ask": "Where in the corner?",
     "options": [("entry", "Entry — braking and turn-in"),
                 ("mid", "Mid — off the pedals"),
                 ("exit", "Exit — on the power")]},
    {"id": "symptom", "required": True, "ask": "What does the car do?",
     "options": [("understeer", "Front pushes wide"),
                 ("oversteer", "Rear steps out")]},
    {"id": "brake", "required": False, "only_phase": "entry",
     "ask": "Still on the brakes?",
     "options": [("any", "Not sure"),
                 ("braking", "While braking"),
                 ("coasting", "After I release the brake")]},
    {"id": "speed", "required": False, "ask": "Which corners?",
     "options": [("any", "Everywhere"),
                 ("slow", "Slow corners"),
                 ("fast", "Fast corners")]},
]

PHASES = ("entry", "mid", "exit")
SYMPTOMS = ("understeer", "oversteer")

# Порядок правок в фазе. Отсутствие фазы в строке — это УТВЕРЖДЕНИЕ «в этой
# фазе рычаг не работает», а не пробел в таблице: без такой проверки
# обращение к отсутствующему ключу роняло бы запрос посреди ответа.
RANK = {
    "arb":      {"entry": 2, "mid": 1, "exit": 1},
    "pressure": {"entry": 3, "mid": 2, "exit": 3},
    "bias":     {"entry": 1},
    "wing":     {"mid": 4, "exit": 4},
    "spring":   {"entry": 5, "mid": 3, "exit": 2},
    "preload":  {"entry": 4},
    "toe":      {"entry": 6, "mid": 5},
}

# Что НЕ советуем и почему. Список ровно тот, что проверяется тестом, — иначе
# таблица врёт про то, что человек увидит.
SKIPPED = [
    {"lever": "Camber", "kind": "uncertain",
     "why": "which way to go depends on which side of the optimum you are on, "
            "and that is measured, not felt — the Tyre Tool reads it off the "
            "tread edges"},
    {"lever": "Differential ramp angles", "kind": "uncertain",
     "why": "the link from ramp angle to locking is not one I can state with "
            "confidence, and a reversed answer here is worse than none"},
    {"lever": "Anti-roll bar blades", "kind": "uncertain",
     "why": "which blade number is stiffer differs between cars"},
    {"lever": "Dampers", "kind": "uncertain",
     "why": "they act on the transition, and which of the four is at work in a "
            "given phase is argued about by people who build these cars"},
    {"lever": "Ride height and rake", "kind": "uncertain",
     "why": "the direction only holds while the car has downforce and the "
            "floor is not bottoming out"},
    {"lever": "Heave and third springs", "kind": "uncertain",
     "why": "they work in bump on both sides at once, not in roll, so they do "
            "not move the balance the way one expects"},
    {"lever": "Less rear toe-in / less front toe-out", "kind": "last_resort",
     "why": "it works, but it trades stability everywhere for turn-in in one "
            "phase — do the bars and pressures first"},
]

# Ось, на которой лечится симптом. Недостаточная поворачиваемость — переду не
# хватает, значит смягчаем ПЕРЕД; избыточная — наоборот.
_LACKS = {"understeer": "Front", "oversteer": "Rear"}
_HELPS = {"understeer": "Rear", "oversteer": "Front"}

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _find(fields, *parts):
    """Первый путь CarSetup, где встречаются все куски. None — если нет.

    Ищем по кускам, а не по жёсткому пути: у разных машин секции разные, и
    один жёсткий путь молча давал бы пустоту на половине гаража. Заодно
    ловится ловушка вида `TiresAero.LeftRearTire.StartingPressure` — секция
    задних шин называется иначе, чем задней подвески.
    """
    for key in sorted(fields or {}):
        if all(part in key for part in parts):
            return key
    return None


def _axle_fields(fields, axle, tail):
    """Пути для обоих колёс оси (или один общий, если он общий на ось)."""
    got = [k for k in sorted(fields or {})
           if k.endswith("." + tail) and axle in k]
    return got


def _numeric(v):
    return bool(_NUM.search(str(v or "")))


# Крайние положения, названные словом. Числовое поле можно двигать, пока не
# упрёшься, и упор виден только в гараже; а вот «Soft» на просьбу «softer» —
# это сразу видимый тупик, и промолчать о нём значит послать человека делать
# то, чего сделать нельзя.
_AT_LIMIT = {"softer": ("soft", "softest", "min", "minimum"),
             "stiffer": ("stiff", "stiffest", "hard", "hardest", "max", "maximum"),
             "a thinner bar": ("min", "minimum", "thinnest")}


def _at_limit(now, move):
    """Стоит ли рычаг уже в том крайнем положении, куда мы его просим."""
    if now is None or _numeric(now):
        return False
    word = str(now).strip().lower()
    return word in _AT_LIMIT.get(move, ())


def advise(phase, symptom, brake="any", speed="any",
           fields=None, tyres=None):
    """Что покрутить. Ответ детерминированный: та же анкета — тот же ответ.

    fields — плоский CarSetup, если он есть: тогда рядом с советом стоит
    текущее значение и настоящий путь до поля. Без него советы те же, просто
    без цифр — инструмент обязан работать и когда сима нет.
    tyres — свод Tyre Tool, если есть: он один умеет сказать, что давление
    уже за рабочим окном, и тогда совет «спусти ещё» переворачивается.
    """
    if phase not in PHASES or symptom not in SYMPTOMS:
        return {"ok": False, "reason": "answer the two questions above"}
    # Неизвестное значение приводим к «не знаю», а не падаем: сюда приходят
    # параметры из адресной строки.
    brake = brake if brake in ("any", "braking", "coasting") else "any"
    speed = speed if speed in ("any", "slow", "fast") else "any"
    fields = fields or {}

    lacks, helps = _LACKS[symptom], _HELPS[symptom]
    moves, unavailable = [], []

    def take(key, lever, move, path, why, caution=None, alt=None):
        rank = RANK.get(key, {}).get(phase)
        if rank is None:
            return                      # в этой фазе рычаг не работает
        if path is None and fields:
            # Сетап есть, а поля в нём нет — значит его нет у ЭТОЙ машины.
            # Сказать честно, а не промолчать.
            unavailable.append({"lever": lever,
                                "why": "this car does not expose that setting"})
            return
        # Сетапа нет вовсе — совет всё равно выдаём. В этом и смысл
        # инструмента: он нужен, когда сима под рукой нет, и первая версия
        # ровно в этом случае возвращала пустоту.
        now = fields.get(path)
        row = {"key": key, "rank": rank, "lever": lever, "move": move,
               "field": path, "now": now, "why": why}
        if caution:
            row["caution"] = caution
        if _at_limit(now, move):
            # Совет, который нельзя выполнить, хуже отсутствия совета: человек
            # уйдёт в гараж и вернётся ни с чем.
            row["at_limit"] = True
            row["caution"] = (f"already at «{now}» — this one has nowhere left "
                              f"to go" + (f", do the {alt} instead" if alt else ""))
        if alt:
            row["alt"] = alt
        moves.append(row)

    # ── 1. Стабилизаторы: самый согласованный рычаг развесовки ──────────────
    soft = _find(fields, "." + lacks + ".", "ArbSize") or _find(fields, lacks, "ArbSize")
    take("arb", f"{lacks} anti-roll bar", "softer",
         soft,
         "a stiffer bar puts more of the lateral load transfer through that "
         "axle, and a tyre gives back less when it is loaded than it loses "
         "when it is unloaded — so that axle ends up with less grip overall",
         alt=(f"stiffer {helps.lower()} bar" if _find(fields, helps, "ArbSize")
              else None))

    # ── 2. Давление на оси, которой не хватает ──────────────────────────────
    press = _axle_fields(fields, lacks, "StartingPressure")
    take("pressure", f"{lacks} tyre pressure", "a little lower",
         press[0] if press else None,
         "inside the working window a lower pressure spreads the contact patch "
         "and softens the sidewall, so the axle carries more",
         caution=_pressure_caution(tyres, lacks))

    # ── 3. Тормозной баланс — только на входе и только под тормозом ─────────
    if brake in ("braking", "any"):
        take("bias", "Brake bias",
             ("towards the rear (a smaller number)" if symptom == "understeer"
              else "towards the front (a larger number)"),
             _find(fields, "BrakePressureBias"),
             "the front tyres cannot brake and turn at the same time: bias "
             "forward spends their grip on slowing down, and nothing is left "
             "to turn with",
             caution="the number in the garage is the share at the FRONT, so "
                     "'towards the rear' means making it smaller")

    # ── 4. Заднее крыло — только там, где оно работает ──────────────────────
    if speed != "slow":
        take("wing", "Rear wing",
             "less angle" if symptom == "understeer" else "more angle",
             _find(fields, "RearWingAngle"),
             "the wing loads the rear axle and its effect grows with the "
             "square of speed, so taking angle off moves the downforce "
             "balance forward",
             caution="this takes grip away from the rear rather than adding it "
                     "at the front — the car gets faster and scarier at once")

    # ── 5. Пружина или торсион на той же оси ────────────────────────────────
    spring = _axle_fields(fields, lacks, "SpringRate")
    torsion = _axle_fields(fields, lacks, "TorsionBarOD")
    # Без сетапа неизвестно, что стоит на этой оси — пружина или торсион. На
    # машине из фикстуры спереди торсионы, сзади пружины, так что угадывать
    # нечего: пишем оба слова, пока не увидим настоящее поле.
    if spring:
        lever, how = f"{lacks} spring", "softer"
    elif torsion:
        lever, how = f"{lacks} torsion bar", "a thinner bar"
    else:
        lever, how = f"{lacks} spring or torsion bar", "softer"
    why = ("same load-transfer logic as the bar, only blunter — the spring also "
           "carries the platform, not just roll")
    if torsion:
        # Про торсион говорим ТОЛЬКО когда видим его в сетапе. Иначе выходит
        # «не знаю, что у тебя стоит» и тут же объяснение про торсион.
        why += ("; a torsion bar's stiffness goes as the fourth power of its "
                "diameter, so thinner is softer")
    take("spring", lever, how,
         (spring or torsion or [None])[0], why,
         caution=("changing the bar moves ride height too — check the car is "
                  "not bottoming out") if torsion else None)

    # ── 6. Преднатяг дифференциала — ТОЛЬКО на входе и накате ───────────────
    # На выходе под тягой блокировку задают углы рамп, преднатяг там лишь
    # малая добавка, и знак зависит от того, буксует ли внутреннее колесо.
    # Это ровно та неопределённость, из-за которой рампы лежат в SKIPPED.
    if brake != "braking":
        take("preload", "Differential preload",
             "less" if symptom == "understeer" else "more",
             _find(fields, "Preload"),
             "preload is locking that is there whatever the throttle is doing: "
             "more of it ties the wheels together, and a tied axle resists "
             "yaw — the car is steadier and turns less")

    # ── 7. Схождение ────────────────────────────────────────────────────────
    if symptom == "understeer":
        take("toe", "Front toe", "more toe-out",
             _find(fields, "Front", "ToeIn"),
             "toe-out gives the outer front wheel its working angle earlier, "
             "so the car takes the initial bite sooner",
             caution="the field is toe-IN, so more toe-out means a more "
                     "negative number")
    else:
        rear_toe = _axle_fields(fields, "Rear", "ToeIn")
        take("toe", "Rear toe", "more toe-in",
             rear_toe[0] if rear_toe else None,
             "toe-in at the rear keeps the rear axle pointing along the car "
             "and resists it stepping out")

    moves.sort(key=lambda m: m["rank"])
    for m in moves:
        m.pop("rank", None)

    return {"ok": True, "phase": phase, "symptom": symptom,
            "brake": brake, "speed": speed,
            "moves": moves,
            "unavailable": unavailable,
            "skipped": _skipped_for(phase, brake, speed),
            "have_setup": bool(fields),
            "headline": _headline(phase, symptom, speed)}


def _pressure_caution(tyres, axle):
    """Оговорка про давление — и предупреждение, если оно уже за окном.

    Направление «ниже = больше сцепления» верно ТОЛЬКО в рабочем окне, за ним
    правило переворачивается. Сказать это надо всегда: Tyre Tool ловит выход
    за окно по короне протектора, но на его данных такое не встретилось ни
    разу из 96 колёс, так что молчание предохранителя ничего не доказывает.
    """
    base = ("this holds inside the working window only — past it the rule "
            "turns around")
    corners = ((tyres or {}).get("corners") or {})
    side = "F" if axle == "Front" else "R"
    bad = [c for c, v in corners.items()
           if c[1] == side and v.get("crown") == "low"]
    if bad:
        return ("the Tyre Tool already reads " + "/".join(sorted(bad)) +
                " as under-inflated — going lower will make it worse")
    return base


def _skipped_for(phase, brake, speed):
    """Что не советуем сейчас. Причина всегда рядом: молчание про рычаг
    читается как «мы про него не знаем»."""
    out = list(SKIPPED)
    if phase == "entry" and brake == "coasting":
        out.append({"lever": "Brake bias", "kind": "not_now",
                    "why": "you are off the brakes by then, so it cannot be "
                           "what you are feeling"})
    if speed == "slow":
        out.append({"lever": "Rear wing", "kind": "not_now",
                    "why": "there is not enough speed for the wing to matter"})
    if phase == "exit":
        out.append({"lever": "Differential preload", "kind": "uncertain",
                    "why": "under power the locking comes from the ramp angles, "
                           "and which way preload helps depends on whether the "
                           "inside wheel is spinning"})
    return out


def _headline(phase, symptom, speed):
    where = {"entry": "on the way in", "mid": "in the middle",
             "exit": "on the way out"}[phase]
    what = ("the front pushes wide" if symptom == "understeer"
            else "the rear steps out")
    only = {"slow": " in slow corners", "fast": " in fast corners"}.get(speed, "")
    return f"{what.capitalize()} {where}{only}. Try these, one at a time."
