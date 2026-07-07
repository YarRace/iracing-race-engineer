"""Конкретные виджеты оверлея. Каждый читает данные из общего Store и рисует.

Добавить новый виджет = новый класс с KEY/TITLE/DEFAULT/draw() + запись в WIDGETS.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen

from overlay.base import OverlayWidget, lap_time

GREEN, RED, AMBER, BLUE, MUTED, WHITE = "#2ecc71", "#e74c3c", "#f1c40f", "#3ea6ff", "#9099a6", "#e8eaed"


def _clr(c):
    try:
        return QColor("#" + format(int(c) & 0xFFFFFF, "06x")) if c else QColor(RED)
    except Exception:
        return QColor(RED)


class InputsWidget(OverlayWidget):
    KEY, TITLE, DEFAULT = "inputs", "Педали и скорость", (240, 110)
    ENDPOINTS = ("live",)

    def draw(self, p):
        l = self.store.get("live")
        self.title(p, "СКОРОСТЬ / ПЕДАЛИ")
        spd = l.get("speed")
        kmh = round(self.ease("spd", spd * 3.6)) if isinstance(spd, (int, float)) else "—"
        g = l.get("gear")
        gear = ("N" if g == 0 else "R" if g == -1 else g) if g is not None else "—"
        self.text(p, 12, 52, kmh, WHITE, 26, True)
        self.text(p, 96, 52, "км/ч", MUTED, 10)
        self.text(p, self.width() - 40, 52, gear, WHITE, 26, True)
        self.bar(p, 12, 66, self.width() - 24, 11, self.ease("thr", l.get("throttle") or 0), QColor(GREEN))
        self.bar(p, 12, 82, self.width() - 24, 11, self.ease("brk", l.get("brake") or 0), QColor(RED))


class FuelWidget(OverlayWidget):
    KEY, TITLE, DEFAULT = "fuel", "Топливо и пит", (210, 130)
    ENDPOINTS = ("strategy",)

    def draw(self, p):
        g = self.store.get("strategy")
        self.title(p, "ТОПЛИВО И ПИТ")
        fuel = g.get("fuel")
        self.text(p, 12, 50, f"{fuel if fuel is not None else '—'} л", WHITE, 22, True)
        lof = g.get("laps_on_fuel")
        self.text(p, 12, 70, f"хватит ~{lof if lof is not None else '—'} кр.", MUTED, 10)
        add = g.get("fuel_to_add")
        if add is not None:
            txt = f"долить +{add} л" if add > 0 else "долить не нужно"
            self.text(p, 12, 94, txt, AMBER if add and add > 0 else GREEN, 13, True)
        pl = g.get("plan") or {}
        if pl.get("stops") is not None:
            s = pl["stops"]
            self.text(p, 12, 116, f"пит-стопов: {'не нужно' if s == 0 else s}", MUTED, 10)


class GForceWidget(OverlayWidget):
    KEY, TITLE, DEFAULT = "gforce", "G-force", (150, 150)
    ENDPOINTS = ("live",)

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
            gx = self.ease("gx", max(-1, min(1, (lat / 9.81) / 2.5)))
            gy = self.ease("gy", max(-1, min(1, (lon / 9.81) / 2.5)))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(BLUE))
            p.drawEllipse(QPointF(cx + gx * R, cy + gy * R), 6, 6)


class DeltaWidget(OverlayWidget):
    KEY, TITLE, DEFAULT = "delta", "Дельта к лучшему", (200, 90)
    ENDPOINTS = ("race",)

    def draw(self, p):
        r = self.store.get("race")
        self.title(p, "ДЕЛЬТА К ЛУЧШЕМУ")
        d = r.get("delta_best")
        if not isinstance(d, (int, float)):
            self.text_center(p, "—", MUTED, 22)
            return
        de = self.ease("d", d)
        col = GREEN if de <= 0 else RED
        self.text_center(p, ("+" if de > 0 else "") + f"{de:.2f}", col, 30, y=self.height() / 2 + 8)


class FlagsWidget(OverlayWidget):
    KEY, TITLE, DEFAULT = "flags", "Флаги", (240, 70)
    ENDPOINTS = ("race",)
    COLORS = {"green": GREEN, "yellow": AMBER, "yellow_waving": AMBER, "caution": AMBER,
              "blue": BLUE, "white": "#e8e8ee", "checkered": "#cfcfcf", "red": RED,
              "black": "#555", "repair": "#e67e22", "disqualify": RED}

    def draw(self, p):
        r = self.store.get("race")
        flags = r.get("flags") or []
        if not flags:
            self.text_center(p, "флагов нет", MUTED, 12)
            return
        x = 10
        for f in flags:
            col = self.COLORS.get(f.get("key"), MUTED)
            label = f.get("label", "")
            w = 12 + len(label) * 8
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(x, self.height() / 2 - 13, w, 26), 6, 6)
            self.text(p, x + 6, self.height() / 2 + 5, label, "#0d0f12", 11, True)
            x += w + 6


class StandingsWidget(OverlayWidget):
    KEY, TITLE, DEFAULT = "standings", "Таблица заезда", (520, 300)
    ENDPOINTS = ("standings",)
    ROW = 24

    def draw(self, p):
        rows = self.store.get("standings") or []
        if not rows:
            self.text(p, 12, 28, "нет данных — выезжай на трассу", MUTED, 11)
            return
        maxrows = max(1, (self.height() - 8) // self.ROW)
        X = {"pos": 10, "name": 42, "gap": 300, "last": 380, "pit": 470}
        for i, r in enumerate(rows[:maxrows]):
            y = 4 + i * self.ROW
            if r.get("is_player"):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(46, 80, 120, 210))
                p.drawRoundedRect(QRectF(2, y, self.width() - 4, self.ROW - 2), 5, 5)
            base = y + self.ROW - 8
            self.text(p, X["pos"], base, r.get("pos", ""), WHITE, 11, True)
            self.text(p, X["name"], base, (r.get("name") or "")[:24], WHITE, 11, bool(r.get("is_player")))
            self.text(p, X["gap"], base, "лидер" if r.get("pos") == 1 else f"+{r.get('gap', '')}", "#cdd3dc", 10)
            self.text(p, X["last"], base, lap_time(r.get("last")), "#cdd3dc", 10)
            if r.get("on_pit"):
                self.text(p, X["pit"], base, "PIT", AMBER, 10, True)


class RelativeWidget(OverlayWidget):
    KEY, TITLE, DEFAULT = "relative", "Relative", (360, 220)
    ENDPOINTS = ("relative",)
    ROW = 26

    def draw(self, p):
        data = self.store.get("relative") or {}
        cars = data.get("cars") or []
        me = next((i for i, c in enumerate(cars) if c.get("is_player")), -1)
        if me < 0:
            self.text(p, 12, 28, "нет данных — на трассе", MUTED, 11)
            return
        sl = cars[max(0, me - 3):me + 4]
        sl = list(reversed(sl))
        for i, c in enumerate(sl):
            y = 4 + i * self.ROW
            if c.get("is_player"):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(46, 80, 120, 210))
                p.drawRoundedRect(QRectF(2, y, self.width() - 4, self.ROW - 2), 5, 5)
            base = y + self.ROW - 9
            p.setBrush(_clr(c.get("class_color")))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(8, y + 6, 5, self.ROW - 12), 2, 2)
            self.text(p, 20, base, f"P{c.get('pos', '')}", MUTED, 10)
            self.text(p, 52, base, (c.get("name") or "")[:20], WHITE, 11, bool(c.get("is_player")))
            gap = c.get("gap")
            if not c.get("is_player") and isinstance(gap, (int, float)):
                col = RED if gap > 0 else GREEN
                self.text(p, self.width() - 70, base, f"{gap:+.1f}", col, 11, True)
            if c.get("on_pit"):
                self.text(p, self.width() - 28, base, "P", AMBER, 10, True)


# порядок в панели управления
WIDGETS = [InputsWidget, FuelWidget, DeltaWidget, GForceWidget, FlagsWidget,
           RelativeWidget, StandingsWidget]
