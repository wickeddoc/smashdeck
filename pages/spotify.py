# pages/spotify.py
"""Spotify control page backed by MPRIS2 over DBus (via jeepney).

A small page-private `SpotifyMpris` helper owns one DBus connection and
exposes a single `snapshot()` returning all player state in one round-trip.
"""

from __future__ import annotations

import io
import threading
import traceback
import urllib.request
from dataclasses import dataclass
from queue import Empty, Full
from typing import Optional

from jeepney import DBusAddress, MatchRule, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.threading import open_dbus_connection, DBusRouter
from PIL import Image

from pages import BasePage
from pages.faces import SPOTIFY_GREEN, PictureFace, render_face

BUTTON_POSITION_VOLUME_UP = 13
BUTTON_POSITION_VOLUME_DOWN = 14

PLAYLIST_KEYS = (24, 25, 26, 27, 28)  # row 4; 29-30 free, 31 = cover art

SPOTIFY_BUS = "org.mpris.MediaPlayer2.spotify"
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"

_PROPS = DBusAddress(MPRIS_PATH, bus_name=SPOTIFY_BUS,
                    interface="org.freedesktop.DBus.Properties")
_PLAYER = DBusAddress(MPRIS_PATH, bus_name=SPOTIFY_BUS,
                     interface=PLAYER_IFACE)


# Note on the missing ``sender=`` field: the D-Bus daemon's ``AddMatch`` resolves
# well-known names server-side, so the bus only delivers matching signals. But
# jeepney's client-side ``MatchRule.matches`` does a strict string compare on
# the ``sender`` header field, and incoming signals carry the sender's unique
# name (e.g. ``:1.245``), not its well-known name. Keeping ``sender=`` in the
# rule made every PropertiesChanged signal fail the client-side filter. The
# remaining fields are specific enough on their own.
def _props_rule() -> MatchRule:
    return MatchRule(
        type="signal",
        interface="org.freedesktop.DBus.Properties",
        member="PropertiesChanged",
        path=MPRIS_PATH,
    )


def _name_owner_rule() -> MatchRule:
    rule = MatchRule(
        type="signal",
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
    artist: str = ""                # all artists, comma-separated
    lead_artist: str = ""           # the first one (whose photo is shown)
    title: str = ""
    album: str = ""
    volume: float = 0.5
    art_url: str = ""


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
                    snap.lead_artist = str(artist_val[0]) if artist_val else ""
                elif isinstance(artist_val, str):
                    snap.artist = snap.lead_artist = artist_val

                title_val = self._unwrap(meta.get("xesam:title"))
                if isinstance(title_val, str):
                    snap.title = title_val

                album_val = self._unwrap(meta.get("xesam:album"))
                if isinstance(album_val, str):
                    snap.album = album_val

                art_url_val = self._unwrap(meta.get("mpris:artUrl"))
                if isinstance(art_url_val, str):
                    snap.art_url = art_url_val

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

    def open_uri(self, uri: str):
        try:
            self._conn.send_and_get_reply(
                new_method_call(_PLAYER, "OpenUri", "s", (uri,))
            )
        except Exception:
            pass


def fetch_art(url: str) -> Optional[Image.Image]:
    """Fetch and decode a cover-art image. Returns None on any failure."""
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = resp.read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        traceback.print_exc()
        return None


def _start_daemon(fn):
    threading.Thread(target=fn, name="artist-photo", daemon=True).start()


class SpotifyWatcher:
    """Follows Spotify while started: one MPRIS connection plus a listener
    thread that calls ``on_change(snapshot, cover_art, artist_photo)``
    whenever the player state, the cover art or the artist photo changes
    (track skipped in the Spotify app, play pressed elsewhere, Spotify
    restarted). Used by the Spotify and Home pages.

    The cover art is fetched on the listener thread, so start() never waits
    on the network. With ``artist_photos`` (an ArtistPhotos), a cached photo
    of the lead artist comes with the track's report; an uncached one is
    looked up on a short-lived thread and reported when it arrives, so a slow
    lookup never holds up the listener or stop(). on_change calls never
    overlap, and none is made or still running once stop() returns.
    """

    def __init__(self, on_change, connect=SpotifyMpris, fetch_art=fetch_art,
                 artist_photos=None, start_thread=_start_daemon):
        self._on_change = on_change
        self._connect = connect
        self._fetch_art = fetch_art
        self._photos = artist_photos
        self._start_thread = start_thread
        self._report_lock = threading.Lock()  # one on_change at a time
        self._artist = ""  # lead artist of the last report
        self._artist_photo: Optional[Image.Image] = None
        self._mpris: Optional[SpotifyMpris] = None
        self._stop: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._filters = []  # open filter context managers
        self._props_q = None
        self._last: Optional[PlayerSnapshot] = None  # last state a page has seen
        self._art_url = ""
        self._art: Optional[Image.Image] = None

    @property
    def mpris(self) -> Optional[SpotifyMpris]:
        """The open connection, for player commands; None when stopped."""
        return self._mpris

    @property
    def art(self) -> Optional[Image.Image]:
        """Cover art of the current track, once fetched."""
        return self._art

    @property
    def artist_photo(self) -> Optional[Image.Image]:
        """Photo of the current lead artist, once found (artist_photos only)."""
        return self._artist_photo

    def start(self) -> PlayerSnapshot:
        """Connect, subscribe and start listening; returns the current state.
        Raises if the session bus can't be reached (nothing is left open)."""
        stop = threading.Event()
        self._stop = stop
        try:
            self._mpris = self._connect()
            self._props_q = self._subscribe(_props_rule())
            name_q = self._subscribe(_name_owner_rule())
        except Exception:
            self.stop()
            raise
        snap = self.snapshot()
        self._thread = threading.Thread(
            target=self._listen, args=(stop, self._mpris, self._props_q, name_q),
            name="spotify-listener", daemon=True)
        self._thread.start()
        return snap

    def _subscribe(self, rule):
        cm, q = self._mpris.subscribe(rule)
        self._filters.append(cm)
        return q

    def stop(self):
        if self._stop is not None:
            self._stop.set()
        with self._report_lock:
            pass  # wait out an on_change in progress; later ones see the stop
        if self._props_q is not None:
            try:
                self._props_q.put_nowait(None)  # wake the listener now
            except Full:
                pass  # a pending signal wakes it just the same
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        for cm in self._filters:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                pass
        self._filters = []
        self._props_q = None
        if self._mpris is not None:
            self._mpris.close()
            self._mpris = None
        self._stop = None
        self._last = None
        self._art_url = ""
        self._art = None
        self._artist = ""
        self._artist_photo = None

    def snapshot(self) -> PlayerSnapshot:
        """The player state right now, which the caller is about to show: the
        listener won't report it again. The empty player when stopped."""
        mpris = self._mpris
        snap = mpris.snapshot() if mpris is not None else PlayerSnapshot()
        self._last = snap
        return snap

    def _refresh_art(self, snap: PlayerSnapshot) -> bool:
        """Refetch cover art if the snapshot's URL differs from the cached one.

        Returns True if the cache was updated, False if the URL was unchanged.
        The URL is remembered even when the fetch fails, so a broken cover
        isn't retried until the track changes.
        """
        if snap.art_url != self._art_url:
            self._art_url = snap.art_url
            self._art = self._fetch_art(snap.art_url)
            return True
        return False

    def _refresh_artist(self, snap: PlayerSnapshot):
        """On a new lead artist, take its photo from the cache (or none yet).
        Returns (photo changed, artist to look up or None). Call with
        _report_lock held: the lookup thread updates the same state."""
        name = snap.lead_artist
        if name == self._artist:
            return False, None
        before = self._artist_photo
        self._artist, self._artist_photo, lookup = name, None, None
        if name and self._photos is not None:
            known, photo = self._photos.known(name)
            if known:
                self._artist_photo = photo
            else:
                lookup = name
        return self._artist_photo is not before, lookup

    def _report(self, stop: threading.Event, snap: PlayerSnapshot, force: bool):
        art_updated = self._refresh_art(snap)  # network: outside the lock
        with self._report_lock:
            photo_changed, lookup = self._refresh_artist(snap)
            changed = force or art_updated or photo_changed or snap != self._last
            self._last = snap
            # The stop check guards against stop() starting during a slow
            # cover fetch: the page may no longer be the one on the deck.
            if changed and not stop.is_set():
                self._on_change(snap, self._art, self._artist_photo)
        if lookup is not None:
            self._start_thread(lambda: self._look_up_artist(stop, lookup))

    def _look_up_artist(self, stop: threading.Event, name: str):
        """Runs on its own thread: fetch the photo, report it if still wanted."""
        try:
            photo = self._photos.lookup(name)
        except Exception:
            traceback.print_exc()
            return
        if photo is None:
            return
        with self._report_lock:
            if stop.is_set() or self._artist != name:
                return  # stopped, or another artist is playing by now
            self._artist_photo = photo
            self._on_change(self._last, self._art, photo)

    def _listen(self, stop, mpris, props_q, name_q):
        """Block on the filter queues; report when state actually changes."""
        try:
            self._report(stop, mpris.snapshot(), force=False)  # initial cover
        except Exception:
            traceback.print_exc()
        while not stop.is_set():
            got_signal = False
            force = False
            try:
                props_q.get(timeout=0.5)
                got_signal = True
                # Drain anything that came in while we were reporting.
                while True:
                    try:
                        props_q.get_nowait()
                    except Empty:
                        break
            except Empty:
                pass
            if stop.is_set():
                break
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
                self._report(stop, mpris.snapshot(), force)
            except Exception:
                traceback.print_exc()


class SpotifyPage(BasePage):
    def __init__(self, controller, watcher=None, artist_photos=None):
        """artist_photos: the ArtistPhotos shared with Home, or None (off)."""
        super().__init__(controller)
        self.artist_photos = artist_photos
        self._watcher = watcher or SpotifyWatcher(self._on_change, artist_photos=artist_photos)
        self._mpris: Optional[SpotifyMpris] = None
        spotify_cfg = controller.config.get("spotify", {})
        self._playlists = spotify_cfg.get("playlists", [])[: len(PLAYLIST_KEYS)]

    def _on_change(self, snap: PlayerSnapshot, art, artist_photo):
        self.render(snap)

    def activate(self):
        snap = self._watcher.start()
        self._mpris = self._watcher.mpris
        # Initial render shows controls + labels with key 31 blank. The
        # watcher fetches the cover art on its thread and reports back, so
        # activate() doesn't block the main thread on the HTTPS round-trip.
        self.render(snap)

    def deactivate(self):
        self._watcher.stop()
        self._mpris = None

    def _snap(self) -> PlayerSnapshot:
        return self._watcher.snapshot()

    def render(self, snap: Optional[PlayerSnapshot] = None):
        self.clear()
        if snap is None:
            snap = self._snap()

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

        photo = self._watcher.artist_photo
        if snap.artist and photo is not None:
            face = PictureFace("Artist", snap.artist, photo)
            self.ctrl.set_key_image(15, pil_image=render_face(face))
        elif snap.artist:
            self.ctrl.set_key_image(15, label=snap.artist[:12], color=SPOTIFY_GREEN)
        if snap.title:
            self.ctrl.set_key_image(23, label=snap.title[:12], color=(30, 215, 96))
        for i, pl in enumerate(self._playlists):
            self.ctrl.set_key_image(
                PLAYLIST_KEYS[i], f"playlist_{i + 1}.png", pl["name"][:12]
            )
        self.ctrl.set_key_image(31, pil_image=self._watcher.art)

    def on_key(self, key):
        mpris = self._mpris
        if mpris is None:
            return
        if key in PLAYLIST_KEYS:
            idx = PLAYLIST_KEYS.index(key)
            if idx < len(self._playlists):
                mpris.open_uri(self._playlists[idx]["uri"])
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
