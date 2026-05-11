# Spotify page: DBus (MPRIS2) backend

**Date:** 2026-05-11
**Status:** Approved design, awaiting implementation plan
**Scope:** Replace `playerctl` subprocess backend in `pages/spotify.py` with a
direct DBus client speaking MPRIS2 to the Spotify desktop client.

## Goals

- Remove the runtime dependency on the `playerctl` system binary.
- Talk directly to Spotify over DBus / MPRIS2 from Python.
- Switch from 2-second polling to signal-driven UI updates.
- Preserve the existing Stream Deck key layout, behavior, and visuals exactly.

## Non-goals

- Changing the Stream Deck UI for the Spotify page (keys, icons, colors, labels).
- Replacing playerctl usage anywhere else (none exists today).
- Adding new Spotify features (queue, playlists, devices, etc.).
- Building a generic MPRIS client; this only targets Spotify.

## Design decisions (resolved during brainstorming)

1. **DBus library:** `jeepney`. Pure-Python, no system deps, no GLib mainloop
   required, fits cleanly with the existing threaded model.
2. **Update model:** Signal-driven. The page subscribes to MPRIS
   `PropertiesChanged` and DBus `NameOwnerChanged`; it does not poll.
3. **Volume control:** Continue to drive MPRIS `Volume` property on keys 13/14.
   Spotify's Linux client may ignore writes on some builds; in that case the
   keys become no-ops, which is acceptable.

## Architecture

`pages/spotify.py` is rewritten around a small, page-private helper class
`SpotifyMpris`. The page class `SpotifyPage` keeps the same public surface
(`render`, `on_key`, `activate`, `deactivate`) and identical key assignments.

```
SpotifyPage  ──owns──▶  SpotifyMpris  ──speaks──▶  org.mpris.MediaPlayer2.spotify
     │                       │                            (Spotify desktop)
     │                       └─ jeepney blocking conn
     │                          + listener thread
     └─ Stream Deck rendering (unchanged)
```

### `SpotifyMpris` (helper, same file)

A thin adapter over jeepney. Owns one blocking DBus connection
(`jeepney.io.threading.open_dbus_connection()`).

Targets:
- Bus name: `org.mpris.MediaPlayer2.spotify`
- Object path: `/org/mpris/MediaPlayer2`
- Interfaces:
  - `org.mpris.MediaPlayer2.Player` — methods + properties
  - `org.freedesktop.DBus.Properties` — `Get`, `GetAll`, `Set`, `PropertiesChanged`
  - `org.freedesktop.DBus` — `AddMatch`, `NameOwnerChanged`

Read API (all return safe defaults if Spotify isn't running):
- `snapshot() -> dict` — single `Properties.GetAll` on the Player interface;
  returns `{status, shuffle, loop, artist, title, album, volume}`.

`render()` calls `snapshot()` once at the top of the method and reads each
field from the returned dict. This replaces today's six separate `playerctl`
invocations with one DBus round-trip per render.

Write API (silent no-op if Spotify isn't running):
- `play_pause()` — `Player.PlayPause`
- `next()` / `previous()` — `Player.Next` / `Player.Previous`
- `set_shuffle(bool)` — `Properties.Set Shuffle`
- `toggle_shuffle()` — convenience over the above
- `set_loop(str)` — `Properties.Set LoopStatus` with `"None"|"Track"|"Playlist"`
- `set_volume(float)` — `Properties.Set Volume`, value clamped to [0, 1]
- `nudge_volume(delta: float)` — read current, clamp `current + delta`, set

### `SpotifyPage`

Lifecycle:
- `activate()` — opens the `SpotifyMpris` connection, takes an initial
  snapshot, calls `render()`, then starts a daemon listener thread.
- `deactivate()` — signals the thread to stop, closes the DBus connection
  (which unblocks `receive()` in the listener), joins with a short timeout,
  drops the helper reference.

Listener thread:
1. On startup, sends two `AddMatch` calls:
   - `type='signal',sender='org.mpris.MediaPlayer2.spotify',
      interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',
      path='/org/mpris/MediaPlayer2'`
   - `type='signal',sender='org.freedesktop.DBus',
      interface='org.freedesktop.DBus',member='NameOwnerChanged',
      arg0='org.mpris.MediaPlayer2.spotify'`
2. Loops on `conn.receive()`:
   - On `PropertiesChanged`: invalidate snapshot cache, re-snapshot, diff
     against `_last_state`, call `self.render()` if changed.
   - On `NameOwnerChanged`: reset `_last_state`, re-snapshot, render
     (handles both Spotify start and quit).
   - On connection close: exit cleanly.

`on_key()` keeps the same dispatch table but calls `SpotifyMpris` methods
instead of `_ctl(...)`. After each action it re-snapshots and renders so the
UI reflects the change immediately, rather than waiting for the round-trip
signal.

## Data flow / MPRIS mapping

| Today (`playerctl`)                        | Replacement                                                              |
| ------------------------------------------ | ------------------------------------------------------------------------ |
| `playerctl status`                         | Property `PlaybackStatus` → `"Playing"` / `"Paused"` / `"Stopped"`       |
| `playerctl shuffle` → `"On"` / `"Off"`     | Property `Shuffle` → `bool`; adapter normalizes to the same strings if needed |
| `playerctl loop`                           | Property `LoopStatus` → `"None"` / `"Track"` / `"Playlist"`              |
| `playerctl metadata --format {{artist}}`   | `Metadata["xesam:artist"]` → `list[str]`, joined with `", "`             |
| `playerctl metadata --format {{title}}`    | `Metadata["xesam:title"]` → `str`                                        |
| `playerctl metadata --format {{album}}`    | `Metadata["xesam:album"]` → `str`                                        |
| `playerctl volume`                         | Property `Volume` → `float` in [0, 1]                                    |
| `playerctl play-pause`                     | Method `PlayPause`                                                       |
| `playerctl next` / `previous`              | Methods `Next` / `Previous`                                              |
| `playerctl shuffle toggle`                 | `Properties.Set Shuffle` to `!current`                                   |
| `playerctl loop <mode>`                    | `Properties.Set LoopStatus`                                              |
| `playerctl volume 0.05+` / `0.05-`         | Read `Volume`, clamp `current ± 0.05`, `Properties.Set Volume`           |

`_snapshot()` continues to capture a comparable tuple and `_last_state`
diffing is preserved — only the source of those values changes.

## Error handling

- **Spotify not running.** DBus calls raise `DBusErrorResponse` with names
  like `org.freedesktop.DBus.Error.ServiceUnknown` or `NameHasNoOwner`.
  `SpotifyMpris` catches these for both reads and writes:
  - Reads return safe defaults: `status="Stopped"`, `shuffle=False`,
    `loop="None"`, empty artist/title/album, `volume=0.5`.
  - Writes are silent no-ops.
  - `render()` therefore draws a neutral, non-highlighted page instead of
    crashing or showing partial state.
- **Spotify started after page is open.** The `NameOwnerChanged` subscription
  fires on registration; the listener immediately re-snapshots and renders.
- **Spotify quits while page is open.** `NameOwnerChanged` fires with an
  empty new-owner; `_last_state` resets, snapshot returns defaults, page
  re-renders neutral.
- **Listener thread crash.** Unexpected exceptions inside the listener are
  logged and the thread exits. The page remains usable in a read-only sense
  until the user re-activates the page (i.e. switches away and back).
- **Connection close on deactivate.** Closing the connection raises a
  `ConnectionClosed`-style exception inside `receive()`; the listener
  catches it and exits cleanly.

## Concurrency model

- Same threading model as today: one daemon thread per active page.
- No GLib mainloop. No asyncio. Just blocking jeepney plus the DBus
  connection as the stop signal — `deactivate()` calls `conn.close()`,
  which unblocks `receive()` and the listener exits. The current
  `threading.Event` is dropped; it served no purpose beyond what closing
  the connection already provides.
- All Stream Deck rendering happens via `self.ctrl.set_key_image(...)`, which
  is already the cross-thread interface in use today.

## File and dependency changes

- **`pages/spotify.py`** — rewritten. `SpotifyMpris` lives in the same file
  as a page-private helper, matching the self-contained style of
  `pages/hue.py`, `pages/kasa.py`, `pages/tapo.py`.
- **`requirements.txt`** — created if absent. Lists `jeepney` and the other
  pip-installable deps already implied by the README (`streamdeck`,
  `Pillow`, `PyYAML`, `phue`, `python-kasa`, `tapo`). If the user prefers to
  manage deps manually, this file can be skipped — only `jeepney` needs to
  be installed for this work.
- **`CLAUDE.md`** — Dependencies section updated: remove the `playerctl`
  system-binary note, add `jeepney`.
- **`config.yaml`** — no schema changes.

## Testing

Manual verification on a system running Spotify:

1. With Spotify open and playing: open the Spotify page → status,
   artist/title/album, shuffle, repeat all reflect reality.
2. Press play/pause, next, previous, shuffle, repeat — UI updates within
   well under a second of the action (signal-driven).
3. Press volume up/down — if the Spotify build honors MPRIS Volume, the
   level changes; if not, the keys are no-ops without errors.
4. Quit Spotify while the page is open → page transitions to neutral state
   without errors.
5. Re-open Spotify → page reflects the new state within a moment.
6. Open the Spotify page with Spotify *not* running → neutral state, no
   errors. Start Spotify → page updates.
7. Switch pages and switch back repeatedly → no thread leaks, no leftover
   connections (verify with `lsof` on the socket if curious).

No automated test scaffolding is added; the project currently has none, and
introducing it is out of scope.

## Out of scope / future work

- DENON Heos integration (already noted as planned in `CLAUDE.md`).
- Migrating other integrations to direct DBus (Hue/Kasa/Tapo don't use DBus).
- Adding playback progress / scrubbing.
- Adding queue, device, or playlist controls.
