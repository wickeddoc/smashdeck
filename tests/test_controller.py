# tests/test_controller.py
"""DeckController key routing and page lifecycle, driven through _on_key the
way the Stream Deck reader thread calls it. Rendering runs for real against a
deck stub that accepts encoded key images."""
import threading
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

import main
from main import RESTART_KEY, DeckController, TransportError
from pages import BasePage

# NAV_KEYS indices, see main.py
HOME, SPOTIFY, HUE, KASA, MONITOR = 0, 1, 2, 3, 6


class ImageDeck:
    """Deck stub with the XL's key image format; stores encoded key images."""

    def __init__(self):
        self.key_images = {}
        self.depth = 0  # nesting of `with deck:` (the library's update_lock)
        self.writes_outside_lock = []
        self.resets = 0
        self.closes = 0
        # None: always connected; n: reports unplugged after n connected() checks
        self.connected_polls = None
        self.vanish_on_unplug = False  # once unplugged, reset()/close() raise

    def connected(self):
        if self.connected_polls is None:
            return True
        self.connected_polls -= 1
        plugged = self.connected_polls >= 0
        if not plugged and self.vanish_on_unplug:
            self.reset = self.close = self._gone
        return plugged

    def is_open(self):
        return self.closes == 0

    def _gone(self):
        raise TransportError("No HID device.")

    def reset(self):
        self.resets += 1

    def close(self):
        self.closes += 1

    def set_brightness(self, percent):
        pass

    def set_key_callback(self, callback):
        pass

    def __enter__(self):
        self.depth += 1
        return self

    def __exit__(self, *exc):
        self.depth -= 1

    def key_count(self):
        return 32

    def key_image_format(self):
        return {"size": (96, 96), "format": "JPEG",
                "flip": (True, True), "rotation": 0}

    def set_key_image(self, key, image):
        if self.depth == 0:
            self.writes_outside_lock.append(key)
        self.key_images[key] = image


class RecordingPage(BasePage):
    """Counts lifecycle calls; can raise like a page whose device is offline."""

    def __init__(self, ctrl, fail_on=None):
        super().__init__(ctrl)
        self.fail_on = fail_on  # None, "render" or "on_key"
        self.renders = 0
        self.activations = 0
        self.deactivations = 0

    def render(self):
        self.renders += 1
        if self.fail_on == "render":
            raise OSError("device unreachable")

    def on_key(self, key):
        if self.fail_on == "on_key":
            raise OSError("device unreachable")

    def activate(self):
        self.activations += 1

    def deactivate(self):
        self.deactivations += 1


@pytest.fixture
def controller(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("{}\n")
    ctrl = DeckController(str(cfg))
    ctrl.deck = ImageDeck()
    return ctrl


def press(ctrl, key):
    ctrl._on_key(ctrl.deck, key, True)


# --- Bug: re-pressing the active page's nav key activated it a second time,
# leaking SpotifyPage's DBus listener thread, which then kept drawing the
# Spotify layout over whatever page was shown next.

def test_repressing_active_nav_key_keeps_activate_deactivate_paired(controller):
    spotify = RecordingPage(controller)
    controller.pages = {"home": RecordingPage(controller), "spotify": spotify}

    press(controller, SPOTIFY)
    press(controller, SPOTIFY)
    press(controller, HOME)

    assert spotify.activations == 1
    assert spotify.deactivations == 1


def test_repressing_active_nav_key_rerenders_page(controller):
    spotify = RecordingPage(controller)
    controller.pages = {"home": RecordingPage(controller), "spotify": spotify}

    press(controller, SPOTIFY)
    press(controller, SPOTIFY)

    assert spotify.renders == 2


# --- Bug: an exception escaping the key callback killed the Stream Deck
# library's reader thread, so the deck ignored every later key press
# (including Restart) until the process was killed.

def test_render_error_on_page_switch_keeps_deck_responsive(controller, capsys):
    home = RecordingPage(controller)
    controller.pages = {
        "home": home,
        "kasa": RecordingPage(controller, fail_on="render"),
    }

    press(controller, KASA)  # Kasa render hits an unreachable plug
    press(controller, HOME)

    assert controller.current_page is home
    assert "device unreachable" in capsys.readouterr().err


def test_on_key_error_keeps_deck_responsive(controller, capsys):
    home = RecordingPage(controller)
    controller.pages = {
        "home": home,
        "hue": RecordingPage(controller, fail_on="on_key"),
    }

    press(controller, HUE)
    press(controller, 16)  # light toggle while the bridge is offline
    press(controller, HOME)

    assert controller.current_page is home
    assert "device unreachable" in capsys.readouterr().err


# --- Active nav key: label strip in the accent colour (spec: style C).

ACCENT = (110, 170, 255)
BLACK = (0, 0, 0)
STRIP_PIXEL = (3, 93)  # inside the 20 px label strip of a 96 px key, left of the text


def key_pixel(ctrl, key, xy):
    """Decode a key's native JPEG, undo the XL's flip, return the RGB at xy."""
    img = Image.open(BytesIO(ctrl.deck.key_images[key])).convert("RGB")
    img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return img.getpixel(xy)


def close_to(rgb, expected, tolerance=24):
    return all(abs(a - b) <= tolerance for a, b in zip(rgb, expected))


def test_active_nav_key_has_accent_label_strip(controller):
    controller.pages = {"home": RecordingPage(controller),
                        "spotify": RecordingPage(controller)}

    press(controller, SPOTIFY)

    assert close_to(key_pixel(controller, SPOTIFY, STRIP_PIXEL), ACCENT)
    assert close_to(key_pixel(controller, HOME, STRIP_PIXEL), BLACK)


def test_label_strip_moves_with_page_switch(controller):
    controller.pages = {"home": RecordingPage(controller),
                        "spotify": RecordingPage(controller)}

    press(controller, SPOTIFY)
    press(controller, HOME)

    assert close_to(key_pixel(controller, HOME, STRIP_PIXEL), ACCENT)
    assert close_to(key_pixel(controller, SPOTIFY, STRIP_PIXEL), BLACK)


def test_nav_key_6_opens_monitor_page(controller):
    monitor = RecordingPage(controller)
    controller.pages = {"home": RecordingPage(controller), "monitor": monitor}

    press(controller, MONITOR)

    assert controller.current_page is monitor
    assert close_to(key_pixel(controller, MONITOR, STRIP_PIXEL), ACCENT)


# --- Signal shutdown must stop the visible page before start()'s finally
# resets/closes the deck, or its thread can write to a reset/closed deck.

def test_shutdown_deactivates_current_page_and_exits_zero(controller):
    home = RecordingPage(controller)
    controller.pages = {"home": home}
    press(controller, HOME)

    with pytest.raises(SystemExit) as exc:
        controller._shutdown()

    assert exc.value.code == 0
    assert home.deactivations == 1
    # The handler leaves reset/close to run()'s finally (exactly once).
    assert (controller.deck.resets, controller.deck.closes) == (0, 0)


def test_shutdown_still_exits_when_deactivate_raises(controller, capsys):
    class Broken(RecordingPage):
        def deactivate(self):
            raise OSError("stuck thread")

    controller.pages = {"home": Broken(controller)}
    press(controller, HOME)

    with pytest.raises(SystemExit) as exc:
        controller._shutdown()

    assert exc.value.code == 0
    assert "stuck thread" in capsys.readouterr().err


# --- An XL key image is several HID reports; the whole write must hold the
# deck's update lock so the reader thread and a page thread can't interleave.

def test_key_images_are_written_under_the_deck_lock(controller):
    controller.pages = {"home": RecordingPage(controller)}

    press(controller, HOME)

    assert controller.deck.key_images  # nav bar was drawn
    assert controller.deck.writes_outside_lock == []
    assert controller.deck.depth == 0


# --- Unplugging the deck must end the process with a non-zero code, so the
# systemd user service (Restart=on-failure) brings SmashDeck back once the
# deck is plugged in again; before, the main thread waited forever.

@pytest.fixture
def fast_poll(monkeypatch):
    monkeypatch.setattr(main, "DECK_POLL_SECONDS", 0.001)


def only_home(controller, monkeypatch):
    home = RecordingPage(controller)
    monkeypatch.setattr(DeckController, "_build_pages", lambda self: {"home": home})
    return home


def test_run_returns_1_when_the_deck_is_unplugged(controller, monkeypatch, fast_poll, capsys):
    home = only_home(controller, monkeypatch)
    controller.deck.connected_polls = 3

    assert controller.run() == 1

    assert (home.activations, home.deactivations) == (1, 1)
    assert controller.deck.resets == 2  # at start-up, then on release
    assert controller.deck.closes == 1
    assert "disconnected" in capsys.readouterr().out


def test_run_tolerates_releasing_a_deck_that_is_gone(controller, monkeypatch, fast_poll):
    only_home(controller, monkeypatch)
    controller.deck.connected_polls = 1
    controller.deck.vanish_on_unplug = True

    assert controller.run() == 1  # no TransportError escapes the release


def test_run_returns_1_when_start_up_fails(controller, monkeypatch, fast_poll, capsys):
    def broken(self):
        raise OSError("bad config")

    monkeypatch.setattr(DeckController, "_build_pages", broken)

    assert controller.run() == 1
    assert controller.deck.closes == 1
    assert "bad config" in capsys.readouterr().err


def test_start_without_a_deck_returns_1(controller, monkeypatch, capsys):
    monkeypatch.setattr(main, "DeviceManager", lambda: SimpleNamespace(enumerate=list))

    assert controller.start() == 1
    assert "No Stream Deck found" in capsys.readouterr().out


def test_wait_ignores_the_closed_deck_during_a_restart(controller, fast_poll):
    controller.deck.connected_polls = 0  # reports unplugged on every check
    controller._restarting = True  # Restart closed the deck and is re-exec'ing
    waiter = threading.Thread(target=controller._wait_while_connected, daemon=True)
    waiter.start()

    waiter.join(0.1)
    assert waiter.is_alive()

    controller._restarting = False
    waiter.join(1.0)
    assert not waiter.is_alive()


def test_failed_restart_exec_stops_waiting_for_it(controller, monkeypatch):
    def no_exec(*args):
        raise OSError("exec failed")

    monkeypatch.setattr(main.os, "execv", no_exec)
    controller.pages = {"home": RecordingPage(controller)}
    press(controller, HOME)

    press(controller, RESTART_KEY)  # _on_key logs the error, the deck stays usable

    assert controller._restarting is False


# --- Home and Monitor show the same weather: one feed, fetched once.

def test_home_and_monitor_share_one_weather_feed(controller):
    pages = controller._build_pages()
    assert pages["home"].weather is pages["monitor"].weather


def test_home_and_spotify_share_one_artist_photo_cache(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("spotify:\n  artist_art:\n    api_key: k\n")
    pages = DeckController(str(cfg))._build_pages()
    assert pages["home"].artist_photos is not None
    assert pages["home"].artist_photos is pages["spotify"].artist_photos


def test_artist_photos_are_off_without_config(controller):
    pages = controller._build_pages()
    assert pages["home"].artist_photos is None
    assert pages["spotify"].artist_photos is None
