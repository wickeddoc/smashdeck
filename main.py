# main.py
import os
import signal
import sys
import yaml
import threading
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
from PIL import Image, ImageDraw, ImageFont

ASSETS_PATH = os.path.join(os.path.dirname(__file__), "icons")

# Nav bar: key index -> (page_name, icon_filename, label)
NAV_KEYS = {
    0: ("home", "home.png", "Home"),
    1: ("spotify", "spotify.png", "Spotify"),
    2: ("hue", "hue.png", "Hue"),
    3: ("kasa", "kasa.png", "Kasa"),
    4: ("tapo", "tapo.png", "Tapo"),
}


class DeckController:
    def __init__(self, config_path="config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
            print(self.config)
        self.deck = None
        self.current_page = None
        self.pages = {}
        self.page_history = []

    def start(self):
        devices = DeviceManager().enumerate()
        if not devices:
            raise RuntimeError("No Stream Deck found")

        self.deck = devices[0]
        self.deck.open()

        # Register clean shutdown
        def shutdown(sig, frame):
            print("\nShutting down...")
            self.deck.reset()
            self.deck.close()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)  # Ctrl+C
        signal.signal(signal.SIGTERM, shutdown)  # kill / systemd stop

        try:

            self.deck.reset()
            self.deck.set_brightness(60)
            self.deck.set_key_callback(self._on_key)

            # Register pages (imported from pages/)
            from pages.home import HomePage
            from pages.spotify import SpotifyPage
            from pages.hue import HuePage
            from pages.kasa import KasaPage
            from pages.tapo import TapoPage

            self.pages = {
                "home": HomePage(self),
                "spotify": SpotifyPage(self),
                "hue": HuePage(self),
                "kasa": KasaPage(self),
                "tapo": TapoPage(self),
            }

            self.switch_page("home")

            # Block main thread without busy-waiting
            threading.Event().wait()

        except Exception:
            import traceback

            traceback.print_exc()
        finally:
            self.deck.reset()
            self.deck.close()

    def switch_page(self, name):
        if self.current_page and self.current_page is not self.pages.get(name):
            self.current_page.deactivate()
            self.page_history.append(self._current_page_name())
        self.current_page = self.pages[name]
        self.render_nav_bar()
        self.current_page.render()
        self.current_page.activate()

    def go_back(self):
        if self.page_history:
            self.current_page.deactivate()
            name = self.page_history.pop()
            self.current_page = self.pages[name]
            self.render_nav_bar()
            self.current_page.render()
            self.current_page.activate()

    def _current_page_name(self):
        for name, page in self.pages.items():
            if page is self.current_page:
                return name
        return None

    def render_nav_bar(self):
        """Draw the persistent top-row navigation bar (keys 0-7)."""
        active = self._current_page_name()
        for key in range(8):
            if key in NAV_KEYS:
                page_name, icon, label = NAV_KEYS[key]
                highlight = (50, 50, 80) if page_name == active else None
                self.set_key_image(key, icon, label, color=highlight or (0, 0, 0))
            else:
                self.set_key_image(key, color=(0, 0, 0))

    def set_key_image(
        self, key, icon_filename=None, label=None, color=(0, 0, 0), highlight=None
    ):
        """Render an icon + optional text label onto a key.

        highlight: optional RGB tuple to draw a colored indicator bar at the
        top of the key (e.g. green for active state).
        """
        image = PILHelper.create_scaled_key_image(
            self.deck,
            (
                Image.open(os.path.join(ASSETS_PATH, icon_filename))
                if icon_filename
                else Image.new("RGB", (72, 72), color)
            ),
            margins=[0, 0, 20 if label else 0, 0],
        )
        draw = ImageDraw.Draw(image)
        if highlight:
            draw.rectangle([(0, 0), (image.width, 4)], fill=highlight)
        if label:
            try:
                font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 12)
            except OSError:
                font = ImageFont.load_default()
            draw.text(
                (image.width // 2, image.height - 5),
                label,
                font=font,
                anchor="mb",
                fill="white",
            )

        self.deck.set_key_image(key, PILHelper.to_native_key_format(self.deck, image))

    def _on_key(self, deck, key, state):
        if not state:  # key down only
            return
        # Top row (0-7): nav bar handles these
        if key in NAV_KEYS:
            page_name = NAV_KEYS[key][0]
            self.switch_page(page_name)
            return
        # Content area: delegate to current page
        if self.current_page:
            self.current_page.on_key(key)


if __name__ == "__main__":
    ctrl = DeckController()
    ctrl.start()
