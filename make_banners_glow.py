# -*- coding: utf-8 -*-
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance, ImageFilter

SRC = r"C:\Users\Ярослав\Downloads\carbon.jpg.jpg"
OUT = r"C:\Users\Ярослав\Pictures\BAR_panels\real_carbon_v2"
os.makedirs(OUT, exist_ok=True)

W, H = 640, 180
MARGIN = 32                 # меньше отступ -> текст крупнее
RED = (232, 64, 28)         # #E8401C — сам текст
GLOW = (255, 95, 55)        # чуть ярче для свечения
FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"
TRACK_F = 0.11              # разрядка букв

base = Image.open(SRC).convert("RGB")
bg = ImageOps.fit(base, (W, H), method=Image.LANCZOS)
bg = ImageEnhance.Brightness(bg).enhance(0.82)

def tw(draw, text, font, track):
    return sum(draw.textlength(c, font=font) for c in text) + track*(len(text)-1)

def fit(draw, text, max_w):
    for s in range(70, 16, -2):           # потолок 70 (было 64)
        f = ImageFont.truetype(FONT_PATH, s); t = s*TRACK_F
        if tw(draw, text, f, t) <= max_w: return f, t
    return ImageFont.truetype(FONT_PATH, 18), 18*TRACK_F

def draw_tracked(draw, text, font, track, cx, cy, fill):
    ws = [draw.textlength(c, font=font) for c in text]
    x = cx - (sum(ws)+track*(len(text)-1))/2
    asc, desc = font.getmetrics(); ty = cy-(asc+desc)/2
    for c, w in zip(text, ws):
        draw.text((x, ty), c, font=font, fill=fill); x += w+track

panels = [
    ("01_setup", "SETUP"), ("02_cockpit", "COCKPIT"), ("03_about", "О КАНАЛЕ"),
    ("04_team_bar", "КОМАНДА BAR"), ("05_socials", "СОЦСЕТИ / ССЫЛКИ"),
    ("06_schedule", "РАСПИСАНИЕ"), ("07_support", "ПОДДЕРЖАТЬ"),
]

for fn, title in panels:
    img = bg.copy().convert("RGBA")
    md = ImageDraw.Draw(img)
    f, t = fit(md, title, W-2*MARGIN)
    # --- лёгкое свечение ---
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    draw_tracked(gd, title, f, t, W/2, H/2, GLOW+(255,))
    glow = glow.filter(ImageFilter.GaussianBlur(5))
    a = glow.split()[3].point(lambda v: int(v*0.65))   # приглушаем свечение
    glow.putalpha(a)
    img = Image.alpha_composite(img, glow)
    # --- чёткий текст + рамка ---
    d = ImageDraw.Draw(img)
    d.rectangle([1, 1, W-2, H-2], outline=RED, width=3)
    draw_tracked(d, title, f, t, W/2, H/2, RED+(255,))
    img = img.convert("RGB")
    p = os.path.join(OUT, fn+".png"); img.save(p); print("OK:", p)
print("\nПапка:", OUT)
