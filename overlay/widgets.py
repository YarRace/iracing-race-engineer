"""Виджеты оверлея, сгруппированные как вкладки инженера: solo / endur / setup.

Простые «список значений» виджеты наследуют StatWidget (переопределяют rows()).
Сложные (графика/таблицы) — от OverlayWidget с draw(). Порядок и группировка в WIDGETS.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QPainterPath, QFont, QPolygonF

from overlay.base import OverlayWidget, lap_time

GREEN, RED, AMBER, BLUE, MUTED, WHITE, PURPLE = "#2ecc71", "#e74c3c", "#f1c40f", "#3ea6ff", "#9099a6", "#e8eaed", "#c77dff"


def _clr(c):
    try:
        return QColor("#" + format(int(c) & 0xFFFFFF, "06x")) if c else QColor(RED)
    except Exception:
        return QColor(RED)


def ev(e):
    return {"Race": "Race", "Practice": "Practice", "Qualify": "Qualify", "Open Qualify": "Qualify",
            "Lone Qualify": "Qualify", "Warmup": "Warmup", "Test": "Test", "Time Trial": "Time Trial",
            "Offline Testing": "Test"}.get(e, e or "—")


def fmt_time(s):
    if not isinstance(s, (int, float)):
        return "—"
    s = int(max(0, s))
    h, m, ss = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{ss:02d}" if h else f"{m}:{ss:02d}"


def wetness(w):
    if w is None:
        return "—"
    return "dry" if w <= 1 else ("drying" if w <= 3 else ("damp" if w <= 5 else "wet"))


def tcol(v):
    if v is None:
        return "#333"
    if v < 70:
        return BLUE
    if v < 100:
        return GREEN
    if v < 108:
        return AMBER
    return RED


def _tele():
    try:
        from overlay import telemetry
        return telemetry.feed()
    except Exception:
        return None


def fastval(name, fallback):
    """Свежее значение из ПРЯМОЙ телеметрии (плавно, 60/сек), иначе — из HTTP (fallback).
    Так быстрые виджеты (скорость/обороты/газ/дельта) идут без HTTP-задержки."""
    t = _tele()
    if t is not None and t.ok:
        v = t.get(name)
        if v is not None:
            return v
    return fallback

def _worst(corner):
    """Худшая зона угла (0..1). Понимает и старый формат — одно число на угол."""
    if isinstance(corner, (int, float)):
        return corner
    if isinstance(corner, dict):
        v = corner.get("min")
        if v is None:
            vals = [x for k, x in corner.items() if k != "min" and isinstance(x, (int, float))]
            return min(vals) if vals else None
        return v
    return None



def _logo(name):
    """QPixmap логотипа марки (или None) — с защитой от отсутствия модуля/файла."""
    try:
        from overlay import logos
        return logos.logo(name)
    except Exception:
        return None


def _draw_logo(p, px, x, cy, size):
    """Логотип, вписанный в бокс (высота=size, ширина≤size×2.4), центр по вертикали cy, слева от x.
    Регулируемый размер — логотипы «пейзажные», поэтому вписываем, а не просто по высоте строки."""
    if px is None:
        return
    scaled = px.scaled(int(size * 2.4), int(size), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    p.drawPixmap(int(x), int(cy - scaled.height() / 2), scaled)


def fmt_driver_name(raw, style="full", case="normal"):
    """Форматирование имени пилота (Kapps Driver Name Style) — общее для Standings/Relative."""
    parts = (raw or "").split()
    if len(parts) >= 2 and style != "full":
        first, last = parts[0], parts[-1]
        if style == "f_last":
            raw = f"{first[0]}. {last}"
        elif style == "last_f":
            raw = f"{last} {first[0]}."
        elif style == "last":
            raw = last
        elif style == "initials":
            raw = f"{first[0]}. {last[0]}."
    return raw.upper() if case == "upper" else raw


class StatWidget(OverlayWidget):
    """База для «список значений»: заголовок + строки (метка … значение).
    Через ⚙: строку скрыть, перекрасить, поменять местами (↑↓)."""
    REORDERABLE = True

    def draw(self, p):
        self.title(p, self.TITLE)
        # группируем строки в «блоки» по метке (метка + её безымянные продолжения)
        blocks, natural, cur = {}, [], None
        for row in self.rows():
            if row[0]:
                cur = row[0]
                if cur not in blocks:
                    blocks[cur] = []
                    natural.append(cur)
            if cur is None:
                continue
            blocks[cur].append(row)
        order = self._opt("order", []) or []
        oset = set(order)
        seq = [k for k in order if k in blocks] + [k for k in natural if k not in oset]
        y = 44
        for label in seq:
            if not self.part_on(label):                       # скрыт через ⚙/редактор
                continue
            top = y
            for row in blocks[label]:
                left = 12
                if row[0]:
                    self.text(p, 12, y, row[0], MUTED, 10)
                    left = 12 + p.fontMetrics().horizontalAdvance(str(row[0])) + 8
                # значение с key=label: кликабельно + берёт свой цвет/размер/шрифт
                self.text_right(p, self.width() - 12, y, row[1],
                                row[2] if len(row) > 2 else WHITE, 14, True, key=label,
                                avail=max(24, self.width() - 12 - left))
                y += 24
            self.hit(label, 8, top - 16, self.width() - 16, y - top)   # вся строка кликабельна

    def parts(self):
        seen, out = set(), []
        for row in self.rows():                           # элементы = помеченные строки (без дублей)
            lbl = row[0]
            if lbl and lbl not in seen:
                seen.add(lbl)
                out.append((lbl, lbl))
        return out

    def rows(self):
        return []


# ================= SOLO =================
class InputsWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "inputs", "Inputs", (240, 110), "solo", ("live",)
    BLURB = "Speed, gear and the pedal traces side by side."

    def draw(self, p):
        l = self.store.get("live")
        self.title(p, "SPEED / PEDALS")
        if self.part_on("speed"):
            spd = fastval("speed", l.get("speed"))
            kmh = round(spd * 3.6) if isinstance(spd, (int, float)) else "—"
            self.text(p, 12, 52, kmh, WHITE, 26, True, key="speed")
            self.text(p, 96, 52, "km/h", MUTED, 10)
        if self.part_on("gear"):
            g = fastval("gear", l.get("gear"))
            gear = ("N" if g == 0 else "R" if g == -1 else g) if g is not None else "—"
            self.text(p, self.width() - 40, 52, gear, WHITE, 26, True, key="gear")
        if self.part_on("throttle"):
            self.bar(p, 12, 66, self.width() - 24, 11, fastval("throttle", l.get("throttle")) or 0, QColor(GREEN), key="throttle")
        if self.part_on("brake"):
            self.bar(p, 12, 82, self.width() - 24, 11, fastval("brake", l.get("brake")) or 0, QColor(RED), key="brake")

    def parts(self):
        return [("speed", "Speed"), ("gear", "Gear"), ("throttle", "Throttle"), ("brake", "Brake")]


class FuelWidget(StatWidget):
    """Топливо и пит-стопы.

    Средний расход отвечает на вопрос «хватит ли, если ехать как ехал».
    Но в гонке важнее второй: «а если поеду быстрее». Поэтому считаем
    запас по ТРЁМ сценариям — средний расход, максимальный из виденных
    и минимальный. Разброс между ними и есть цена агрессии.

    Запас в кругах красим отдельно: меньше двух кругов — красный, потому
    что на этом остатке уже нельзя проехать лишний круг под жёлтыми.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "fuel", "Fuel & pit", (230, 220), "solo", ("strategy",)
    BLURB = "Fuel left, burn rate and what the next stop needs."

    def extra_settings(self, lay):
        self.opt_check(lay, "Burn scenarios", "show_scenarios", True)
        self.opt_check(lay, "Refuel in laps", "show_add_laps", True)
        self.opt_slider(lay, "Warn below (laps)", "warn_laps", 1, 10, 2)

    def rows(self):
        g = self.store.get("strategy")
        pl = g.get("plan") or {}
        fuel = g.get("fuel")
        avg, mx, mn = g.get("avg_burn"), g.get("max_burn"), g.get("min_burn")
        left = g.get("laps_on_fuel")
        warn = self._opt("warn_laps", 2)

        col = WHITE
        if isinstance(left, (int, float)):
            col = RED if left < warn else (AMBER if left < warn * 2 else GREEN)
        out = [("Fuel", f"{fuel} L" if fuel is not None else "—"),
               ("Range", f"~{left} laps" if left is not None else "—", col)]

        if self._opt("show_scenarios", True) and isinstance(fuel, (int, float)):
            # Подписи короткие не для красоты: колонка подписи в StatWidget
            # узкая, и «At average» налезало на значение справа.
            for label, burn, c in (("Average", avg, WHITE),
                                   ("Pushing", mx, AMBER),
                                   ("Saving", mn, GREEN)):
                if isinstance(burn, (int, float)) and burn > 0:
                    out.append((label, f"{fuel / burn:.1f} laps  ({burn:.2f} L)", c))

        add = g.get("fuel_to_add")
        if isinstance(add, (int, float)):
            out.append(("Add", f"+{add} L" if add > 0 else "not needed",
                        AMBER if add > 0 else GREEN))
            # тот же долив в кругах: литры в black box проще править, зная их цену
            if add > 0 and isinstance(avg, (int, float)) and avg and self._opt("show_add_laps", True):
                out.append(("Adds", f"~{add / avg:.1f} laps"))
        if pl.get("stops") is not None:
            out.append(("Pit stops", "not needed" if pl["stops"] == 0 else str(pl["stops"])))
        return out


class DeltaWidget(OverlayWidget):
    """Дельта к лучшему кругу крупной цифрой.

    Под цифрой — полоса: она заполняется от центра влево при выигрыше и
    вправо при проигрыше. Цифру надо прочитать, полосу видно боковым
    зрением, и в повороте это единственное, на что хватает внимания.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "delta", "Delta to best", (220, 120), "solo", ("race",)
    BLURB = "Delta to your best lap, in one large number."

    def extra_settings(self, lay):
        self.opt_slider(lay, "Bar scale (0.1s)", "scale", 5, 50, 10)
        self.opt_check(lay, "Bar under the number", "show_bar", True)
        self.opt_choice(lay, "Decimal places", "digits",
                        [("2", "0.00"), ("3", "0.000")])

    def draw(self, p):
        self.title(p, "DELTA TO BEST")
        d = fastval("delta_best", self.store.get("race").get("delta_best"))
        bar = self._opt("show_bar", True)
        cy = self.height() * (0.52 if bar else 0.5) + 8

        if not isinstance(d, (int, float)):
            self.text_center(p, "—", MUTED, 22, y=cy)
            return

        col = GREEN if d <= 0 else RED
        digits = int(self._opt("digits", "2"))
        self.text_center(p, ("+" if d > 0 else "") + f"{d:.{digits}f}", col, 30, y=cy, key="delta")

        if not bar:
            return
        scale = max(0.1, self._opt("scale", 10) / 10.0)   # ± сек на полную половину
        w, y, h = self.width(), self.height() - 20, 10.0
        cx = w / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#20252d"))
        p.drawRoundedRect(QRectF(12, y, w - 24, h), h / 2, h / 2)
        frac = max(-1.0, min(1.0, d / scale))
        if abs(frac) > 0.01:
            half = (w / 2 - 12) * abs(frac)
            p.setBrush(QColor(col))
            rect = QRectF(cx, y, half, h) if frac > 0 else QRectF(cx - half, y, half, h)
            p.drawRoundedRect(rect, h / 2, h / 2)
        p.setBrush(QColor("#3a4150"))                     # центральная риска
        p.drawRect(QRectF(cx - 1, y - 3, 2, h + 6))


class ShiftWidget(StatWidget):
    """Обороты и момент переключения.

    Голое число оборотов бесполезно: важно, сколько осталось до переключения.
    Показываем процент от точки шифта и сколько оборотов в запасе — на это
    можно смотреть боковым зрением, не считая цифры.

    Смещение точки: многие переключают раньше, чем советует SDK, потому что
    держат машину в полке момента. Настройка сдвигает порог на ±500 об/мин.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "shift", "RPM & shift", (200, 130), "solo", ("race",)
    BLURB = "Revs and the moment to pull the next gear."

    def extra_settings(self, lay):
        self.opt_slider(lay, "Shift point offset (rpm)", "shift_offset", -500, 500, 0)
        self.opt_check(lay, "Rpm left to shift", "show_left", True)

    def rows(self):
        r = self.store.get("race")
        rpm = fastval("rpm", r.get("rpm"))
        sh = fastval("shift_rpm", r.get("shift_rpm"))
        if isinstance(sh, (int, float)) and sh > 0:
            sh = max(1000.0, sh + self._opt("shift_offset", 0))

        if not isinstance(rpm, (int, float)):
            return [("RPM", "—"), ("Shift at", "—")]

        frac = rpm / sh if isinstance(sh, (int, float)) and sh > 0 else None
        up = frac is not None and frac >= 1.0
        near = frac is not None and frac >= 0.94

        col = RED if up else (AMBER if near else WHITE)
        out = [("RPM", str(round(rpm)), col)]
        if frac is not None:
            out.append(("Of shift", f"{round(frac * 100)}%", col))
            if self._opt("show_left", True):
                left = sh - rpm
                out.append(("To shift", f"{round(left)}" if left > 0 else "NOW",
                            AMBER if near and not up else MUTED))
            out.append(("Shift at", str(round(sh))))
        else:
            out.append(("Shift at", "—"))
        return out


class TopSpeedWidget(StatWidget):
    """Скорость: сейчас, максимум за круг и максимум за сессию.

    Максимум за сессию сам по себе бесполезен — он снимается один раз
    и больше не меняется. А вот максимум ЗА КРУГ показывает, теряешь ли
    ты на прямой: упал на 4 км/ч — значит вышел из поворота хуже.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "topspeed", "Top speed", (210, 130), "solo", ("live", "race")
    BLURB = "Speed now, best this lap and best this session."

    def extra_settings(self, lay):
        self.opt_choice(lay, "Units", "units",
                        [("kmh", "km/h"), ("mph", "mph")])
        self.opt_check(lay, "Best of this lap", "show_lap_max", True)

    def _sp(self, kmh):
        if not isinstance(kmh, (int, float)):
            return "—"
        if self._opt("units", "kmh") == "mph":
            return f"{round(kmh / 1.609)} mph"
        return f"{round(kmh)} km/h"

    def rows(self):
        spd = self.store.get("live").get("speed")
        lap = self.store.get("race").get("lap")
        kmh = spd * 3.6 if isinstance(spd, (int, float)) else None

        if lap is not None and lap != getattr(self, "_lap", None):
            self._lap = lap
            self._prev_lap_mx = getattr(self, "_lap_mx", None)
            self._lap_mx = 0.0
        if kmh is not None:
            self._mx = max(getattr(self, "_mx", 0.0), kmh)
            self._lap_mx = max(getattr(self, "_lap_mx", 0.0), kmh)

        out = [("Now", self._sp(kmh))]
        if self._opt("show_lap_max", True):
            lm = getattr(self, "_lap_mx", None)
            prev = getattr(self, "_prev_lap_mx", None)
            col = WHITE
            if isinstance(lm, (int, float)) and isinstance(prev, (int, float)) and prev > 0:
                col = GREEN if lm >= prev else AMBER
            out.append(("This lap", self._sp(lm), col))
            if isinstance(prev, (int, float)) and prev > 0:
                out.append(("Last lap", self._sp(prev), MUTED))
        out.append(("Session", self._sp(getattr(self, "_mx", None)), BLUE))
        return out


class SlipWidget(StatWidget):
    """Срыв: не просто «скользит», а В КАКУЮ СТОРОНУ.

    Раньше виджет смотрел только на скорость рыскания и говорил «sliding».
    Но снос передней оси и занос задней лечатся ПРОТИВОПОЛОЖНЫМ: при сносе
    руль надо распустить, при заносе — ловить. Одно слово на оба случая
    ничем не помогает.

    Различаем по несоответствию руля и рыскания: много руля при слабом
    рыскании — машина не поворачивает, снос; рыскание больше, чем просит
    руль, — задняя ось поехала.

    Виджет САМ КАЛИБРУЕТСЯ под машину. Связь руля и рыскания зависит от
    передаточного числа рулевой и колёсной базы, а SDK отдаёт угол РУЛЯ,
    а не колёс. Любая зашитая константа врала бы: у формулы и у GT3 эти
    числа разные. Поэтому копим отношение рыскания к рулю на СПОКОЙНЫХ
    участках, берём медиану за норму этой машины и сравниваем с ней.

    Это признак, а не измерение: настоящий угол увода требует данных
    с колёс, которых в SDK нет.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "slip", "Slip", (210, 130), "solo", ("live",)
    BLURB = "Not just that the car is sliding — which end is sliding."
    MIN_SPEED = 8.0                                  # м/с, ниже — манёвры в боксе


    CALIB_N = 200                                    # замеров нормы (≈ 3 секунды)
    CALIB_MIN = 40                                   # с чего начинаем верить медиане

    def _balance(self, live, yr, dps, thr):
        """Снос / занос / нейтрально — по отклонению от нормы ЭТОЙ машины."""
        steer = fastval("steer", live.get("steer"))
        spd = fastval("speed", live.get("speed"))
        if not (isinstance(steer, (int, float)) and isinstance(spd, (int, float))):
            return ("Balance", "—", MUTED)
        if spd <= self.MIN_SPEED or abs(steer) < 0.05:
            return ("Balance", "—", MUTED)      # стоим или едем прямо — судить не о чем

        k = abs(yr) / (abs(steer) * spd)
        base = getattr(self, "_calib", [])
        if dps < thr:                                # норму копим только на держащей машине
            base = (base + [k])[-self.CALIB_N:]
            self._calib = base
        if len(base) < self.CALIB_MIN:
            return ("Balance", "learning…", MUTED)

        ref = sorted(base)[len(base) // 2]            # медиана устойчивее среднего к выбросам
        if ref <= 1e-9:
            return ("Balance", "—", MUTED)
        ratio = k / ref
        if ratio < 0.6:
            return ("Balance", "understeer", AMBER)
        if ratio > 1.6:
            return ("Balance", "oversteer", RED)
        return ("Balance", "balanced", GREEN)

    def extra_settings(self, lay):
        self.opt_slider(lay, "Slip threshold (°/s)", "thr", 10, 60, 25)
        self.opt_check(lay, "Tell understeer from oversteer", "detect_kind", True)

    def rows(self):
        l = self.store.get("live")
        yr = fastval("yaw_rate", l.get("yaw_rate"))
        if not isinstance(yr, (int, float)):
            return [("Slip", "—")]

        dps = abs(yr * 180 / math.pi)
        thr = self._opt("thr", 25)
        state, col = (("stable", GREEN) if dps < thr
                      else ("sliding", AMBER) if dps < thr * 2 else ("spinning!", RED))
        out = [("State", state, col)]

        if self._opt("detect_kind", True):
            out.append(self._balance(l, yr, dps, thr))

        out.append(("Yaw rate", f"{round(dps)}°/s"))
        return out


class PosTrendWidget(StatWidget):
    """Движение по позициям за заезд.

    «+2 со старта» полезно, но не говорит, что происходит СЕЙЧАС. Поэтому
    держим ещё и лучшую с худшей позицией и последнее изменение: подряд
    падающая позиция в середине гонки — повод проверить резину, а не
    гнать сильнее.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "postrend", "Position trend", (210, 150), "solo", ("race",)
    BLURB = "How your position moved across the race."

    def extra_settings(self, lay):
        self.opt_choice(lay, "Count by", "which",
                        [("class", "in class"), ("overall", "overall")])
        self.opt_check(lay, "Best and worst this session", "show_range", True)

    def rows(self):
        r = self.store.get("race")
        pos = (r.get("class_position") if self._opt("which", "class") == "class"
               else r.get("position"))
        if pos is None:
            return [("Position", "—")]

        if not hasattr(self, "_start"):
            self._start = self._best = self._worst = pos
        self._best = min(self._best, pos)
        self._worst = max(self._worst, pos)
        last = getattr(self, "_last", pos)
        self._last = pos

        d = self._start - pos
        txt, col = ((f"▲ +{d}", GREEN) if d > 0 else
                    (f"▼ {d}", RED) if d < 0 else ("= 0", MUTED))
        out = [("Position", f"P{pos}"), ("Since start", txt, col)]

        if pos != last:                              # только что обогнали или обошли
            moved = last - pos
            out.append(("Just now", f"{'gained' if moved > 0 else 'lost'} {abs(moved)}",
                        GREEN if moved > 0 else RED))
        if self._opt("show_range", True):
            out.append(("Best / worst", f"P{self._best} / P{self._worst}"))
        return out


class PositionWidget(StatWidget):
    """Позиция и разрывы.

    Само число разрыва мало значит: важно, РАСТЁТ он или тает. Полторы
    секунды до впереди идущего — это атака, если вчера было три, и оборона,
    если вчера была одна. Считаем изменение за несколько секунд по своей
    истории замеров и рисуем стрелку.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "position", "Position & gaps", (220, 170), "solo", ("race",)
    BLURB = "Position in class, gaps to the car ahead and behind."
    TREND_N = 180                                    # ≈ 3 секунды при 60 к/с

    def extra_settings(self, lay):
        self.opt_check(lay, "Closing arrows", "show_trend", True)
        self.opt_check(lay, "Overall position", "show_overall", True)

    def _arrow(self, key, gap):
        """▲ догоняешь / ▼ отстаёшь — по изменению разрыва."""
        hist = getattr(self, "_h", {})
        if not isinstance(gap, (int, float)):
            return "", MUTED
        seq = (hist.get(key, []) + [abs(gap)])[-self.TREND_N:]
        hist[key] = seq
        self._h = hist
        if len(seq) < self.TREND_N // 2:
            return "", MUTED
        d = seq[-1] - seq[0]
        if d < -0.05:
            return " ▲", GREEN                  # разрыв сокращается
        if d > 0.05:
            return " ▼", RED
        return "", MUTED

    def rows(self):
        r = self.store.get("race")
        cp, pos = r.get("class_position"), r.get("position")
        ga, gb = r.get("gap_ahead"), r.get("gap_behind")
        trend = self._opt("show_trend", True)

        out = [("In class", f"P{cp}" if cp is not None else "—", PURPLE)]
        if self._opt("show_overall", True):
            out.append(("Overall", f"P{pos}" if pos is not None else "—"))

        for label, gap, key in (("Ahead", ga, "a"), ("Behind", gb, "b")):
            if not isinstance(gap, (int, float)):
                out.append((label, "—"))
                continue
            arrow, col = self._arrow(key, gap) if trend else ("", WHITE)
            # ближе секунды — зона атаки и зона риска, красим отдельно
            base = AMBER if abs(gap) < 1.0 else WHITE
            out.append((label, f"{abs(gap):.1f} s{arrow}", col if arrow else base))
        return out


class TimingWidget(StatWidget):
    """Времена круга. Голые три времени мало говорят: важна РАЗНИЦА между
    последним и лучшим — по ней видно, едешь ты в темпе или сыплешься."""

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "timing", "Laps", (210, 150), "solo", ("race",)
    BLURB = "Last, best and predicted lap — and the gaps between them."

    def extra_settings(self, lay):
        self.opt_check(lay, "Delta to best", "show_delta", True)
        self.opt_check(lay, "Predicted lap", "show_pred", True)
        self.opt_check(lay, "Lap number", "show_lap", False)

    def rows(self):
        r = self.store.get("race")
        last, best = r.get("last_lap_time"), r.get("best_lap_time")
        out = []
        if self._opt("show_lap", False):
            lap = r.get("lap")
            out.append(("Lap", str(lap) if lap is not None else "—"))

        # последний круг красим сам по себе: личный рекорд — фиолетовым,
        # как в таймингах iRacing, чтобы не искать глазами в какой строке
        last_col = WHITE
        if isinstance(last, (int, float)) and isinstance(best, (int, float)):
            last_col = PURPLE if last <= best else WHITE
        out.append(("Last", lap_time(last), last_col))
        out.append(("Best", lap_time(best), PURPLE))

        if self._opt("show_delta", True):
            if isinstance(last, (int, float)) and isinstance(best, (int, float)):
                d = last - best
                out.append(("Δ to best", f"{d:+.3f}", GREEN if d <= 0 else RED))
            else:
                out.append(("Δ to best", "—"))
        if self._opt("show_pred", True):
            out.append(("Predicted", lap_time(r.get("predicted"))))
        return out


class CycleBind:
    """Примесь: листать опцию виджета кнопкой/клавишей/хатом (вперёд/назад), как black box.
    Класс задаёт CYCLE_OPT (какую опцию листать) и CYCLE_VALUES (список её значений).
    Работает с ЛЮБЫМ рулём/геймпадом/клавиатурой (см. overlay/button_input.py).
    Использование: self._cycle_init() в __init__ + self.cycle_assign_ui(lay) в настройках."""
    CYCLE_OPT = None
    CYCLE_VALUES = ()
    CYCLE_DEFAULT = None

    def _cycle_init(self):
        try:
            from overlay import button_input
            h = button_input.hub()
            h.pressed.connect(self._cycle_action)
            for opt_key, act in (("cycle_btn", "next"), ("cycle_btn_prev", "prev")):
                bd = self._opt(opt_key, None)
                if bd:
                    h.bind(f"{self.KEY}.{act}", bd)
        except Exception:
            pass

    def _cycle_action(self, action_id):
        if action_id == f"{self.KEY}.next":
            self.cycle_value(+1)
        elif action_id == f"{self.KEY}.prev":
            self.cycle_value(-1)

    def cycle_value(self, step=1):
        vals = list(self.CYCLE_VALUES)
        if not vals or not self.CYCLE_OPT:
            return
        cur = self._opt(self.CYCLE_OPT, self.CYCLE_DEFAULT if self.CYCLE_DEFAULT is not None else vals[0])
        base = vals.index(cur) if cur in vals else 0
        self.config.set_widget_opt(self.KEY, self.CYCLE_OPT, vals[(base + step) % len(vals)])
        self.update()

    def cycle_assign_ui(self, lay):
        from PySide6.QtWidgets import QLabel, QHBoxLayout, QPushButton, QWidget
        try:
            from overlay import button_input
            h = button_input.hub()
        except Exception:
            lay.addWidget(QLabel("Input unavailable"))
            return
        lay.addWidget(QLabel("Cycle — button / key / hat:"))

        def add_row(title, opt_key, action):
            row = QWidget()
            hb = QHBoxLayout(row)
            hb.setContentsMargins(0, 0, 0, 0)
            cap = QLabel(title)
            cap.setFixedWidth(48)
            lbl = QLabel()
            assign = QPushButton("Assign")
            clear = QPushButton("✖")
            clear.setFixedWidth(30)
            aid = f"{self.KEY}.{action}"

            def show():
                bd = self._opt(opt_key, None)
                lbl.setText(bd.get("name", "set") if bd else "not set")

            def on_cap(binding, name):
                self.config.set_widget_opt(self.KEY, opt_key, binding)
                h.bind(aid, binding)
                assign.setText("Assign")
                assign.setEnabled(True)
                show()
                try:
                    h.captured.disconnect(on_cap)
                except Exception:
                    pass

            def arm():
                try:
                    h.captured.disconnect(on_cap)
                except Exception:
                    pass
                h.captured.connect(on_cap)
                h.capture()
                assign.setText("Press any button / key…")
                assign.setEnabled(False)

            def clr():
                self.config.set_widget_opt(self.KEY, opt_key, None)
                h.unbind(aid)
                show()

            assign.clicked.connect(arm)
            clear.clicked.connect(clr)
            show()
            hb.addWidget(cap)
            hb.addWidget(lbl, 1)
            hb.addWidget(assign)
            hb.addWidget(clear)
            lay.addWidget(row)

        add_row("▶ Next", "cycle_btn", "next")
        add_row("◀ Prev", "cycle_btn_prev", "prev")


class OptimalWidget(CycleBind, StatWidget):
    # ⚙ → «Показывать»: как в ирке — последний/лучший/оптимальный/прогноз/дельта
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "optimal", "Optimal lap", (210, 90), "solo", ("race",)
    BLURB = "The lap you could have driven from your best sectors."
    MODES = [("optimal", "Optimal"), ("last", "Last"), ("best", "Best"),
             ("predicted", "Predicted"), ("delta", "Δ to best")]
    CYCLE_OPT, CYCLE_DEFAULT = "mode", "optimal"
    CYCLE_VALUES = [m for m, _ in MODES]

    def __init__(self, store, config, parent=None):
        super().__init__(store, config, parent)
        self._cycle_init()          # кнопка/клавиша/хат листает режим (вперёд/назад)

    def rows(self):
        r = self.store.get("race")
        mode = self._opt("mode", "optimal")
        if mode == "last":
            return [("Last", lap_time(r.get("last_lap_time")), WHITE)]
        if mode == "best":
            return [("Best", lap_time(r.get("best_lap_time")), PURPLE)]
        if mode == "predicted":
            return [("Predicted", lap_time(r.get("predicted")), WHITE)]
        if mode == "delta":
            d = r.get("delta_best")
            txt = f"{d:+.2f}s" if isinstance(d, (int, float)) else "—"
            return [("Δ to best", txt, GREEN if isinstance(d, (int, float)) and d <= 0 else RED)]
        # optimal — сумма лучших секторов
        log = r.get("lap_log") or []
        nsec = max((len(x.get("sectors") or []) for x in log), default=0)
        best = []
        for i in range(nsec):
            v = [x["sectors"][i] for x in log if x.get("sectors") and len(x["sectors"]) > i and x["sectors"][i]]
            best.append(min(v) if v else None)
        if not best or any(b is None for b in best):
            return [("Optimal", "—")]
        opt = sum(best)
        times = [x["time"] for x in log if x.get("time", 0) > 0]
        actual = min(times) if times else None
        out = [("Optimal", lap_time(opt), PURPLE), ("Best", lap_time(actual))]
        if actual:
            gain = actual - opt
            out.append(("Potential", f"−{gain:.2f}s" if gain > 0.01 else "at the limit", GREEN))
        return out

    def extra_settings(self, lay):
        self.opt_choice(lay, "Show", "mode", self.MODES)
        self.cycle_assign_ui(lay)

class SummaryWidget(StatWidget):
    """Итог сессии: позиция, темп, стабильность, инциденты.

    Разброс времён — честная мера стабильности, но по нему одному нельзя
    судить: один вылет растягивает разброс, хотя остальные круги ровные.
    Поэтому рядом показываем СРЕДНИЙ круг по чистым и сколько их было.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "summary", "Session summary", (220, 190), "solo", ("race", "damage")
    BLURB = "The session in one card: position, pace, consistency, incidents."

    def extra_settings(self, lay):
        self.opt_check(lay, "Typical lap", "show_avg", True)
        self.opt_check(lay, "Lap counter", "show_count", True)

    def rows(self):
        r = self.store.get("race")
        log = r.get("lap_log") or []
        t = sorted(x["time"] for x in log if x.get("time", 0) > 0)

        best = t[0] if t else r.get("best_lap_time")
        out = [("Position", f"P{r.get('class_position') or '—'}"),
               ("Best", lap_time(best), PURPLE)]

        if t and self._opt("show_avg", True):
            # медиана, а не среднее: один вылет не должен утаскивать «темп»
            med = t[len(t) // 2]
            out.append(("Typical lap", lap_time(med)))
            if isinstance(best, (int, float)):
                out.append(("Off pace", f"+{med - best:.2f}s",
                            GREEN if med - best < 0.5 else AMBER))
        if t:
            spread = t[-1] - t[0]
            out.append(("Spread", f"±{spread / 2:.2f}s",
                        GREEN if spread < 1.0 else AMBER))
        else:
            out.append(("Spread", "—"))
        if self._opt("show_count", True):
            out.append(("Clean laps", str(len(t))))

        inc = self.store.get("damage").get("incidents")
        inc = inc if isinstance(inc, (int, float)) else 0
        out.append(("Incidents", f"{inc}x", RED if inc >= 4 else WHITE))
        return out


class SessionWidget(StatWidget):
    """Что за сессия и сколько её осталось.

    Время суток НА ТРАССЕ добавлено не для красоты: в эндурансе по нему
    планируют смену на фары и понимают, когда упадёт температура покрытия.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "session", "Session", (220, 150), "solo", ("session",)
    BLURB = "What session this is and how much of it is left."

    def extra_settings(self, lay):
        self.opt_check(lay, "Track time of day", "show_tod", True)
        self.opt_check(lay, "Strength of field", "show_sof", True)
        self.opt_check(lay, "Laps completed", "show_done", False)

    def rows(self):
        s = self.store.get("session")
        lr, lt = s.get("laps_remain"), s.get("laps_total")
        out = [("Event", ev(s.get("session_type")))]

        tr = s.get("time_remain")
        # красным последние пять минут: время дозаправиться и не попасть
        # под клетчатый флаг посреди круга
        col = RED if isinstance(tr, (int, float)) and 0 < tr <= 300 else WHITE
        out.append(("Time left", fmt_time(tr), col))

        if lr is not None:
            out.append(("Laps left", f"{lr}{'/' + str(lt) if lt else ''}"))
        else:
            out.append(("Laps left", "—"))
        if self._opt("show_done", False) and lr is not None and lt:
            out.append(("Done", f"{max(0, lt - lr)} of {lt}"))
        if self._opt("show_tod", True):
            out.append(("Track time", s.get("time_of_day") or "—"))
        if self._opt("show_sof", True):
            sof = s.get("sof")
            out.append(("SoF", f"{round(sof / 1000, 1)}k" if isinstance(sof, (int, float)) else "—"))
        return out


class RecordDeltaWidget(StatWidget):
    """Личный рекорд трассы и насколько ты от него сегодня.

    Рекорд — это то, что ты УЖЕ проезжал, значит цель достижима. Добавлен
    последний круг: сравнение рекорда с лучшим за сессию говорит о форме,
    а с последним кругом — о том, что происходит прямо сейчас.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "recorddelta", "Delta to record", (220, 150), "solo", ("session", "race")
    BLURB = "Your track record and how far off it you are today."

    def extra_settings(self, lay):
        self.opt_check(lay, "Last lap", "show_last", True)

    def rows(self):
        rec = self.store.get("session").get("record")
        race = self.store.get("race")
        if not isinstance(rec, (int, float)):
            return [("Record", "none yet"), ("", "drive a clean lap", MUTED)]

        out = [("Your record", lap_time(rec), PURPLE)]
        best = race.get("best_lap_time")
        out.append(("Session best", lap_time(best)))
        if isinstance(best, (int, float)):
            d = best - rec
            out.append(("Δ to record", f"{d:+.2f}s", GREEN if d <= 0 else RED))
            if d <= 0:
                out.append(("", "new record!", GREEN))

        if self._opt("show_last", True):
            last = race.get("last_lap_time")
            if isinstance(last, (int, float)):
                dl = last - rec
                out.append(("Last lap", f"{lap_time(last)}  {dl:+.2f}",
                            GREEN if dl <= 0 else WHITE))
        return out


class ErsWidget(StatWidget):
    """Заряд и расход гибрида.

    Текущий процент отвечает «сколько есть», но не «трачу ли я больше
    обычного». Поэтому запоминаем расход на ПРОШЛОМ круге и показываем
    рядом — так видно, экономишь ты батарею или сливаешь её раньше срока.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "ers", "ERS / hybrid", (210, 150), "solo", ("race",)
    BLURB = "Hybrid charge and how fast you are spending it."

    def extra_settings(self, lay):
        self.opt_check(lay, "Deploy on the last lap", "show_last", True)
        self.opt_slider(lay, "Low threshold (%)", "low", 5, 50, 20)

    def rows(self):
        r = self.store.get("race")
        e, d = r.get("energy_pct"), r.get("deploy_pct")
        if not isinstance(e, (int, float)):
            return [("Hybrid", "no data on this car")]

        lap = r.get("lap")
        if lap is not None and lap != getattr(self, "_lap", None):
            self._lap = lap
            self._prev_deploy = getattr(self, "_cur_deploy", None)
        if isinstance(d, (int, float)):
            self._cur_deploy = d

        b = round(e * 100)
        low = self._opt("low", 20)
        col = GREEN if b >= 50 else (AMBER if b >= low else RED)
        out = [("Battery", f"{b}%", col)]
        out.append(("Deploy/lap", f"{round(d * 100)}%" if isinstance(d, (int, float)) else "—"))

        if self._opt("show_last", True):
            prev = getattr(self, "_prev_deploy", None)
            if isinstance(prev, (int, float)) and isinstance(d, (int, float)):
                diff = (d - prev) * 100
                out.append(("Last lap", f"{round(prev * 100)}%", MUTED))
                out.append(("Vs last", f"{diff:+.0f}%", AMBER if diff > 3 else GREEN))
            else:
                out.append(("Last lap", "—", MUTED))
        return out


class WeatherWidget(StatWidget):
    """Погода и температуры.

    Раньше виджет показывал ветер, влажность и покрытие — и молчал про
    ТЕМПЕРАТУРЫ, хотя это два самых нужных числа: от температуры трассы
    зависит и сцепление, и то, как быстро уйдёт резина.

    Тренд считается по своей истории: держим замеры и сравниваем с тем,
    что было несколько минут назад. Остывающая трасса означает, что круги
    начнут улучшаться, нагревающаяся — что резина поедет раньше срока.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "weather", "Weather", (220, 170), "solo", ("race", "live")
    BLURB = "Air and track temperature, wind, humidity, time of day."
    TREND_N = 90                                    # замеров в памяти (≈ полторы минуты)

    def extra_settings(self, lay):
        self.opt_choice(lay, "Degrees", "units",
                        [("c", "°C"), ("f", "°F")])
        self.opt_check(lay, "Temperature trend", "show_trend", True)
        self.opt_check(lay, "Humidity and wind", "show_wind", True)

    def _deg(self, c):
        if not isinstance(c, (int, float)):
            return "—"
        if self._opt("units", "c") == "f":
            return f"{round(c * 9 / 5 + 32)}°F"
        return f"{round(c)}°C"

    def rows(self):
        r, l = self.store.get("race"), self.store.get("live")
        tt, at = l.get("track_temp"), l.get("air_temp")

        hist = getattr(self, "_hist", [])
        if isinstance(tt, (int, float)):
            hist = (hist + [tt])[-self.TREND_N:]
            self._hist = hist

        out = [("Track", self._deg(tt)), ("Air", self._deg(at))]

        if self._opt("show_trend", True):
            if len(hist) >= self.TREND_N // 2:
                d = hist[-1] - hist[0]
                if d > 0.3:
                    out.append(("Trend", f"▲ +{d:.1f}°", AMBER))
                elif d < -0.3:
                    out.append(("Trend", f"▼ {d:.1f}°", BLUE))
                else:
                    out.append(("Trend", "steady", MUTED))
            else:
                out.append(("Trend", "measuring…", MUTED))

        wet = r.get("track_wetness")
        out.append(("Surface", wetness(wet), GREEN if (wet or 0) <= 1 else AMBER))

        if self._opt("show_wind", True):
            wv, h = r.get("wind_vel"), r.get("humidity")
            out.append(("Wind", f"{wv:.1f} m/s" if isinstance(wv, (int, float)) else "—"))
            out.append(("Humidity", f"{round(h * 100)}%" if isinstance(h, (int, float)) else "—"))
        return out


class PitHelperWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "pithelper", "Pit helper", (210, 110), "solo", ("race", "live", "strategy")
    BLURB = "Pit lane: limiter, speed and where the box is."

    LIMIT_KMH = 60.0                                   # пит-лимит iRacing по умолчанию

    def rows(self):
        r = self.store.get("race")
        if not r.get("on_pit"):
            return [("Pit", "not on pit lane")]
        spd = self.store.get("live").get("speed")
        kmh = spd * 3.6 if isinstance(spd, (int, float)) else None
        add = self.store.get("strategy").get("fuel_to_add")

        # Лимитер уже декодируется из EngineWarnings — мы просто не смотрели.
        # Забытый лимитер стоит дороже превышения: проезд мимо бокса и штраф.
        limiter = any(w.get("key") == "pit_limiter" for w in (r.get("warnings") or []))
        over = kmh is not None and kmh > self.LIMIT_KMH + 2

        out = [("Limiter", "ON" if limiter else "OFF", GREEN if limiter else RED)]
        if kmh is not None:
            excess = kmh - self.LIMIT_KMH
            out.append(("Speed", f"{round(kmh)} km/h", RED if over else GREEN))
            if over:
                out.append(("Over limit", f"+{excess:.1f} km/h", RED))
        else:
            out.append(("Speed", "—"))
        if not limiter and not over:
            out.append(("!", "turn the limiter on", AMBER))
        out.append(("Add", f"+{add} L" if isinstance(add, (int, float)) and add > 0 else "not needed"))
        return out


class MetricsWidget(StatWidget):
    """Как ты работаешь педалями — по разбору стинта.

    Проценты сами по себе не подсказывают, много это или мало. Поэтому
    рядом ставим оценку словом: у трейл-брейкинга и плавности газа есть
    диапазоны, за пределами которых машину либо не догружают, либо срывают.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "metrics", "Sensors & balance", (250, 160), "solo", ("result",)
    BLURB = "How you work the pedals, measured over the stint."

    def extra_settings(self, lay):
        self.opt_check(lay, "Verdict in words", "show_verdict", True)

    @staticmethod
    def _judge(v, lo, hi):
        """Ниже нормы / в норме / выше нормы."""
        if v is None:
            return "—", MUTED
        if v < lo:
            return "low", AMBER
        if v > hi:
            return "high", AMBER
        return "good", GREEN

    def rows(self):
        s = (self.store.get("result") or {}).get("symptoms") or {}
        verdict = self._opt("show_verdict", True)
        out = []

        i = s.get("inputs") or {}
        if i:
            tb = i.get("trail_brake_pct")
            if isinstance(tb, (int, float)):
                lab, col = self._judge(tb, 15, 45)
                out.append(("Trail braking", f"{tb:.0f}%" + (f"  {lab}" if verdict else ""), col))
            sm = i.get("throttle_smoothness")
            if isinstance(sm, (int, float)):
                v = sm * 100
                lab, col = self._judge(v, 70, 101)
                out.append(("Throttle", f"{v:.0f}%" + (f"  {lab}" if verdict else ""), col))

        tire = s.get("tire") or {}
        b = tire.get("front_rear_balance")
        if isinstance(b, (int, float)):
            out.append(("Tire balance",
                        f"{'front' if b > 0 else 'rear'} +{abs(b):.1f}°",
                        AMBER if abs(b) >= 3 else GREEN))
        return out or [("Sensors", "after stint"), ("", "drive a few laps", MUTED)]


class TireTempsWidget(OverlayWidget):
    """Температуры покрышек по трём зонам каждого колеса.

    Квадратики с цифрами были, а вывода не было. Добавлены две вещи, ради
    которых на этот виджет вообще смотрят:

    ПЕРЕКОС ВНУТРИ КОЛЕСА — разница между краями. Горячий внутренний край
    означает избыток развала, горячий внешний — недостаток или мало
    давления. Само по себе колесо может быть в норме по средней температуре
    и при этом стоять неправильно.

    РАЗНИЦА ОСЕЙ — перегретый перед против перегретого зада, то есть снос
    против заноса. То же, что показывает виджет баланса, но вживую, а не
    после стинта.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "tiretemps", "Tire temps", (260, 200), "solo", ("live",)
    BLURB = "Tyre temperature across three zones of every wheel."

    def extra_settings(self, lay):
        self.opt_choice(lay, "Degrees", "units",
                        [("c", "°C"), ("f", "°F")])
        self.opt_check(lay, "Skew inside the tyre", "show_skew", True)
        self.opt_check(lay, "Axle difference", "show_axle", True)
        self.opt_slider(lay, "Noticeable skew (°)", "skew_thr", 3, 30, 8)

    def _num(self, v):
        if not isinstance(v, (int, float)):
            return "—"
        if self._opt("units", "c") == "f":
            return round(v * 9 / 5 + 32)
        return round(v)

    @staticmethod
    def _avg(corner):
        vals = [corner.get(k) for k in ("tl", "tm", "tr")]
        vals = [v for v in vals if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else None

    def draw(self, p):
        self.title(p, "TIRE TEMPS")
        t = self.store.get("live").get("tires") or {}
        skew_on = self._opt("show_skew", True)
        thr = self._opt("skew_thr", 8)

        cells = [("LF", 12, 34), ("RF", self.width() / 2 + 4, 34),
                 ("LR", 12, 100), ("RR", self.width() / 2 + 4, 100)]
        pw = (self.width() / 2 - 20) / 3

        for c, x, y in cells:
            corner = t.get(c) or {}
            label = c
            if skew_on:
                l, r = corner.get("tl"), corner.get("tr")
                if isinstance(l, (int, float)) and isinstance(r, (int, float)):
                    d = l - r
                    if abs(d) >= thr:
                        # какой край горит: внутренний у левых колёс — это tl,
                        # у правых — tr, поэтому пишем стороной, а не «inner»
                        label = f"{c}  {'◀' if d > 0 else '▶'}{abs(d):.0f}°"
            self.text(p, x, y, label, MUTED, 9)
            for i, k in enumerate(("tl", "tm", "tr")):
                v = corner.get(k)
                p.setBrush(QColor(tcol(v)))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(x + i * pw, y + 6, pw - 3, 20), 4, 4)
                self.text(p, x + i * pw + 4, y + 20, self._num(v), "#0d0f12", 9, True)

        if not self._opt("show_axle", True):
            return
        fr = [self._avg(t.get(c) or {}) for c in ("LF", "RF")]
        re = [self._avg(t.get(c) or {}) for c in ("LR", "RR")]
        fr = [v for v in fr if v is not None]
        re = [v for v in re if v is not None]
        y = self.height() - 12
        if not fr or not re:
            self.text(p, 12, y, "axles: waiting for data", MUTED, 10)
            return
        d = sum(fr) / len(fr) - sum(re) / len(re)
        if abs(d) < thr / 2:
            self.text(p, 12, y, "axles balanced", GREEN, 10)
        else:
            self.text(p, 12, y,
                      f"front hotter +{d:.0f}°" if d > 0 else f"rear hotter +{abs(d):.0f}°",
                      AMBER, 10)


class WearWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "wear", "Tire wear", (220, 150), "solo", ("wear",)
    BLURB = "Remaining tread, per wheel and per zone."

    def draw(self, p):
        self.title(p, "TIRE WEAR")
        w = self.store.get("wear") or {}
        cells = [("LF", "LF", 12, 40), ("RF", "RF", self.width() / 2 + 4, 40),
                 ("LR", "LR", 12, 98), ("RR", "RR", self.width() / 2 + 4, 98)]
        half = self.width() / 2 - 20
        zw = half / 3
        for c, name, x, y in cells:
            corner = w.get(c)
            # старый формат — одно число на угол; новый — зоны l/m/r + min
            if isinstance(corner, (int, float)):
                corner = {"l": corner, "m": corner, "r": corner, "min": corner}
            corner = corner or {}
            worst = corner.get("min")
            col = "#333" if worst is None else (
                GREEN if worst > 0.5 else (AMBER if worst > 0.3 else RED))
            self.text(p, x, y, name, MUTED, 9)
            self.text(p, x, y + 18, "—" if worst is None else f"{round(worst * 100)}%",
                      col, 15, True)
            # три зоны отдельными столбиками: видно, каким краем ест резину
            for i, k in enumerate(("l", "m", "r")):
                v = corner.get(k)
                zc = "#333" if v is None else (
                    GREEN if v > 0.5 else (AMBER if v > 0.3 else RED))
                self.bar(p, x + i * zw, y + 24, zw - 3, 7, (v or 0), QColor(zc))
                self.text(p, x + i * zw, y + 44, "—" if v is None else round(v * 100),
                          MUTED, 8)


class RelativeWidget(CycleBind, OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "relative", "Relative", (360, 220), "solo", ("relative",)
    BLURB = "The cars physically nearest you on track, not on the timesheet."
    ROW = 26
    CYCLE_OPT, CYCLE_DEFAULT = "name_style", "full"
    CYCLE_VALUES = ["full", "f_last", "last_f", "last", "initials"]

    def __init__(self, store, config, parent=None):
        super().__init__(store, config, parent)
        self._cycle_init()

    def draw(self, p):
        cars = (self.store.get("relative") or {}).get("cars") or []
        me = next((i for i, c in enumerate(cars) if c.get("is_player")), -1)
        if me < 0:
            self.text(p, 12, 28, "no data — get on track", MUTED, 11)
            return
        show_ir = self._opt("show_ir", True)
        nstyle = self._opt("name_style", "full")
        logo_mode = self._opt("manuf_logo", "off")
        show_logos = logo_mode == "always" or (logo_mode == "multi" and
                     len({c.get("manufacturer") for c in cars if c.get("manufacturer")}) > 1)
        logo_size = int(self._opt("logo_size", 24))
        w = self.width()
        for i, c in enumerate(list(reversed(cars[max(0, me - 3):me + 4]))):
            y = 4 + i * self.ROW
            player = bool(c.get("is_player"))
            if player:
                hi = QColor(46, 60, 96, 210) if self._opt("colorblind", False) else QColor(38, 96, 60, 210)
                p.setBrush(hi)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(2, y, w - 4, self.ROW - 2), 5, 5)
            base = y + self.ROW - 9
            num = str(c.get("number") or "")             # номер в боксе цвета класса
            p.setBrush(_clr(c.get("class_color")))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(8, y + 4, 28, self.ROW - 8), 3, 3)
            self.text(p, 22 - len(num) * 3.2, base, num, "#0d0f12", 10, True)
            self.text(p, 42, base, f"P{c.get('pos', '')}", MUTED, 10)
            nm = fmt_driver_name(c.get("name") or "", nstyle)
            self.text(p, 72, base, nm[:14 if show_ir else 17], WHITE, 11, player)
            if show_logos:                               # логотип — справа от имени, слева от iR
                _draw_logo(p, _logo(c.get("manufacturer")), w - 122 - int(logo_size * 2.4),
                           y + self.ROW / 2, logo_size)
            if show_ir:
                ir = c.get("irating")
                self.text(p, w - 118, base, f"{ir/1000:.1f}k" if ir else "—", "#9aa4b0", 9)
            gap = c.get("gap")
            if not player and isinstance(gap, (int, float)):
                self.text(p, w - 70, base, f"{gap:+.1f}", self._cb(RED if gap > 0 else GREEN), 11, True)
            if c.get("on_pit"):
                self.text(p, w - 28, base, "P", AMBER, 10, True)

    def extra_settings(self, lay):
        self.opt_check(lay, "Show iRating", "show_ir", True)
        self.opt_choice(lay, "Name", "name_style",
                        [("full", "Full"), ("f_last", "J. Last"), ("last_f", "Last J."),
                         ("last", "Last"), ("initials", "J. R.")])
        self.opt_choice(lay, "Manuf. logo", "manuf_logo",
                        [("off", "Off"), ("multi", "Multi-make"), ("always", "Always")])
        self.opt_slider(lay, "Logo size", "logo_size", 12, 40, 24)
        self.cycle_assign_ui(lay)


class MyCarWidget(OverlayWidget):
    """Моя машина: логотип марки + название модели (на чём еду)."""
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "mycar", "My car", (240, 74), "solo", ("standings",)
    BLURB = "Which car you are in: badge and model name."

    def draw(self, p):
        self.title(p, "MY CAR")
        rows = self.store.get("standings") or []
        me = next((r for r in rows if r.get("is_player")), None)
        if not me:
            self.text(p, 12, self.height() / 2 + 10, "—", MUTED, 15)
            return
        x = 12
        px = _logo(me.get("manufacturer"))
        if px is not None:
            size = int(self._opt("logo_size", 40))       # регулируемый размер (виджет высокий)
            scaled = px.scaled(int(size * 2.4), size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(12, int(self.height() / 2 - scaled.height() / 2 + 4), scaled)
            x = 12 + scaled.width() + 12
        self.text(p, x, self.height() / 2 + 12, me.get("car") or "—", WHITE, 15, True)

    def extra_settings(self, lay):
        self.opt_slider(lay, "Logo size", "logo_size", 16, 64, 40)


class Head2HeadWidget(CycleBind, OverlayWidget):
    """Голова к голове (идея RaceLab Head 2 Head): ты vs соперник — разрыв + Δ лучшего круга.
    Соперник выбирается: впереди / сзади / лидер класса."""
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "head2head", "Head 2 head", (390, 140), "solo", ("standings",)
    BLURB = "You against one rival — the gap and the best-lap difference."
    CYCLE_OPT, CYCLE_DEFAULT = "vs", "ahead"
    CYCLE_VALUES = ["ahead", "behind", "leader"]

    def __init__(self, store, config, parent=None):
        super().__init__(store, config, parent)
        self._cycle_init()

    def draw(self, p):
        self.title(p, "HEAD 2 HEAD")
        rows = self.store.get("standings") or []
        me = next((r for r in rows if r.get("is_player")), None)
        if not me:
            self.text(p, 12, self.height() / 2 + 8, "no data — get on track", MUTED, 11)
            return
        rival = self._pick_rival(rows, me)
        w, h = self.width(), self.height()
        self._line(p, 26, me, True)
        p.setPen(QPen(QColor("#2a2f38")))                # тонкий разделитель
        p.drawLine(10, int(h / 2 - 4), w - 10, int(h / 2 - 4))
        if not rival:
            self._ctext(p, w / 2, h / 2 + 24, "no rival (class leader)", MUTED, 11)
            return
        self._line(p, h - 40, rival, False)
        mg, rg = me.get("gap"), rival.get("gap")         # разрыв между нами (сек)
        if isinstance(mg, (int, float)) and isinstance(rg, (int, float)):
            d = mg - rg                                  # >0 — я позади соперника
            self._ctext(p, w / 2, h / 2 + 12, f"{d:+.1f}s", AMBER, 15)
        mb, rb = me.get("best"), rival.get("best")
        if isinstance(mb, (int, float)) and isinstance(rb, (int, float)) and mb > 0 and rb > 0:
            db = mb - rb                                 # <0 — мой лучший круг быстрее
            self._ctext(p, w / 2, h / 2 + 30, f"Δbest {db:+.2f}", self._cb(GREEN if db <= 0 else RED), 11)

    def _line(self, p, y, r, mine):
        w = self.width()
        logo_size = int(self._opt("logo_size", 20))
        self.text(p, 8, y + 16, f"P{r.get('pos', '')}", AMBER if mine else "#9aa4b0", 13, True)
        num = str(r.get("number") or "")
        p.setBrush(_clr(r.get("class_color")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(40, y + 2, 26, 18), 3, 3)
        self.text(p, 53 - len(num) * 3.2, y + 16, num, "#0d0f12", 10, True)
        x = 72
        if self._opt("manuf_logo", True):
            _draw_logo(p, _logo(r.get("manufacturer")), x, y + 11, logo_size)
            x += int(logo_size * 2.4) + 6
        nm = fmt_driver_name(r.get("name") or "", self._opt("name_style", "last"))
        self.text(p, x, y + 16, nm[:14], WHITE if mine else "#cdd3dc", 12, mine)
        self.text_right(p, w - 66, y + 16, lap_time(r.get("last")), "#cdd3dc", 11)
        self.text_right(p, w - 8, y + 16, lap_time(r.get("best")), PURPLE, 11)

    def _ctext(self, p, cx, y, s, color, size, bold=True):
        f = QFont("Segoe UI")
        f.setPixelSize(int(size))
        f.setBold(bold)
        p.setFont(f)
        p.setPen(QPen(QColor(self._cb(color) if color in (GREEN, RED) else color)))
        wd = p.fontMetrics().horizontalAdvance(str(s))
        p.drawText(int(cx - wd / 2), int(y), str(s))

    def _pick_rival(self, rows, me):
        mode = self._opt("vs", "ahead")
        cls = me.get("car_class")
        grp = [r for r in rows if r.get("car_class") == cls] or list(rows)
        grp.sort(key=lambda r: r.get("pos") or 9999)
        idx = next((i for i, r in enumerate(grp) if r.get("is_player")), None)
        if idx is None:
            return None
        if mode == "leader":
            return grp[0] if grp[0] is not me else (grp[1] if len(grp) > 1 else None)
        if mode == "behind":
            return grp[idx + 1] if idx + 1 < len(grp) else None
        return grp[idx - 1] if idx - 1 >= 0 else None    # ahead

    def extra_settings(self, lay):
        self.opt_choice(lay, "Compare vs", "vs",
                        [("ahead", "Ahead"), ("behind", "Behind"), ("leader", "Leader")])
        self.opt_choice(lay, "Name", "name_style",
                        [("full", "Full"), ("f_last", "J. Last"), ("last", "Last"), ("initials", "J. R.")])
        self.opt_check(lay, "Manuf. logo", "manuf_logo", True)
        self.opt_slider(lay, "Logo size", "logo_size", 12, 40, 20)
        self.cycle_assign_ui(lay)


class LaptimeGraphWidget(OverlayWidget):
    """График времён кругов (идея RaceLab Laptime graph): столбики по кругам, цвет по скорости
    (лучший — фиолетовый, худший — красный). Из race.lap_log (последние круги)."""
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "laptimegraph", "Laptime graph", (300, 160), "solo", ("race",)
    BLURB = "Every lap as a bar, coloured by pace."

    def draw(self, p):
        self.title(p, "LAPTIME GRAPH")
        log = (self.store.get("race") or {}).get("lap_log") or []
        laps = [e for e in log if isinstance(e.get("time"), (int, float)) and e["time"] > 0]
        laps = laps[-int(self._opt("laps", 15)):]
        if not laps:
            self.text(p, 12, self.height() / 2, "drive laps — graph builds", MUTED, 10)
            return
        times = [e["time"] for e in laps]
        best, worst = min(times), max(times)
        rng = (worst - best) or 1.0
        w, h = self.width(), self.height()
        x0, y0 = 12, 32
        pw, ph = w - 24, h - y0 - 22                      # область графика
        base_y = y0 + ph
        n = len(laps)
        bw = pw / n
        for i, e in enumerate(laps):
            t = e["time"]
            frac = (t - best) / rng                       # 0 = лучший, 1 = худший
            bh = 4 + frac * (ph - 4)                       # худший круг — высокий столбик (медленно)
            col = PURPLE if t == best else (GREEN if frac < 0.34 else (AMBER if frac < 0.67 else RED))
            p.setBrush(QColor(self._cb(col)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x0 + i * bw + 1, base_y - bh, max(2.0, bw - 2), bh), 2, 2)
        self.text(p, x0, h - 6, f"best {lap_time(best)}", self._cb(PURPLE), 9)
        self.text_right(p, w - 12, h - 6, f"last {lap_time(times[-1])}", "#cdd3dc", 9)
        self.text_right(p, w - 12, y0 - 4, f"{n} laps", MUTED, 8)

    def extra_settings(self, lay):
        self.opt_slider(lay, "Laps shown", "laps", 5, 40, 15)


class DeltaTraceWidget(OverlayWidget):
    """Скользящий график дельты к лучшему кругу (идея RaceLab Delta trace): линия ползёт вправо,
    зелёный (ниже линии) — отыгрываешь, красный (выше) — теряешь. История копится по кадрам."""
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "deltatrace", "Delta trace", (300, 120), "solo", ("race",)
    BLURB = "A rolling trace of your delta to the best lap."

    def draw(self, p):
        self.title(p, "DELTA TRACE")
        race = self.store.get("race") or {}
        d = fastval("delta_best", race.get("delta_best"))
        buf = getattr(self, "_buf", None)
        if buf is None:
            buf = self._buf = []
        buf.append(d if isinstance(d, (int, float)) else None)
        w, h = self.width(), self.height()
        plot_w = max(20, w - 16)
        if len(buf) > plot_w + 4:                         # держим ровно на ширину
            del buf[:len(buf) - (plot_w + 4)]
        scale = max(0.1, self._opt("range", 15) / 10.0)   # ± сек полная шкала (слайдер 0.1с)
        mid = 30 + (h - 46) / 2.0
        half = (h - 46) / 2.0

        def sy(v):
            return mid + max(-1.0, min(1.0, v / scale)) * half   # + (позади) вниз, − (впереди) вверх

        samples = buf[-plot_w:]
        # заливка «колонками» (зелёная ниже линии / красная выше)
        for i, v in enumerate(samples):
            if not isinstance(v, (int, float)):
                continue
            c = QColor(self._cb(GREEN if v <= 0 else RED))
            c.setAlpha(70)
            p.setPen(QPen(c, 1))
            p.drawLine(int(8 + i), int(mid), int(8 + i), int(sy(v)))
        # нулевая линия
        p.setPen(QPen(QColor("#3a4150"), 1))
        p.drawLine(8, int(mid), w - 8, int(mid))
        # сама линия поверх
        p.setPen(QPen(QColor("#e8eaed"), 1.6))
        prev = None
        for i, v in enumerate(samples):
            if not isinstance(v, (int, float)):
                prev = None
                continue
            pt = (8 + i, sy(v))
            if prev is not None:
                p.drawLine(int(prev[0]), int(prev[1]), int(pt[0]), int(pt[1]))
            prev = pt
        cur = next((v for v in reversed(samples) if isinstance(v, (int, float))), None)
        if isinstance(cur, (int, float)):
            self.text_right(p, w - 10, 20, f"{cur:+.2f}", self._cb(GREEN if cur <= 0 else RED), 13, True)

    def extra_settings(self, lay):
        self.opt_slider(lay, "Range (0.1s)", "range", 5, 40, 15)


class LaptimeSpreadWidget(OverlayWidget):
    """Разброс времён кругов (идея RaceLab Laptime spread): распределение по оси времени —
    насколько стабилен. Штрихи = круги, зелёная полоса = медиана±σ (уже = стабильнее)."""
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "laptimespread", "Laptime spread", (300, 132), "solo", ("race",)
    BLURB = "Where your laps cluster, and which ones are outliers."

    def draw(self, p):
        self.title(p, "LAPTIME SPREAD")
        log = (self.store.get("race") or {}).get("lap_log") or []
        times = [e["time"] for e in log if isinstance(e.get("time"), (int, float)) and e["time"] > 0]
        times = times[-int(self._opt("laps", 30)):]
        if not times:
            self.text(p, 12, self.height() / 2, "drive laps — spread builds", MUTED, 10)
            return
        n = len(times)
        best, worst = min(times), max(times)
        mean = sum(times) / n
        std = (sum((t - mean) ** 2 for t in times) / n) ** 0.5
        srt = sorted(times)
        median = srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2.0
        w, h = self.width(), self.height()
        x0, pw = 14, w - 28
        axis_y = int(h * 0.60)
        rng = (worst - best) or 1.0

        def X(t):
            return x0 + (t - best) / rng * pw

        if std > 0 and worst > best:                      # зона стабильности: медиана ± σ
            bx1, bx2 = X(max(best, median - std)), X(min(worst, median + std))
            c = QColor(self._cb(GREEN))
            c.setAlpha(45)
            p.setBrush(c)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(bx1, axis_y - 17, max(2.0, bx2 - bx1), 34), 4, 4)
        p.setPen(QPen(QColor("#3a4150"), 1))              # ось времени
        p.drawLine(x0, axis_y, x0 + pw, axis_y)
        for t in times:                                   # круги — штрихи, цвет по скорости
            frac = (t - best) / rng
            col = PURPLE if t == best else (GREEN if frac < 0.34 else (AMBER if frac < 0.67 else RED))
            x = X(t)
            p.setPen(QPen(QColor(self._cb(col)), 2))
            p.drawLine(int(x), axis_y - 13, int(x), axis_y + 13)
        mx = X(median)                                    # медиана — белая риска
        p.setPen(QPen(QColor("#e8eaed"), 1.5))
        p.drawLine(int(mx), axis_y - 19, int(mx), axis_y + 19)
        self.text(p, x0, axis_y - 24, f"med {lap_time(median)} · {n} laps", MUTED, 9)
        self.text_right(p, w - 10, 20, f"σ {std:.2f}s", "#cdd3dc", 12, True)
        self.text(p, x0, axis_y + 34, lap_time(best), self._cb(PURPLE), 9)
        self.text_right(p, x0 + pw, axis_y + 34, lap_time(worst), self._cb(RED), 9)

class HStandingsWidget(CycleBind, OverlayWidget):
    """Горизонтальная таблица заезда (идея RaceLab H. standings): карточки пилотов в РЯД —
    позиция + номер + имя + отрыв. Окно: от P1 или вокруг меня. С логотипами марок."""
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "hstandings", "H. standings", (640, 70), "solo", ("standings",)
    BLURB = "The field as a horizontal strip of driver cards."
    CYCLE_OPT, CYCLE_DEFAULT = "anchor", "top"
    CYCLE_VALUES = ["top", "me"]

    def __init__(self, store, config, parent=None):
        super().__init__(store, config, parent)
        self._cycle_init()

    def draw(self, p):
        rows = self.store.get("standings") or []
        if not rows:
            self.text(p, 12, self.height() / 2 + 4, "no data — get on track", MUTED, 11)
            return
        shown = self._window(rows, int(self._opt("cards", 6)), self._opt("anchor", "top"))
        if not shown:
            return
        nstyle = self._opt("name_style", "last")
        show_logos = self._opt("manuf_logo", False)
        logo_size = int(self._opt("logo_size", 16))
        w, h = self.width(), self.height()
        cw = w / len(shown)
        for i, r in enumerate(shown):
            x = i * cw
            player = bool(r.get("is_player"))
            if player:
                p.setBrush(QColor(38, 96, 60, 210))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(x + 2, 4, cw - 4, h - 8), 6, 6)
            if i:                                          # разделитель между карточками
                p.setPen(QPen(QColor("#2a2f38"), 1))
                p.drawLine(int(x), 8, int(x), h - 8)
            self.text(p, x + 8, 26, f"P{r.get('pos', '')}", WHITE, 15, True)
            num = str(r.get("number") or "")               # номер в боксе цвета класса
            p.setBrush(_clr(r.get("class_color")))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x + 42, 12, 26, 17), 3, 3)
            self.text(p, x + 55 - len(num) * 3.2, 25, num, "#0d0f12", 9, True)
            if show_logos:
                _draw_logo(p, _logo(r.get("manufacturer")), x + 74, 20, logo_size)
            nm = fmt_driver_name(r.get("name") or "", nstyle)
            self.text(p, x + 8, 47, nm[:12], WHITE if player else "#cdd3dc", 11, player)
            gc = AMBER if (r.get("laps_down") or 0) >= 1 else MUTED
            self.text(p, x + 8, 63, r.get("gap_txt") or "", gc, 9)

    def _window(self, rows, n, anchor):
        srt = sorted(rows, key=lambda r: r.get("pos") or 9999)
        if anchor == "me":
            idx = next((i for i, r in enumerate(srt) if r.get("is_player")), 0)
            lo = max(0, min(idx - n // 2, len(srt) - n))
            return srt[max(0, lo):max(0, lo) + n]
        return srt[:n]                                     # от P1 (лидерборд)

    def extra_settings(self, lay):
        self.opt_number(lay, "Cards", "cards", 3, 12, 6)
        self.opt_choice(lay, "Anchor", "anchor", [("top", "From P1"), ("me", "Around me")])
        self.opt_choice(lay, "Name", "name_style",
                        [("last", "Last"), ("f_last", "J. Last"), ("initials", "J. R."), ("full", "Full")])
        self.opt_check(lay, "Manuf. logo", "manuf_logo", False)
        self.opt_slider(lay, "Logo size", "logo_size", 12, 32, 16)
        self.cycle_assign_ui(lay)


class StandingsWidget(CycleBind, OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP = "standings", "Standings", (620, 300), "solo"
    BLURB = "The full field, sorted the way race control sorts it."
    ENDPOINTS = ("standings", "session", "race", "live")
    ROW = 24
    CYCLE_OPT, CYCLE_DEFAULT = "rows_style", "me"
    CYCLE_VALUES = ["me", "solid", "stripes", "stripes_rev"]

    def __init__(self, store, config, parent=None):
        super().__init__(store, config, parent)
        self._cycle_init()

    def draw(self, p):
        rows = self.store.get("standings") or []
        if not rows:
            self.text(p, 12, 28, "no data — get on track", MUTED, 11)
            return
        show_ir = self._opt("show_ir", True)
        show_sr = self._opt("show_sr", True)
        show_best = self._opt("show_best", True)
        rstyle = self._opt("rows_style", "me")
        cmode = self._opt("class_color_mode", "num_bg")
        nstyle, ncase = self._opt("name_style", "full"), self._opt("name_case", "normal")
        rstyle_sr = self._opt("rating_style", "badge")
        show_num, show_pit = self._opt("show_num", True), self._opt("show_pit", True)
        w = self.width()
        X = {"num": 8, "pos": 44, "name": 68, "ir": w - 350, "sr": w - 298,
             "gap": w - 232, "last": w - 154, "best": w - 78, "pit": w - 26}
        strip_dy = 0
        if self._opt("show_info", False):                # инфо-полоса сверху (температуры/часы)
            self._draw_info_strip(p, w)
            strip_dy = 18
        # шапка: SoF (если включён) + подписи колонок (всегда)
        hy = strip_dy + 17
        if self._opt("show_sof", True):
            s = self.store.get("session") or {}
            sof = s.get("sof")
            sof_txt = "SoF —"
            if sof:
                sof_txt = f"SoF {sof}" if self._opt("sof_precise", True) else f"SoF {sof/1000:.1f}k"
            self.text(p, 10, hy, sof_txt, AMBER, 10, True)
            n, cls = s.get("cars_class"), s.get("car_class")
            if n:
                self.text(p, 92, hy, f"{n} cars" + (f" · {cls}" if cls else ""), MUTED, 9)
        if show_ir:
            self.text(p, X["ir"], hy, "iR", MUTED, 8)
        if show_sr:
            self.text(p, X["sr"], hy, "SR", MUTED, 8)
        self.text(p, X["gap"], hy, "GAP", MUTED, 8)
        self.text(p, X["last"], hy, "LAST", MUTED, 8)
        if show_best:
            self.text(p, X["best"], hy, "BEST", MUTED, 8)
        y0 = strip_dy + 24
        cfg_rows = int(self._opt("rows", 24))
        nrows = min(cfg_rows, max(1, (self.height() - y0 - 2) // self.ROW))
        lr = ((self.store.get("race") or {}).get("car_left_right") or 0) if self._opt("car_lr_border", False) else 0
        logo_mode = self._opt("manuf_logo", "off")       # логотипы марок (off/multi/always)
        show_logos = logo_mode == "always" or (logo_mode == "multi" and
                     len({r.get("manufacturer") for r in rows if r.get("manufacturer")}) > 1)
        logo_size = int(self._opt("logo_size", 26))      # регулируемый размер логотипа
        logo_dx = (int(logo_size * 2.4) + 6) if show_logos else 0
        show_gain = self._opt("show_ir_gain", False)     # прогноз ± iRating
        for i, r in enumerate(rows[:nrows]):
            y = y0 + i * self.ROW
            player = bool(r.get("is_player"))
            self._row_bg(p, i, y, w, player, rstyle, r, cmode)
            base = y + self.ROW - 8
            if show_num:
                self._draw_number(p, X, y, r, cmode)
            elif cmode != "row_bg":                      # без номера — тонкая полоска цвета класса
                p.setBrush(_clr(r.get("class_color")))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(X["num"], y + 3, 5, self.ROW - 6), 2, 2)
            dim = "#6b7280" if r.get("out") else None    # сошедший — приглушённо
            self.text(p, X["pos"], base, r.get("pos", ""), dim or WHITE, 11, True)
            nm = self._fmt_name(r.get("name") or "", nstyle, ncase)
            self.text(p, X["name"] + logo_dx, base, nm[:20], dim or WHITE, 11, player)
            if show_logos:                               # логотип марки слева от имени
                _draw_logo(p, _logo(r.get("manufacturer")), X["name"], y + self.ROW / 2, logo_size)
            if show_ir:
                ir = r.get("irating")
                self.text(p, X["ir"], base, f"{ir/1000:.1f}k" if ir else "—", "#9aa4b0", 10)
                if show_gain:                            # ± прогноз рейтинга (оценка)
                    g = r.get("ir_gain")
                    if isinstance(g, (int, float)):
                        self.text(p, X["ir"] + 30, base, f"{g:+d}", self._cb(GREEN if g >= 0 else RED), 8)
            if show_sr:
                self._draw_sr(p, X, y, base, r, rstyle_sr)
            gap_c = AMBER if (r.get("laps_down") or 0) >= 1 else "#cdd3dc"
            self.text(p, X["gap"], base, r.get("gap_txt") or "—", dim or self._cb(gap_c), 10)
            self.text(p, X["last"], base, lap_time(r.get("last")), dim or "#cdd3dc", 10)
            if show_best:
                self.text(p, X["best"], base, lap_time(r.get("best")), dim or self._cb(PURPLE), 10)
            if show_pit and r.get("on_pit"):
                self.text(p, X["pit"], base, "P", AMBER, 10, True)
            if player and lr:                            # подсветка: машина сбоку
                self._draw_lr(p, y, w, lr)

    # --- хелперы отрисовки строки (стиль Kapps) ---
    def _fmt_name(self, raw, style, case):
        return fmt_driver_name(raw, style, case)

    def _row_bg(self, p, i, y, w, player, style, r, cmode):
        p.setPen(Qt.NoPen)
        if player:                                       # игрок — всегда подсвечен
            hi = QColor(46, 60, 96, 210) if self._opt("colorblind", False) else QColor(38, 96, 60, 210)
            p.setBrush(hi)
            p.drawRoundedRect(QRectF(2, y, w - 4, self.ROW - 2), 5, 5)
            return
        if cmode == "row_bg":                            # multiclass: фон строки цветом класса
            c = _clr(r.get("class_color"))
            c.setAlpha(46)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(2, y, w - 4, self.ROW - 2), 5, 5)
            return
        shade = None                                     # стиль полос (Kapps Rows Style)
        if style == "solid":
            shade = 10
        elif style == "stripes" and i % 2 == 0:
            shade = 13
        elif style == "stripes_rev" and i % 2 == 1:
            shade = 13
        if shade:
            p.setBrush(QColor(255, 255, 255, shade))
            p.drawRoundedRect(QRectF(2, y, w - 4, self.ROW - 2), 5, 5)

    def _draw_number(self, p, X, y, r, cmode):
        num = str(r.get("number") or "")
        p.setPen(Qt.NoPen)
        if cmode == "num":                               # нейтральный бокс, цифры цвета класса
            p.setBrush(QColor(24, 27, 32))
            p.drawRoundedRect(QRectF(X["num"], y + 3, 28, self.ROW - 6), 3, 3)
            self.text(p, X["num"] + 14 - len(num) * 3.2, y + self.ROW - 8, num,
                      _clr(r.get("class_color")).name(), 10, True)
        else:                                            # цветной бокс, тёмные цифры (Number BG / Row BG)
            p.setBrush(_clr(r.get("class_color")))
            p.drawRoundedRect(QRectF(X["num"], y + 3, 28, self.ROW - 6), 3, 3)
            self.text(p, X["num"] + 14 - len(num) * 3.2, y + self.ROW - 8, num, "#0d0f12", 10, True)

    def _draw_sr(self, p, X, y, base, r, style):
        lic, sr = r.get("lic"), r.get("sr")
        licc = r.get("lic_color") or "#9099a6"           # уже hex-строка (LICENSE_COLORS)
        if not lic:
            self.text(p, X["sr"], base, "—", "#9aa4b0", 10)
            return
        if style == "text":                              # без бейджа — буква цветом + рейтинг
            self.text(p, X["sr"], base, f"{lic} {sr:.2f}" if sr is not None else lic, licc, 10, True)
            return
        p.setBrush(QColor(licc))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(X["sr"], y + 5, 15, self.ROW - 10), 3, 3)
        self.text(p, X["sr"] + 4, base - 1, lic, "#0d0f12", 9, True)
        if style != "compact" and sr is not None:        # compact — только буква
            self.text(p, X["sr"] + 19, base, f"{sr:.2f}", "#9aa4b0", 10)

    def _draw_lr(self, p, y, w, lr):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(AMBER))
        if lr in (2, 4, 5):                              # споттер: машина слева
            p.drawRect(QRectF(2, y, 3, self.ROW - 2))
        if lr in (3, 4, 6):                              # машина справа
            p.drawRect(QRectF(w - 5, y, 3, self.ROW - 2))

    # --- инфо-полоса (температуры / влажность / часы) ---
    def _tfmt(self, v, units, prec):
        if not isinstance(v, (int, float)):
            return "—"
        f = v * 9 / 5 + 32
        if units == "f":
            return f"{f:.1f}°F" if prec else f"{round(f)}°F"
        if units == "both":
            return f"{v:.0f}/{f:.0f}°"
        return f"{v:.1f}°C" if prec else f"{round(v)}°C"

    def _info_segments(self):
        live = self.store.get("live") or {}
        race = self.store.get("race") or {}
        sess = self.store.get("session") or {}
        u, prec = self._opt("track_temp_units", "default"), self._opt("track_precise", False)
        segs = []
        if self._opt("track_air_temp", True):
            segs.append(("AIR", self._tfmt(live.get("air_temp"), u, prec)))
        if self._opt("track_surface_temp", True):
            segs.append(("TRK", self._tfmt(live.get("track_temp"), u, prec)))
        if self._opt("track_humidity", False):
            h = race.get("humidity")
            segs.append(("HUM", f"{round(h*100)}%" if isinstance(h, (int, float)) else "—"))
        # мои температуры (по чужим машинам iRacing не отдаёт)
        cu, cprec = self._opt("car_temp_units", "default"), self._opt("car_precise", False)
        if self._opt("car_oil_temp", False):
            segs.append(("OIL", self._tfmt(live.get("oil_temp"), cu, cprec)))
        if self._opt("car_water_temp", False):
            segs.append(("WAT", self._tfmt(live.get("water_temp"), cu, cprec)))
        if self._opt("car_brake_bias", False):
            bb = live.get("brake_bias")
            segs.append(("BB", f"{bb:.1f}%" if isinstance(bb, (int, float)) else "—"))
        if self._opt("show_clock", False):
            from PySide6.QtCore import QTime
            t, fmt = QTime.currentTime(), self._opt("clock_format", "24h")
            if fmt == "12h":
                segs.append(("", t.toString("h:mm ap")))
            elif fmt == "12h_short":
                segs.append(("", t.toString("h:mma")))
            else:
                segs.append(("", t.toString("HH:mm")))
        if self._opt("show_session_clock", False):
            tod = sess.get("time_of_day")
            if isinstance(tod, (int, float)):
                segs.append(("SES", f"{int(tod//3600) % 24:02d}:{int((tod % 3600)//60):02d}"))
        return segs

    def _draw_info_strip(self, p, w):
        x = 10
        for label, val in self._info_segments():
            if label:
                self.text(p, x, 13, label, MUTED, 8)
                x += len(label) * 6 + 4
            self.text(p, x, 13, str(val), "#cdd3dc", 10, True)
            x += len(str(val)) * 7 + 16

    def extra_settings(self, lay):
        # ── Layout (яркость/радиус/тень/шрифт/colour-blind — универсальные, в общем диалоге) ──
        self.opt_number(lay, "Rows", "rows", 1, 64, 24)
        self.opt_choice(lay, "Rows style", "rows_style",
                        [("me", "Only me"), ("solid", "Solid"), ("stripes", "Stripes"), ("stripes_rev", "Striped 2")])
        # ── Driver identity ──
        self.opt_check(lay, "Car numbers", "show_num", True)
        self.opt_choice(lay, "Name", "name_style",
                        [("full", "Full"), ("f_last", "J. Last"), ("last_f", "Last J."), ("last", "Last"), ("initials", "J. R.")])
        self.opt_choice(lay, "Case", "name_case", [("normal", "Normal"), ("upper", "UPPER")])
        self.opt_choice(lay, "Class colour", "class_color_mode",
                        [("num", "Number"), ("num_bg", "Number BG"), ("row_bg", "Row BG")])
        self.opt_check(lay, "Car left/right", "car_lr_border", False)
        self.opt_check(lay, "Show pit", "show_pit", True)
        self.opt_choice(lay, "Manuf. logo", "manuf_logo",
                        [("off", "Off"), ("multi", "Multi-make"), ("always", "Always")])
        self.opt_slider(lay, "Logo size", "logo_size", 12, 44, 26)
        # ── Ratings ──
        self.opt_check(lay, "Show iRating", "show_ir", True)
        self.opt_check(lay, "Show iRating gain", "show_ir_gain", False)
        self.opt_check(lay, "Show Safety Rating", "show_sr", True)
        self.opt_choice(lay, "Rating style", "rating_style",
                        [("badge", "Badge"), ("compact", "Compact"), ("text", "Text")])
        self.opt_check(lay, "Show best lap", "show_best", True)
        self.opt_check(lay, "Show SoF", "show_sof", True)
        self.opt_check(lay, "SoF precise", "sof_precise", True)
        # ── Info bar / temps / clock ──
        self.opt_check(lay, "Info bar", "show_info", False)
        self.opt_check(lay, "Air temp", "track_air_temp", True)
        self.opt_check(lay, "Track temp", "track_surface_temp", True)
        self.opt_check(lay, "Humidity", "track_humidity", False)
        self.opt_check(lay, "Temp precise", "track_precise", False)
        self.opt_choice(lay, "Temp units", "track_temp_units",
                        [("default", "°C"), ("f", "°F"), ("both", "Both")])
        self.opt_check(lay, "Oil temp (mine)", "car_oil_temp", False)
        self.opt_check(lay, "Water temp (mine)", "car_water_temp", False)
        self.opt_check(lay, "Brake bias (mine)", "car_brake_bias", False)
        self.opt_check(lay, "Car temp precise", "car_precise", False)
        self.opt_choice(lay, "Car units", "car_temp_units",
                        [("default", "°C"), ("f", "°F"), ("both", "Both")])
        self.opt_check(lay, "Local clock", "show_clock", False)
        self.opt_choice(lay, "Clock format", "clock_format",
                        [("24h", "19:45"), ("12h", "7:45pm"), ("12h_short", "7:45p")])
        self.opt_check(lay, "Session clock", "show_session_clock", False)
        self.cycle_assign_ui(lay)


class FlagsWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "flags", "Flags", (240, 70), "solo", ("race",)
    BLURB = "Flags as they are shown, plus the ones already waved."
    COLORS = {"green": GREEN, "yellow": AMBER, "yellow_waving": AMBER, "caution": AMBER, "blue": BLUE,
              "white": "#e8e8ee", "checkered": "#cfcfcf", "red": RED, "black": "#555",
              "repair": "#e67e22", "disqualify": RED}

    def draw(self, p):
        flags = self.store.get("race").get("flags") or []
        if not flags:
            self.text_center(p, "no flags", MUTED, 12)
            return
        x = 10
        for f in flags:
            label = f.get("label", "")
            w = 12 + len(label) * 8
            p.setBrush(QColor(self.COLORS.get(f.get("key"), MUTED)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, self.height() / 2 - 13, w, 26), 6, 6)
            self.text(p, x + 6, self.height() / 2 + 5, label, "#0d0f12", 11, True)
            x += w + 6


class GForceWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "gforce", "G-force", (150, 150), "solo", ("live",)
    BLURB = "Lateral and longitudinal load as a moving dot."

    def draw(self, p):
        l = self.store.get("live")
        cx, cy = self.width() / 2, self.height() / 2
        R = min(cx, cy) - 12
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#2a2f38")))
        p.drawEllipse(QPointF(cx, cy), R, R)
        p.drawEllipse(QPointF(cx, cy), R * 0.66, R * 0.66)
        p.drawLine(int(cx), int(cy - R), int(cx), int(cy + R))
        p.drawLine(int(cx - R), int(cy), int(cx + R), int(cy))
        lat, lon = l.get("lat_accel"), l.get("long_accel")
        if lat is not None and lon is not None:
            gx = max(-1, min(1, (lat / 9.81) / 2.5))
            gy = max(-1, min(1, (lon / 9.81) / 2.5))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(BLUE))
            p.drawEllipse(QPointF(cx + gx * R, cy + gy * R), 6, 6)


class RadarWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "radar", "Radar", (150, 150), "solo", ("relative", "race")
    BLURB = "Cars around you drawn from above, at close range."

    def draw(self, p):
        cars = (self.store.get("relative") or {}).get("cars") or []
        if not any(c.get("is_player") for c in cars):
            self.text_center(p, "radar — get on track", MUTED, 10)
            return
        p.setBrush(QColor(10, 12, 15))
        p.setPen(QPen(QColor("#2a2f38")))
        p.drawRoundedRect(QRectF(self.width() / 2 - 30, 12, 60, self.height() - 24), 8, 8)
        cx = self.width() / 2
        p.setBrush(QColor(GREEN))                        # игрок — зелёный (отличать от синих LMP2)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(cx - 4, self.height() / 2 - 7, 8, 14), 2, 2)
        for c in cars:
            if c.get("is_player"):
                continue
            rp = c.get("rel_pct")
            if rp is None or abs(rp) > 0.04:
                continue
            y = self.height() / 2 - max(-1, min(1, rp / 0.04)) * (self.height() / 2 - 20)
            p.setBrush(_clr(c.get("class_color")))
            p.drawEllipse(QPointF(cx, y), 5, 5)
        lr = self.store.get("race").get("car_left_right") or 0
        p.setBrush(QColor(AMBER))
        if lr in (1, 3, 4):
            p.drawRect(QRectF(6, 30, 6, self.height() - 60))
        if lr in (2, 3, 5):
            p.drawRect(QRectF(self.width() - 12, 30, 6, self.height() - 60))


class TrackMapWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "trackmap", "Track map", (240, 200), "solo", ("trackmap", "relative")
    BLURB = "The circuit drawn from your own laps, with the field on it."

    def draw(self, p):
        tm = self.store.get("trackmap") or {}
        pts = tm.get("points") or []
        if not pts:
            self.text(p, 12, 28, "drive a lap — map will build", MUTED, 10)
            return
        top = 0
        if self._opt("show_name", True):                 # официальное имя трассы (из SDK, не угадываем)
            name, cfg = tm.get("track"), tm.get("config")
            if name:
                if cfg and cfg.lower() not in name.lower():
                    name = f"{name} · {cfg}"             # конфиг дописываем, если не вошёл в имя
                self.text_center(p, name, WHITE, 11, y=14)
                top = 20                                 # освобождаем место — карту сдвигаем ниже
        sc = min(self.width(), self.height() - top) / 100.0
        ox = (self.width() - 100 * sc) / 2
        oy = top + (self.height() - top - 100 * sc) / 2
        path = QPainterPath()
        for i, pt in enumerate(pts):
            x, y = ox + pt["x"] * sc, oy + pt["y"] * sc
            path.lineTo(x, y) if i else path.moveTo(x, y)
        # НЕ замыкаем: у самодельной карты есть дрейф → замыкающая линия резала бы полкарты
        pen = QPen(QColor(self._opt("line_color", "#8b97a6")))
        pen.setWidthF(float(self._opt("line_w", 4)))     # толщина линии трассы (⚙)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        cars = (self.store.get("relative") or {}).get("cars") or []
        spts = sorted(pts, key=lambda q: q.get("pct", 0))   # привязка — по pct (карта хранится в порядке траектории)
        cr = float(self._opt("car_r", 7))                # размер машинок (⚙)
        shown = 0
        # игрок рисуется ПОСЛЕДНИМ — поверх остальных, чтоб его было видно
        for c in sorted(cars, key=lambda cc: 1 if cc.get("is_player") else 0):
            lp = c.get("lap_pct")
            if lp is None:
                continue
            pos = self._on_track(lp, spts)
            player = c.get("is_player")
            r = cr + 1 if player else cr
            cx, cy = ox + pos[0] * sc, oy + pos[1] * sc
            p.setPen(QPen(QColor(13, 15, 18), 1.5))      # тёмная обводка — контраст на линии
            p.setBrush(QColor(GREEN) if player else _clr(c.get("class_color")))   # игрок зелёный
            p.drawEllipse(QPointF(cx, cy), r, r)
            num = str(c.get("number") or "")             # номер машины на кружке
            if num and r >= 5:
                f = QFont("Segoe UI")
                f.setPointSizeF(max(6.0, r * 0.95))
                f.setBold(True)
                p.setFont(f)
                p.setPen(QPen(QColor("#0d0f12")))
                p.drawText(QRectF(cx - r, cy - r - 1, r * 2, r * 2), Qt.AlignCenter, num)
            shown += 1
        self.text(p, 10, self.height() - 8, f"cars: {shown}", MUTED, 9)    # диагностика/инфо

    def extra_settings(self, lay):
        self.opt_slider(lay, "Track line width", "line_w", 1, 14, 4)
        self.opt_slider(lay, "Car dot size", "car_r", 4, 18, 7)
        self.opt_check(lay, "Show track name", "show_name", True)

    @staticmethod
    def _on_track(pct, s):
        """Позиция машины по доле круга. s — точки, ОТСОРТИРОВАННЫЕ по pct.
        Корректно кладёт машину даже на шве старт/финиш (между последней и первой точкой)."""
        n = len(s)
        if n == 0:
            return (50.0, 50.0)
        pct = pct % 1.0
        first, last = s[0]["pct"], s[-1]["pct"]
        if pct <= first or pct >= last:                      # шов: между последней и первой точкой по кругу
            a, b = s[-1], s[0]
            span = (b["pct"] + 1.0 - a["pct"]) or 1.0
            t = pct + 1.0 if pct < first else pct
            f = (t - a["pct"]) / span
            return (a["x"] + (b["x"] - a["x"]) * f, a["y"] + (b["y"] - a["y"]) * f)
        for i in range(n - 1):
            if s[i]["pct"] <= pct <= s[i + 1]["pct"]:
                span = (s[i + 1]["pct"] - s[i]["pct"]) or 1.0
                f = (pct - s[i]["pct"]) / span
                return (s[i]["x"] + (s[i + 1]["x"] - s[i]["x"]) * f,
                        s[i]["y"] + (s[i + 1]["y"] - s[i]["y"]) * f)
        return (s[0]["x"], s[0]["y"])


class DeltaBarWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "deltabar", "Delta bar", (260, 92), "solo", ("race",)
    BLURB = "Delta to best as a bar you can read without focusing."
    SCALE = 1.0                                          # ±1 c = полный бар

    def draw(self, p):
        self.title(p, "DELTA TO BEST")
        d = fastval("delta_best", self.store.get("race").get("delta_best"))
        cx = self.width() / 2
        y = self.height() * 0.64
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 12, 15))
        p.drawRoundedRect(QRectF(12, y - 9, self.width() - 24, 18), 9, 9)
        if isinstance(d, (int, float)):
            w = (self.width() / 2 - 12) * min(1.0, abs(d) / self.SCALE)
            col = GREEN if d <= 0 else RED
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(cx, y - 9, w, 18) if d <= 0 else QRectF(cx - w, y - 9, w, 18), 9, 9)
            self.text_center(p, f"{d:+.2f}", col, 22, y=y - 20, key="delta")
        else:
            self.text_center(p, "—", MUTED, 16, y=y - 20)
        p.setBrush(QColor("#3a4150"))                    # центральная риска
        p.drawRect(QRectF(cx - 1, y - 12, 2, 24))


class WearGraphWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "weargraph", "Wear graph", (240, 160), "solo", ("wear", "race")
    BLURB = "Tyre wear over the stint, as a line per wheel."
    COLORS = {"LF": "#3ea6ff", "RF": "#f1c40f", "LR": "#22d3ee", "RR": "#e67e22"}

    def draw(self, p):
        self.title(p, "TIRE WEAR BY LAP")
        w = self.store.get("wear") or {}
        lap = self.store.get("race").get("lap")
        keys = ("LF", "RF", "LR", "RR")
        if (lap is not None and lap != getattr(self, "_lastlap", None)
                and any(_worst(w.get(k)) is not None for k in keys)):
            self._lastlap = lap                          # снимок износа раз в круг
            self._hist = (getattr(self, "_hist", []) + [{k: _worst(w.get(k)) for k in keys}])[-40:]
        hist = getattr(self, "_hist", [])
        x0, y0, ww, hh = 14, 34, self.width() - 28, self.height() - 52
        p.setPen(QPen(QColor("#2a2f38")))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(x0, y0, ww, hh))
        if len(hist) < 2:
            self.text(p, x0 + 8, y0 + hh / 2, "drive a couple of laps", MUTED, 10)
        else:
            n = len(hist)
            for k, col in self.COLORS.items():
                pen = QPen(QColor(col))
                pen.setWidth(2)
                p.setPen(pen)
                prev = None
                for i, s in enumerate(hist):
                    v = s.get(k)
                    if not isinstance(v, (int, float)):
                        prev = None
                        continue
                    x = x0 + ww * i / (n - 1)
                    yy = y0 + hh * (1 - max(0.0, min(1.0, v)))
                    if prev:
                        p.drawLine(int(prev[0]), int(prev[1]), int(x), int(yy))
                    prev = (x, yy)
        lx = x0                                          # легенда по углам
        for k, col in self.COLORS.items():
            self.text(p, lx, self.height() - 6, k, col, 9, True)
            lx += 36


class SpotterWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "spotter", "Spotter", (210, 110), "solo", ("race",)
    BLURB = "Spotter calls in text: car left, car right, three wide."

    def draw(self, p):
        lr = self.store.get("race").get("car_left_right") or 0
        left, right = lr in (2, 4, 5), lr in (3, 4, 6)
        wide = lr in (5, 6)
        cy = self.height() / 2
        self._tri(p, True, left, cy)
        self._tri(p, False, right, cy)
        if not left and not right:
            self.text_center(p, "clear", GREEN, 15)
        else:
            self.text_center(p, "3 WIDE!" if wide else "CAR ALONGSIDE",
                             RED if wide else AMBER, 13, y=self.height() - 12)

    def _tri(self, p, is_left, active, cy):
        p.setBrush(QColor(RED) if active else QColor("#20252d"))
        p.setPen(Qt.NoPen)
        w = self.width()
        pts = ([QPointF(14, cy), QPointF(54, cy - 28), QPointF(54, cy + 28)] if is_left
               else [QPointF(w - 14, cy), QPointF(w - 54, cy - 28), QPointF(w - 54, cy + 28)])
        p.drawPolygon(QPolygonF(pts))


class WeatherRadarWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "weatherradar", "Weather radar", (250, 130), "solo", ("race", "live")
    BLURB = "Rain approaching the circuit, and how soon."

    def draw(self, p):
        self.title(p, "WEATHER")
        r, l = self.store.get("race"), self.store.get("live")
        cx, cy = 54.0, self.height() * 0.58
        R = min(cx - 12, self.height() * 0.30)
        p.setPen(QPen(QColor("#2a2f38")))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R, R)
        self.text(p, cx - 4, cy - R - 3, "N", MUTED, 8)      # север
        wd = r.get("wind_dir")
        if isinstance(wd, (int, float)):                     # стрелка ветра
            ax, ay = cx + math.sin(wd) * R * 0.82, cy - math.cos(wd) * R * 0.82
            pen = QPen(QColor(BLUE))
            pen.setWidth(3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(int(cx), int(cy), int(ax), int(ay))
        x = 104
        tt, at, wv, wet = l.get("track_temp"), l.get("air_temp"), r.get("wind_vel"), r.get("track_wetness")
        self.text(p, x, 46, f"track {round(tt)}°" if isinstance(tt, (int, float)) else "track —", WHITE, 12, True)
        self.text(p, x, 66, f"air {round(at)}°" if isinstance(at, (int, float)) else "air —", "#cdd3dc", 11)
        self.text(p, x, 86, f"wind {wv:.1f} m/s" if isinstance(wv, (int, float)) else "wind —", "#cdd3dc", 11)
        self.text(p, x, 106, "surface: " + wetness(wet), GREEN if (wet or 0) <= 1 else AMBER, 11)


# ================= ENDURANCE =================
class DriverStintWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "e_driver", "Driver & stint", (240, 138), "endur", ("standings", "race")
    BLURB = "Who is in the car and how long this stint has run."

    def rows(self):
        st = self.store.get("standings") or []
        me = next((d for d in st if d.get("is_player")), {})
        name = me.get("name")
        # круг берём у МАШИНЫ (CarIdxLap из standings), а не из своей телеметрии:
        # пока за рулём напарник, свой канал Lap стоит на нуле
        lap = me.get("lap")
        if not isinstance(lap, int) or lap < 0:
            lap = self.store.get("race").get("lap")
        if name and name != getattr(self, "_drv", None):      # пересели — начался новый стинт
            self._drv = name
            self._t0 = time.monotonic()
            self._lap0 = lap if isinstance(lap, int) else None
        stint = fmt_time(time.monotonic() - self._t0) if getattr(self, "_t0", None) else "—"
        l0 = getattr(self, "_lap0", None)
        done = lap - l0 if isinstance(lap, int) and isinstance(l0, int) else None
        return [("Driver", (name or "—")[:18]),
                ("Stint", stint, BLUE),
                ("Stint laps", str(done) if done is not None else "—", GREEN),
                ("Lap", str(lap) if isinstance(lap, int) and lap >= 0 else "—")]


class TimeLeftWidget(OverlayWidget):
    """Сколько осталось гонки — крупно, с полосой прогресса.

    В эндурансе на часы смотрят краем глаза, и полоса читается быстрее цифр.
    Последние пять минут красным: это окно последнего пит-стопа.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "e_time", "Time left", (240, 130), "endur", ("session",)
    BLURB = "Time left in the race, big, with a progress bar."

    def extra_settings(self, lay):
        self.opt_check(lay, "Progress bar", "show_bar", True)
        self.opt_slider(lay, "Warn before (min)", "warn_min", 1, 30, 5)

    def draw(self, p):
        self.title(p, "RACE TIME LEFT")
        s = self.store.get("session")
        tr = s.get("time_remain")
        warn = self._opt("warn_min", 5) * 60
        col = RED if isinstance(tr, (int, float)) and 0 < tr <= warn else WHITE

        bar = self._opt("show_bar", True)
        self.text_center(p, fmt_time(tr), col, 26,
                         y=self.height() / 2 + (2 if bar else 10), key="time")

        if bar:
            total = None
            if isinstance(tr, (int, float)):
                total = max(getattr(self, "_total", 0.0), tr)   # старт = самый большой виденный
                self._total = total
            y, h = self.height() - 34, 10.0
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#20252d"))
            p.drawRoundedRect(QRectF(12, y, self.width() - 24, h), h / 2, h / 2)
            if total and total > 0 and isinstance(tr, (int, float)):
                done = max(0.0, min(1.0, 1.0 - tr / total))
                p.setBrush(QColor(col if col == RED else GREEN))
                p.drawRoundedRect(QRectF(12, y, (self.width() - 24) * done, h), h / 2, h / 2)

        lr = s.get("laps_remain")
        if lr is not None:
            self.text(p, 12, self.height() - 8, f"laps left: {lr}", MUTED, 10)


class TeamIncidentsWidget(StatWidget):
    """Инциденты команды в эндурансе.

    Голое число ничего не решает — решает, сколько осталось до лимита.
    В командных гонках лимит общий, и штраф прилетает всей машине, поэтому
    показываем остаток и долю, которую наездил ты.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "e_incidents", "Team incidents", (220, 150), "endur", ("damage",)
    BLURB = "Incident count for the whole team, not just you."

    def extra_settings(self, lay):
        self.opt_number(lay, "Incident limit", "limit", 0, 200, 17)
        self.opt_check(lay, "My share", "show_share", True)

    def rows(self):
        d = self.store.get("damage")
        ti = d.get("team_incidents")
        mine = d.get("incidents")
        ti = ti if isinstance(ti, (int, float)) else 0
        mine = mine if isinstance(mine, (int, float)) else 0
        limit = self._opt("limit", 17)

        out = [("Team", f"{ti}x", GREEN if ti < 4 else (AMBER if ti < 8 else RED)),
               ("Mine", f"{mine}x")]
        if limit:
            left = limit - ti
            out.append(("Left", f"{max(0, left)} to limit",
                        GREEN if left > 5 else (AMBER if left > 2 else RED)))
            if left <= 0:
                out.append(("", "limit reached", RED))
        if self._opt("show_share", True) and ti:
            out.append(("My share", f"{round(mine / ti * 100)}%"))
        return out


# ================= SETUP =================
class SymptomsWidget(StatWidget):
    """Поведение машины по фазам поворота: вход, середина, выход.

    Три одинаковых слова в столбик мало что дают. Добавлен ВЫВОД: если во
    всех трёх фазах одно и то же — это общая беда сетапа и лечится
    крыльями или пружинами; если только на входе или только на выходе —
    точечная правка, и подсказка будет другая.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "s_symptoms", "Symptoms", (250, 180), "setup", ("result",)
    BLURB = "What the car does on entry, mid-corner and exit."
    _M = {"understeer": ("understeer", AMBER), "oversteer": ("oversteer", RED),
          "neutral": ("neutral", GREEN)}
    _HINT = {
        "entry": {"understeer": "softer front, brake bias rearward",
                  "oversteer": "brake bias forward"},
        "mid": {"understeer": "softer front, no more rear wing",
                "oversteer": "stiffer rear, more wing"},
        "exit": {"understeer": "softer rear, less diff lock",
                 "oversteer": "less diff lock, gentler throttle"},
    }

    def extra_settings(self, lay):
        self.opt_check(lay, "Setup hint", "show_hint", True)

    def rows(self):
        bal = ((self.store.get("result") or {}).get("symptoms") or {}).get("balance")
        if not bal:
            return [("Symptoms", "after stint"), ("", "drive a few laps", MUTED)]

        out, seen = [], []
        for k, name in (("entry", "Entry"), ("mid", "Mid"), ("exit", "Exit")):
            t = (bal.get(k) or {}).get("tendency")
            lab, col = self._M.get(t, ("—", MUTED))
            out.append((name, lab, col))
            if t in ("understeer", "oversteer"):
                seen.append((k, t))

        if not self._opt("show_hint", True) or not seen:
            return out

        kinds = {t for _, t in seen}
        if len(seen) == 3 and len(kinds) == 1:
            kind = seen[0][1]
            out.append(("Verdict", f"{kind} everywhere", AMBER))
            out.append(("Try", "wings and springs overall", MUTED))
        else:
            phase, kind = seen[0]
            out.append(("Worst at", phase, AMBER))
            hint = self._HINT.get(phase, {}).get(kind)
            if hint:
                out.append(("Try", hint, MUTED))
        return out


class BalanceWidget(StatWidget):
    """Тепловой баланс осей — и что с ним делать в сетапе.

    Разница температур сама по себе ничего не подсказывает новичку. Поэтому
    переводим её в понятную сторону: перегретый перед означает, что машина
    цепляется носом и её сносит; перегретый зад — что она вращается.
    Рядом даём направление правки, а не только диагноз.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "s_balance", "Front/rear balance", (240, 150), "setup", ("result",)
    BLURB = "Heat balance front to rear — and the setup change it asks for."

    def extra_settings(self, lay):
        self.opt_slider(lay, "Noticeable from (°)", "thr", 1, 15, 3)
        self.opt_check(lay, "Setup hint", "show_hint", True)

    def rows(self):
        tire = ((self.store.get("result") or {}).get("symptoms") or {}).get("tire") or {}
        b = tire.get("front_rear_balance")
        if not isinstance(b, (int, float)):
            return [("Balance", "after stint"), ("", "drive a few laps", MUTED)]

        thr = self._opt("thr", 3)
        front = b > 0
        out = [("Hotter axle", "front" if front else "rear",
                AMBER if abs(b) >= thr else GREEN),
               ("Difference", f"{abs(b):.1f}°")]

        if abs(b) < thr:
            out.append(("Verdict", "balanced", GREEN))
        else:
            out.append(("Feels like", "understeer" if front else "oversteer",
                        AMBER if front else RED))
            if self._opt("show_hint", True):
                out.append(("Try", "softer front / more rear wing" if front
                            else "softer rear / less rear wing", MUTED))
        return out


class WearTrendWidget(StatWidget):
    """Скорость износа резины и сколько её осталось.

    Одного «осталось 25 кругов» мало для решения: важно, ХВАТИТ ли этого
    до конца гонки. Поэтому сравниваем остаток с числом кругов до финиша
    и говорим прямо — доедешь или менять.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "s_weartrend", "Wear trend", (220, 150), "setup", ("strategy",)
    BLURB = "How fast the tyres are going away, and how much is left."

    def extra_settings(self, lay):
        self.opt_check(lay, "Will they last to the finish", "show_verdict", True)

    def rows(self):
        g = self.store.get("strategy")
        wpl, left = g.get("tire_wear_per_lap"), g.get("tire_laps_left")
        togo, worst = g.get("laps_to_go"), g.get("tire_min")

        out = []
        if isinstance(worst, (int, float)):
            pct = round(worst * 100)
            out.append(("Worst tire", f"{pct}%",
                        GREEN if pct > 50 else (AMBER if pct > 30 else RED)))
        out.append(("Wear/lap", f"{wpl * 100:.2f}%" if isinstance(wpl, (int, float)) else "—"))
        out.append(("Tires left", f"{left:.0f} laps" if isinstance(left, (int, float)) else "—"))

        if self._opt("show_verdict", True):
            if isinstance(left, (int, float)) and isinstance(togo, (int, float)):
                out.append(("To finish", f"{int(togo)} laps"))
                if left >= togo:
                    out.append(("Verdict", "will last", GREEN))
                else:
                    out.append(("Verdict", f"short by {togo - left:.0f}", RED))
            elif g.get("change_tires"):
                out.append(("Verdict", "change them", RED))
        return out


# порядок в панели: сгруппировано solo → endur → setup
class RaceBarWidget(OverlayWidget):
    """Компактный мини-HUD одной полосой (идея из RaceLab): передача + шифт-лайты +
    скорость/обороты + позиция + нижняя строка (темп./топливо/круг). Свой дизайн."""
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "racebar", "Race bar", (474, 150), "solo", ("live", "race", "strategy")
    BLURB = "A one-line HUD: gear, shift lights, delta and fuel."

    def draw(self, p):
        live, race, strat = self.store.get("live"), self.store.get("race"), self.store.get("strategy")
        W, H = self.width(), self.height()

        def T(x, y, w, h, s, color, px, align=Qt.AlignCenter, bold=True):
            f = QFont("Segoe UI")
            f.setPixelSize(max(9, int(px)))
            f.setBold(bold)
            p.setFont(f)
            p.setPen(QPen(QColor(color)))
            p.drawText(QRectF(x, y, w, h), align | Qt.AlignVCenter, str(s))

        rpm, shift = fastval("rpm", race.get("rpm")), fastval("shift_rpm", race.get("shift_rpm"))
        frac = 0.0
        if isinstance(rpm, (int, float)) and isinstance(shift, (int, float)) and shift > 0:
            frac = max(0.0, min(1.0, rpm / shift))
        # шифт-лайты: ряд точек, загорается зелёным→жёлтым→красным по мере оборотов
        n = 15
        x0, x1, yy, r = 0.29 * W, 0.62 * W, 0.16 * H, max(3.0, 0.032 * H)
        p.setPen(Qt.NoPen)
        for i in range(n):
            on = frac >= (i + 0.85) / n
            c = GREEN if i < n * 0.53 else (AMBER if i < n * 0.8 else RED)
            p.setBrush(QColor(c) if on else QColor("#30353d"))
            p.drawEllipse(QPointF(x0 + (x1 - x0) * i / (n - 1), yy), r, r)
        # круг передачи
        gx, gy, gr = 0.13 * W, 0.50 * H, 0.30 * H
        p.setBrush(QColor(24, 27, 32))
        p.setPen(QPen(QColor("#454b54"), max(2.0, 0.03 * H)))
        p.drawEllipse(QPointF(gx, gy), gr, gr)
        g = fastval("gear", live.get("gear"))
        gear = ("N" if g == 0 else "R" if g == -1 else str(g)) if g is not None else "—"
        T(gx - gr, gy - gr, gr * 2, gr * 2, gear, RED if frac >= 0.97 else WHITE, gr * 1.05)
        # средние показатели: скорость и обороты
        spd = fastval("speed", live.get("speed"))
        kmh = round(spd * 3.6) if isinstance(spd, (int, float)) else "—"
        T(0.29 * W, 0.33 * H, 0.13 * W, 0.15 * H, "SPD", "#8a93a0", 0.10 * H, Qt.AlignLeft)
        T(0.29 * W, 0.45 * H, 0.14 * W, 0.24 * H, kmh, WHITE, 0.20 * H, Qt.AlignLeft)
        T(0.44 * W, 0.33 * H, 0.13 * W, 0.15 * H, "RPM", "#8a93a0", 0.10 * H, Qt.AlignLeft)
        T(0.44 * W, 0.45 * H, 0.17 * W, 0.24 * H, round(rpm) if isinstance(rpm, (int, float)) else "—",
          WHITE, 0.20 * H, Qt.AlignLeft)
        # позиция крупно справа
        pos = race.get("position")
        T(0.64 * W, 0.18 * H, 0.33 * W, 0.46 * H, f"P{pos}" if pos else "P—", WHITE, 0.38 * H)
        # нижняя строка: температура трассы · топливо · последний круг
        p.setBrush(QColor(0, 0, 0, 90))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0.03 * W, 0.72 * H, 0.94 * W, 0.22 * H), 7, 7)
        tt, fuel, ll = live.get("track_temp"), strat.get("fuel"), race.get("last_lap_time")
        yb, hb = 0.74 * H, 0.18 * H
        T(0.06 * W, yb, 0.22 * W, hb, f"{round(tt)}°C" if isinstance(tt, (int, float)) else "—",
          "#cdd3dc", 0.10 * H, Qt.AlignLeft)
        T(0.37 * W, yb, 0.22 * W, hb, f"{fuel} L" if fuel is not None else "— L",
          AMBER, 0.10 * H, Qt.AlignLeft)
        T(0.66 * W, yb, 0.30 * W, hb, lap_time(ll), "#cdd3dc", 0.10 * H, Qt.AlignLeft)


class LapLogWidget(OverlayWidget):
    """Лог кругов таблицей: круг, время, разница, температура.

    График времён кругов (Laptime graph) показывает форму, но не даёт
    прочитать конкретные цифры. Таблица отвечает на другой вопрос: «что
    было на восьмом круге и почему он медленнее седьмого».

    Температура трассы стоит рядом с временем не для полноты. Круг на
    горячей трассе медленнее на несколько десятых при том же пилотаже, и
    без этой колонки такой круг выглядит как ошибка, которой не было.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = ("laplog", "Laptime log", (330, 220),
                                             "solo", ("race",))
    BLURB = "A table of laps: number, time, delta, track temperature."
    ROW = 24

    def extra_settings(self, lay):
        self.opt_slider(lay, "Laps in the table", "rows", 3, 20, 7)
        self.opt_check(lay, "Temperature column", "show_temp", True)
        self.opt_check(lay, "Delta to best", "show_delta", True)

    def draw(self, p):
        self.title(p, "LAPTIME LOG")
        log = (self.store.get("race").get("lap_log") or [])
        rows = [x for x in log if isinstance(x.get("time"), (int, float)) and x["time"] > 0]
        if not rows:
            self.text(p, 12, self.height() / 2, "drive a lap", MUTED, 11)
            return

        n = int(self._opt("rows", 7))
        show_temp = self._opt("show_temp", True)
        show_delta = self._opt("show_delta", True)
        best = min(x["time"] for x in rows)
        rows = sorted(rows, key=lambda x: x.get("lap") or 0, reverse=True)[:n]

        W = self.width()
        x_lap, x_time = 12, 58
        x_delta = W - (108 if show_temp else 20)
        x_temp = W - 56

        y = 34
        self.text(p, x_lap, y, "LAP", MUTED, 9)
        self.text(p, x_time, y, "TIME", MUTED, 9)
        if show_delta:
            self.text(p, x_delta, y, "Δ", MUTED, 9)
        if show_temp:
            self.text(p, x_temp, y, "TRACK", MUTED, 9)

        y += 8
        for r in rows:
            y += self.ROW
            if y > self.height() - 6:
                break
            t = r["time"]
            is_best = abs(t - best) < 1e-6
            self.text(p, x_lap, y, str(r.get("lap") or "—"), MUTED, 11)
            self.text(p, x_time, y, lap_time(t), PURPLE if is_best else WHITE, 12, True)
            if show_delta:
                d = t - best
                self.text(p, x_delta, y, "——" if is_best else f"{d:+.2f}",
                          MUTED if is_best else (GREEN if d < 0 else RED), 11)
            if show_temp:
                tt = r.get("track_temp")
                self.text(p, x_temp, y,
                          f"{round(tt)}°" if isinstance(tt, (int, float)) else "—",
                          MUTED, 11)


class BlindSpotWidget(OverlayWidget):
    """Слепая зона: две широкие панели по краям экрана.

    У нас уже есть Radar (точки вокруг машины) и Spotter (треугольники).
    Разница не в данных — они те же, car_left_right, — а в подаче.
    Радар и споттер надо НАЙТИ ГЛАЗАМИ, а в повороте на это нет времени.
    Этот виджет растягивается на всю ширину экрана и работает боковым
    зрением: загорелось справа — не поворачивай туда.

    Поэтому здесь нет мелкого текста и нет цифр. Только большое пятно.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = ("blindspot", "Blind spot", (620, 120),
                                             "solo", ("race",))
    BLURB = ("Two wide bars at the screen edges when a car sits alongside.")

    def extra_settings(self, lay):
        self.opt_slider(lay, "Glow brightness (%)", "glow", 20, 100, 85)
        self.opt_check(lay, "LEFT/RIGHT labels", "show_labels", True)
        self.opt_check(lay, "Red when three wide", "warn_wide", True)

    def draw(self, p):
        lr = self.store.get("race").get("car_left_right") or 0
        left, right = lr in (2, 4, 5), lr in (3, 4, 6)
        wide = lr in (5, 6)
        glow = self._opt("glow", 85) / 100.0
        labels = self._opt("show_labels", True)
        hot = RED if (wide and self._opt("warn_wide", True)) else AMBER

        W, H = self.width(), self.height()
        pad = 10
        bw = max(60.0, W * 0.22)                     # панель = пятая часть ширины
        for is_left, on in ((True, left), (False, right)):
            x = pad if is_left else W - bw - pad
            rect = QRectF(x, pad, bw, H - pad * 2)
            p.setPen(Qt.NoPen)
            if on:
                # мягкое свечение: три вложенных прямоугольника с растущей
                # прозрачностью — дешевле настоящего размытия и не тормозит
                c = QColor(hot)
                for k in (2.2, 1.4, 1.0):
                    g = QColor(c)
                    g.setAlphaF(min(1.0, glow * (0.22 if k > 2 else 0.4 if k > 1.2 else 1.0)))
                    p.setBrush(g)
                    p.drawRoundedRect(rect.adjusted(-6 * k, -6 * k, 6 * k, 6 * k), 14, 14)
            else:
                p.setBrush(QColor(22, 26, 32, 150))
                p.drawRoundedRect(rect, 14, 14)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor("#2a2f38"), 2))
                p.drawRoundedRect(rect, 14, 14)

            if labels:
                self.text(p, rect.x() + 12, rect.y() + 20,
                          "LEFT" if is_left else "RIGHT",
                          "#0d0f12" if on else MUTED, 10, True)



class CornerLossWidget(OverlayWidget):
    """Где потеряно время в последнем круге — по поворотам.

    Дельта к лучшему кругу говорит СКОЛЬКО, но не говорит ГДЕ. Узнать это
    можно было только выйдя из машины и открыв вкладку разбора; на длинной
    практике так никто не делает, и та же ошибка повторяется круг за кругом.

    Здесь три худших поворота последнего круга висят поверх игры — прочесть
    их можно на прямой, и следующий круг ехать уже иначе.

    ВАЖНО: это ПРОШЛЫЙ круг, а не текущий. Разбор считается по сохранённому
    кругу, то есть появляется после пересечения линии. Живой посегментной
    дельты у нас нет, и делать вид, что есть, нельзя: пилот принял бы её
    за подсказку прямо сейчас.

    Своя отрисовка, а не StatWidget: причина потери — это фраза, и в колонку
    значений она не помещается ни при каком кегле. Первая версия наследовала
    StatWidget, и «slower through the middle» рисовалось тем же крупным
    шрифтом, что и цифры, забивая собой весь виджет.
    """

    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = ("cornerloss", "Corner losses",
                                             (300, 150), "solo", ("corners",))
    BLURB = "The three corners where the last lap lost the most time."
    ROW = 30

    def extra_settings(self, lay):
        self.opt_slider(lay, "Corners shown", "rows", 1, 6, 3)
        self.opt_check(lay, "Total lap delta", "show_total", True)
        self.opt_check(lay, "What went wrong", "show_reason", True)

    def draw(self, p):
        self.title(p, "CORNER LOSSES")
        r = self.store.get("corners") or {}
        if not r.get("ok"):
            self.text(p, 12, self.height() / 2, "after a lap", MUTED, 11)
            return

        W = self.width()
        y = 34
        if self._opt("show_total", True):
            d = r.get("delta") or 0.0
            self.text(p, 12, y, "LAP", MUTED, 9)
            self.text_right(p, W - 12, y, f"{d:+.2f}s",
                            RED if d > 0 else GREEN, 13, True, key="lap")
            y += 22

        worst = [s for s in (r.get("segments") or [])
                 if (s.get("loss") or 0.0) > 0.01]
        worst.sort(key=lambda s: -(s.get("loss") or 0.0))
        if not worst:
            self.text(p, 12, y + 6, "no corner lost time", GREEN, 12)
            return

        show_reason = self._opt("show_reason", True)
        for s in worst[:int(self._opt("rows", 3))]:
            if y > self.height() - 12:
                break
            self.text(p, 12, y, f"Corner {s['index']}", WHITE, 12, True)
            self.text_right(p, W - 12, y, f"+{s['loss']:.2f}s", AMBER, 13, True,
                            key=f"c{s['index']}", avail=W - 110)
            y += 14
            if show_reason:
                # Причина — мелким и приглушённым: это пояснение к цифре,
                # а не сама цифра.
                self.text(p, 12, y, _short_reason(s.get("phase")), MUTED, 10)
                y += 16
            else:
                y += 4

    def parts(self):
        return [("lap", "Lap delta")] + [(f"c{i}", f"Corner {i}") for i in range(1, 7)]


def _short_reason(phase):
    """Фаза словом. На оверлее нет места на предложение — только суть."""
    return {"braking": "braked too early",
            "apex": "slower through the middle",
            "exit": "late back on power",
            "flat": "arrived slower",
            "entry": "lost on entry"}.get(phase, "lost time here")


WIDGETS = [
    InputsWidget, PositionWidget, RelativeWidget, StandingsWidget, MyCarWidget, Head2HeadWidget,
    LaptimeGraphWidget, DeltaTraceWidget, LaptimeSpreadWidget, HStandingsWidget,
    LapLogWidget, BlindSpotWidget, CornerLossWidget,
    FuelWidget, TimingWidget, RaceBarWidget,
    DeltaWidget, ShiftWidget, GForceWidget, TopSpeedWidget, SlipWidget, PosTrendWidget,
    SummaryWidget, TireTempsWidget, WearWidget, SessionWidget, RecordDeltaWidget, ErsWidget,
    WeatherWidget, FlagsWidget, RadarWidget, TrackMapWidget, OptimalWidget, PitHelperWidget, MetricsWidget,
    DeltaBarWidget, WearGraphWidget, SpotterWidget, WeatherRadarWidget,
    DriverStintWidget, TimeLeftWidget, TeamIncidentsWidget,
    SymptomsWidget, BalanceWidget, WearTrendWidget,
]
