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
                if row[0]:
                    self.text(p, 12, y, row[0], MUTED, 10)
                # значение с key=label: кликабельно + берёт свой цвет/размер/шрифт
                self.text_right(p, self.width() - 12, y, row[1],
                                row[2] if len(row) > 2 else WHITE, 14, True, key=label)
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
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "fuel", "Fuel & pit", (210, 156), "solo", ("strategy",)

    def rows(self):
        g = self.store.get("strategy")
        pl = g.get("plan") or {}
        add = g.get("fuel_to_add")
        burn = g.get("avg_burn")
        r = [("Fuel", f"{g.get('fuel', '—')} L"),
             ("Range", f"~{g.get('laps_on_fuel', '—')} laps")]
        if add is not None:
            r.append(("Add", f"+{add} L" if add > 0 else "not needed", AMBER if add and add > 0 else GREEN))
            # тот же долив, но в кругах — литры в black box проще править, зная их цену в кругах
            if add > 0 and burn:
                r.append(("Adds", f"~{add / burn:.1f} laps"))
        if pl.get("stops") is not None:
            r.append(("Pit stops", "not needed" if pl["stops"] == 0 else str(pl["stops"])))
        return r


class DeltaWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "delta", "Delta to best", (200, 90), "solo", ("race",)

    def draw(self, p):
        self.title(p, "DELTA TO BEST")
        d = fastval("delta_best", self.store.get("race").get("delta_best"))
        if not isinstance(d, (int, float)):
            self.text_center(p, "—", MUTED, 22)
            return
        col = GREEN if d <= 0 else RED
        self.text_center(p, ("+" if d > 0 else "") + f"{d:.2f}", col, 30, y=self.height() / 2 + 8)


class ShiftWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "shift", "RPM & shift", (180, 90), "solo", ("race",)

    def rows(self):
        r = self.store.get("race")
        rpm, sh = fastval("rpm", r.get("rpm")), fastval("shift_rpm", r.get("shift_rpm"))
        up = rpm is not None and sh and rpm >= sh
        return [("RPM", str(round(rpm)) if rpm is not None else "—", RED if up else WHITE),
                ("", "↑ SHIFT" if up else "accelerating", AMBER if up else MUTED)]


class TopSpeedWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "topspeed", "Top speed", (190, 90), "solo", ("live",)

    def rows(self):
        spd = self.store.get("live").get("speed")
        kmh = spd * 3.6 if isinstance(spd, (int, float)) else None
        if kmh is not None:
            self._mx = max(getattr(self, "_mx", 0), kmh)
        return [("Now", f"{round(kmh)} km/h" if kmh is not None else "—"),
                ("Max", f"{round(getattr(self, '_mx', 0))} km/h", BLUE)]


class SlipWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "slip", "Slip", (180, 90), "solo", ("live",)

    def rows(self):
        yr = self.store.get("live").get("yaw_rate")
        if yr is None:
            return [("Slip", "—")]
        dps = abs(yr * 180 / math.pi)
        lab, col = ("stable", GREEN) if dps < 25 else (("sliding", AMBER) if dps < 50 else ("spinning!", RED))
        return [("State", lab, col), ("Yaw rate", f"{round(dps)}°/s")]


class PosTrendWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "postrend", "Position trend", (190, 90), "solo", ("race",)

    def rows(self):
        pos = self.store.get("race").get("position")
        if pos is None:
            return [("Position", "—")]
        if not hasattr(self, "_start"):
            self._start = pos
        d = self._start - pos
        txt, col = (f"▲ +{d}", GREEN) if d > 0 else ((f"▼ {d}", RED) if d < 0 else ("= 0", MUTED))
        return [("Position", f"P{pos}"), ("Since start", txt, col)]


class PositionWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "position", "Position & gaps", (210, 130), "solo", ("race",)

    def rows(self):
        r = self.store.get("race")
        cp, pos = r.get("class_position"), r.get("position")
        ga, gb = r.get("gap_ahead"), r.get("gap_behind")
        return [("In class", f"P{cp}" if cp is not None else "—", PURPLE),
                ("Overall", f"P{pos}" if pos is not None else "—"),
                ("Ahead", f"{ga:.1f} s" if isinstance(ga, (int, float)) else "—"),
                ("Behind", f"{gb:.1f} s" if isinstance(gb, (int, float)) else "—")]


class TimingWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "timing", "Laps", (210, 110), "solo", ("race",)

    def rows(self):
        r = self.store.get("race")
        return [("Last", lap_time(r.get("last_lap_time"))),
                ("Best", lap_time(r.get("best_lap_time")), PURPLE),
                ("Predicted", lap_time(r.get("predicted")))]


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
    MODES = [("optimal", "Optimal"), ("last", "Last"), ("best", "Best"),
             ("predicted", "Predicted"), ("delta", "Δ to best")]
    CYCLE_OPT, CYCLE_DEFAULT = "mode", "optimal"
    CYCLE_VALUES = [m for m, _ in MODES]

    def __init__(self, store, config):
        super().__init__(store, config)
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
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "summary", "Session summary", (210, 130), "solo", ("race", "damage")

    def rows(self):
        r = self.store.get("race")
        log = r.get("lap_log") or []
        t = [x["time"] for x in log if x.get("time", 0) > 0]
        best = min(t) if t else r.get("best_lap_time")
        spread = (max(t) - min(t)) if t else None
        inc = self.store.get("damage").get("incidents")
        return [("Position", f"P{r.get('class_position', '—')}"),
                ("Best", lap_time(best), PURPLE),
                ("Spread", f"±{spread/2:.2f}s" if spread is not None else "—"),
                ("Incidents", f"{inc if inc is not None else 0}x")]


class SessionWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "session", "Session", (210, 110), "solo", ("session",)

    def rows(self):
        s = self.store.get("session")
        lr, lt = s.get("laps_remain"), s.get("laps_total")
        return [("Event", ev(s.get("session_type"))),
                ("Time left", fmt_time(s.get("time_remain"))),
                ("Laps", f"{lr}{'/' + str(lt) if lt else ''}" if lr is not None else "—")]


class RecordDeltaWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "recorddelta", "Delta to record", (210, 110), "solo", ("session", "race")

    def rows(self):
        rec = self.store.get("session").get("record")
        if rec is None:
            return [("Record", "none — drive a lap")]
        cur = self.store.get("race").get("best_lap_time")
        r = [("Your record", lap_time(rec), PURPLE), ("Now", lap_time(cur))]
        if isinstance(cur, (int, float)):
            d = cur - rec
            r.append(("Δ", f"{d:+.2f}s", GREEN if d <= 0 else RED))
        return r


class ErsWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "ers", "ERS / hybrid", (200, 90), "solo", ("race",)

    def rows(self):
        r = self.store.get("race")
        e, d = r.get("energy_pct"), r.get("deploy_pct")
        if e is None:
            return [("Hybrid", "no data")]
        b = round(e * 100)
        col = GREEN if b >= 50 else (AMBER if b >= 20 else RED)
        return [("Battery", f"{b}%", col), ("Deploy/lap", f"{round(d*100)}%" if d is not None else "—")]


class WeatherWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "weather", "Weather", (200, 110), "solo", ("race",)

    def rows(self):
        r = self.store.get("race")
        wv, h = r.get("wind_vel"), r.get("humidity")
        return [("Wind", f"{wv:.1f} m/s" if isinstance(wv, (int, float)) else "—"),
                ("Humidity", f"{round((h or 0)*100)}%" if h is not None else "—"),
                ("Surface", wetness(r.get("track_wetness")))]


class PitHelperWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "pithelper", "Pit helper", (210, 110), "solo", ("race", "live", "strategy")

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
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "metrics", "Sensors & balance", (220, 110), "solo", ("result",)

    def rows(self):
        s = (self.store.get("result") or {}).get("symptoms") or {}
        out = []
        if s.get("inputs"):
            i = s["inputs"]
            out.append(("Trail braking", f"{i.get('trail_brake_pct', 0):.0f}%"))
            out.append(("Throttle smoothness", f"{(i.get('throttle_smoothness') or 0)*100:.0f}%"))
        if s.get("tire") and s["tire"].get("front_rear_balance") is not None:
            b = s["tire"]["front_rear_balance"]
            out.append(("Tire balance", f"{'front' if b > 0 else 'rear'} +{abs(b):.1f}°"))
        return out or [("Sensors", "after stint")]


class TireTempsWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "tiretemps", "Tire temps", (240, 150), "solo", ("live",)

    def draw(self, p):
        self.title(p, "TIRE TEMPS")
        t = self.store.get("live").get("tires") or {}
        cells = [("LF", "LF", 12, 34), ("RF", "RF", self.width() / 2 + 4, 34),
                 ("LR", "LR", 12, 92), ("RR", "RR", self.width() / 2 + 4, 92)]
        pw = (self.width() / 2 - 20) / 3
        for c, name, x, y in cells:
            self.text(p, x, y, name, MUTED, 9)
            corner = t.get(c) or {}
            for i, k in enumerate(("tl", "tm", "tr")):
                v = corner.get(k)
                p.setBrush(QColor(tcol(v)))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(x + i * pw, y + 6, pw - 3, 20), 4, 4)
                self.text(p, x + i * pw + 4, y + 20, "—" if v is None else round(v), "#0d0f12", 9, True)


class WearWidget(OverlayWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "wear", "Tire wear", (220, 150), "solo", ("wear",)

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
    ROW = 26
    CYCLE_OPT, CYCLE_DEFAULT = "name_style", "full"
    CYCLE_VALUES = ["full", "f_last", "last_f", "last", "initials"]

    def __init__(self, store, config):
        super().__init__(store, config)
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
    CYCLE_OPT, CYCLE_DEFAULT = "vs", "ahead"
    CYCLE_VALUES = ["ahead", "behind", "leader"]

    def __init__(self, store, config):
        super().__init__(store, config)
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
    CYCLE_OPT, CYCLE_DEFAULT = "anchor", "top"
    CYCLE_VALUES = ["top", "me"]

    def __init__(self, store, config):
        super().__init__(store, config)
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
    ENDPOINTS = ("standings", "session", "race", "live")
    ROW = 24
    CYCLE_OPT, CYCLE_DEFAULT = "rows_style", "me"
    CYCLE_VALUES = ["me", "solid", "stripes", "stripes_rev"]

    def __init__(self, store, config):
        super().__init__(store, config)
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
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "e_time", "Time left", (200, 100), "endur", ("session",)

    def draw(self, p):
        self.title(p, "RACE TIME LEFT")
        s = self.store.get("session")
        self.text_center(p, fmt_time(s.get("time_remain")), WHITE, 26, y=self.height() / 2 + 10)
        lr = s.get("laps_remain")
        if lr is not None:
            self.text(p, 12, self.height() - 10, f"laps: {lr}", MUTED, 10)


class TeamIncidentsWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "e_incidents", "Team incidents", (210, 90), "endur", ("damage",)

    def rows(self):
        d = self.store.get("damage")
        ti = d.get("team_incidents")
        col = GREEN if (ti or 0) < 4 else (AMBER if ti < 8 else RED)
        return [("Team", f"{ti if ti is not None else 0}x", col),
                ("Mine", f"{d.get('incidents', 0)}x")]


# ================= SETUP =================
class SymptomsWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "s_symptoms", "Symptoms", (220, 130), "setup", ("result",)
    _M = {"understeer": ("understeer", AMBER), "oversteer": ("oversteer", RED), "neutral": ("neutral", GREEN)}

    def rows(self):
        bal = ((self.store.get("result") or {}).get("symptoms") or {}).get("balance")
        if not bal:
            return [("Symptoms", "after stint")]
        out = []
        for k, name in (("entry", "Entry"), ("mid", "Mid"), ("exit", "Exit")):
            t = (bal.get(k) or {}).get("tendency")
            lab, col = self._M.get(t, ("—", MUTED))
            out.append((name, lab, col))
        return out


class BalanceWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "s_balance", "Front/rear balance", (220, 90), "setup", ("result",)

    def rows(self):
        tire = ((self.store.get("result") or {}).get("symptoms") or {}).get("tire") or {}
        b = tire.get("front_rear_balance")
        if b is None:
            return [("Balance", "after stint")]
        return [("Hotter", "front" if b > 0 else "rear"), ("Difference", f"{abs(b):.1f}°")]


class WearTrendWidget(StatWidget):
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "s_weartrend", "Wear trend", (210, 90), "setup", ("strategy",)

    def rows(self):
        g = self.store.get("strategy")
        wpl, left = g.get("tire_wear_per_lap"), g.get("tire_laps_left")
        return [("Wear/lap", f"{wpl*100:.2f}%" if wpl is not None else "—"),
                ("Tires left", f"{left:.0f} laps" if left is not None else "—")]


# порядок в панели: сгруппировано solo → endur → setup
class RaceBarWidget(OverlayWidget):
    """Компактный мини-HUD одной полосой (идея из RaceLab): передача + шифт-лайты +
    скорость/обороты + позиция + нижняя строка (темп./топливо/круг). Свой дизайн."""
    KEY, TITLE, DEFAULT, GROUP, ENDPOINTS = "racebar", "Race bar", (474, 150), "solo", ("live", "race", "strategy")

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


WIDGETS = [
    InputsWidget, PositionWidget, RelativeWidget, StandingsWidget, MyCarWidget, Head2HeadWidget,
    LaptimeGraphWidget, DeltaTraceWidget, LaptimeSpreadWidget, HStandingsWidget,
    FuelWidget, TimingWidget, RaceBarWidget,
    DeltaWidget, ShiftWidget, GForceWidget, TopSpeedWidget, SlipWidget, PosTrendWidget,
    SummaryWidget, TireTempsWidget, WearWidget, SessionWidget, RecordDeltaWidget, ErsWidget,
    WeatherWidget, FlagsWidget, RadarWidget, TrackMapWidget, OptimalWidget, PitHelperWidget, MetricsWidget,
    DeltaBarWidget, WearGraphWidget, SpotterWidget, WeatherRadarWidget,
    DriverStintWidget, TimeLeftWidget, TeamIncidentsWidget,
    SymptomsWidget, BalanceWidget, WearTrendWidget,
]
