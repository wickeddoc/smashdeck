# Spotify Cover Art Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the current Spotify track's album cover art on Stream Deck key 31, replacing the album-name text label.

**Architecture:** Parse `mpris:artUrl` into the existing `PlayerSnapshot`. Add a small helper on `SpotifyPage` that fetches the URL via stdlib `urllib.request`, decodes it with Pillow, and caches the result keyed on the URL (refetch only when the URL changes). Extend `main.py`'s `set_key_image` to accept an optional `pil_image` source so the page can hand in a PIL image instead of a filename.

**Tech Stack:** Python 3, Pillow (already a dep), stdlib `urllib.request` / `io.BytesIO`. No new pip dependencies.

**Reference spec:** `docs/superpowers/specs/2026-05-11-spotify-cover-art-design.md`

**Testing posture:** No automated tests added (consistent with project posture). Manual smoke at each task: a Python one-liner for `set_key_image` extension; a live deck + Spotify session for the page-level changes.

---

## File map

- **Modify:** `pages/spotify.py` — extract `mpris:artUrl` into `PlayerSnapshot`, add `_art_url`/`_art_image` state and `_fetch_art()` helper, route art through `render(snap)`.
- **Modify:** `main.py` — extend `set_key_image` to accept an optional `pil_image` source.

No other files change.

---

## Task 1: Extend `set_key_image` in `main.py` to accept a PIL image

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Update the typing imports**

In `main.py`, find the existing imports at the top of the file:

```python
import os
import signal
import sys
import threading

import yaml
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
```

Add `from typing import Optional` immediately below `import threading`:

```python
import os
import signal
import sys
import threading
from typing import Optional

import yaml
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
```

- [ ] **Step 2: Replace `set_key_image` with the `pil_image`-aware version**

Find the current `set_key_image` method (around line 137):

```python
    def set_key_image(
        self, key, icon_filename=None, label=None, color=(0, 0, 0), highlight=None
    ):
        """Render an icon + optional text label onto a key.

        highlight: optional RGB tuple to draw a colored indicator bar at the
        top of the key (e.g. green for active state).
        """
        image = PILHelper.create_scaled_key_image(
            self.deck,
            (
                Image.open(os.path.join(ASSETS_PATH, icon_filename))
                if icon_filename
                else Image.new("RGB", self._key_size, color)
            ),
            margins=[0, 0, 20 if label else 0, 0],
        )
        draw = ImageDraw.Draw(image)

        if highlight:
            draw.rectangle([(0, 0), (image.width, 4)], fill=highlight)
        if label:
            try:
                font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 12)
            except OSError:
                font = ImageFont.load_default()
            draw.text(
                (image.width // 2, image.height - 5),
                label,
                font=font,
                anchor="mb",
                fill="white",
            )

        self.deck.set_key_image(key, PILHelper.to_native_key_format(self.deck, image))
```

Replace it with:

```python
    def set_key_image(
        self,
        key,
        icon_filename=None,
        label=None,
        color=(0, 0, 0),
        highlight=None,
        pil_image: Optional[Image.Image] = None,
    ):
        """Render an icon + optional text label onto a key.

        Source precedence: pil_image > icon_filename > blank colour.

        highlight: optional RGB tuple to draw a coloured indicator bar at the
        top of the key (e.g. green for active state).
        """
        if pil_image is not None:
            source = pil_image
        elif icon_filename:
            source = Image.open(os.path.join(ASSETS_PATH, icon_filename))
        else:
            source = Image.new("RGB", self._key_size, color)

        image = PILHelper.create_scaled_key_image(
            self.deck,
            source,
            margins=[0, 0, 20 if label else 0, 0],
        )
        draw = ImageDraw.Draw(image)

        if highlight:
            draw.rectangle([(0, 0), (image.width, 4)], fill=highlight)
        if label:
            try:
                font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 12)
            except OSError:
                font = ImageFont.load_default()
            draw.text(
                (image.width // 2, image.height - 5),
                label,
                font=font,
                anchor="mb",
                fill="white",
            )

        self.deck.set_key_image(key, PILHelper.to_native_key_format(self.deck, image))
```

The differences from the original:
- New keyword-only parameter `pil_image: Optional[Image.Image] = None` at the end.
- The image-source selection moves from an inline ternary into an explicit `if/elif/else` so a third source (the `pil_image`) can be added cleanly.

- [ ] **Step 3: Smoke-test that the module still imports**

```
~/.virtualenvs/smashdeck/bin/python -c "import main; print('imports OK')"
```

Expected: prints `imports OK`. No traceback.

- [ ] **Step 4: Smoke-test that the new parameter is accepted (without a real deck)**

```
~/.virtualenvs/smashdeck/bin/python -c "
import inspect
import main
sig = inspect.signature(main.DeckController.set_key_image)
print(list(sig.parameters.keys()))
"
```

Expected output: `['self', 'key', 'icon_filename', 'label', 'color', 'highlight', 'pil_image']`

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "main: accept optional PIL image source in set_key_image"
```

---

## Task 2: Extract `mpris:artUrl` into `PlayerSnapshot`

**Files:**
- Modify: `pages/spotify.py`

- [ ] **Step 1: Add `art_url` field to `PlayerSnapshot`**

Find the `PlayerSnapshot` dataclass (around line 56):

```python
@dataclass
class PlayerSnapshot:
    status: str = "Stopped"         # "Playing" / "Paused" / "Stopped"
    shuffle: bool = False
    loop: str = "None"              # "None" / "Track" / "Playlist"
    artist: str = ""
    title: str = ""
    album: str = ""
    volume: float = 0.5
```

Add an `art_url` field at the end:

```python
@dataclass
class PlayerSnapshot:
    status: str = "Stopped"         # "Playing" / "Paused" / "Stopped"
    shuffle: bool = False
    loop: str = "None"              # "None" / "Track" / "Playlist"
    artist: str = ""
    title: str = ""
    album: str = ""
    volume: float = 0.5
    art_url: str = ""
```

- [ ] **Step 2: Extract `mpris:artUrl` in `snapshot()`**

In `SpotifyMpris.snapshot()`, find the Metadata extraction block:

```python
            meta = self._unwrap(props.get("Metadata"))
            if isinstance(meta, dict):
                artist_val = self._unwrap(meta.get("xesam:artist"))
                if isinstance(artist_val, list):
                    snap.artist = ", ".join(str(a) for a in artist_val)
                elif isinstance(artist_val, str):
                    snap.artist = artist_val

                title_val = self._unwrap(meta.get("xesam:title"))
                if isinstance(title_val, str):
                    snap.title = title_val

                album_val = self._unwrap(meta.get("xesam:album"))
                if isinstance(album_val, str):
                    snap.album = album_val
```

Append the `mpris:artUrl` extraction inside the same `if isinstance(meta, dict):` block, after the album extraction:

```python
            meta = self._unwrap(props.get("Metadata"))
            if isinstance(meta, dict):
                artist_val = self._unwrap(meta.get("xesam:artist"))
                if isinstance(artist_val, list):
                    snap.artist = ", ".join(str(a) for a in artist_val)
                elif isinstance(artist_val, str):
                    snap.artist = artist_val

                title_val = self._unwrap(meta.get("xesam:title"))
                if isinstance(title_val, str):
                    snap.title = title_val

                album_val = self._unwrap(meta.get("xesam:album"))
                if isinstance(album_val, str):
                    snap.album = album_val

                art_url_val = self._unwrap(meta.get("mpris:artUrl"))
                if isinstance(art_url_val, str):
                    snap.art_url = art_url_val
```

- [ ] **Step 3: Smoke-test the snapshot picks up the URL**

If Spotify is running:

```
~/.virtualenvs/smashdeck/bin/python -c "
from pages.spotify import SpotifyMpris
m = SpotifyMpris()
s = m.snapshot()
print('art_url:', repr(s.art_url))
m.close()
"
```

Expected: prints something like `art_url: 'https://i.scdn.co/image/ab67616d0000b273...'` when a track is playing. Prints `art_url: ''` if Spotify isn't running or no track is loaded — that's correct.

If Spotify isn't running, run only this minimum check:

```
~/.virtualenvs/smashdeck/bin/python -c "
from pages.spotify import PlayerSnapshot
print(PlayerSnapshot())
"
```

Expected: prints a `PlayerSnapshot(...)` whose `art_url=''` is present in the repr.

- [ ] **Step 4: Commit**

```bash
git add pages/spotify.py
git commit -m "spotify: extract mpris:artUrl into PlayerSnapshot"
```

---

## Task 3: Add `_fetch_art` helper and `_art_url` / `_art_image` state on `SpotifyPage`

**Files:**
- Modify: `pages/spotify.py`

- [ ] **Step 1: Add new imports**

Find the top-of-file imports in `pages/spotify.py`. They currently look like:

```python
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from queue import Empty
from typing import Optional

from jeepney import DBusAddress, MatchRule, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.threading import open_dbus_connection, DBusRouter

from pages import BasePage
```

Add `import io`, `import urllib.request`, and `from PIL import Image` so the page can fetch and decode cover art:

```python
from __future__ import annotations

import io
import threading
import traceback
import urllib.request
from dataclasses import dataclass
from queue import Empty
from typing import Optional

from jeepney import DBusAddress, MatchRule, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.threading import open_dbus_connection, DBusRouter
from PIL import Image

from pages import BasePage
```

- [ ] **Step 2: Add state attributes to `SpotifyPage.__init__`**

Find `SpotifyPage.__init__` (around line 207):

```python
class SpotifyPage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        self._mpris: Optional[SpotifyMpris] = None
        self._last_state: Optional[PlayerSnapshot] = None
        self._stop: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._props_cm = None
        self._props_q = None
        self._name_cm = None
        self._name_q = None
```

Add two cover-art attributes immediately below the existing ones:

```python
class SpotifyPage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        self._mpris: Optional[SpotifyMpris] = None
        self._last_state: Optional[PlayerSnapshot] = None
        self._stop: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._props_cm = None
        self._props_q = None
        self._name_cm = None
        self._name_q = None
        self._art_url: str = ""
        self._art_image: Optional[Image.Image] = None
```

- [ ] **Step 3: Add the `_fetch_art` static helper on `SpotifyPage`**

Insert this method on `SpotifyPage` immediately after `__init__` and before `activate`:

```python
    @staticmethod
    def _fetch_art(url: str) -> Optional[Image.Image]:
        """Fetch and decode a cover-art image. Returns None on any failure."""
        if not url:
            return None
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read()
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            traceback.print_exc()
            return None
```

- [ ] **Step 4: Smoke-test the fetch helper**

Pick any public HTTPS image URL (Spotify CDN is the realistic case). For an offline-friendly check, use a small known PNG. Run:

```
~/.virtualenvs/smashdeck/bin/python -c "
from pages.spotify import SpotifyPage
img = SpotifyPage._fetch_art('https://www.python.org/static/img/python-logo.png')
print(type(img).__name__ if img else None, img.size if img else None)
"
```

Expected: prints `Image (760, 240)` (or similar non-zero dimensions). If the host is unreachable, expect a traceback on stderr followed by `None None` — that confirms the broad-except path works.

Also test the empty-URL path:

```
~/.virtualenvs/smashdeck/bin/python -c "
from pages.spotify import SpotifyPage
print(SpotifyPage._fetch_art(''))
"
```

Expected: prints `None`. No traceback (the empty-URL branch returns early).

- [ ] **Step 5: Commit**

```bash
git add pages/spotify.py
git commit -m "spotify: add _fetch_art helper and cover-art state on the page"
```

---

## Task 4: Wire up the URL-change fetch and render the image on key 31

**Files:**
- Modify: `pages/spotify.py`

- [ ] **Step 1: Replace `activate()` to do the initial fetch and update state atomically**

Find the existing `activate` (around line 218):

```python
    def activate(self):
        self._mpris = SpotifyMpris()
        self._stop = threading.Event()
        self._props_cm, self._props_q = self._mpris.subscribe(_props_rule())
        self._name_cm, self._name_q = self._mpris.subscribe(_name_owner_rule())
        self._last_state = self._mpris.snapshot()
        self.render()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
```

Replace with:

```python
    def activate(self):
        self._mpris = SpotifyMpris()
        self._stop = threading.Event()
        self._props_cm, self._props_q = self._mpris.subscribe(_props_rule())
        self._name_cm, self._name_q = self._mpris.subscribe(_name_owner_rule())
        self._last_state = self._mpris.snapshot()
        self._refresh_art(self._last_state)
        self.render()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
```

- [ ] **Step 2: Add the `_refresh_art` helper**

Insert this method on `SpotifyPage` immediately after `_fetch_art` (the static helper added in Task 3):

```python
    def _refresh_art(self, snap: PlayerSnapshot) -> None:
        """Refetch cover art if the snapshot's URL differs from the cached one."""
        if snap.art_url != self._art_url:
            self._art_url = snap.art_url
            self._art_image = self._fetch_art(snap.art_url)
```

- [ ] **Step 3: Call `_refresh_art` from `_listen`**

Find the inside of `_listen`'s update block (around line 286–294):

```python
            if not got_signal:
                continue
            try:
                snap = mpris.snapshot()
                if force or snap != self._last_state:
                    self.render(snap)
            except Exception:
                traceback.print_exc()
```

Add the art refresh before the diff check, so the cache is updated for every signal that actually arrived:

```python
            if not got_signal:
                continue
            try:
                snap = mpris.snapshot()
                self._refresh_art(snap)
                if force or snap != self._last_state:
                    self.render(snap)
            except Exception:
                traceback.print_exc()
```

(Yes, `_refresh_art` runs even when we don't end up rendering — but `_refresh_art` short-circuits when the URL hasn't changed, so this is cheap in the steady state.)

- [ ] **Step 4: Update `render(snap)` to swap key 31 from album text to the cover image**

Find the end of `render(snap)` (the three label keys, around line 320):

```python
        if snap.artist:
            self.ctrl.set_key_image(15, label=snap.artist[:12], color=(30, 215, 96))
        if snap.title:
            self.ctrl.set_key_image(23, label=snap.title[:12], color=(30, 215, 96))
        if snap.album:
            self.ctrl.set_key_image(31, label=snap.album[:12], color=(30, 215, 96))
```

Replace the album-text line (key 31) with a `pil_image` call. Artist (15) and title (23) keep their text labels:

```python
        if snap.artist:
            self.ctrl.set_key_image(15, label=snap.artist[:12], color=(30, 215, 96))
        if snap.title:
            self.ctrl.set_key_image(23, label=snap.title[:12], color=(30, 215, 96))
        self.ctrl.set_key_image(31, pil_image=self._art_image)
```

Note that the `if snap.album:` guard is removed — `set_key_image(31, pil_image=None)` correctly renders a blank key when there is no cover, which is the desired fallback.

- [ ] **Step 5: Update `deactivate()` to clear the cached art**

Find the existing `deactivate` (around line 228) and locate the trailing cleanup lines:

```python
        if self._mpris is not None:
            self._mpris.close()
            self._mpris = None
        self._stop = None
        self._last_state = None
```

Replace with:

```python
        if self._mpris is not None:
            self._mpris.close()
            self._mpris = None
        self._stop = None
        self._last_state = None
        self._art_url = ""
        self._art_image = None
```

This ensures that re-activating the page later starts from a clean slate — the next snapshot's URL will be compared against an empty string and will (correctly) trigger a fresh fetch.

- [ ] **Step 6: Smoke-test (module import)**

```
~/.virtualenvs/smashdeck/bin/python -c "from pages.spotify import SpotifyPage, PlayerSnapshot; s = PlayerSnapshot(art_url='x'); print('ok', s.art_url)"
```

Expected: `ok x`. No traceback.

- [ ] **Step 7: Lint**

```
~/.virtualenvs/smashdeck/bin/ruff check pages/spotify.py
```

Expected: `All checks passed!`

- [ ] **Step 8: Manual smoke on the deck (if available)**

With the Stream Deck XL connected and Spotify playing:

```
~/.virtualenvs/smashdeck/bin/python main.py
```

Navigate to the Spotify page. Verify:

1. Key 31 shows the current track's cover art instead of album text (artist on 15 and title on 23 still show text).
2. Skip to next track — cover updates within ~1 s.
3. Press play/pause — cover stays put (no URL change → no refetch).
4. Quit Spotify (e.g. `pkill spotify`) — key 31 goes blank along with the rest of the neutral state.
5. Re-open Spotify and resume playback — cover reappears.
6. Switch to another page and back to Spotify — cover reloads cleanly.

If Spotify isn't available, skip the deck smoke and report so.

- [ ] **Step 9: Commit**

```bash
git add pages/spotify.py
git commit -m "spotify: render cover art on key 31"
```

---

## Post-implementation checklist

- [ ] `~/.virtualenvs/smashdeck/bin/ruff check .` passes (no new lint errors).
- [ ] No new pip dependencies introduced (`git diff master -- requirements.txt` is empty).
- [ ] No automated test failures (the project has none — nothing to break).
- [ ] If the deck is available: all six manual deck-smoke steps in Task 4 Step 8 pass.
- [ ] No regressions on the Spotify page controls (play/pause, next/prev, shuffle, repeat, volume still work).

Done.
