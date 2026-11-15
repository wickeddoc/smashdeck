# SmashDeck

A Python app that turns an [Elgato Stream Deck XL](https://www.elgato.com/stream-deck-xl) into a desktop home-automation controller.

## What it does

SmashDeck renders icon + label keys onto a Stream Deck XL and routes key presses to per-page handlers. The top row is a persistent navigation bar; the rest of the deck is owned by whichever page is active.

### Integrations

| Page    | Backend                              | Status      |
|---------|--------------------------------------|-------------|
| Home    | —                                    | Implemented |
| Spotify | DBus / MPRIS2 (`jeepney`)            | Implemented |
| Hue     | `phue` (Philips Hue bridge)          | Implemented |
| Kasa    | `python-kasa` (TP-Link Kasa)         | Implemented |
| Tapo    | `tapo` SDK (TP-Link Tapo)            | Implemented |
| Monitor | psutil, sysfs hwmon, `nvidia-smi`, Open-Meteo | Implemented |
| Heos    | DENON Heos                           | Planned     |

The Spotify page renders the current track's album cover on key 31 and updates automatically on track changes (via `org.mpris.MediaPlayer2.spotify` PropertiesChanged signals). Up to 5 playlists from `config.yaml` are shown on row 4 and start playback via MPRIS2 `OpenUri` — no Spotify credentials needed.

## Requirements

- A connected Stream Deck XL (32 keys, 4×8). Smaller models (Original / Mini / Mk.2) work too — icons are auto-scaled by the Stream Deck library at render time.
- Python 3, with deps from `requirements.txt`: `streamdeck`, `Pillow`, `PyYAML`, `phue`, `python-kasa`, `tapo`, `jeepney`, `psutil`.
- A running D-Bus session bus (standard on any Linux desktop) for the Spotify page.
- Optional: `nvidia-smi` (NVIDIA driver) for the Monitor page's GPU keys; without it they show "n/a".

## Setup

```bash
pip install -r requirements.txt        # ideally into a virtualenv
cp config.yaml.dist config.yaml
# edit config.yaml: Hue bridge IP + scenes, Kasa/Tapo device hosts,
# Tapo credentials, Spotify playlists, Monitor disks + weather location
```

## Running

```bash
python main.py          # main app
python device_info.py   # diagnostics for connected Stream Decks
```

### As a service at desktop login

`deploy/` runs SmashDeck as a systemd **user** service bound to
`graphical-session.target`. It starts when you log into your desktop
(tested with KDE Plasma 6 on Wayland; any systemd-managed session works) and
stops at logout, which resets the deck. It is a user service rather than a
system one because it needs your session: the Spotify page talks to the
session DBus, and the deck's device permissions are granted to the user
logged in on the seat.

```bash
deploy/install.sh --dry-run          # show what would happen; changes nothing
deploy/install.sh                    # install, enable at login, start now
journalctl --user -u smashdeck -f    # logs
systemctl --user restart smashdeck   # after pulling new code (or press Restart on the deck)
deploy/uninstall.sh                  # stop, disable and remove the service
```

The installer:

- finds the venv: `$SMASHDECK_PYTHON`, else `.venv/`, else the
  virtualenvwrapper env named in a `.venv` file;
- checks the dependencies and `config.yaml`;
- installs `deploy/70-streamdeck.rules` with sudo if no Stream Deck udev rule
  exists yet;
- renders `deploy/smashdeck.service.in` into
  `~/.config/systemd/user/smashdeck.service`, then enables and starts it.

It refuses to run while SmashDeck is already running outside systemd,
because two instances can't share the deck.

Unplugging is handled automatically. If the deck is unplugged while SmashDeck
runs, it notices within about a second and exits with a failure code. If the
deck is missing at login, startup fails the same way. Either way, the service
retries every 10 s and comes back as soon as the deck is plugged in again.

## Layout

Keys are numbered 0–31, left-to-right, top-to-bottom (4 rows × 8 columns).

- **Keys 0–4, 6** — global nav bar: Home, Spotify, Hue, Kasa, Tapo, Monitor (the current page's key has a blue label strip)
- **Key 5** — reserved / blank
- **Key 7** — Restart (re-execs the process)
- **Keys 8–31** — page content area (rows 2–4)

Per-page content:

- **Home** — brightness keys 8–11 (25/50/75/100 %)
- **Spotify** — controls on row 2, artist/title labels, playlists on keys
  24–28, cover art on key 31
- **Hue** — rooms on row 2, lights of the selected room on row 3, scenes on
  row 4; an unreachable bridge shows an error key instead of crashing
- **Kasa / Tapo** — devices on row 2, tap to toggle
- **Monitor** — row 2: CPU/GPU temperature, load and power, VRAM, whole-PC power; row 3: RAM, two disks, hottest NVMe, disk read/write, network down/up (Mbit/s); row 4: Open-Meteo weather (now, feels like, humidity, wind, rain, UV, tomorrow, next sunrise/sunset). Values are colour-coded green/amber/red and refresh every 2 s while the page is open; weather refreshes every 15 min, or immediately when a weather key is pressed.

## Project layout

```
main.py            DeckController, nav bar, key routing, config load
device_info.py     Stream Deck diagnostics
config.yaml        Local config (gitignored — see config.yaml.dist)
pages/
  __init__.py      BasePage ABC (render / on_key / activate / deactivate / clear)
  home.py          HomePage — deck brightness keys
  spotify.py       SpotifyPage — DBus/MPRIS2 via jeepney: play/pause, next,
                   prev, shuffle, repeat, volume, playlists (OpenUri), cover
                   art on key 31, with a PropertiesChanged signal listener
                   for auto-refresh
  hue.py           HuePage — rooms (row 2), lights of selected room (row 3),
                   scenes (row 4); lazy bridge connect with error fallback
  kasa.py          KasaPage — toggle Kasa devices
  tapo.py          TapoPage — toggle Tapo devices
  monitor/         MonitorPage — PC metrics + weather (nav key 6)
    sources.py     psutil / hwmon / nvidia-smi -> SystemSample
    weather.py     Open-Meteo client (no API key)
    tiles.py       what each key shows (build_tiles) and how it is drawn
deploy/            systemd user service for desktop login
  install.sh       render + enable + start smashdeck.service (--dry-run)
  uninstall.sh     stop, disable, remove it
  smashdeck.service.in  unit template (paths filled in by install.sh)
  70-streamdeck.rules   udev rule granting the seat user deck access
tests/             pytest suite (FakeController/FakeDeck, no hardware needed)
icons/             144×144 PNG key icons (XL native; auto-downscaled for
                   smaller decks)
generate_icons.py  Pillow icon generator
requirements.txt   pip dependencies
requirements-dev.txt  dev dependencies (pytest)
```

## Adding a new page

1. Create `pages/<name>.py` extending `BasePage`; implement `render()` and `on_key(key)`.
2. Register it in `DeckController.start()` (`self.pages` dict).
3. Add an entry to `NAV_KEYS` in `main.py` (`key_index → (page_name, icon, label)`).
4. Add any required config to `config.yaml`.

## Regenerating icons

`generate_icons.py` produces 144×144 PNGs (Stream Deck XL native) into `./icons/` (created if missing). Smaller decks downscale automatically at render time.

```bash
python generate_icons.py                  # default: 144×144
ICON_SIZE=72 python generate_icons.py     # for Original / Mini, if you want
                                          # a pre-sized set on disk
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

Page logic is tested against a `FakeController`/`FakeDeck` pair (`tests/conftest.py`); no Stream Deck or network access is required.

## Linting

```bash
ruff check .
```
