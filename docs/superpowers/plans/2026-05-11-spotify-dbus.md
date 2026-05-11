# Spotify DBus (MPRIS2) Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `playerctl` in `pages/spotify.py` with a direct DBus client (`jeepney`) speaking MPRIS2 to the Spotify desktop client, driven by signals instead of polling.

**Architecture:** A small page-private `SpotifyMpris` helper owns one `jeepney.io.threading` DBus connection and exposes `snapshot()` (one `Properties.GetAll`) plus a handful of write methods. `SpotifyPage` keeps its current public surface (`activate`, `deactivate`, `render`, `on_key`) and key layout. A single listener thread subscribes to `PropertiesChanged` and `NameOwnerChanged`, drains both filter queues with bounded-timeout `get()`, and re-renders only when the state snapshot actually changed.

**Tech Stack:** Python 3, `jeepney` (pure-Python DBus), `threading.Thread`, existing `streamdeck` + `Pillow` for rendering.

**Reference spec:** `docs/superpowers/specs/2026-05-11-spotify-dbus-design.md`

**Testing posture:** Per the approved spec, no automated test scaffolding is added — the project has none today. Each task includes a manual smoke step the engineer must run before committing.

---

## File map

- **Modify:** `pages/spotify.py` — full rewrite. `SpotifyMpris` helper lives here as a page-private class.
- **Create:** `requirements.txt` — first-time creation; lists pip-installable deps including `jeepney`.
- **Modify:** `CLAUDE.md` — Dependencies section: drop `playerctl`, add `jeepney`.

No changes to: `main.py`, `pages/__init__.py`, `config.yaml`, any other page file.

---

## Task 1: Add jeepney dependency

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Create `requirements.txt`**

Create `requirements.txt` with this content:

```
streamdeck
Pillow
PyYAML
phue
python-kasa
tapo
jeepney
```

- [ ] **Step 2: Install jeepney in the project venv**

The repo has a `.venv` directory. Use it:

Run: `.venv/bin/pip install jeepney`

Expected: `Successfully installed jeepney-<version>` (or "Requirement already satisfied" if pre-existing).

- [ ] **Step 3: Verify the import works**

Run: `.venv/bin/python -c "import jeepney; from jeepney.io.threading import open_dbus_connection; print(jeepney.__version__)"`

Expected: prints a version string (e.g. `0.8.0`), no traceback.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add jeepney for direct DBus access (MPRIS2)"
```

---

## Task 2: Scaffold `SpotifyMpris` with a minimal `snapshot()`

In this task we replace `pages/spotify.py` end-to-end, but only the read side and only the `PlaybackStatus` field. The page still renders correctly because nothing else has been wired up yet — we'll wire the full snapshot in the next task. This keeps each change reviewable.

**Files:**
- Modify: `pages/spotify.py` (full rewrite)

- [ ] **Step 1: Replace `pages/spotify.py`**

Replace the entire file with:

```python
# pages/spotify.py
"""Spotify control page backed by MPRIS2 over DBus (via jeepney).

A small page-private `SpotifyMpris` helper owns one DBus connection and
exposes a single `snapshot()` returning all player state in one round-trip.
This task implements only PlaybackStatus; subsequent tasks expand it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from jeepney import DBusAddress, new_method_call
from jeepney.io.threading import open_dbus_connection

from pages import BasePage

BUTTON_POSITION_VOLUME_UP = 13
BUTTON_POSITION_VOLUME_DOWN = 14

SPOTIFY_BUS = "org.mpris.MediaPlayer2.spotify"
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"

_PROPS = DBusAddress(MPRIS_PATH, bus_name=SPOTIFY_BUS,
                    interface="org.freedesktop.DBus.Properties")


@dataclass
class PlayerSnapshot:
    status: str = "Stopped"         # "Playing" / "Paused" / "Stopped"
    shuffle: bool = False
    loop: str = "None"              # "None" / "Track" / "Playlist"
    artist: str = ""
    title: str = ""
    album: str = ""
    volume: float = 0.5


class SpotifyMpris:
    """Thin adapter over jeepney for Spotify's MPRIS2 interface."""

    def __init__(self):
        self._conn = open_dbus_connection(bus="SESSION")

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # --- read API ---

    def snapshot(self) -> PlayerSnapshot:
        """One round-trip read of all player properties.

        Returns safe defaults if Spotify isn't running.
        """
        try:
            msg = new_method_call(_PROPS, "GetAll", "s", (PLAYER_IFACE,))
            reply = self._conn.send_and_get_reply(msg)
            props = reply.body[0]  # a{sv}: dict[str, (sig, value)]
        except Exception:
            return PlayerSnapshot()

        snap = PlayerSnapshot()
        status = self._unwrap(props.get("PlaybackStatus"))
        if isinstance(status, str):
            snap.status = status
        return snap

    @staticmethod
    def _unwrap(variant):
        """jeepney returns variants as (signature, value) tuples."""
        if variant is None:
            return None
        if isinstance(variant, tuple) and len(variant) == 2:
            return variant[1]
        return variant


class SpotifyPage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        self._mpris: Optional[SpotifyMpris] = None
        self._last_state: Optional[PlayerSnapshot] = None

    def activate(self):
        self._mpris = SpotifyMpris()

    def deactivate(self):
        if self._mpris is not None:
            self._mpris.close()
            self._mpris = None
        self._last_state = None

    def _snap(self) -> PlayerSnapshot:
        if self._mpris is None:
            return PlayerSnapshot()
        return self._mpris.snapshot()

    def render(self):
        self.clear()
        snap = self._snap()
        self._last_state = snap

        playing = snap.status == "Playing"
        player_status = "pause.png" if playing else "play.png"
        self.ctrl.set_key_image(
            8, player_status, highlight=(30, 215, 96) if playing else None
        )
        self.ctrl.set_key_image(9, "prev.png")
        self.ctrl.set_key_image(10, "next.png")
        self.ctrl.set_key_image(11, "shuffle.png")
        self.ctrl.set_key_image(12, "repeat.png")
        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_DOWN, "vol_down.png")
        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_UP, "vol_up.png")

    def on_key(self, key):
        # Wired in Task 4 — placeholder for now.
        return
```

- [ ] **Step 2: Smoke-test the snapshot with Spotify running**

With Spotify open and a track playing or paused, run:

```
.venv/bin/python -c "
from pages.spotify import SpotifyMpris
m = SpotifyMpris()
print(m.snapshot())
m.close()
"
```

Expected: prints a `PlayerSnapshot(status='Playing', ...)` or `'Paused'`. All other fields are still defaults — that's correct for this task.

- [ ] **Step 3: Smoke-test the snapshot with Spotify closed**

Close Spotify completely (`pkill spotify` or quit from the app). Run the same command:

```
.venv/bin/python -c "
from pages.spotify import SpotifyMpris
m = SpotifyMpris()
print(m.snapshot())
m.close()
"
```

Expected: prints `PlayerSnapshot(status='Stopped', shuffle=False, loop='None', artist='', title='', album='', volume=0.5)`. No traceback.

- [ ] **Step 4: Commit**

```bash
git add pages/spotify.py
git commit -m "spotify: scaffold SpotifyMpris with PlaybackStatus snapshot"
```

---

## Task 3: Expand `snapshot()` to all player properties

**Files:**
- Modify: `pages/spotify.py` (replace the `snapshot` method only)

- [ ] **Step 1: Replace `SpotifyMpris.snapshot`**

In `pages/spotify.py`, replace the `snapshot` method body with the full mapping:

```python
    def snapshot(self) -> PlayerSnapshot:
        """One round-trip read of all player properties.

        Returns safe defaults if Spotify isn't running.
        """
        try:
            msg = new_method_call(_PROPS, "GetAll", "s", (PLAYER_IFACE,))
            reply = self._conn.send_and_get_reply(msg)
            props = reply.body[0]
        except Exception:
            return PlayerSnapshot()

        snap = PlayerSnapshot()

        status = self._unwrap(props.get("PlaybackStatus"))
        if isinstance(status, str):
            snap.status = status

        shuffle = self._unwrap(props.get("Shuffle"))
        if isinstance(shuffle, bool):
            snap.shuffle = shuffle

        loop = self._unwrap(props.get("LoopStatus"))
        if isinstance(loop, str):
            snap.loop = loop

        volume = self._unwrap(props.get("Volume"))
        if isinstance(volume, (int, float)):
            snap.volume = float(volume)

        meta = self._unwrap(props.get("Metadata")) or {}
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

        return snap
```

- [ ] **Step 2: Smoke-test full snapshot with Spotify playing**

With Spotify playing a track, run:

```
.venv/bin/python -c "
from pages.spotify import SpotifyMpris
m = SpotifyMpris()
s = m.snapshot()
print(f'status={s.status} shuffle={s.shuffle} loop={s.loop}')
print(f'artist={s.artist!r} title={s.title!r} album={s.album!r}')
print(f'volume={s.volume}')
m.close()
"
```

Expected:
- `status` is `Playing` or `Paused`
- `artist`, `title`, `album` are non-empty strings reflecting the current track
- `shuffle` is True/False matching the Spotify UI
- `loop` is one of `None`/`Track`/`Playlist`
- `volume` is a float between 0 and 1

- [ ] **Step 3: Toggle shuffle in Spotify, re-run snapshot, verify it changed**

In the Spotify app, toggle shuffle. Re-run the command from Step 2. Expected: `shuffle` field flips.

- [ ] **Step 4: Commit**

```bash
git add pages/spotify.py
git commit -m "spotify: expand snapshot() to full MPRIS2 property set"
```

---

## Task 4: Add write methods and wire `on_key`

**Files:**
- Modify: `pages/spotify.py`

- [ ] **Step 1: Add write methods to `SpotifyMpris`**

Insert these methods inside `SpotifyMpris`, just after `snapshot()`:

```python
    # --- write API (silent no-op if Spotify isn't running) ---

    def _player_call(self, member: str):
        addr = DBusAddress(MPRIS_PATH, bus_name=SPOTIFY_BUS,
                           interface=PLAYER_IFACE)
        try:
            self._conn.send_and_get_reply(new_method_call(addr, member))
        except Exception:
            pass

    def _set_prop(self, name: str, signature: str, value):
        try:
            msg = new_method_call(
                _PROPS, "Set", "ssv",
                (PLAYER_IFACE, name, (signature, value)),
            )
            self._conn.send_and_get_reply(msg)
        except Exception:
            pass

    def play_pause(self):
        self._player_call("PlayPause")

    def next(self):
        self._player_call("Next")

    def previous(self):
        self._player_call("Previous")

    def toggle_shuffle(self):
        self._set_prop("Shuffle", "b", not self.snapshot().shuffle)

    def set_loop(self, mode: str):
        if mode in ("None", "Track", "Playlist"):
            self._set_prop("LoopStatus", "s", mode)

    def cycle_loop(self):
        cycle = {"None": "Playlist", "Playlist": "Track", "Track": "None"}
        self.set_loop(cycle.get(self.snapshot().loop, "None"))

    def nudge_volume(self, delta: float):
        current = self.snapshot().volume
        new = max(0.0, min(1.0, current + delta))
        self._set_prop("Volume", "d", new)
```

- [ ] **Step 2: Update `SpotifyPage.render` to reflect shuffle and loop**

Replace the body of `render()` with the full visual logic:

```python
    def render(self):
        self.clear()
        snap = self._snap()
        self._last_state = snap

        playing = snap.status == "Playing"
        player_status = "pause.png" if playing else "play.png"
        self.ctrl.set_key_image(
            8, player_status, highlight=(30, 215, 96) if playing else None
        )
        self.ctrl.set_key_image(9, "prev.png")
        self.ctrl.set_key_image(10, "next.png")
        self.ctrl.set_key_image(
            11, "shuffle.png",
            highlight=(30, 215, 96) if snap.shuffle else None,
        )

        repeat_icon = "repeat_one.png" if snap.loop == "Track" else "repeat.png"
        repeat_highlight = (30, 215, 96) if snap.loop in ("Playlist", "Track") else None
        self.ctrl.set_key_image(12, repeat_icon, highlight=repeat_highlight)

        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_DOWN, "vol_down.png")
        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_UP, "vol_up.png")

        if snap.artist:
            self.ctrl.set_key_image(15, label=snap.artist[:12], color=(30, 215, 96))
        if snap.title:
            self.ctrl.set_key_image(23, label=snap.title[:12], color=(30, 215, 96))
        if snap.album:
            self.ctrl.set_key_image(31, label=snap.album[:12], color=(30, 215, 96))
```

- [ ] **Step 3: Implement `on_key`**

Replace the existing `on_key` stub with:

```python
    def on_key(self, key):
        if self._mpris is None:
            return
        actions = {
            8: self._mpris.play_pause,
            9: self._mpris.previous,
            10: self._mpris.next,
            11: self._mpris.toggle_shuffle,
            12: self._mpris.cycle_loop,
            BUTTON_POSITION_VOLUME_DOWN: lambda: self._mpris.nudge_volume(-0.05),
            BUTTON_POSITION_VOLUME_UP: lambda: self._mpris.nudge_volume(+0.05),
        }
        if key in actions:
            actions[key]()
            self.render()  # immediate UI feedback; listener will also fire
```

- [ ] **Step 4: Smoke-test the page on the Stream Deck**

Run: `.venv/bin/python main.py`

With Spotify playing, navigate to the Spotify page on the deck. Verify:
- Key 8 reflects play/pause state, highlighted green when playing.
- Key 9/10 step prev/next track. Page text updates after the press.
- Key 11 (shuffle) toggles and the green highlight follows the state.
- Key 12 (repeat) cycles through `None → Playlist → Track → None`; icon changes to `repeat_one.png` in Track mode.
- Keys 13/14 (volume down/up) adjust system Spotify volume if the build honors it; otherwise they're harmless no-ops.
- Keys 15/23/31 show artist/title/album truncated to 12 chars.

There is no background update yet — that's Task 5. The page is correct on entry and after each key press; external changes (e.g. Spotify advancing tracks on its own) won't update the UI until the next key press.

- [ ] **Step 5: Commit**

```bash
git add pages/spotify.py
git commit -m "spotify: wire on_key + render() through SpotifyMpris"
```

---

## Task 5: Signal-driven background listener

**Files:**
- Modify: `pages/spotify.py`

- [ ] **Step 1: Add imports and match rules at module top**

Add to the top of `pages/spotify.py`, after the existing `jeepney` imports:

```python
import threading
import traceback
from queue import Empty

from jeepney import MatchRule
from jeepney.bus_messages import message_bus
```

Then add module-level match rule builders below the `_PROPS` constant:

```python
def _props_rule() -> MatchRule:
    return MatchRule(
        type="signal",
        sender=SPOTIFY_BUS,
        interface="org.freedesktop.DBus.Properties",
        member="PropertiesChanged",
        path=MPRIS_PATH,
    )


def _name_owner_rule() -> MatchRule:
    rule = MatchRule(
        type="signal",
        sender="org.freedesktop.DBus",
        interface="org.freedesktop.DBus",
        member="NameOwnerChanged",
    )
    rule.add_arg_condition(0, SPOTIFY_BUS)
    return rule
```

- [ ] **Step 2: Extend `SpotifyMpris` with subscription helpers**

Add these methods inside `SpotifyMpris`:

```python
    def subscribe(self, rule: MatchRule):
        """Register a match rule with the bus and open a filter queue.

        Returns (context_manager, queue). The caller must keep the context
        manager open until done listening.
        """
        cm = self._conn.filter(rule)
        q = cm.__enter__()
        try:
            self._conn.send_and_get_reply(message_bus.AddMatch(rule))
        except Exception:
            cm.__exit__(None, None, None)
            raise
        return cm, q
```

- [ ] **Step 3: Rewrite `activate` and `deactivate` to manage the listener thread**

Replace the existing `activate` and `deactivate` methods with:

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

    def deactivate(self):
        self._stop.set()
        # Listener wakes within the 0.5s queue.get timeout and exits because
        # _stop is set. Then we tear down the filters and close the conn.
        if hasattr(self, "_thread") and self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if hasattr(self, "_props_cm"):
            try:
                self._props_cm.__exit__(None, None, None)
            except Exception:
                pass
        if hasattr(self, "_name_cm"):
            try:
                self._name_cm.__exit__(None, None, None)
            except Exception:
                pass
        if self._mpris is not None:
            self._mpris.close()
            self._mpris = None
        self._last_state = None
```

- [ ] **Step 4: Add the listener loop**

Add this method to `SpotifyPage`:

```python
    def _listen(self):
        """Block on filter queues; re-render when state actually changes."""
        while not self._stop.is_set():
            got_signal = False
            force = False
            try:
                self._props_q.get(timeout=0.5)
                got_signal = True
                # Drain anything that came in while we were rendering.
                while True:
                    try:
                        self._props_q.get_nowait()
                    except Empty:
                        break
            except Empty:
                pass
            try:
                while True:
                    self._name_q.get_nowait()
                    got_signal = True
                    force = True
            except Empty:
                pass

            if not got_signal or self._mpris is None:
                continue
            try:
                snap = self._mpris.snapshot()
                if force or snap != self._last_state:
                    self._last_state = snap
                    self.render()
            except Exception:
                traceback.print_exc()
```

- [ ] **Step 5: Smoke-test signal-driven updates**

Run: `.venv/bin/python main.py`

Navigate to the Spotify page. With Spotify playing:

1. **External play/pause:** Press space in the Spotify app (not on the deck). The deck's key 8 should flip play↔pause within ~1 second. PASS criterion.
2. **External track skip:** Click "next" in the Spotify app. The deck's artist/title/album labels should update within ~1 second.
3. **Quit Spotify entirely** (e.g. `pkill spotify`). Within ~1 second the deck should re-render to the neutral state: key 8 shows `play.png` (no highlight), shuffle/repeat un-highlighted, artist/title/album cleared.
4. **Re-open Spotify and start playback.** Within ~1 second the deck should reflect the new state.
5. **Navigate away from the Spotify page and back several times.** No traceback, no leaked threads. Verify with `ps -T -p $(pgrep -f "python main.py")` that thread count is stable across page switches.

- [ ] **Step 6: Commit**

```bash
git add pages/spotify.py
git commit -m "spotify: replace polling with signal-driven listener"
```

---

## Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Dependencies section**

In `CLAUDE.md`, find this block under `## Dependencies`:

```
- `playerctl` — System binary required for Spotify control (not a pip package)
```

Replace it with:

```
- `jeepney` — Pure-Python DBus client used by `pages/spotify.py` to talk to Spotify over MPRIS2
```

- [ ] **Step 2: Update the Project Overview line that mentions playerctl**

Find this line near the top of `CLAUDE.md`:

```
SmashDeck is a Python application that drives an Elgato Stream Deck XL as a home automation controller. Implemented integrations: Spotify (via `playerctl`), Philips Hue (via `phue`), TP-Link Kasa (via `python-kasa`), and Tapo (via the `tapo` SDK). DENON Heos is planned but not implemented.
```

Replace `via `playerctl`` with `via DBus/MPRIS2`:

```
SmashDeck is a Python application that drives an Elgato Stream Deck XL as a home automation controller. Implemented integrations: Spotify (via DBus/MPRIS2), Philips Hue (via `phue`), TP-Link Kasa (via `python-kasa`), and Tapo (via the `tapo` SDK). DENON Heos is planned but not implemented.
```

- [ ] **Step 3: Verify no other mentions of playerctl remain**

Run: `grep -rn "playerctl" .`

Expected: no matches (except possibly in committed `docs/superpowers/specs/2026-05-11-spotify-dbus-design.md`, where it appears as part of the mapping table — that's fine and historical).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for DBus Spotify backend"
```

---

## Post-implementation checklist

- [ ] `ruff check .` passes (no new lint errors introduced)
- [ ] All six manual smoke tests from Task 5 pass
- [ ] No traceback when starting `main.py` with Spotify either running or not running
- [ ] No traceback when navigating to/from the Spotify page repeatedly

Done.
