# pages/spotify.py
"""Spotify control page backed by MPRIS2 over DBus (via jeepney).

A small page-private `SpotifyMpris` helper owns one DBus connection and
exposes a single `snapshot()` returning all player state in one round-trip.
This task implements only PlaybackStatus; subsequent tasks expand it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from jeepney import DBusAddress, new_method_call
from jeepney.io.threading import open_dbus_connection, DBusRouter

from pages import BasePage

BUTTON_POSITION_VOLUME_UP = 13
BUTTON_POSITION_VOLUME_DOWN = 14

SPOTIFY_BUS = "org.mpris.MediaPlayer2.spotify"
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"

_PROPS = DBusAddress(MPRIS_PATH, bus_name=SPOTIFY_BUS,
                    interface="org.freedesktop.DBus.Properties")


@dataclass
class PlayerSnapshot:
    status: str = "Stopped"         # "Playing" / "Paused" / "Stopped"
    shuffle: bool = False
    loop: str = "None"              # "None" / "Track" / "Playlist"
    artist: str = ""
    title: str = ""
    album: str = ""
    volume: float = 0.5


class SpotifyMpris:
    """Thin adapter over jeepney for Spotify's MPRIS2 interface."""

    def __init__(self):
        self._conn = DBusRouter(open_dbus_connection(bus="SESSION"))

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # --- read API ---

    def snapshot(self) -> PlayerSnapshot:
        """One round-trip read of all player properties.

        Returns safe defaults if Spotify isn't running.
        """
        try:
            msg = new_method_call(_PROPS, "GetAll", "s", (PLAYER_IFACE,))
            reply = self._conn.send_and_get_reply(msg)
            props = reply.body[0]  # a{sv}: dict[str, (sig, value)]
            snap = PlayerSnapshot()
            status = self._unwrap(props.get("PlaybackStatus"))
            if isinstance(status, str):
                snap.status = status
            return snap
        except Exception:
            return PlayerSnapshot()

    @staticmethod
    def _unwrap(variant):
        """jeepney returns variants as (signature, value) tuples."""
        if variant is None:
            return None
        if isinstance(variant, tuple) and len(variant) == 2:
            return variant[1]
        return variant


class SpotifyPage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        self._mpris: Optional[SpotifyMpris] = None
        self._last_state: Optional[PlayerSnapshot] = None

    def activate(self):
        self._mpris = SpotifyMpris()

    def deactivate(self):
        if self._mpris is not None:
            self._mpris.close()
            self._mpris = None
        self._last_state = None

    def _snap(self) -> PlayerSnapshot:
        if self._mpris is None:
            return PlayerSnapshot()
        return self._mpris.snapshot()

    def render(self):
        self.clear()
        snap = self._snap()
        self._last_state = snap

        playing = snap.status == "Playing"
        player_status = "pause.png" if playing else "play.png"
        self.ctrl.set_key_image(
            8, player_status, highlight=(30, 215, 96) if playing else None
        )
        self.ctrl.set_key_image(9, "prev.png")
        self.ctrl.set_key_image(10, "next.png")
        self.ctrl.set_key_image(11, "shuffle.png")
        self.ctrl.set_key_image(12, "repeat.png")
        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_DOWN, "vol_down.png")
        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_UP, "vol_up.png")

    def on_key(self, key):
        del key  # wired in Task 4
