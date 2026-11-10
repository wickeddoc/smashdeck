# tests/test_controller.py
"""DeckController key routing and page lifecycle, driven through _on_key the
way the Stream Deck reader thread calls it. Rendering runs for real against a
deck stub that accepts encoded key images."""
from io import BytesIO

import pytest
from PIL import Image

from main import DeckController
from pages import BasePage

# NAV_KEYS indices, see main.py
HOME, SPOTIFY, HUE, KASA, MONITOR = 0, 1, 2, 3, 6


class ImageDeck:
    """Deck stub with the XL's key image format; stores encoded key images."""

    def __init__(self):
        self.key_images = {}
        self.depth = 0  # nesting of `with deck:` (the library's update_lock)
        self.writes_outside_lock = []

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
