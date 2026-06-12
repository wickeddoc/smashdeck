# Missing features: Hue scenes, Spotify playlists, brightness, resilience

**Date:** 2026-06-12
**Status:** Approved design
**Scope:** Implement the features that `config.yaml.dist`, the icon set, and the
README already promise but that have no code behind them, plus fix the crash
and secret-leak issues found during the project audit.

## Background (audit findings)

The three existing spec/plan pairs (Spotify DBus, 144×144 icons, cover art)
are fully implemented. What remains promised-but-missing:

| Promise | Evidence | Status |
|---|---|---|
| Hue scenes | `hue.scenes` in config.yaml.dist, 5 `scene_*.png` icons | No code |
| Spotify playlists | `spotify.playlists` in config, 5 `playlist_*.png` icons | No code |
| Deck brightness control | 4 `brightness_*.png` icons | Hardcoded 60 |
| Heos page | README "Planned" | No code (out of scope here) |

And the defects:

- `HuePage.__init__` connects to the bridge at startup; an unreachable bridge
  crashes the whole app before the deck renders anything.
- `DeckController.__init__` does `print(self.config)`, leaking the Tapo
  password to stdout/journal.
- `hue.rooms` config is dead (rooms come from the bridge), and the Spotify
  OAuth fields are dead (the DBus backend needs no credentials).
- `go_back()` / `page_history` in `main.py` is dead code — nothing maps a key
  to it.
- `test.py` is an untracked scratch script with a hardcoded IP and a side
  effect (turns off light 5).

## Goals

- Hue scenes: row 4 of the Hue page lists scenes from config; tap to activate.
- Spotify playlists: row 4 (keys 24–28) lists up to 5 playlists from config;
  tap to start playback via MPRIS2 `Player.OpenUri` — **no OAuth needed**.
- Home page: brightness keys (25/50/75/100 %) using the existing icons.
- Hue page survives an unreachable bridge: lazy connect on first render,
  `error.png` shown on failure, retried on next visit.
- Remove the secret leak and the dead config/code.
- Introduce a minimal pytest harness (fake controller/deck) so page logic is
  testable without hardware or network.

## Non-goals

- Heos integration — independent subsystem, needs its own brainstorm/spec
  (device discovery, telnet/HEOS CLI protocol choice).
- Moving Kasa/Tapo/Hue network I/O off the USB callback thread — worthwhile
  but a separate refactor; noted as follow-up.
- Spotify Web API features (search, queue, devices). `OpenUri` covers playlist
  launching without credentials.
- Persisting brightness across restarts.

## Design decisions

1. **Playlists via MPRIS2 `OpenUri`,** not the Web API: the config's
   `client_id`/`client_secret`/`redirect_uri` fields are removed. Playlist
   URIs (`spotify:playlist:…`) stay.
2. **Scene icons from config:** each scene entry gains an optional
   `icon:` field (default `scene_relax.png`); the existing `color` field is
   kept for the dist example but unused by code (YAGNI on colour rendering).
3. **Key layout:**
   - Hue page: rooms row 2 (8–15), lights row 3 (16–23), scenes row 4 (24–31).
   - Spotify page: playlists on 24–28 (29–30 stay free, 31 is cover art).
   - Home page: brightness on 8–11.
4. **Lazy Hue connect:** `Bridge` construction moves out of `__init__` into a
   `_connect()` helper called from `render()`; failure renders `error.png` on
   key 8 and returns. Page construction can no longer crash the app.
5. **Testing:** pytest + a `FakeController`/`FakeDeck` in `tests/conftest.py`
   capturing `set_key_image` calls. Network SDKs are faked per-test
   (monkeypatch `pages.hue.Bridge`, inject a fake `SpotifyMpris`).
6. **Cleanup:** delete `test.py`, remove `go_back`/`page_history`, remove
   `hue.rooms` and Spotify OAuth fields from `config.yaml.dist`, update
   README/CLAUDE.md.

## Follow-ups (suggested, not in this plan)

- Heos page (own spec).
- Async/executor refresh so Kasa/Tapo/Hue renders don't block the USB
  callback thread; periodic state refresh while a page is visible.
- Replace `print()` with the `logging` module project-wide.
- KasaPage migration off the deprecated `SmartPlug` API to
  `kasa.Device.connect` / `Discover`.
- Tapo device-type support beyond `p100` (config `type:` field).
- pyproject.toml with ruff config; systemd user unit for autostart.
