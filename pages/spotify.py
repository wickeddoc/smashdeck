# pages/spotify.py
import subprocess
import threading
from pages import BasePage

POLL_INTERVAL = 2  # seconds

BUTTON_POSITION_VOLUME_UP = 13
BUTTON_POSITION_VOLUME_DOWN = 14


class SpotifyPage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        self._stop_event = threading.Event()
        self._poll_thread = None
        self._last_state = None

    def _ctl(self, cmd, *args):
        result = subprocess.run(
            ["playerctl", "--player=spotify", cmd, *args],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _get_status(self):
        """Returns 'Playing', 'Paused', or 'Stopped'."""
        return self._ctl("status")

    def _get_now_playing_artist(self):
        return self._ctl("metadata", "--format", "{{artist}}")

    def _get_now_playing_title(self):
        return self._ctl("metadata", "--format", "{{title}}")

    def _get_now_playing_album(self):
        return self._ctl("metadata", "--format", "{{album}}")

    def _get_volume(self):
        try:
            return float(self._ctl("volume"))
        except ValueError:
            return 0.5

    def _get_shuffle(self):
        """Returns True if shuffle is enabled."""
        return self._ctl("shuffle") == "On"

    def _get_loop(self):
        """Returns 'None', 'Playlist', or 'Track'."""
        return self._ctl("loop")

    def _cycle_loop(self):
        """Cycle through loop modes: None -> Playlist -> Track -> None."""
        cycle = {"None": "Playlist", "Playlist": "Track", "Track": "None"}
        current = self._get_loop()
        self._ctl("loop", cycle.get(current, "None"))

    def _snapshot(self):
        """Capture current player state as a comparable tuple."""
        return (
            self._get_status(),
            self._get_shuffle(),
            self._get_loop(),
            self._get_now_playing_artist(),
            self._get_now_playing_title(),
            self._get_now_playing_album(),
        )

    def _poll_loop(self):
        while not self._stop_event.wait(POLL_INTERVAL):
            state = self._snapshot()
            if state != self._last_state:
                self._last_state = state
                self.render()

    def activate(self):
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def deactivate(self):
        self._stop_event.set()
        self._poll_thread = None
        self._last_state = None

    def render(self):
        self.clear()

        playing = self._get_status() == "Playing"
        shuffle = self._get_shuffle()
        loop = self._get_loop()

        player_status = "pause.png" if playing else "play.png"
        self.ctrl.set_key_image(
            8, player_status, highlight=(30, 215, 96) if playing else None
        )
        self.ctrl.set_key_image(9, "prev.png")
        self.ctrl.set_key_image(10, "next.png")
        self.ctrl.set_key_image(
            11,
            "shuffle.png",
            highlight=(30, 215, 96) if shuffle else None,
        )

        # Repeat: different icon for track mode, highlight when active
        repeat_icon = "repeat_one.png" if loop == "Track" else "repeat.png"
        repeat_highlight = (30, 215, 96) if loop in ("Playlist", "Track") else None
        self.ctrl.set_key_image(12, repeat_icon, highlight=repeat_highlight)

        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_DOWN, "vol_down.png")
        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_UP, "vol_up.png")

        # Show current artist a key (truncated)
        artist = self._get_now_playing_artist()
        if artist:
            self.ctrl.set_key_image(15, label=artist[:12], color=(30, 215, 96))

        # Show current track on a key (truncated)
        title = self._get_now_playing_title()
        if title:
            self.ctrl.set_key_image(23, label=title[:12], color=(30, 215, 96))

        # Show current album on a key (truncated)
        album = self._get_now_playing_album()
        if album:
            self.ctrl.set_key_image(31, label=album[:12], color=(30, 215, 96))

    def on_key(self, key):
        actions = {
            8: lambda: self._ctl("play-pause"),
            9: lambda: self._ctl("previous"),
            10: lambda: self._ctl("next"),
            11: lambda: self._ctl("shuffle", "toggle"),
            12: self._cycle_loop,
            BUTTON_POSITION_VOLUME_DOWN: lambda: self._ctl("volume", "0.05-"),
            BUTTON_POSITION_VOLUME_UP: lambda: self._ctl("volume", "0.05+"),
        }
        if key in actions:
            actions[key]()
            self._last_state = self._snapshot()
            self.render()  # refresh state
