#!/usr/bin/env python3
"""Generate Stream Deck icons (default: 144x144 for XL/Mk.2).

Override the output resolution with the ICON_SIZE env var, e.g.
``ICON_SIZE=72 python generate_icons.py`` for an Original / Mini set.
"""

from PIL import Image, ImageDraw, ImageFont
import math
import os

SIZE = int(os.environ.get("ICON_SIZE", "144"))
_SCALE = SIZE / 72  # design coords stay 72-based and scale on the fly
OUT = "icons"
os.makedirs(OUT, exist_ok=True)


def _s(v):
    """Scale a 72-based design coordinate (or line width / font size) to SIZE."""
    return int(round(v * _SCALE))


def new(bg=(0, 0, 0)):
    img = Image.new("RGBA", (SIZE, SIZE), bg)
    return img, ImageDraw.Draw(img)


def save(img, name):
    img.save(os.path.join(OUT, name))
    print(f"  ✓ {name}")


# ── Navigation ──────────────────────────────────────────


def icon_back():
    img, d = new((40, 40, 50))
    pts = [(_s(48), _s(18)), (_s(24), _s(36)), (_s(48), _s(54))]
    d.polygon(pts, fill=(200, 200, 220))
    d.line([(_s(24), _s(36)), (_s(54), _s(36))], fill=(200, 200, 220), width=_s(4))
    save(img, "back.png")


def icon_home():
    img, d = new((30, 60, 90))
    d.polygon([(_s(36), _s(14)), (_s(14), _s(34)), (_s(58), _s(34))], fill=(255, 255, 255))
    d.rectangle([(_s(20), _s(34)), (_s(52), _s(56))], fill=(255, 255, 255))
    d.rectangle([(_s(31), _s(42)), (_s(41), _s(56))], fill=(30, 60, 90))
    save(img, "home.png")


def icon_settings():
    img, d = new((60, 60, 60))
    cx, cy, r = 36, 36, 12
    for i in range(8):
        angle = i * 45
        rad = math.radians(angle)
        x1 = cx + (r + 4) * math.cos(rad)
        y1 = cy + (r + 4) * math.sin(rad)
        d.ellipse(
            [(_s(x1 - 5), _s(y1 - 5)), (_s(x1 + 5), _s(y1 + 5))],
            fill=(200, 200, 200),
        )
    d.ellipse(
        [(_s(cx - r), _s(cy - r)), (_s(cx + r), _s(cy + r))],
        fill=(200, 200, 200),
    )
    d.ellipse(
        [(_s(cx - 6), _s(cy - 6)), (_s(cx + 6), _s(cy + 6))],
        fill=(60, 60, 60),
    )
    save(img, "settings.png")


# ── Hue / Lights ────────────────────────────────────────


def icon_hue_logo():
    img, d = new((10, 10, 30))
    d.ellipse([(_s(16), _s(10)), (_s(56), _s(50))], fill=(80, 40, 120))
    d.ellipse([(_s(20), _s(14)), (_s(52), _s(46))], fill=(120, 60, 180))
    d.ellipse([(_s(26), _s(18)), (_s(46), _s(42))], fill=(255, 200, 50))
    d.rectangle([(_s(30), _s(42)), (_s(42), _s(52))], fill=(180, 180, 180))
    d.rectangle([(_s(32), _s(52)), (_s(40), _s(56))], fill=(150, 150, 150))
    save(img, "hue.png")


def icon_light_on():
    img, d = new((10, 10, 10))
    cx, cy = 36, 28
    for i in range(8):
        angle = math.radians(i * 45)
        x1 = cx + 18 * math.cos(angle)
        y1 = cy + 18 * math.sin(angle)
        x2 = cx + 26 * math.cos(angle)
        y2 = cy + 26 * math.sin(angle)
        d.line([(_s(x1), _s(y1)), (_s(x2), _s(y2))], fill=(255, 220, 50), width=_s(2))
    d.ellipse([(_s(20), _s(12)), (_s(52), _s(44))], fill=(255, 230, 80))
    d.rectangle([(_s(28), _s(44)), (_s(44), _s(54))], fill=(200, 200, 200))
    d.rectangle([(_s(30), _s(54)), (_s(42), _s(58))], fill=(170, 170, 170))
    save(img, "light_on.png")


def icon_light_off():
    img, d = new((10, 10, 10))
    d.ellipse([(_s(20), _s(12)), (_s(52), _s(44))], fill=(60, 60, 70))
    d.rectangle([(_s(28), _s(44)), (_s(44), _s(54))], fill=(100, 100, 100))
    d.rectangle([(_s(30), _s(54)), (_s(42), _s(58))], fill=(80, 80, 80))
    save(img, "light_off.png")


def icon_brightness(level, name):
    """level: 0.0 to 1.0"""
    bg_val = int(10 + level * 30)
    img, d = new((bg_val, bg_val, bg_val + 5))
    r = 8 + level * 12  # raw design-space pixels; we'll _s() at use
    cx, cy = 36, 32
    col_val = int(100 + level * 155)
    color = (col_val, col_val, int(col_val * 0.6))
    d.ellipse(
        [(_s(cx - r), _s(cy - r)), (_s(cx + r), _s(cy + r))],
        fill=color,
    )
    if level > 0.2:
        ray_len = 4 + level * 8
        for i in range(8):
            angle = math.radians(i * 45)
            x1 = cx + (r + 2) * math.cos(angle)
            y1 = cy + (r + 2) * math.sin(angle)
            x2 = cx + (r + 2 + ray_len) * math.cos(angle)
            y2 = cy + (r + 2 + ray_len) * math.sin(angle)
            d.line(
                [(_s(x1), _s(y1)), (_s(x2), _s(y2))],
                fill=color,
                width=_s(2),
            )
    save(img, name)


# ── Spotify / Music ─────────────────────────────────────


def icon_spotify():
    img, d = new((25, 20, 20))
    d.ellipse([(_s(10), _s(10)), (_s(62), _s(62))], fill=(30, 215, 96))
    for i, (y_off, length) in enumerate([(20, 28), (28, 22), (36, 16)]):
        x_start = 36 - length // 2
        x_end = 36 + length // 2
        pts = []
        for x in range(x_start, x_end + 1):
            progress = (x - x_start) / max(1, (x_end - x_start))
            curve = -4 * math.sin(progress * math.pi)
            pts.append((_s(x), _s(y_off + curve)))
        for j in range(len(pts) - 1):
            d.line([pts[j], pts[j + 1]], fill=(0, 0, 0), width=_s(3))
    save(img, "spotify.png")


def icon_play_pause():
    img, d = new((30, 30, 30))
    d.polygon([(_s(22), _s(18)), (_s(22), _s(54)), (_s(40), _s(36))], fill=(30, 215, 96))
    d.rectangle([(_s(44), _s(18)), (_s(48), _s(54))], fill=(200, 200, 200))
    d.rectangle([(_s(52), _s(18)), (_s(56), _s(54))], fill=(200, 200, 200))
    save(img, "play_pause.png")


def icon_play():
    img, d = new((30, 215, 96))
    d.polygon([(_s(24), _s(16)), (_s(24), _s(56)), (_s(54), _s(36))], fill=(0, 0, 0))
    save(img, "play.png")


def icon_pause():
    img, d = new((30, 215, 96))
    d.rectangle([(_s(22), _s(16)), (_s(32), _s(56))], fill=(0, 0, 0))
    d.rectangle([(_s(40), _s(16)), (_s(50), _s(56))], fill=(0, 0, 0))
    save(img, "pause.png")


def icon_next():
    img, d = new((30, 30, 30))
    d.polygon([(_s(20), _s(18)), (_s(20), _s(54)), (_s(42), _s(36))], fill=(200, 200, 220))
    d.polygon([(_s(38), _s(18)), (_s(38), _s(54)), (_s(56), _s(36))], fill=(200, 200, 220))
    save(img, "next.png")


def icon_prev():
    img, d = new((30, 30, 30))
    d.polygon([(_s(52), _s(18)), (_s(52), _s(54)), (_s(30), _s(36))], fill=(200, 200, 220))
    d.polygon([(_s(34), _s(18)), (_s(34), _s(54)), (_s(16), _s(36))], fill=(200, 200, 220))
    save(img, "prev.png")


def icon_vol_up():
    img, d = new((30, 30, 40))
    d.polygon(
        [
            (_s(14), _s(28)), (_s(14), _s(44)),
            (_s(24), _s(44)), (_s(34), _s(54)),
            (_s(34), _s(18)), (_s(24), _s(28)),
        ],
        fill=(180, 180, 200),
    )
    for offset in [6, 14]:
        pts = []
        for a in range(-35, 36, 5):
            rad = math.radians(a)
            x = 38 + offset * math.cos(rad)
            y = 36 - offset * math.sin(rad)
            pts.append((_s(x), _s(y)))
        for j in range(len(pts) - 1):
            d.line([pts[j], pts[j + 1]], fill=(100, 200, 255), width=_s(2))
    d.line([(_s(54), _s(12)), (_s(54), _s(24))], fill=(100, 255, 100), width=_s(3))
    d.line([(_s(48), _s(18)), (_s(60), _s(18))], fill=(100, 255, 100), width=_s(3))
    save(img, "vol_up.png")


def icon_vol_down():
    img, d = new((30, 30, 40))
    d.polygon(
        [
            (_s(14), _s(28)), (_s(14), _s(44)),
            (_s(24), _s(44)), (_s(34), _s(54)),
            (_s(34), _s(18)), (_s(24), _s(28)),
        ],
        fill=(180, 180, 200),
    )
    pts = []
    for a in range(-35, 36, 5):
        rad = math.radians(a)
        x = 38 + 6 * math.cos(rad)
        y = 36 - 6 * math.sin(rad)
        pts.append((_s(x), _s(y)))
    for j in range(len(pts) - 1):
        d.line([pts[j], pts[j + 1]], fill=(100, 200, 255), width=_s(2))
    d.line([(_s(48), _s(18)), (_s(60), _s(18))], fill=(255, 100, 100), width=_s(3))
    save(img, "vol_down.png")


def icon_shuffle():
    img, d = new((30, 30, 30))
    d.line([(_s(16), _s(22)), (_s(40), _s(50))], fill=(200, 200, 220), width=_s(3))
    d.line([(_s(16), _s(50)), (_s(40), _s(22))], fill=(200, 200, 220), width=_s(3))
    d.polygon([(_s(40), _s(18)), (_s(40), _s(28)), (_s(52), _s(22))], fill=(200, 200, 220))
    d.polygon([(_s(40), _s(44)), (_s(40), _s(54)), (_s(52), _s(50))], fill=(200, 200, 220))
    save(img, "shuffle.png")


def _draw_repeat_arrows(d, color=(200, 200, 220)):
    """Draw looping arrows shared by repeat icons."""
    d.line([(_s(16), _s(24)), (_s(52), _s(24))], fill=color, width=_s(3))
    d.polygon([(_s(48), _s(18)), (_s(58), _s(24)), (_s(48), _s(30))], fill=color)
    d.line([(_s(20), _s(46)), (_s(56), _s(46))], fill=color, width=_s(3))
    d.polygon([(_s(24), _s(40)), (_s(14), _s(46)), (_s(24), _s(52))], fill=color)
    d.arc([(_s(48), _s(24)), (_s(60), _s(46))], start=270, end=90, fill=color, width=_s(3))
    d.arc([(_s(12), _s(24)), (_s(24), _s(46))], start=90, end=270, fill=color, width=_s(3))


def icon_repeat():
    img, d = new((30, 30, 30))
    _draw_repeat_arrows(d)
    save(img, "repeat.png")


def icon_repeat_one():
    img, d = new((30, 30, 30))
    _draw_repeat_arrows(d)
    try:
        font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", _s(18))
    except OSError:
        font = ImageFont.load_default()
    d.text((_s(36), _s(35)), "1", font=font, anchor="mm", fill=(255, 255, 255))
    save(img, "repeat_one.png")


# ── Heating / Kasa / Tapo ───────────────────────────────


def icon_heating():
    img, d = new((50, 15, 10))
    d.ellipse([(_s(22), _s(24)), (_s(50), _s(58))], fill=(255, 100, 20))
    d.ellipse([(_s(26), _s(16)), (_s(46), _s(48))], fill=(255, 160, 30))
    d.ellipse([(_s(30), _s(20)), (_s(42), _s(44))], fill=(255, 220, 60))
    d.ellipse([(_s(33), _s(28)), (_s(39), _s(40))], fill=(255, 250, 150))
    save(img, "heating.png")


def icon_power_on():
    img, d = new((0, 80, 20))
    cx, cy, r = 36, 38, 16
    d.arc(
        [(_s(cx - r), _s(cy - r)), (_s(cx + r), _s(cy + r))],
        start=220,
        end=320,
        fill=(255, 255, 255),
        width=_s(4),
    )
    d.line(
        [(_s(cx), _s(cy - r - 2)), (_s(cx), _s(cy - 2))],
        fill=(255, 255, 255),
        width=_s(4),
    )
    save(img, "power_on.png")


def icon_power_off():
    img, d = new((80, 20, 20))
    cx, cy, r = 36, 38, 16
    d.arc(
        [(_s(cx - r), _s(cy - r)), (_s(cx + r), _s(cy + r))],
        start=220,
        end=320,
        fill=(200, 200, 200),
        width=_s(4),
    )
    d.line(
        [(_s(cx), _s(cy - r - 2)), (_s(cx), _s(cy - 2))],
        fill=(200, 200, 200),
        width=_s(4),
    )
    save(img, "power_off.png")


def icon_thermometer():
    img, d = new((20, 20, 40))
    d.rounded_rectangle([(_s(30), _s(10)), (_s(42), _s(48))], radius=_s(6), fill=(200, 200, 220))
    d.ellipse([(_s(26), _s(42)), (_s(46), _s(62))], fill=(200, 200, 220))
    d.rectangle([(_s(33), _s(24)), (_s(39), _s(48))], fill=(220, 50, 50))
    d.ellipse([(_s(29), _s(45)), (_s(43), _s(59))], fill=(220, 50, 50))
    save(img, "thermometer.png")


def icon_fan():
    img, d = new((20, 30, 40))
    cx, cy = 36, 36
    for angle_offset in [0, 90, 180, 270]:
        pts = []
        for a in range(0, 80, 2):
            rad = math.radians(a + angle_offset)
            r = 6 + a * 0.25
            pts.append((_s(cx + r * math.cos(rad)), _s(cy + r * math.sin(rad))))
        if len(pts) > 1:
            for j in range(len(pts) - 1):
                d.line([pts[j], pts[j + 1]], fill=(150, 200, 255), width=_s(3))
    d.ellipse(
        [(_s(cx - 5), _s(cy - 5)), (_s(cx + 5), _s(cy + 5))],
        fill=(200, 200, 220),
    )
    save(img, "fan.png")


def icon_kasa():
    img, d = new((10, 40, 30))
    d.rounded_rectangle([(_s(14), _s(16)), (_s(58), _s(52))], radius=_s(8), fill=(60, 180, 120))
    d.rounded_rectangle([(_s(24), _s(24)), (_s(30), _s(38))], radius=_s(2), fill=(255, 255, 255))
    d.rounded_rectangle([(_s(42), _s(24)), (_s(48), _s(38))], radius=_s(2), fill=(255, 255, 255))
    d.ellipse([(_s(32), _s(42)), (_s(40), _s(48))], fill=(255, 255, 255))
    save(img, "kasa.png")


def icon_tapo():
    img, d = new((10, 20, 50))
    cx, cy = 36, 36
    d.rounded_rectangle([(_s(16), _s(18)), (_s(56), _s(54))], radius=_s(10), fill=(50, 130, 220))
    for r_off in [8, 15]:
        pts = []
        for a in range(-45, 46, 5):
            rad = math.radians(a)
            x = cx + r_off * math.cos(rad)
            y = cy - 4 - r_off * math.sin(rad)
            pts.append((_s(x), _s(y)))
        for j in range(len(pts) - 1):
            d.line([pts[j], pts[j + 1]], fill=(255, 255, 255), width=_s(2))
    d.ellipse(
        [(_s(cx - 3), _s(cy - 1)), (_s(cx + 3), _s(cy + 5))],
        fill=(255, 255, 255),
    )
    save(img, "tapo.png")


# ── Scenes / Presets ────────────────────────────────────


def icon_scene(name, color, filename):
    img, d = new(tuple(c // 4 for c in color))
    for r in range(24, 0, -1):
        factor = r / 24
        c = tuple(int(v * factor) for v in color)
        d.ellipse([(_s(36 - r), _s(32 - r)), (_s(36 + r), _s(32 + r))], fill=c)
    save(img, filename)


def icon_playlist(color, filename):
    img, d = new((20, 20, 20))
    for y_off in [18, 28, 38, 48]:
        line_len = 36 if y_off < 48 else 28
        d.line([(_s(18), _s(y_off)), (_s(18 + line_len), _s(y_off))], fill=color, width=_s(2))
    d.ellipse([(_s(44), _s(42)), (_s(54), _s(52))], fill=color)
    d.line([(_s(54), _s(20)), (_s(54), _s(48))], fill=color, width=_s(2))
    d.line([(_s(54), _s(20)), (_s(62), _s(24))], fill=color, width=_s(2))
    save(img, filename)


# ── Misc ────────────────────────────────────────────────


def icon_blank():
    img, d = new((0, 0, 0))
    save(img, "blank.png")


def icon_error():
    img, d = new((80, 0, 0))
    d.line([(_s(20), _s(20)), (_s(52), _s(52))], fill=(255, 255, 255), width=_s(4))
    d.line([(_s(52), _s(20)), (_s(20), _s(52))], fill=(255, 255, 255), width=_s(4))
    save(img, "error.png")


def icon_refresh():
    img, d = new((30, 50, 60))
    cx, cy, r = 36, 36, 16
    d.arc(
        [(_s(cx - r), _s(cy - r)), (_s(cx + r), _s(cy + r))],
        start=30,
        end=330,
        fill=(150, 220, 255),
        width=_s(3),
    )
    angle = math.radians(330)
    ax = cx + r * math.cos(angle)
    ay = cy + r * math.sin(angle)
    d.polygon(
        [(_s(ax), _s(ay - 6)), (_s(ax + 8), _s(ay)), (_s(ax), _s(ay + 6))],
        fill=(150, 220, 255),
    )
    save(img, "refresh.png")


# ── Generate All ────────────────────────────────────────

if __name__ == "__main__":
    print(f"Generating Stream Deck icons ({SIZE}x{SIZE})...\n")

    print("Navigation:")
    icon_back()
    icon_home()
    icon_settings()

    print("\nLights:")
    icon_hue_logo()
    icon_light_on()
    icon_light_off()
    icon_brightness(0.25, "brightness_25.png")
    icon_brightness(0.50, "brightness_50.png")
    icon_brightness(0.75, "brightness_75.png")
    icon_brightness(1.00, "brightness_100.png")

    print("\nMusic:")
    icon_spotify()
    icon_play_pause()
    icon_play()
    icon_pause()
    icon_next()
    icon_prev()
    icon_vol_up()
    icon_vol_down()
    icon_shuffle()
    icon_repeat()
    icon_repeat_one()

    print("\nHeating / Devices:")
    icon_heating()
    icon_power_on()
    icon_power_off()
    icon_thermometer()
    icon_fan()
    icon_kasa()
    icon_tapo()

    print("\nScenes:")
    icon_scene("Relax", (255, 147, 41), "scene_relax.png")
    icon_scene("Focus", (150, 180, 255), "scene_focus.png")
    icon_scene("Party", (255, 50, 200), "scene_party.png")
    icon_scene("Night", (80, 40, 120), "scene_night.png")
    icon_scene("Energy", (50, 255, 100), "scene_energy.png")

    print("\nPlaylists:")
    icon_playlist((30, 215, 96), "playlist_1.png")
    icon_playlist((255, 100, 100), "playlist_2.png")
    icon_playlist((100, 150, 255), "playlist_3.png")
    icon_playlist((255, 200, 50), "playlist_4.png")
    icon_playlist((200, 100, 255), "playlist_5.png")

    print("\nMisc:")
    icon_blank()
    icon_error()
    icon_refresh()

    total = len(os.listdir(OUT))
    print(f"\n✅ Done! {total} icons generated in {OUT}/")
