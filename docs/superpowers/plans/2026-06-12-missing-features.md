# Missing Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the features already promised by config/icons (Hue scenes, Spotify playlists, deck brightness), make the Hue page crash-proof, and remove dead config, dead code, and a secret leak.

**Architecture:** All changes follow the existing page model: each page owns keys 8–31, the controller owns the nav bar. New behaviour is config-driven (`config.yaml`). A small pytest harness with a `FakeController` makes page logic testable without a Stream Deck or network — network SDKs are faked per-test.

**Tech Stack:** Python 3, pytest (new dev dep), existing deps (`phue`, `jeepney`, Pillow). No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-06-12-missing-features-design.md`

---

## File map

| File | Change |
|---|---|
| `tests/conftest.py` | Create — `FakeDeck`, `FakeController` fixtures |
| `tests/test_hue_page.py` | Create — lazy connect, scenes |
| `tests/test_spotify_playlists.py` | Create — playlist keys, OpenUri |
| `tests/test_home_page.py` | Create — brightness keys |
| `requirements-dev.txt` | Create — `pytest` |
| `main.py` | Remove config print + dead `go_back`/`page_history` |
| `pages/hue.py` | Lazy connect, error key, scenes row |
| `pages/spotify.py` | `open_uri()`, playlist row |
| `pages/home.py` | Brightness keys |
| `config.yaml.dist` | Drop dead keys, add scene `icon:` |
| `test.py` | Delete (untracked scratch file) |
| `README.md`, `CLAUDE.md` | Update docs |

---

### Task 1: Test harness

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest
```

- [ ] **Step 2: Install it**

Run: `pip install -r requirements-dev.txt`
Expected: pytest installed into the project venv.

- [ ] **Step 3: Create `tests/__init__.py`** (empty file) **and `tests/conftest.py`**

```python
# tests/conftest.py
"""Shared fakes: a controller/deck pair that records rendering calls."""
import pytest


class FakeDeck:
    def __init__(self):
        self.brightness = None

    def key_count(self):
        return 32

    def set_brightness(self, value):
        self.brightness = value


class FakeController:
    """Stands in for DeckController; records every set_key_image call."""

    def __init__(self, config=None):
        self.config = config or {}
        self.deck = FakeDeck()
        self.images = {}  # key index -> kwargs of last render

    def set_key_image(self, key, icon_filename=None, label=None,
                      color=(0, 0, 0), highlight=None, pil_image=None):
        self.images[key] = {
            "icon": icon_filename,
            "label": label,
            "color": color,
            "highlight": highlight,
            "pil_image": pil_image,
        }

    def switch_page(self, name):
        self.switched_to = name


@pytest.fixture
def ctrl():
    return FakeController()
```

- [ ] **Step 4: Verify pytest collects (zero tests is fine)**

Run: `python -m pytest tests/ -q`
Expected: `no tests ran` (exit code 5 is OK at this point).

- [ ] **Step 5: Commit**

```bash
git add requirements-dev.txt tests/
git commit -m "test: add pytest harness with FakeController/FakeDeck"
```

---

### Task 2: Stop printing config (secret leak) and remove dead navigation code

**Files:**
- Modify: `main.py:28-31` (config print), `main.py:114-127` (`go_back`, and `page_history` at line 36 / its append in `switch_page`)

- [ ] **Step 1: Remove the config print**

In `DeckController.__init__`, change:

```python
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
            print(self.config)
```

to:

```python
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
```

- [ ] **Step 2: Remove `page_history` and `go_back`**

Delete `self.page_history = []` from `__init__`, delete the whole `go_back()` method, and simplify `switch_page` to:

```python
    def switch_page(self, name):
        if self.current_page and self.current_page is not self.pages.get(name):
            self.current_page.deactivate()
        self.current_page = self.pages[name]
        self.render_nav_bar()
        self.current_page.render()
        self.current_page.activate()
```

- [ ] **Step 3: Lint and sanity-check**

Run: `ruff check main.py && python -c "import ast; ast.parse(open('main.py').read())"`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "main: stop printing config (leaks Tapo password); drop dead go_back/page_history"
```

---

### Task 3: HuePage — lazy bridge connection with error rendering

**Files:**
- Modify: `pages/hue.py`
- Test: `tests/test_hue_page.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hue_page.py
"""HuePage logic against a faked phue.Bridge."""
import pages.hue as hue_mod
from pages.hue import HuePage


class FakeGroup:
    def __init__(self, group_id, name):
        self.group_id = group_id
        self.name = name


class FakeBridge:
    def __init__(self, ip):
        self.ip = ip
        self.groups = [FakeGroup(1, "Living"), FakeGroup(2, "Bedroom")]
        self.scene_calls = []

    def get_group(self, group_id):
        return {"lights": []}

    def activate_scene(self, group_id, scene_id, transition_time=4):
        self.scene_calls.append((group_id, scene_id))


class BrokenBridge:
    def __init__(self, ip):
        raise OSError("bridge unreachable")


HUE_CFG = {
    "hue": {
        "bridge_ip": "10.0.0.2",
        "scenes": [
            {"name": "Relax", "group_id": 1, "scene_id": "abc",
             "icon": "scene_relax.png"},
            {"name": "Party", "group_id": 1, "scene_id": "def",
             "icon": "scene_party.png"},
        ],
    }
}


def test_init_does_not_connect(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", BrokenBridge)
    ctrl.config = HUE_CFG
    HuePage(ctrl)  # must not raise


def test_render_with_unreachable_bridge_shows_error(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", BrokenBridge)
    ctrl.config = HUE_CFG
    page = HuePage(ctrl)
    page.render()
    assert ctrl.images[8]["icon"] == "error.png"


def test_render_lists_rooms_from_bridge(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", FakeBridge)
    ctrl.config = HUE_CFG
    page = HuePage(ctrl)
    page.render()
    assert ctrl.images[8]["label"] == "Living"
    assert ctrl.images[9]["label"] == "Bedroom"


def test_render_lists_scenes_on_row_4(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", FakeBridge)
    ctrl.config = HUE_CFG
    page = HuePage(ctrl)
    page.render()
    assert ctrl.images[24]["icon"] == "scene_relax.png"
    assert ctrl.images[24]["label"] == "Relax"
    assert ctrl.images[25]["icon"] == "scene_party.png"


def test_scene_key_activates_scene(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", FakeBridge)
    ctrl.config = HUE_CFG
    page = HuePage(ctrl)
    page.render()
    page.on_key(25)
    assert page.bridge.scene_calls == [(1, "def")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hue_page.py -v`
Expected: FAIL — `test_init_does_not_connect` raises `OSError` (current code connects in `__init__`); scene tests fail with `KeyError: 24`.

- [ ] **Step 3: Rewrite `pages/hue.py`**

```python
# pages/hue.py
import traceback

from phue import Bridge

from pages import BasePage


class HuePage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        self._cfg = self.ctrl.config.get("hue", {})
        self.scenes = self._cfg.get("scenes", [])
        self.bridge = None
        self.rooms = []
        self.selected_room = None
        self._light_ids = []  # light IDs currently shown on row 3

    def _connect(self) -> bool:
        """Connect to the bridge on first use. Returns False on failure so the
        page can render an error key instead of crashing the app."""
        if self.bridge is not None:
            return True
        try:
            bridge = Bridge(self._cfg.get("bridge_ip"))
            self.rooms = [
                {"name": room.name, "group_id": room.group_id}
                for room in bridge.groups
            ]
            self.bridge = bridge
            return True
        except Exception:
            traceback.print_exc()
            self.bridge = None
            return False

    def render(self):
        self.clear()
        if not self._connect():
            self.ctrl.set_key_image(8, "error.png", "No bridge")
            return
        self._render_rooms()
        if self.selected_room is not None:
            self._render_lights()
        self._render_scenes()

    def _render_rooms(self):
        for i, room in enumerate(self.rooms[:8]):
            key = 8 + i
            highlight = (120, 60, 180) if i == self.selected_room else None
            self.ctrl.set_key_image(key, "hue.png", room["name"], highlight=highlight)

    def _render_lights(self):
        room = self.rooms[self.selected_room]
        group = self.bridge.get_group(room["group_id"])
        light_ids = [int(lid) for lid in group.get("lights", [])]
        self._light_ids = light_ids[:8]

        for i, lid in enumerate(self._light_ids):
            light = self.bridge.get_light(lid)
            is_on = light["state"]["on"]
            icon = "light_on.png" if is_on else "light_off.png"
            highlight = (255, 220, 50) if is_on else None
            name = light["name"][:10]
            self.ctrl.set_key_image(16 + i, icon, name, highlight=highlight)

    def _render_scenes(self):
        for i, scene in enumerate(self.scenes[:8]):
            icon = scene.get("icon", "scene_relax.png")
            self.ctrl.set_key_image(24 + i, icon, scene["name"][:10])

    def on_key(self, key):
        if self.bridge is None:
            # Bridge was unreachable at render time; retry on next render.
            self.render()
            return

        # Row 2 (keys 8-15): room selection
        if 8 <= key <= 15:
            idx = key - 8
            if idx < len(self.rooms):
                self.selected_room = idx
                self.render()

        # Row 3 (keys 16-23): toggle light
        elif 16 <= key <= 23:
            idx = key - 16
            if idx < len(self._light_ids):
                lid = self._light_ids[idx]
                is_on = self.bridge.get_light(lid, "on")
                self.bridge.set_light(lid, "on", not is_on)
                self._render_lights()

        # Row 4 (keys 24-31): activate scene
        elif 24 <= key <= 31:
            idx = key - 24
            if idx < len(self.scenes):
                scene = self.scenes[idx]
                self.bridge.activate_scene(scene["group_id"], scene["scene_id"])
```

(Note: the unused `selected_light` attribute and its debug `print` are dropped.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_hue_page.py -v`
Expected: 5 passed.

- [ ] **Step 5: Lint and commit**

```bash
ruff check pages/hue.py
git add pages/hue.py tests/test_hue_page.py
git commit -m "hue: lazy bridge connect with error key; activate scenes from row 4"
```

---

### Task 4: Spotify playlists via MPRIS2 OpenUri

**Files:**
- Modify: `pages/spotify.py`
- Test: `tests/test_spotify_playlists.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_spotify_playlists.py
"""SpotifyPage playlist rendering and OpenUri dispatch, no DBus needed."""
from pages.spotify import SpotifyPage

SPOTIFY_CFG = {
    "spotify": {
        "playlists": [
            {"name": "Chill", "uri": "spotify:playlist:xxxxx"},
            {"name": "Work", "uri": "spotify:playlist:yyyyy"},
        ]
    }
}


class FakeMpris:
    def __init__(self):
        self.opened = []

    def open_uri(self, uri):
        self.opened.append(uri)


def test_render_shows_playlists_on_row_4(ctrl):
    ctrl.config = SPOTIFY_CFG
    page = SpotifyPage(ctrl)
    page.render()  # _mpris is None -> default snapshot; playlists still render
    assert ctrl.images[24]["icon"] == "playlist_1.png"
    assert ctrl.images[24]["label"] == "Chill"
    assert ctrl.images[25]["icon"] == "playlist_2.png"
    assert ctrl.images[25]["label"] == "Work"


def test_playlist_key_calls_open_uri(ctrl):
    ctrl.config = SPOTIFY_CFG
    page = SpotifyPage(ctrl)
    fake = FakeMpris()
    page._mpris = fake
    page.on_key(25)
    assert fake.opened == ["spotify:playlist:yyyyy"]


def test_no_playlists_configured_renders_nothing_on_24(ctrl):
    ctrl.config = {"spotify": {}}
    page = SpotifyPage(ctrl)
    page.render()
    # clear() paints it black; no playlist icon must overwrite it
    assert ctrl.images[24]["icon"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_spotify_playlists.py -v`
Expected: FAIL — `KeyError`/`None` icon on key 24; `on_key(25)` hits the
existing dispatch table and calls `FakeMpris` methods that don't exist →
`AttributeError` or silent miss with empty `opened`.

- [ ] **Step 3: Implement**

In `pages/spotify.py`:

3a. Add a module constant under the existing volume-key constants:

```python
PLAYLIST_KEYS = (24, 25, 26, 27, 28)  # row 4; 29-30 free, 31 = cover art
```

3b. Add to `SpotifyMpris` (after `nudge_volume`):

```python
    def open_uri(self, uri: str):
        try:
            self._conn.send_and_get_reply(
                new_method_call(_PLAYER, "OpenUri", "s", (uri,))
            )
        except Exception:
            pass
```

3c. In `SpotifyPage.__init__`, after the art attributes:

```python
        spotify_cfg = controller.config.get("spotify", {})
        self._playlists = spotify_cfg.get("playlists", [])[: len(PLAYLIST_KEYS)]
```

3d. In `SpotifyPage.render()`, before the final `set_key_image(31, ...)` line:

```python
        for i, pl in enumerate(self._playlists):
            self.ctrl.set_key_image(
                PLAYLIST_KEYS[i], f"playlist_{i + 1}.png", pl["name"][:12]
            )
```

3e. In `SpotifyPage.on_key()`, after the `actions` dispatch:

```python
        if key in actions:
            actions[key]()
            self.render()  # immediate UI feedback; listener will also fire
        elif key in PLAYLIST_KEYS:
            idx = PLAYLIST_KEYS.index(key)
            if idx < len(self._playlists):
                mpris.open_uri(self._playlists[idx]["uri"])
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: all pass (Hue + Spotify + harness).

- [ ] **Step 5: Lint and commit**

```bash
ruff check pages/spotify.py
git add pages/spotify.py tests/test_spotify_playlists.py
git commit -m "spotify: launch config playlists via MPRIS2 OpenUri on row 4"
```

---

### Task 5: Home page brightness control

**Files:**
- Modify: `pages/home.py`
- Test: `tests/test_home_page.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_home_page.py
from pages.home import HomePage


def test_render_shows_brightness_keys(ctrl):
    page = HomePage(ctrl)
    page.render()
    assert ctrl.images[8]["icon"] == "brightness_25.png"
    assert ctrl.images[11]["icon"] == "brightness_100.png"


def test_brightness_key_sets_deck_brightness(ctrl):
    page = HomePage(ctrl)
    page.on_key(10)
    assert ctrl.deck.brightness == 75


def test_other_keys_do_nothing(ctrl):
    page = HomePage(ctrl)
    page.on_key(20)
    assert ctrl.deck.brightness is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_home_page.py -v`
Expected: FAIL — `KeyError: 8` (HomePage renders nothing today).

- [ ] **Step 3: Implement `pages/home.py`**

```python
# pages/home.py
from pages import BasePage

BRIGHTNESS_KEYS = {8: 25, 9: 50, 10: 75, 11: 100}


class HomePage(BasePage):
    def render(self):
        self.clear()
        for key, pct in BRIGHTNESS_KEYS.items():
            self.ctrl.set_key_image(key, f"brightness_{pct}.png", f"{pct}%")

    def on_key(self, key):
        pct = BRIGHTNESS_KEYS.get(key)
        if pct is not None:
            self.ctrl.deck.set_brightness(pct)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
ruff check pages/home.py
git add pages/home.py tests/test_home_page.py
git commit -m "home: deck brightness keys (25/50/75/100%)"
```

---

### Task 6: Config and docs cleanup

**Files:**
- Modify: `config.yaml.dist`, `README.md`, `CLAUDE.md`
- Delete: `test.py` (untracked scratch script — hardcoded IP, side effect of
  turning off light 5; superseded by `tests/`)

- [ ] **Step 1: Rewrite `config.yaml.dist`**

```yaml
# config.yaml
hue:
  bridge_ip: "192.168.1.1"
  # Rooms are read live from the bridge; only scenes need configuring.
  # Find scene IDs via the bridge API: http://<bridge_ip>/api/<user>/scenes
  scenes:
    - name: "Relax"
      group_id: 1
      scene_id: "abc123"
      icon: "scene_relax.png"   # any icon from icons/
    - name: "Focus"
      group_id: 1
      scene_id: "def456"
      icon: "scene_focus.png"

kasa:
  devices:
    - name: "Heater"
      host: "192.168.1.2"
    - name: "Fan"
      host: "192.168.1.3"

tapo:
  email: "YOUR_TAPO_EMAIL"
  password: "YOUR_TAPO_PASSWORD"
  devices:
    - name: "Lamp 1"
      host: "192.168.1.30"
    - name: "Strip 1"
      host: "192.168.1.31"

spotify:
  # No credentials needed: playback control and playlist launching go over
  # DBus/MPRIS2. Up to 5 playlists are shown on row 4 of the Spotify page.
  playlists:
    - name: "Chill"
      uri: "spotify:playlist:xxxxx"
    - name: "Work"
      uri: "spotify:playlist:yyyyy"
```

- [ ] **Step 2: Delete the scratch script**

```bash
rm test.py
```

- [ ] **Step 3: Update `README.md`**

- Integrations table: keep Heos as "Planned".
- Setup section: drop "Spotify OAuth client id/secret/redirect" from the
  config.yaml edit list; mention scenes/playlists/brightness instead.
- Layout section: document Hue rows (rooms/lights/scenes), Spotify row 4
  playlists, Home brightness keys.
- Add a "Tests" section: `python -m pytest tests/` (install
  `requirements-dev.txt` first).
- Project-layout tree: remove nothing, add `tests/` and `requirements-dev.txt`.

- [ ] **Step 4: Update `CLAUDE.md`**

- Dependencies section: remove the `test.py` mention next to `phue`; add
  pytest under a dev-dependencies note.
- Architecture: HuePage now connects lazily and renders scenes on row 4;
  SpotifyPage renders playlists on keys 24–28 via `OpenUri`; HomePage has
  brightness keys 8–11.
- Configuration: `spotify` section holds only `playlists`; `hue` holds
  `bridge_ip` + `scenes`.
- Add a Testing section: `python -m pytest tests/` with the FakeController
  pattern described in one line.

- [ ] **Step 5: Final verification**

Run: `python -m pytest tests/ -q && ruff check .`
Expected: all tests pass, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add config.yaml.dist README.md CLAUDE.md
git rm --cached test.py 2>/dev/null; rm -f test.py
git commit -m "config/docs: drop dead OAuth + rooms config, document scenes/playlists/brightness/tests"
```

> Reminder for the executor: the user's real `config.yaml` is gitignored —
> after this lands they should add `icon:` fields to their scenes and can
> delete the `client_id`/`client_secret`/`redirect_uri` lines.

---

## Out of scope (tracked in the spec's Follow-ups section)

Heos page (needs its own spec), async refresh off the USB callback thread,
`logging` migration, python-kasa `SmartPlug` deprecation, Tapo device types
beyond P100, pyproject/ruff config, systemd unit.
