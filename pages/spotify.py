# pages/spotify.py
"""Spotify control page backed by MPRIS2 over DBus (via jeepney).

A small page-private `SpotifyMpris` helper owns one DBus connection and
exposes a single `snapshot()` returning all player state in one round-trip.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from queue import Empty
from typing import Optional

from jeepney import DBusAddress, MatchRule, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.threading import open_dbus_connection, DBusRouter

from pages import BasePage

BUTTON_POSITION_VOLUME_UP = 13
BUTTON_POSITION_VOLUME_DOWN = 14

SPOTIFY_BUS = "org.mpris.MediaPlayer2.spotify"
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"

_PROPS = DBusAddress(MPRIS_PATH, bus_name=SPOTIFY_BUS,
                    interface="org.freedesktop.DBus.Properties")
_PLAYER = DBusAddress(MPRIS_PATH, bus_name=SPOTIFY_BUS,
                     interface=PLAYER_IFACE)


def _props_rule() -> MatchRule:
    return MatchRule(
        type="signal",
        sender=SPOTIFY_BUS,
        interface="org.freedesktop.DBus.Properties",
        member="PropertiesChanged",
        path=MPRIS_PATH,
    )


def _name_owner_rule() -> MatchRule:
    rule = MatchRule(
        type="signal",
        sender="org.freedesktop.DBus",
        interface="org.freedesktop.DBus",
        member="NameOwnerChanged",
    )
    rule.add_arg_condition(0, SPOTIFY_BUS)
    return rule


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
    """Thin adapter over jeepney for Spotify's MPRIS2 interface.

    Note: ``_dbus_conn`` is kept alongside the ``_conn`` router because
    ``DBusRouter.close()`` only stops the receiver thread; the underlying
    socket is owned by ``DBusConnection`` and must be closed separately.
    """

    def __init__(self):
        self._dbus_conn = open_dbus_connection(bus="SESSION")
        self._conn = DBusRouter(self._dbus_conn)

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass
        try:
            self._dbus_conn.close()
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

            shuffle = self._unwrap(props.get("Shuffle"))
            if isinstance(shuffle, bool):
                snap.shuffle = shuffle

            loop = self._unwrap(props.get("LoopStatus"))
            if isinstance(loop, str):
                snap.loop = loop

            volume = self._unwrap(props.get("Volume"))
            if isinstance(volume, (int, float)):
                snap.volume = float(volume)

            meta = self._unwrap(props.get("Metadata"))
            if isinstance(meta, dict):
                artist_val = self._unwrap(meta.get("xesam:artist"))
                if isinstance(artist_val, list):
                    snap.artist = ", ".join(str(a) for a in artist_val)
                elif isinstance(artist_val, str):
                    snap.artist = artist_val

                title_val = self._unwrap(meta.get("xesam:title"))
                if isinstance(title_val, str):
                    snap.title = title_val

                album_val = self._unwrap(meta.get("xesam:album"))
                if isinstance(album_val, str):
                    snap.album = album_val

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

    def subscribe(self, rule: MatchRule):
        """Register a match rule with the bus and open a filter queue.

        Returns (context_manager, queue). The caller must keep the context
        manager open until done listening.
        """
        cm = self._conn.filter(rule)
        q = cm.__enter__()
        try:
            self._conn.send_and_get_reply(message_bus.AddMatch(rule))
        except Exception:
            cm.__exit__(None, None, None)
            raise
        return cm, q

    # --- write API (silent no-op if Spotify isn't running) ---

    def _player_call(self, member: str):
        try:
            self._conn.send_and_get_reply(new_method_call(_PLAYER, member))
        except Exception:
            pass

    def _set_prop(self, name: str, signature: str, value):
        try:
            msg = new_method_call(
                _PROPS, "Set", "ssv",
                (PLAYER_IFACE, name, (signature, value)),
            )
            self._conn.send_and_get_reply(msg)
        except Exception:
            pass

    def play_pause(self):
        self._player_call("PlayPause")

    def next(self):
        self._player_call("Next")

    def previous(self):
        self._player_call("Previous")

    def toggle_shuffle(self):
        self._set_prop("Shuffle", "b", not self.snapshot().shuffle)

    def set_loop(self, mode: str):
        if mode in ("None", "Track", "Playlist"):
            self._set_prop("LoopStatus", "s", mode)

    def cycle_loop(self):
        cycle = {"None": "Playlist", "Playlist": "Track", "Track": "None"}
        self.set_loop(cycle.get(self.snapshot().loop, "None"))

    def nudge_volume(self, delta: float):
        current = self.snapshot().volume
        new = max(0.0, min(1.0, current + delta))
        self._set_prop("Volume", "d", new)


class SpotifyPage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        self._mpris: Optional[SpotifyMpris] = None
        self._last_state: Optional[PlayerSnapshot] = None
        self._stop: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._props_cm = None
        self._props_q = None
        self._name_cm = None
        self._name_q = None

    def activate(self):
        self._mpris = SpotifyMpris()
        self._stop = threading.Event()
        self._props_cm, self._props_q = self._mpris.subscribe(_props_rule())
        self._name_cm, self._name_q = self._mpris.subscribe(_name_owner_rule())
        self._last_state = self._mpris.snapshot()
        self.render()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def deactivate(self):
        if self._stop is not None:
            self._stop.set()
        # Listener wakes within the 0.5s queue.get timeout and exits because
        # _stop is set. Then we tear down the filters and close the conn.
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._props_cm is not None:
            try:
                self._props_cm.__exit__(None, None, None)
            except Exception:
                pass
            self._props_cm = None
        if self._name_cm is not None:
            try:
                self._name_cm.__exit__(None, None, None)
            except Exception:
                pass
            self._name_cm = None
        self._props_q = None
        self._name_q = None
        if self._mpris is not None:
            self._mpris.close()
            self._mpris = None
        self._stop = None
        self._last_state = None

    def _listen(self):
        """Block on filter queues; re-render when state actually changes."""
        stop = self._stop
        props_q = self._props_q
        name_q = self._name_q
        mpris = self._mpris
        if stop is None or props_q is None or name_q is None or mpris is None:
            return
        while not stop.is_set():
            got_signal = False
            force = False
            try:
                props_q.get(timeout=0.5)
                got_signal = True
                # Drain anything that came in while we were rendering.
                while True:
                    try:
                        props_q.get_nowait()
                    except Empty:
                        break
            except Empty:
                pass
            try:
                while True:
                    name_q.get_nowait()
                    got_signal = True
                    force = True
            except Empty:
                pass

            if not got_signal:
                continue
            try:
                snap = mpris.snapshot()
                if force or snap != self._last_state:
                    self.render(snap)
            except Exception:
                traceback.print_exc()

    def _snap(self) -> PlayerSnapshot:
        if self._mpris is None:
            return PlayerSnapshot()
        return self._mpris.snapshot()

    def render(self, snap: Optional[PlayerSnapshot] = None):
        self.clear()
        if snap is None:
            snap = self._snap()
        self._last_state = snap

        playing = snap.status == "Playing"
        player_status = "pause.png" if playing else "play.png"
        self.ctrl.set_key_image(
            8, player_status, highlight=(30, 215, 96) if playing else None
        )
        self.ctrl.set_key_image(9, "prev.png")
        self.ctrl.set_key_image(10, "next.png")
        self.ctrl.set_key_image(
            11, "shuffle.png",
            highlight=(30, 215, 96) if snap.shuffle else None,
        )

        repeat_icon = "repeat_one.png" if snap.loop == "Track" else "repeat.png"
        repeat_highlight = (30, 215, 96) if snap.loop in ("Playlist", "Track") else None
        self.ctrl.set_key_image(12, repeat_icon, highlight=repeat_highlight)

        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_DOWN, "vol_down.png")
        self.ctrl.set_key_image(BUTTON_POSITION_VOLUME_UP, "vol_up.png")

        if snap.artist:
            self.ctrl.set_key_image(15, label=snap.artist[:12], color=(30, 215, 96))
        if snap.title:
            self.ctrl.set_key_image(23, label=snap.title[:12], color=(30, 215, 96))
        if snap.album:
            self.ctrl.set_key_image(31, label=snap.album[:12], color=(30, 215, 96))

    def on_key(self, key):
        mpris = self._mpris
        if mpris is None:
            return
        actions = {
            8: mpris.play_pause,
            9: mpris.previous,
            10: mpris.next,
            11: mpris.toggle_shuffle,
            12: mpris.cycle_loop,
            BUTTON_POSITION_VOLUME_DOWN: lambda: mpris.nudge_volume(-0.05),
            BUTTON_POSITION_VOLUME_UP: lambda: mpris.nudge_volume(+0.05),
        }
        if key in actions:
            actions[key]()
            self.render()  # immediate UI feedback; listener will also fire
