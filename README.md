# SmashDeck

A Python app that turns an [Elgato Stream Deck XL](https://www.elgato.com/stream-deck-xl) into a desktop home-automation controller.

## What it does

SmashDeck renders icon + label keys onto a Stream Deck XL and routes key presses to per-page handlers. The top row is a persistent navigation bar; the rest of the deck is owned by whichever page is active.

### Integrations

| Page    | Backend                              | Status      |
|---------|--------------------------------------|-------------|
| Home    | —                                    | Implemented |
| Spotify | `playerctl` (system binary)          | Implemented |
| Hue     | `phue` (Philips Hue bridge)          | Implemented |
| Kasa    | `python-kasa` (TP-Link Kasa)         | Implemented |
| Tapo    | `tapo` SDK (TP-Link Tapo)            | Implemented |
| Heos    | DENON Heos                           | Planned     |

## Requirements

- A connected Stream Deck XL (32 keys, 4×8)
- Python 3 with: `streamdeck`, `Pillow`, `PyYAML`, `phue`, `python-kasa`, `tapo`
- `playerctl` available on `$PATH` (for the Spotify page)

## Setup

```bash
cp config.yaml.dist config.yaml
# edit config.yaml: Hue bridge IP, Kasa/Tapo device hosts, Tapo credentials,
# Spotify OAuth client id/secret/redirect, playlists, rooms, scenes
```

## Running

```bash
python main.py          # main app
python device_info.py   # diagnostics for connected Stream Decks
```

## Layout

Keys are numbered 0–31, left-to-right, top-to-bottom (4 rows × 8 columns).

- **Keys 0–4** — global nav bar: Home, Spotify, Hue, Kasa, Tapo
- **Keys 5–7** — reserved / blank
- **Keys 8–31** — page content area (rows 2–4)

## Project layout

```
main.py            DeckController, nav bar, key routing, config load
device_info.py     Stream Deck diagnostics
config.yaml        Local config (gitignored — see config.yaml.dist)
pages/
  __init__.py      BasePage ABC (render / on_key / activate / deactivate / clear)
  home.py          HomePage — empty content area
  spotify.py       SpotifyPage — playerctl: play/pause, next, prev, shuffle, vol
  hue.py           HuePage — rooms (row 2) + lights of selected room (row 3)
  kasa.py          KasaPage — toggle Kasa devices
  tapo.py          TapoPage — toggle Tapo devices
icons/             72×72 PNG key icons + generate_icons.py (Pillow generator)
```

## Adding a new page

1. Create `pages/<name>.py` extending `BasePage`; implement `render()` and `on_key(key)`.
2. Register it in `DeckController.start()` (`self.pages` dict).
3. Add an entry to `NAV_KEYS` in `main.py` (`key_index → (page_name, icon, label)`).
4. Add any required config to `config.yaml`.

## Regenerating icons

`generate_icons.py` produces the 72×72 PNGs into `./icons/` (created if missing):

```bash
python generate_icons.py    # writes to ./icons/
```

## Linting

```bash
ruff check .
```
