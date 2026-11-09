# tests/test_controller.py
"""DeckController key routing and page lifecycle, driven through _on_key the
way the Stream Deck reader thread calls it. Rendering runs for real against a
deck stub that accepts encoded key images."""
import pytest

from main import DeckController
from pages import BasePage

# NAV_KEYS indices, see main.py
HOME, SPOTIFY, HUE, KASA = 0, 1, 2, 3


class ImageDeck:
    """Deck stub with the XL's key image format; stores encoded key images."""

    def __init__(self):
        self.key_images = {}

    def key_count(self):
        return 32

    def key_image_format(self):
        return {"size": (96, 96), "format": "JPEG",
                "flip": (True, True), "rotation": 0}

    def set_key_image(self, key, image):
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
