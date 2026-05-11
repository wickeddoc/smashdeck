# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SmashDeck is a Python application that drives an Elgato Stream Deck XL as a home automation controller. Implemented integrations: Spotify (via DBus/MPRIS2), Philips Hue (via `phue`), TP-Link Kasa (via `python-kasa`), and Tapo (via the `tapo` SDK). DENON Heos is planned but not implemented.

## Running

```bash
pip install -r requirements.txt    # one-time, into a venv
python main.py                     # run the app (requires a connected Stream Deck)
python device_info.py              # print diagnostic info about connected Stream Decks
```

## Regenerating Icons

Icons are 144×144 PNGs (Stream Deck XL native resolution) generated with
Pillow. The Stream Deck library downscales them automatically at render time
for smaller models (Original / Mini / Mk.2). Output directory is `icons/`.

```bash
python generate_icons.py                  # default: 144×144
ICON_SIZE=72 python generate_icons.py     # for Original / Mini, if you want
                                          # a pre-sized set on disk
```

## Linting

The project uses Ruff (`.ruff_cache/` exists). No pyproject.toml or ruff config file is present yet.

```bash
ruff check .
```

## Architecture

### Core (`main.py`)
- `DeckController` — Central controller that owns the Stream Deck device, manages pages, handles key routing, and renders icon+label images onto keys.
- Loads device config from `config.yaml`.
- Signal handlers (SIGINT/SIGTERM) ensure clean shutdown (reset + close).

### Page System (`pages/`)
- `BasePage` (ABC in `pages/__init__.py`) — abstract `render()` / `on_key(key)`, optional `activate()` / `deactivate()` lifecycle hooks (e.g. SpotifyPage starts/stops a DBus signal-listener thread), and `clear()` which wipes only the content area (keys 8–31), preserving the nav bar.
- Each page subclass controls keys 8–31; keys 0–7 are owned by the controller's nav bar.
- Pages navigate between each other via `self.ctrl.switch_page("page_name")`.
- **HomePage** (`pages/home.py`) — empty content area; navigation is provided by the persistent nav bar.
- **SpotifyPage** (`pages/spotify.py`) — Controls Spotify playback via DBus/MPRIS2 (play/pause, next, prev, shuffle, repeat, volume). Renders the current track's album cover on key 31, fetched from `mpris:artUrl` via stdlib `urllib.request`. A background thread subscribes to `PropertiesChanged` so the page reflects external state changes (track skips in the Spotify app, etc.) automatically.
- **HuePage / KasaPage / TapoPage** — row 2 lists devices/rooms; tap to toggle (Hue also surfaces lights of the selected room on row 3).

### Key Layout Convention
Keys are numbered 0–31 (4 rows × 8 columns, left-to-right, top-to-bottom). Keys 0–4 are a persistent global nav bar (Home, Spotify, Hue, Kasa, Tapo), defined by `NAV_KEYS` in `main.py`. Keys 5–7 are reserved/blank. Keys 8–31 are the page's content area (rows 2–4).

### Configuration (`config.yaml`)
YAML file with sections for `hue`, `kasa`, and `spotify`. Contains device IPs, room/scene definitions, and Spotify OAuth credentials. New integrations should add their config section here.

## Dependencies

- `streamdeck` — Stream Deck USB communication (python-elgato-streamdeck)
- `Pillow` — Image rendering for key icons
- `PyYAML` — Config parsing
- `phue` — Philips Hue bridge control (used by `pages/hue.py` and `test.py`)
- `python-kasa` — TP-Link Kasa smart plug control (`pages/kasa.py`)
- `tapo` — TP-Link Tapo smart device SDK (`pages/tapo.py`)
- `jeepney` — Pure-Python DBus client used by `pages/spotify.py` to talk to Spotify over MPRIS2

## Adding a New Page

1. Create `pages/<name>.py` with a class extending `BasePage`.
2. Implement `render()` (set key images) and `on_key(key)` (handle presses).
3. Register in `DeckController.start()` inside `self.pages` dict.
4. Add an entry to `NAV_KEYS` in `main.py` (key index → `(page_name, icon_filename, label)`) so the page is reachable from the top-row nav bar.
5. Add any needed config to `config.yaml`.
