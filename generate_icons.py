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
    # Arrow pointing left
    pts = [(48, 18), (24, 36), (48, 54)]
    d.polygon(pts, fill=(200, 200, 220))
    d.line([(24, 36), (54, 36)], fill=(200, 200, 220), width=4)
    save(img, "back.png")


def icon_home():
    img, d = new((30, 60, 90))
    # House shape
    d.polygon([(36, 14), (14, 34), (58, 34)], fill=(255, 255, 255))  # roof
    d.rectangle([(20, 34), (52, 56)], fill=(255, 255, 255))  # body
    d.rectangle([(31, 42), (41, 56)], fill=(30, 60, 90))  # door
    save(img, "home.png")


def icon_settings():
    img, d = new((60, 60, 60))
    cx, cy, r = 36, 36, 12
    # Gear teeth
    for i in range(8):
        angle = i * 45
        rad = math.radians(angle)
        x1 = cx + (r + 4) * math.cos(rad)
        y1 = cy + (r + 4) * math.sin(rad)
        d.ellipse([(x1 - 5, y1 - 5), (x1 + 5, y1 + 5)], fill=(200, 200, 200))
    d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(200, 200, 200))
    d.ellipse([(cx - 6, cy - 6), (cx + 6, cy + 6)], fill=(60, 60, 60))
    save(img, "settings.png")


# ── Hue / Lights ────────────────────────────────────────


def icon_hue_logo():
    img, d = new((10, 10, 30))
    # Stylized bulb with colored glow
    # Outer glow
    d.ellipse([(16, 10), (56, 50)], fill=(80, 40, 120))
    d.ellipse([(20, 14), (52, 46)], fill=(120, 60, 180))
    # Bulb center
    d.ellipse([(26, 18), (46, 42)], fill=(255, 200, 50))
    # Base
    d.rectangle([(30, 42), (42, 52)], fill=(180, 180, 180))
    d.rectangle([(32, 52), (40, 56)], fill=(150, 150, 150))
    save(img, "hue.png")


def icon_light_on():
    img, d = new((10, 10, 10))
    # Rays
    cx, cy = 36, 28
    for i in range(8):
        angle = math.radians(i * 45)
        x1 = cx + 18 * math.cos(angle)
        y1 = cy + 18 * math.sin(angle)
        x2 = cx + 26 * math.cos(angle)
        y2 = cy + 26 * math.sin(angle)
        d.line([(x1, y1), (x2, y2)], fill=(255, 220, 50), width=2)
    # Bulb
    d.ellipse([(20, 12), (52, 44)], fill=(255, 230, 80))
    # Base
    d.rectangle([(28, 44), (44, 54)], fill=(200, 200, 200))
    d.rectangle([(30, 54), (42, 58)], fill=(170, 170, 170))
    save(img, "light_on.png")


def icon_light_off():
    img, d = new((10, 10, 10))
    # Bulb (dimmed)
    d.ellipse([(20, 12), (52, 44)], fill=(60, 60, 70))
    # Base
    d.rectangle([(28, 44), (44, 54)], fill=(100, 100, 100))
    d.rectangle([(30, 54), (42, 58)], fill=(80, 80, 80))
    save(img, "light_off.png")


def icon_brightness(level, name):
    """level: 0.0 to 1.0"""
    bg_val = int(10 + level * 30)
    img, d = new((bg_val, bg_val, bg_val + 5))
    # Sun with size based on level
    r = int(8 + level * 12)
    cx, cy = 36, 32
    col_val = int(100 + level * 155)
    color = (col_val, col_val, int(col_val * 0.6))
    d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=color)
    # Rays
    if level > 0.2:
        ray_len = int(4 + level * 8)
        for i in range(8):
            angle = math.radians(i * 45)
            x1 = cx + (r + 2) * math.cos(angle)
            y1 = cy + (r + 2) * math.sin(angle)
            x2 = cx + (r + 2 + ray_len) * math.cos(angle)
            y2 = cy + (r + 2 + ray_len) * math.sin(angle)
            d.line([(x1, y1), (x2, y2)], fill=color, width=2)
    save(img, name)


# ── Spotify / Music ─────────────────────────────────────


def icon_spotify():
    img, d = new((25, 20, 20))
    # Green circle
    d.ellipse([(10, 10), (62, 62)], fill=(30, 215, 96))
    # Three curved bars (simplified as arcs)
    for i, (y_off, length) in enumerate([(20, 28), (28, 22), (36, 16)]):
        x_start = 36 - length // 2
        x_end = 36 + length // 2
        # Approximate arc with a thick line that curves
        pts = []
        for x in range(x_start, x_end + 1):
            progress = (x - x_start) / max(1, (x_end - x_start))
            curve = -4 * math.sin(progress * math.pi)
            pts.append((x, y_off + curve))
        for j in range(len(pts) - 1):
            d.line([pts[j], pts[j + 1]], fill=(0, 0, 0), width=3)
    save(img, "spotify.png")


def icon_play_pause():
    img, d = new((30, 30, 30))
    # Play triangle
    d.polygon([(22, 18), (22, 54), (40, 36)], fill=(30, 215, 96))
    # Pause bars
    d.rectangle([(44, 18), (48, 54)], fill=(200, 200, 200))
    d.rectangle([(52, 18), (56, 54)], fill=(200, 200, 200))
    save(img, "play_pause.png")


def icon_play():
    img, d = new((30, 215, 96))
    d.polygon([(24, 16), (24, 56), (54, 36)], fill=(0, 0, 0))
    save(img, "play.png")


def icon_pause():
    img, d = new((30, 215, 96))
    d.rectangle([(22, 16), (32, 56)], fill=(0, 0, 0))
    d.rectangle([(40, 16), (50, 56)], fill=(0, 0, 0))
    save(img, "pause.png")


def icon_next():
    img, d = new((30, 30, 30))
    d.polygon([(20, 18), (20, 54), (42, 36)], fill=(200, 200, 220))
    d.polygon([(38, 18), (38, 54), (56, 36)], fill=(200, 200, 220))
    save(img, "next.png")


def icon_prev():
    img, d = new((30, 30, 30))
    d.polygon([(52, 18), (52, 54), (30, 36)], fill=(200, 200, 220))
    d.polygon([(34, 18), (34, 54), (16, 36)], fill=(200, 200, 220))
    save(img, "prev.png")


def icon_vol_up():
    img, d = new((30, 30, 40))
    # Speaker
    d.polygon(
        [(14, 28), (14, 44), (24, 44), (34, 54), (34, 18), (24, 28)],
        fill=(180, 180, 200),
    )
    # Sound waves
    for r_off in [8, 16]:
        for angle in range(-40, 41, 4):
            rad = math.radians(angle)
            x = 36 + r_off * math.cos(rad)
            y = 36 + r_off * math.sin(rad - math.pi / 2) + r_off * math.sin(rad)
            x = 36 + r_off * math.cos(math.radians(angle))
            y = 36 - r_off * math.sin(math.radians(90 - angle))
        # Simpler: just draw arcs as dots
    # Simple curved lines for sound
    for offset in [6, 14]:
        pts = []
        for a in range(-35, 36, 5):
            rad = math.radians(a)
            x = 38 + offset * math.cos(rad)
            y = 36 - offset * math.sin(rad)
            pts.append((x, y))
        for j in range(len(pts) - 1):
            d.line([pts[j], pts[j + 1]], fill=(100, 200, 255), width=2)
    # Plus sign
    d.line([(54, 12), (54, 24)], fill=(100, 255, 100), width=3)
    d.line([(48, 18), (60, 18)], fill=(100, 255, 100), width=3)
    save(img, "vol_up.png")


def icon_vol_down():
    img, d = new((30, 30, 40))
    # Speaker
    d.polygon(
        [(14, 28), (14, 44), (24, 44), (34, 54), (34, 18), (24, 28)],
        fill=(180, 180, 200),
    )
    # One sound wave
    pts = []
    for a in range(-35, 36, 5):
        rad = math.radians(a)
        x = 38 + 6 * math.cos(rad)
        y = 36 - 6 * math.sin(rad)
        pts.append((x, y))
    for j in range(len(pts) - 1):
        d.line([pts[j], pts[j + 1]], fill=(100, 200, 255), width=2)
    # Minus sign
    d.line([(48, 18), (60, 18)], fill=(255, 100, 100), width=3)
    save(img, "vol_down.png")


def icon_shuffle():
    img, d = new((30, 30, 30))
    # Crossed arrows
    d.line([(16, 22), (40, 50)], fill=(200, 200, 220), width=3)
    d.line([(16, 50), (40, 22)], fill=(200, 200, 220), width=3)
    # Arrow heads
    d.polygon([(40, 18), (40, 28), (52, 22)], fill=(200, 200, 220))
    d.polygon([(40, 44), (40, 54), (52, 50)], fill=(200, 200, 220))
    save(img, "shuffle.png")


def _draw_repeat_arrows(d, color=(200, 200, 220)):
    """Draw looping arrows shared by repeat icons."""
    # Top arrow (left to right)
    d.line([(16, 24), (52, 24)], fill=color, width=3)
    d.polygon([(48, 18), (58, 24), (48, 30)], fill=color)
    # Bottom arrow (right to left)
    d.line([(20, 46), (56, 46)], fill=color, width=3)
    d.polygon([(24, 40), (14, 46), (24, 52)], fill=color)
    # Connecting curves
    d.arc([(48, 24), (60, 46)], start=270, end=90, fill=color, width=3)
    d.arc([(12, 24), (24, 46)], start=90, end=270, fill=color, width=3)


def icon_repeat():
    img, d = new((30, 30, 30))
    _draw_repeat_arrows(d)
    save(img, "repeat.png")


def icon_repeat_one():
    img, d = new((30, 30, 30))
    _draw_repeat_arrows(d)
    # "1" overlay in center
    try:
        font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    d.text((36, 35), "1", font=font, anchor="mm", fill=(255, 255, 255))
    save(img, "repeat_one.png")


# ── Heating / Kasa / Tapo ───────────────────────────────


def icon_heating():
    img, d = new((50, 15, 10))
    # Flame
    d.ellipse([(22, 24), (50, 58)], fill=(255, 100, 20))
    d.ellipse([(26, 16), (46, 48)], fill=(255, 160, 30))
    d.ellipse([(30, 20), (42, 44)], fill=(255, 220, 60))
    d.ellipse([(33, 28), (39, 40)], fill=(255, 250, 150))
    save(img, "heating.png")


def icon_power_on():
    img, d = new((0, 80, 20))
    # Power symbol
    cx, cy, r = 36, 38, 16
    d.arc(
        [(cx - r, cy - r), (cx + r, cy + r)],
        start=220,
        end=320,
        fill=(255, 255, 255),
        width=4,
    )
    d.line([(cx, cy - r - 2), (cx, cy - 2)], fill=(255, 255, 255), width=4)
    save(img, "power_on.png")


def icon_power_off():
    img, d = new((80, 20, 20))
    # Power symbol
    cx, cy, r = 36, 38, 16
    d.arc(
        [(cx - r, cy - r), (cx + r, cy + r)],
        start=220,
        end=320,
        fill=(200, 200, 200),
        width=4,
    )
    d.line([(cx, cy - r - 2), (cx, cy - 2)], fill=(200, 200, 200), width=4)
    save(img, "power_off.png")


def icon_thermometer():
    img, d = new((20, 20, 40))
    # Thermometer body
    d.rounded_rectangle([(30, 10), (42, 48)], radius=6, fill=(200, 200, 220))
    # Bulb
    d.ellipse([(26, 42), (46, 62)], fill=(200, 200, 220))
    # Mercury
    d.rectangle([(33, 24), (39, 48)], fill=(220, 50, 50))
    d.ellipse([(29, 45), (43, 59)], fill=(220, 50, 50))
    save(img, "thermometer.png")


def icon_fan():
    img, d = new((20, 30, 40))
    cx, cy = 36, 36
    # Fan blades
    for angle_offset in [0, 90, 180, 270]:
        pts = []
        for a in range(0, 80, 2):
            rad = math.radians(a + angle_offset)
            r = 6 + a * 0.25
            pts.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
        if len(pts) > 1:
            for j in range(len(pts) - 1):
                d.line([pts[j], pts[j + 1]], fill=(150, 200, 255), width=3)
    # Center hub
    d.ellipse([(cx - 5, cy - 5), (cx + 5, cy + 5)], fill=(200, 200, 220))
    save(img, "fan.png")


def icon_kasa():
    img, d = new((10, 40, 30))
    # Outer rounded rectangle (plug body)
    d.rounded_rectangle([(14, 16), (58, 52)], radius=8, fill=(60, 180, 120))
    # Two prongs
    d.rounded_rectangle([(24, 24), (30, 38)], radius=2, fill=(255, 255, 255))
    d.rounded_rectangle([(42, 24), (48, 38)], radius=2, fill=(255, 255, 255))
    # Power dot
    d.ellipse([(32, 42), (40, 48)], fill=(255, 255, 255))
    save(img, "kasa.png")


def icon_tapo():
    img, d = new((10, 20, 50))
    # Stylized smart device with wifi waves
    cx, cy = 36, 36
    # Device body
    d.rounded_rectangle([(16, 18), (56, 54)], radius=10, fill=(50, 130, 220))
    # Wifi-like arcs
    for r_off in [8, 15]:
        pts = []
        for a in range(-45, 46, 5):
            rad = math.radians(a)
            x = cx + r_off * math.cos(rad)
            y = cy - 4 - r_off * math.sin(rad)
            pts.append((x, y))
        for j in range(len(pts) - 1):
            d.line([pts[j], pts[j + 1]], fill=(255, 255, 255), width=2)
    # Center dot
    d.ellipse([(cx - 3, cy - 1), (cx + 3, cy + 5)], fill=(255, 255, 255))
    save(img, "tapo.png")


# ── Scenes / Presets ────────────────────────────────────


def icon_scene(name, color, filename):
    img, d = new(tuple(c // 4 for c in color))
    # Gradient-ish circle
    for r in range(24, 0, -1):
        factor = r / 24
        c = tuple(int(v * factor) for v in color)
        d.ellipse([(36 - r, 32 - r), (36 + r, 32 + r)], fill=c)
    save(img, filename)


def icon_playlist(color, filename):
    img, d = new((20, 20, 20))
    # Music note lines
    for y_off in [18, 28, 38, 48]:
        width = 36 if y_off < 48 else 28
        d.line([(18, y_off), (18 + width, y_off)], fill=color, width=2)
    # Note symbol
    d.ellipse([(44, 42), (54, 52)], fill=color)
    d.line([(54, 20), (54, 48)], fill=color, width=2)
    d.line([(54, 20), (62, 24)], fill=color, width=2)
    save(img, filename)


# ── Misc ────────────────────────────────────────────────


def icon_blank():
    img, d = new((0, 0, 0))
    save(img, "blank.png")


def icon_error():
    img, d = new((80, 0, 0))
    # X mark
    d.line([(20, 20), (52, 52)], fill=(255, 255, 255), width=4)
    d.line([(52, 20), (20, 52)], fill=(255, 255, 255), width=4)
    save(img, "error.png")


def icon_refresh():
    img, d = new((30, 50, 60))
    # Circular arrow
    cx, cy, r = 36, 36, 16
    d.arc(
        [(cx - r, cy - r), (cx + r, cy + r)],
        start=30,
        end=330,
        fill=(150, 220, 255),
        width=3,
    )
    # Arrow head
    angle = math.radians(330)
    ax = cx + r * math.cos(angle)
    ay = cy + r * math.sin(angle)
    d.polygon([(ax, ay - 6), (ax + 8, ay), (ax, ay + 6)], fill=(150, 220, 255))
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
