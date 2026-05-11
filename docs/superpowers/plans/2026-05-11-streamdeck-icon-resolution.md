# Stream Deck Icon Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate Stream Deck icons natively at 144×144 (XL native resolution), keep behavior working on other models by leveraging the library's built-in scaler, and log the detected deck model at startup.

**Architecture:** `generate_icons.py` gains an `ICON_SIZE` env-controlled output size (default 144) and a tiny `_s()` helper that scales 72-based design coordinates to the output size at draw time. `main.py` reads the deck's identity and native key size at startup, caches the native size on the controller, and uses it for the blank-source fallback in `set_key_image`.

**Tech Stack:** Python 3, Pillow (PIL), `streamdeck` (python-elgato-streamdeck) — all already present.

**Reference spec:** `docs/superpowers/specs/2026-05-11-streamdeck-icon-resolution-design.md`

**Testing posture:** No automated tests added (consistent with the project's existing posture). Manual verification per task using the connected XL and PIL/file commands to confirm image dimensions.

---

## File map

- **Modify:** `generate_icons.py` — add `ICON_SIZE` env var support, add `_s()` helper, wrap every pixel-coordinate / line-width / font-size literal in icon-drawing functions with `_s(...)`. Color values, angles, and loop counters stay raw.
- **Modify:** `main.py` — read deck identity at startup, cache native key size, drop the hardcoded `72` from `set_key_image`'s blank-source fallback.
- **Modify:** `CLAUDE.md` — "Regenerating Icons" section: bump documented size to 144 and mention the `ICON_SIZE` override.
- **Regenerate (binary output):** all PNGs under `icons/`.

No changes to: `pages/`, `device_info.py`, `config.yaml`, `requirements.txt`.

---

## Task 1: Add deck identification and cache native key size in `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Update `DeckController.__init__` to declare the new attribute**

In `main.py`, find the `__init__` method:

```python
    def __init__(self, config_path="config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
            print(self.config)
        self.deck = None
        self.current_page = None
        self.pages = {}
        self.page_history = []
```

Add `self._key_size = (72, 72)` (a safe default) after `self.deck = None`:

```python
    def __init__(self, config_path="config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
            print(self.config)
        self.deck = None
        self._key_size = (72, 72)
        self.current_page = None
        self.pages = {}
        self.page_history = []
```

- [ ] **Step 2: Add the identification + cache block in `start()`**

In `start()`, find this block:

```python
        self.deck = devices[0]
        self.deck.open()
```

Insert the identification logic immediately after `self.deck.open()`:

```python
        self.deck = devices[0]
        self.deck.open()

        deck_type = self.deck.deck_type()
        self._key_size = self.deck.key_image_format()["size"]
        known = ("XL", "Mk.2", "Original", "Mini", "Plus")
        is_known = any(k.lower() in deck_type.lower() for k in known)
        if is_known:
            print(
                f"Stream Deck: {deck_type} "
                f"(key images: {self._key_size[0]}x{self._key_size[1]})"
            )
        else:
            print(
                f"Warning: untested Stream Deck model '{deck_type}'; "
                f"proceeding anyway. (key images: "
                f"{self._key_size[0]}x{self._key_size[1]})"
            )
```

- [ ] **Step 3: Manual smoke test**

With your Stream Deck XL connected (and no Spotify required), run:

```
~/.virtualenvs/smashdeck/bin/python main.py
```

Expected: very soon after the config prints, you see a line like:

```
Stream Deck: Stream Deck XL (key images: 144x144)
```

Then press Ctrl+C to exit. If you see the warning line instead (untested model), report the actual `deck.deck_type()` string back — the whitelist may need extending.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "main: log Stream Deck model + native key size at startup"
```

---

## Task 2: Drop hardcoded `72` from the blank-source fallback

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Replace the hardcoded size**

In `main.py`, find `set_key_image` and the blank-source line:

```python
        image = PILHelper.create_scaled_key_image(
            self.deck,
            (
                Image.open(os.path.join(ASSETS_PATH, icon_filename))
                if icon_filename
                else Image.new("RGB", (72, 72), color)
            ),
            margins=[0, 0, 20 if label else 0, 0],
        )
```

Change `Image.new("RGB", (72, 72), color)` to `Image.new("RGB", self._key_size, color)`:

```python
        image = PILHelper.create_scaled_key_image(
            self.deck,
            (
                Image.open(os.path.join(ASSETS_PATH, icon_filename))
                if icon_filename
                else Image.new("RGB", self._key_size, color)
            ),
            margins=[0, 0, 20 if label else 0, 0],
        )
```

- [ ] **Step 2: Manual smoke test**

Run:

```
~/.virtualenvs/smashdeck/bin/python main.py
```

Expected: the deck powers up, the home page renders, blank keys are still black. Press Ctrl+C to exit. No traceback.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "main: use deck-native size for blank-source image"
```

---

## Task 3: Add `ICON_SIZE` env support and `_s()` helper to `generate_icons.py`

**Files:**
- Modify: `generate_icons.py`

- [ ] **Step 1: Add `os` import is already there; add `_s()` and rework `SIZE`**

In `generate_icons.py`, find the top:

```python
#!/usr/bin/env python3
"""Generate 72x72 PNG icons for the Stream Deck home automation project."""

from PIL import Image, ImageDraw, ImageFont
import math
import os

SIZE = 72
OUT = "icons"
os.makedirs(OUT, exist_ok=True)
```

Replace it with:

```python
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
```

- [ ] **Step 2: Update the final print line**

Find the bottom of the file, the line that says:

```python
    print("Generating Stream Deck icons (72×72)...\n")
```

Replace with:

```python
    print(f"Generating Stream Deck icons ({SIZE}x{SIZE})...\n")
```

- [ ] **Step 3: Run the script to verify the helper works at default size**

```
~/.virtualenvs/smashdeck/bin/python generate_icons.py
```

Expected: prints `Generating Stream Deck icons (144x144)...`. Icons are generated (still at 72-based proportions inside a 144 canvas — they'll appear in the top-left quadrant of each 144×144 PNG until Task 4 wraps the coords). This is intentional and temporary.

Verify one file size: `file icons/play.png` should report `144 x 144`.

- [ ] **Step 4: Commit**

```bash
git add generate_icons.py
git commit -m "icons: parameterize generator output size via ICON_SIZE (default 144)"
```

---

## Task 4: Wrap every pixel coordinate / size with `_s(...)` in all icon functions

This is the bulk of the change. The rules are:

**Wrap with `_s(...)`:**
- Every numeric x/y coordinate that appears inside Pillow drawing calls
  (`polygon`, `ellipse`, `rectangle`, `rounded_rectangle`, `line`, `arc`,
  `text`, `chord`, `pieslice`).
- Every `width=N` argument to a drawing call.
- Every `ImageFont.truetype(..., size)` size argument.
- Every numeric offset/radius/length used as a pixel measurement inside
  expressions (e.g. `r = 6 + a * 0.25`, `cx + 18 * math.cos(...)`,
  `(r + 2 + ray_len)`, `int(8 + level * 12)`, etc.).
- Numeric `radius=N` arguments to `rounded_rectangle`.

**Do NOT wrap:**
- RGB tuples (color values): `(30, 215, 96)`, `(255, 255, 255)`, `(0, 0, 0)`.
- Angles in degrees: `start=220`, `end=320`, `i * 45`, `math.radians(angle)`.
- `range(...)` iteration counts (e.g. `range(8)` for eight gear teeth).
- Probability/level multipliers (e.g. `level` in `icon_brightness`).
- The `factor` variable inside `icon_scene`'s gradient loop (it's a 0–1
  ratio, not a pixel value).

**Files:**
- Modify: `generate_icons.py`

- [ ] **Step 1: Update each icon function**

Work function by function. Below are the exact wrapped bodies. Replace each function's body (everything between `def NAME(...):` and the next blank line / next `def`).

Reference for what counts as a pixel value: any number that contributes to a coordinate, length, width, or font size on the canvas.

**`icon_back`:**

```python
def icon_back():
    img, d = new((40, 40, 50))
    pts = [(_s(48), _s(18)), (_s(24), _s(36)), (_s(48), _s(54))]
    d.polygon(pts, fill=(200, 200, 220))
    d.line([(_s(24), _s(36)), (_s(54), _s(36))], fill=(200, 200, 220), width=_s(4))
    save(img, "back.png")
```

**`icon_home`:**

```python
def icon_home():
    img, d = new((30, 60, 90))
    d.polygon([(_s(36), _s(14)), (_s(14), _s(34)), (_s(58), _s(34))], fill=(255, 255, 255))
    d.rectangle([(_s(20), _s(34)), (_s(52), _s(56))], fill=(255, 255, 255))
    d.rectangle([(_s(31), _s(42)), (_s(41), _s(56))], fill=(30, 60, 90))
    save(img, "home.png")
```

**`icon_settings`:**

```python
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
```

**`icon_hue_logo`:**

```python
def icon_hue_logo():
    img, d = new((10, 10, 30))
    d.ellipse([(_s(16), _s(10)), (_s(56), _s(50))], fill=(80, 40, 120))
    d.ellipse([(_s(20), _s(14)), (_s(52), _s(46))], fill=(120, 60, 180))
    d.ellipse([(_s(26), _s(18)), (_s(46), _s(42))], fill=(255, 200, 50))
    d.rectangle([(_s(30), _s(42)), (_s(42), _s(52))], fill=(180, 180, 180))
    d.rectangle([(_s(32), _s(52)), (_s(40), _s(56))], fill=(150, 150, 150))
    save(img, "hue.png")
```

**`icon_light_on`:**

```python
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
```

**`icon_light_off`:**

```python
def icon_light_off():
    img, d = new((10, 10, 10))
    d.ellipse([(_s(20), _s(12)), (_s(52), _s(44))], fill=(60, 60, 70))
    d.rectangle([(_s(28), _s(44)), (_s(44), _s(54))], fill=(100, 100, 100))
    d.rectangle([(_s(30), _s(54)), (_s(42), _s(58))], fill=(80, 80, 80))
    save(img, "light_off.png")
```

**`icon_brightness`:**

```python
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
```

**`icon_spotify`:**

```python
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
```

**`icon_play_pause`:**

```python
def icon_play_pause():
    img, d = new((30, 30, 30))
    d.polygon([(_s(22), _s(18)), (_s(22), _s(54)), (_s(40), _s(36))], fill=(30, 215, 96))
    d.rectangle([(_s(44), _s(18)), (_s(48), _s(54))], fill=(200, 200, 200))
    d.rectangle([(_s(52), _s(18)), (_s(56), _s(54))], fill=(200, 200, 200))
    save(img, "play_pause.png")
```

**`icon_play`:**

```python
def icon_play():
    img, d = new((30, 215, 96))
    d.polygon([(_s(24), _s(16)), (_s(24), _s(56)), (_s(54), _s(36))], fill=(0, 0, 0))
    save(img, "play.png")
```

**`icon_pause`:**

```python
def icon_pause():
    img, d = new((30, 215, 96))
    d.rectangle([(_s(22), _s(16)), (_s(32), _s(56))], fill=(0, 0, 0))
    d.rectangle([(_s(40), _s(16)), (_s(50), _s(56))], fill=(0, 0, 0))
    save(img, "pause.png")
```

**`icon_next`:**

```python
def icon_next():
    img, d = new((30, 30, 30))
    d.polygon([(_s(20), _s(18)), (_s(20), _s(54)), (_s(42), _s(36))], fill=(200, 200, 220))
    d.polygon([(_s(38), _s(18)), (_s(38), _s(54)), (_s(56), _s(36))], fill=(200, 200, 220))
    save(img, "next.png")
```

**`icon_prev`:**

```python
def icon_prev():
    img, d = new((30, 30, 30))
    d.polygon([(_s(52), _s(18)), (_s(52), _s(54)), (_s(30), _s(36))], fill=(200, 200, 220))
    d.polygon([(_s(34), _s(18)), (_s(34), _s(54)), (_s(16), _s(36))], fill=(200, 200, 220))
    save(img, "prev.png")
```

**`icon_vol_up`:**

```python
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
```

Note: the existing `icon_vol_up` had a couple of dead-code loops over `r_off` that did nothing visible (the inner block overwrote `x` and `y` then fell through without drawing). Drop those during the wrap — they're not behavior, they're dead code. The wrapped function above already omits them.

**`icon_vol_down`:**

```python
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
```

**`icon_shuffle`:**

```python
def icon_shuffle():
    img, d = new((30, 30, 30))
    d.line([(_s(16), _s(22)), (_s(40), _s(50))], fill=(200, 200, 220), width=_s(3))
    d.line([(_s(16), _s(50)), (_s(40), _s(22))], fill=(200, 200, 220), width=_s(3))
    d.polygon([(_s(40), _s(18)), (_s(40), _s(28)), (_s(52), _s(22))], fill=(200, 200, 220))
    d.polygon([(_s(40), _s(44)), (_s(40), _s(54)), (_s(52), _s(50))], fill=(200, 200, 220))
    save(img, "shuffle.png")
```

**`_draw_repeat_arrows`:**

```python
def _draw_repeat_arrows(d, color=(200, 200, 220)):
    """Draw looping arrows shared by repeat icons."""
    d.line([(_s(16), _s(24)), (_s(52), _s(24))], fill=color, width=_s(3))
    d.polygon([(_s(48), _s(18)), (_s(58), _s(24)), (_s(48), _s(30))], fill=color)
    d.line([(_s(20), _s(46)), (_s(56), _s(46))], fill=color, width=_s(3))
    d.polygon([(_s(24), _s(40)), (_s(14), _s(46)), (_s(24), _s(52))], fill=color)
    d.arc([(_s(48), _s(24)), (_s(60), _s(46))], start=270, end=90, fill=color, width=_s(3))
    d.arc([(_s(12), _s(24)), (_s(24), _s(46))], start=90, end=270, fill=color, width=_s(3))
```

**`icon_repeat`:**

```python
def icon_repeat():
    img, d = new((30, 30, 30))
    _draw_repeat_arrows(d)
    save(img, "repeat.png")
```

**`icon_repeat_one`:**

```python
def icon_repeat_one():
    img, d = new((30, 30, 30))
    _draw_repeat_arrows(d)
    try:
        font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", _s(18))
    except OSError:
        font = ImageFont.load_default()
    d.text((_s(36), _s(35)), "1", font=font, anchor="mm", fill=(255, 255, 255))
    save(img, "repeat_one.png")
```

**`icon_heating`:**

```python
def icon_heating():
    img, d = new((50, 15, 10))
    d.ellipse([(_s(22), _s(24)), (_s(50), _s(58))], fill=(255, 100, 20))
    d.ellipse([(_s(26), _s(16)), (_s(46), _s(48))], fill=(255, 160, 30))
    d.ellipse([(_s(30), _s(20)), (_s(42), _s(44))], fill=(255, 220, 60))
    d.ellipse([(_s(33), _s(28)), (_s(39), _s(40))], fill=(255, 250, 150))
    save(img, "heating.png")
```

**`icon_power_on`:**

```python
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
```

**`icon_power_off`:**

```python
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
```

**`icon_thermometer`:**

```python
def icon_thermometer():
    img, d = new((20, 20, 40))
    d.rounded_rectangle([(_s(30), _s(10)), (_s(42), _s(48))], radius=_s(6), fill=(200, 200, 220))
    d.ellipse([(_s(26), _s(42)), (_s(46), _s(62))], fill=(200, 200, 220))
    d.rectangle([(_s(33), _s(24)), (_s(39), _s(48))], fill=(220, 50, 50))
    d.ellipse([(_s(29), _s(45)), (_s(43), _s(59))], fill=(220, 50, 50))
    save(img, "thermometer.png")
```

**`icon_fan`:**

```python
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
```

**`icon_kasa`:**

```python
def icon_kasa():
    img, d = new((10, 40, 30))
    d.rounded_rectangle([(_s(14), _s(16)), (_s(58), _s(52))], radius=_s(8), fill=(60, 180, 120))
    d.rounded_rectangle([(_s(24), _s(24)), (_s(30), _s(38))], radius=_s(2), fill=(255, 255, 255))
    d.rounded_rectangle([(_s(42), _s(24)), (_s(48), _s(38))], radius=_s(2), fill=(255, 255, 255))
    d.ellipse([(_s(32), _s(42)), (_s(40), _s(48))], fill=(255, 255, 255))
    save(img, "kasa.png")
```

**`icon_tapo`:**

```python
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
```

**`icon_scene`:**

```python
def icon_scene(name, color, filename):
    img, d = new(tuple(c // 4 for c in color))
    for r in range(24, 0, -1):
        factor = r / 24
        c = tuple(int(v * factor) for v in color)
        d.ellipse([(_s(36 - r), _s(32 - r)), (_s(36 + r), _s(32 + r))], fill=c)
    save(img, filename)
```

**`icon_playlist`:**

```python
def icon_playlist(color, filename):
    img, d = new((20, 20, 20))
    for y_off in [18, 28, 38, 48]:
        width = 36 if y_off < 48 else 28
        d.line([(_s(18), _s(y_off)), (_s(18 + width), _s(y_off))], fill=color, width=_s(2))
    d.ellipse([(_s(44), _s(42)), (_s(54), _s(52))], fill=color)
    d.line([(_s(54), _s(20)), (_s(54), _s(48))], fill=color, width=_s(2))
    d.line([(_s(54), _s(20)), (_s(62), _s(24))], fill=color, width=_s(2))
    save(img, filename)
```

**`icon_blank`:** (no coords; leave as-is — `new(...)` handles `SIZE`).

```python
def icon_blank():
    img, d = new((0, 0, 0))
    save(img, "blank.png")
```

**`icon_error`:**

```python
def icon_error():
    img, d = new((80, 0, 0))
    d.line([(_s(20), _s(20)), (_s(52), _s(52))], fill=(255, 255, 255), width=_s(4))
    d.line([(_s(52), _s(20)), (_s(20), _s(52))], fill=(255, 255, 255), width=_s(4))
    save(img, "error.png")
```

**`icon_refresh`:**

```python
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
```

- [ ] **Step 2: Lint check**

```
~/.virtualenvs/smashdeck/bin/ruff check generate_icons.py
```

Expected: `All checks passed!` (one pre-existing concern: `name` parameter of `icon_scene` is unused — that's pre-existing, not caused by this task, leave alone).

- [ ] **Step 3: Smoke test — generate icons at default (144)**

```
~/.virtualenvs/smashdeck/bin/python generate_icons.py
```

Expected output starts with `Generating Stream Deck icons (144x144)...` and lists every icon. No tracebacks.

Verify one icon's dimensions:

```
file icons/play.png
```

Expected: `... PNG image data, 144 x 144, ...`

Pick one geometrically simple icon and one detailed icon and eyeball them — open `icons/play.png` and `icons/spotify.png`. They should look like the same icons as before, just at higher resolution. No content stuck in the top-left quadrant.

- [ ] **Step 4: Smoke test — generate at override size 72**

```
ICON_SIZE=72 ~/.virtualenvs/smashdeck/bin/python generate_icons.py
```

Expected: `Generating Stream Deck icons (72x72)...`. `file icons/play.png` reports `72 x 72`. This restores the project to a state where the previously-checked-in 72×72 icons are reproduced — confirms `_s()` rounding is correct.

Then restore the 144×144 set:

```
~/.virtualenvs/smashdeck/bin/python generate_icons.py
```

- [ ] **Step 5: Commit the generator + regenerated PNGs together**

```bash
git add generate_icons.py icons/
git commit -m "icons: regenerate at native 144x144 (XL resolution)"
```

(Both the code and the binary PNGs are committed in the same commit — the PNGs are the output of the code and travel together.)

---

## Task 5: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Regenerating Icons section**

In `CLAUDE.md`, find this section:

```markdown
## Regenerating Icons

Icons are 72x72 PNGs generated with Pillow. The generator script outputs to a hardcoded path — update `OUT` in the script before running:

```bash
python icons/generate_icons.py
```
```

Replace it with:

```markdown
## Regenerating Icons

Icons are 144×144 PNGs (Stream Deck XL native resolution) generated with
Pillow. The Stream Deck library downscales them automatically at render time
for smaller models (Original / Mini / Mk.2). Output directory is `icons/`.

```bash
python generate_icons.py                  # default: 144×144
ICON_SIZE=72 python generate_icons.py     # for Original / Mini, if you want
                                          # a pre-sized set on disk
```
```

Note: the original block also had a wrong path (`python icons/generate_icons.py`). The script actually lives at the repo root (`generate_icons.py`). The replacement fixes that.

- [ ] **Step 2: Verify CLAUDE.md mentions the right resolution**

```
grep -n "144" CLAUDE.md
```

Expected: at least one match showing the new line.

```
grep -n "72x72\|72×72" CLAUDE.md
```

Expected: zero matches (the only 72 reference left should be the `ICON_SIZE=72` example, not `72×72`).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for 144x144 icon resolution"
```

---

## Post-implementation checklist

- [ ] `~/.virtualenvs/smashdeck/bin/ruff check .` passes (no new lint errors).
- [ ] `~/.virtualenvs/smashdeck/bin/python main.py` prints the deck-identification line on startup.
- [ ] `file icons/play.png` reports `144 x 144`.
- [ ] Visual check on the deck: icons look sharper than they did pre-change.
- [ ] No regressions on the Spotify page (already-working signal listener still functions).

Done.
