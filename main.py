# main.py
import os
import signal
import sys
import time
import traceback
from typing import Optional

import yaml
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.Transport.Transport import TransportError

ASSETS_PATH = os.path.join(os.path.dirname(__file__), "icons")

# Nav bar: key index -> (page_name, icon_filename, label)
NAV_KEYS = {
    0: ("home", "home.png", "Home"),
    1: ("spotify", "spotify.png", "Spotify"),
    2: ("hue", "hue.png", "Hue"),
    3: ("kasa", "kasa.png", "Kasa"),
    4: ("tapo", "tapo.png", "Tapo"),
    6: ("monitor", "monitor.png", "Monitor"),
}

RESTART_KEY = 7

# How often the main thread checks that the deck is still plugged in.
DECK_POLL_SECONDS = 1.0

FONT_PATH = "/usr/share/fonts/TTF/DejaVuSans.ttf"
BOLD_FONT_PATH = "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
LABEL_STRIP = 20  # px below the icon reserved for the label
NAV_ACTIVE_COLOR = (110, 170, 255)  # label strip of the current page's nav key
LABEL_ON_STRIP = (10, 20, 40)  # label text drawn on a coloured strip


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


class DeckController:
    def __init__(self, config_path="config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.deck = None
        self._key_size = (72, 72)
        self.current_page = None
        self.pages = {}
        self._restarting = False  # Restart key: deck closed, os.execv pending

    def start(self) -> int:
        """Open the first Stream Deck and run until it is unplugged.

        Returns the process exit code: non-zero when no deck is found or the
        deck went away, so a supervisor (the systemd user service,
        Restart=on-failure) starts SmashDeck again. SIGINT/SIGTERM exit 0
        via _shutdown.
        """
        devices = DeviceManager().enumerate()
        if not devices:
            print("No Stream Deck found")
            return 1

        self.deck = devices[0]
        self.deck.open()

        deck_type = self.deck.deck_type()
        self._key_size = self.deck.key_image_format()["size"]
        known = ("XL", "Mk.2", "Original", "Mini", "Plus")
        is_known = any(k.lower() in deck_type.lower() for k in known)
        if is_known:
            print(
                f"Stream Deck: {deck_type} "
                f"(key images: {self._key_size[0]}x{self._key_size[1]})"
            )
        else:
            print(
                f"Warning: untested Stream Deck model '{deck_type}'; "
                f"proceeding anyway. (key images: "
                f"{self._key_size[0]}x{self._key_size[1]})"
            )

        # Register clean shutdown
        signal.signal(signal.SIGINT, self._shutdown)  # Ctrl+C
        signal.signal(signal.SIGTERM, self._shutdown)  # kill / systemd stop

        return self.run()

    def run(self) -> int:
        """Drive the opened deck until it is unplugged; returns the exit code."""
        try:
            self.deck.reset()
            self.deck.set_brightness(60)
            self.deck.set_key_callback(self._on_key)
            self.pages = self._build_pages()
            self.switch_page("home")
            self._wait_while_connected()
            print("Stream Deck disconnected; exiting so the service can restart SmashDeck")
            return 1
        except Exception:
            traceback.print_exc()
            return 1
        finally:
            self._deactivate_current_page()
            self._release_deck()

    def _build_pages(self):
        from pages.artist_photos import ArtistPhotos
        from pages.home import HomePage
        from pages.hue import HuePage
        from pages.kasa import KasaPage
        from pages.monitor import MonitorPage
        from pages.monitor.weather_feed import WeatherFeed
        from pages.spotify import SpotifyPage
        from pages.tapo import TapoPage

        # Shared by the pages showing them, so switching pages doesn't refetch:
        # one weather reading (Home, Monitor), one artist-photo cache (Home,
        # Spotify; None when the optional feature is off).
        weather = WeatherFeed.from_config(self.config.get("monitor") or {})
        photos = ArtistPhotos.from_config(self.config.get("spotify") or {})
        return {
            "home": HomePage(self, weather=weather, artist_photos=photos),
            "spotify": SpotifyPage(self, artist_photos=photos),
            "hue": HuePage(self),
            "kasa": KasaPage(self),
            "tapo": TapoPage(self),
            "monitor": MonitorPage(self, weather=weather),
        }

    def _wait_while_connected(self):
        """Block the main thread until the deck goes away.

        The library's reader thread closes the device when a read fails
        (is_open() turns False); connected() re-enumerates USB to catch an
        unplug that doesn't surface as a read error. While a Restart re-exec
        is pending the deck is closed on purpose, so keep waiting for execv.
        Signals (SIGINT/SIGTERM) interrupt the sleep and unwind via _shutdown.
        """
        while self._restarting or (self.deck.is_open() and self.deck.connected()):
            time.sleep(DECK_POLL_SECONDS)

    def _deactivate_current_page(self):
        """Stop the visible page's background work; safe to call twice."""
        page, self.current_page = self.current_page, None
        if page is None:
            return
        try:
            page.deactivate()
        except Exception:
            traceback.print_exc()

    def _release_deck(self):
        """Reset and close the deck, tolerating one that is already gone."""
        for release in (self.deck.reset, self.deck.close):
            try:
                release()
            except TransportError as e:  # the deck is already unplugged
                print(f"Stream Deck {release.__name__} skipped: {e!r}")

    def _shutdown(self, sig=None, frame=None):
        """Signal handler: stop the visible page, then unwind via SystemExit.

        The deck is reset and closed exactly once, by run()'s finally.
        Deactivating first keeps a page thread (Monitor's poll) from writing
        to a reset or closed deck.
        """
        print("\nShutting down...")
        self._deactivate_current_page()
        sys.exit(0)

    def switch_page(self, name):
        page = self.pages[name]
        # Re-selecting the active page only re-renders it: activate() must
        # stay paired with exactly one deactivate(), or pages that start
        # resources there (SpotifyPage's listener thread) leak them.
        changed = page is not self.current_page
        if changed and self.current_page:
            self.current_page.deactivate()
        self.current_page = page
        self.render_nav_bar()
        page.render()
        if changed:
            page.activate()

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
                strip = NAV_ACTIVE_COLOR if page_name == active else None
                self.set_key_image(key, icon, label, label_bg=strip)
            elif key == RESTART_KEY:
                self.set_key_image(key, "refresh.png", "Restart")
            else:
                self.set_key_image(key, color=(0, 0, 0))

    def set_key_image(
        self,
        key,
        icon_filename=None,
        label=None,
        color=(0, 0, 0),
        highlight=None,
        pil_image: Optional[Image.Image] = None,
        label_bg=None,
    ):
        """Render an icon + optional text label onto a key.

        Source precedence: pil_image > icon_filename > blank colour.

        highlight: optional RGB tuple to draw a coloured indicator bar at the
        top of the key (e.g. green for active state).

        label_bg: optional RGB tuple; fills the label strip below the icon and
        draws the label in bold dark text on it (marks the active nav key).
        """
        if pil_image is not None:
            source = pil_image
        elif icon_filename:
            source = Image.open(os.path.join(ASSETS_PATH, icon_filename))
        else:
            source = Image.new("RGB", self._key_size, color)

        image = PILHelper.create_scaled_key_image(
            self.deck,
            source,
            margins=[0, 0, LABEL_STRIP if label else 0, 0],
        )
        draw = ImageDraw.Draw(image)

        if highlight:
            draw.rectangle([(0, 0), (image.width, 4)], fill=highlight)
        if label:
            if label_bg:
                draw.rectangle(
                    [(0, image.height - LABEL_STRIP), (image.width, image.height)],
                    fill=label_bg,
                )
            draw.text(
                (image.width // 2, image.height - 5),
                label,
                font=_font(BOLD_FONT_PATH if label_bg else FONT_PATH, 12),
                anchor="mb",
                fill=LABEL_ON_STRIP if label_bg else "white",
            )

        native = PILHelper.to_native_key_format(self.deck, image)
        # An XL key image is several HID reports and the transport locks only
        # per report: hold the deck's update lock so the reader thread (nav
        # keys) and a page thread can't interleave one image's reports.
        with self.deck:
            self.deck.set_key_image(key, native)

    def _on_key(self, deck, key, state):
        if not state:  # key down only
            return
        # Runs on the Stream Deck library's reader thread, which only catches
        # its own TransportError: anything else escaping here kills the thread
        # and the deck stops responding to every key, Restart included.
        try:
            self._dispatch_key(key)
        except Exception:
            traceback.print_exc()

    def _dispatch_key(self, key):
        # Top row (0-7): nav bar handles these
        if key in NAV_KEYS:
            page_name = NAV_KEYS[key][0]
            self.switch_page(page_name)
            return
        if key == RESTART_KEY:
            self._restart()
            return
        # Content area: delegate to current page
        if self.current_page:
            self.current_page.on_key(key)

    def _restart(self):
        """Re-exec the running process in place after resetting the deck."""
        print("\nRestarting...")
        self._restarting = True  # the main thread must not read this as an unplug
        try:
            if self.current_page:
                self.current_page.deactivate()
            self.deck.reset()
            self.deck.close()
        except Exception:
            traceback.print_exc()
        try:
            os.execv(sys.executable, [sys.executable, *sys.argv])
        except Exception:
            # The deck is closed now: let the main thread see that and exit
            # non-zero, so the service restarts SmashDeck instead.
            self._restarting = False
            raise


if __name__ == "__main__":
    sys.exit(DeckController().start())
