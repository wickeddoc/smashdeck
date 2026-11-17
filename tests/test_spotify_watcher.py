# tests/test_spotify_watcher.py
"""SpotifyWatcher: the MPRIS connection + PropertiesChanged listener that the
Spotify and Home pages share, driven by a fake connection whose filter queues
the test feeds by hand. The listener thread is real."""
import queue
import threading
import time
from dataclasses import replace

import pytest

from pages.spotify import PlayerSnapshot, SpotifyMpris, SpotifyWatcher

PLAYING = PlayerSnapshot(status="Playing", artist="Zombie Hyperdrive",
                         lead_artist="Zombie Hyperdrive", title="Gigawatt",
                         art_url="https://art/1")


class FakeFilter:
    def __init__(self):
        self.exited = False

    def __exit__(self, *exc):
        self.exited = True


class FakeMpris:
    def __init__(self, snap=PLAYING):
        self.snap = snap
        self.filters = []
        self.queues = []  # [PropertiesChanged, NameOwnerChanged], as subscribed
        self.closed = False

    def snapshot(self):
        return self.snap

    def subscribe(self, rule):
        self.filters.append(FakeFilter())
        self.queues.append(queue.Queue())
        return self.filters[-1], self.queues[-1]

    def close(self):
        self.closed = True

    # signals
    def props_changed(self, **changes):
        self.snap = replace(self.snap, **changes)
        self.queues[0].put("PropertiesChanged")

    def spotify_restarted(self):
        self.queues[1].put("NameOwnerChanged")


def wait_until(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


class FakePhotos:
    """Stands in for ArtistPhotos: `cached` answers known(), `found` lookup()."""

    def __init__(self):
        self.cached = {}
        self.found = {}
        self.lookups = []

    def known(self, artist):
        return artist in self.cached, self.cached.get(artist)

    def lookup(self, artist):
        self.lookups.append(artist)
        return self.found.get(artist)


class Harness:
    def __init__(self, mpris, photos=None):
        self.mpris = mpris
        self.changes = []  # (snapshot, art) per on_change call
        self.photos = []  # artist photo per on_change call
        self.arts = []  # urls fetched
        self.pending = []  # artist lookups waiting to "run on their thread"
        self.watcher = SpotifyWatcher(self._on_change, connect=lambda: mpris,
                                      fetch_art=self._fetch_art, artist_photos=photos,
                                      start_thread=self.pending.append)

    def _on_change(self, snap, art, photo):
        self.changes.append((snap, art))
        self.photos.append(photo)

    def run_lookups(self):
        while self.pending:
            self.pending.pop(0)()

    def _fetch_art(self, url):
        self.arts.append(url)
        return f"image of {url}" if url else None


@pytest.fixture
def h():
    harness = Harness(FakeMpris())
    yield harness
    harness.watcher.stop()


def listener_threads():
    return [t for t in threading.enumerate() if t.name == "spotify-listener"]


def test_start_returns_the_current_snapshot(h):
    assert h.watcher.start() == PLAYING
    assert h.watcher.mpris is h.mpris


def test_cover_art_is_fetched_off_the_caller_thread_and_reported(h):
    h.watcher.start()
    assert wait_until(lambda: h.changes)
    assert h.changes == [(PLAYING, "image of https://art/1")]
    assert h.watcher.art == "image of https://art/1"


def test_a_property_change_reports_the_new_state(h):
    h.watcher.start()
    wait_until(lambda: h.changes)
    h.mpris.props_changed(status="Paused")
    assert wait_until(lambda: len(h.changes) == 2)
    assert h.changes[-1][0].status == "Paused"
    assert h.arts == ["https://art/1"]  # same cover: not fetched again


def test_a_signal_without_a_real_change_is_ignored(h):
    h.watcher.start()
    wait_until(lambda: h.changes)
    h.mpris.props_changed()  # e.g. a Volume-only signal Spotify sends
    h.mpris.props_changed(title="Next song", art_url="https://art/2")
    assert wait_until(lambda: len(h.changes) == 2)
    time.sleep(0.1)
    assert [snap.title for snap, _ in h.changes] == ["Gigawatt", "Next song"]
    assert h.changes[-1][1] == "image of https://art/2"


def test_spotify_restarting_always_reports(h):
    h.watcher.start()
    wait_until(lambda: h.changes)
    h.mpris.spotify_restarted()
    assert wait_until(lambda: len(h.changes) == 2)


def test_snapshot_marks_the_state_as_seen(h):
    h.watcher.start()
    wait_until(lambda: h.changes)
    h.mpris.snap = replace(PLAYING, status="Paused")
    assert h.watcher.snapshot().status == "Paused"  # a page drew it already
    h.mpris.queues[0].put("PropertiesChanged")
    time.sleep(0.2)
    assert len(h.changes) == 1


def test_snapshot_before_start_is_the_empty_player():
    w = SpotifyWatcher(lambda snap, art: None, connect=FakeMpris)
    assert w.snapshot() == PlayerSnapshot()


def test_stop_ends_the_thread_and_closes_everything(h):
    h.watcher.start()
    wait_until(lambda: h.changes)
    h.watcher.stop()
    assert listener_threads() == []
    assert all(f.exited for f in h.mpris.filters)
    assert h.mpris.closed
    assert h.watcher.mpris is None
    assert h.watcher.art is None


def test_no_change_is_reported_after_stop(h):
    h.watcher.start()
    wait_until(lambda: h.changes)
    h.watcher.stop()
    h.mpris.props_changed(status="Paused")
    time.sleep(0.1)
    assert len(h.changes) == 1


def test_stop_without_start_is_harmless():
    SpotifyWatcher(lambda snap, art: None, connect=FakeMpris).stop()


def test_a_failed_start_leaves_nothing_open():
    mpris = FakeMpris()

    def subscribe_fails(rule):
        raise OSError("DBus said no")

    mpris.subscribe = subscribe_fails
    w = SpotifyWatcher(lambda snap, art: None, connect=lambda: mpris)
    with pytest.raises(OSError):
        w.start()
    assert mpris.closed
    assert w.mpris is None
    assert listener_threads() == []


# --- artist photos (optional ArtistPhotos) ------------------------------------

@pytest.fixture
def ph():
    photos = FakePhotos()
    harness = Harness(FakeMpris(), photos)
    harness.fake_photos = photos
    yield harness
    harness.watcher.stop()


def test_without_artist_photos_the_photo_is_always_none(h):
    h.watcher.start()
    assert wait_until(lambda: h.changes)
    assert h.photos == [None]
    assert h.pending == []


def test_a_cached_photo_comes_with_the_first_report(ph):
    ph.fake_photos.cached["Zombie Hyperdrive"] = "photo of ZH"
    ph.watcher.start()
    assert wait_until(lambda: ph.changes)
    assert ph.photos == ["photo of ZH"]
    assert ph.watcher.artist_photo == "photo of ZH"
    assert ph.pending == []


def test_an_uncached_photo_is_looked_up_off_the_listener_and_reported(ph):
    ph.fake_photos.found["Zombie Hyperdrive"] = "photo of ZH"
    ph.watcher.start()
    assert wait_until(lambda: ph.changes and ph.pending)
    assert ph.photos == [None]  # the key shows the name meanwhile
    ph.run_lookups()
    assert ph.photos == [None, "photo of ZH"]
    assert ph.changes[-1] == (PLAYING, "image of https://art/1")


def test_no_photo_found_means_no_second_report(ph):
    ph.watcher.start()
    assert wait_until(lambda: ph.pending)
    ph.run_lookups()
    assert ph.fake_photos.lookups == ["Zombie Hyperdrive"]
    assert ph.photos == [None]


def test_the_photo_stays_while_the_artist_does(ph):
    ph.fake_photos.cached["Zombie Hyperdrive"] = "photo of ZH"
    ph.watcher.start()
    assert wait_until(lambda: ph.changes)
    ph.mpris.props_changed(title="Next song", art_url="https://art/2")
    assert wait_until(lambda: len(ph.changes) == 2)
    assert ph.photos == ["photo of ZH", "photo of ZH"]
    assert ph.fake_photos.lookups == []


def test_a_new_artist_drops_the_old_photo_at_once(ph):
    ph.fake_photos.cached["Zombie Hyperdrive"] = "photo of ZH"
    ph.watcher.start()
    assert wait_until(lambda: ph.changes)
    ph.mpris.props_changed(artist="Boy Harsher", lead_artist="Boy Harsher")
    assert wait_until(lambda: len(ph.changes) == 2)
    assert ph.photos[-1] is None


def test_a_lookup_for_an_artist_no_longer_playing_is_dropped(ph):
    ph.fake_photos.found["Zombie Hyperdrive"] = "photo of ZH"
    ph.watcher.start()
    assert wait_until(lambda: ph.pending)
    ph.mpris.props_changed(artist="Boy Harsher", lead_artist="Boy Harsher")
    assert wait_until(lambda: len(ph.changes) == 2)
    ph.run_lookups()
    assert ph.photos == [None, None]


def test_a_lookup_finishing_after_stop_reports_nothing(ph):
    ph.fake_photos.found["Zombie Hyperdrive"] = "photo of ZH"
    ph.watcher.start()
    assert wait_until(lambda: ph.pending)
    ph.watcher.stop()
    ph.run_lookups()
    assert ph.photos == [None]


def test_a_failing_lookup_is_logged_not_raised(ph, capsys):
    def broken(artist):
        raise RuntimeError("bug")

    ph.fake_photos.lookup = broken
    ph.watcher.start()
    assert wait_until(lambda: ph.pending)
    ph.run_lookups()
    assert "RuntimeError" in capsys.readouterr().err


def test_stop_waits_for_a_photo_report_in_progress():
    entered, release = threading.Event(), threading.Event()

    def slow_page(snap, art, photo):
        if photo is not None:  # the lookup thread's report
            entered.set()
            release.wait(2)

    photos = FakePhotos()
    photos.found["Zombie Hyperdrive"] = "photo of ZH"
    w = SpotifyWatcher(slow_page, connect=FakeMpris, fetch_art=lambda url: "img",
                       artist_photos=photos)  # real lookup threads
    w.start()
    assert entered.wait(2)  # the page is drawing the photo
    stopper = threading.Thread(target=w.stop)
    stopper.start()
    stopper.join(0.2)
    assert stopper.is_alive()  # must not return while the page still draws
    release.set()
    stopper.join(2)
    assert not stopper.is_alive()


# --- the lead artist comes from MPRIS metadata ---------------------------------

class FakeConn:
    def __init__(self, props):
        self.props = props

    def send_and_get_reply(self, msg):
        class Reply:
            body = (self.props,)
        return Reply()


@pytest.mark.parametrize("artists, joined, lead", [
    (("as", ["Daft Punk", "Pharrell Williams"]), "Daft Punk, Pharrell Williams", "Daft Punk"),
    (("as", ["Crosby, Stills, Nash & Young"]), "Crosby, Stills, Nash & Young",
     "Crosby, Stills, Nash & Young"),
    (("s", "Boy Harsher"), "Boy Harsher", "Boy Harsher"),
    (("as", []), "", ""),
])
def test_snapshot_reads_all_artists_and_the_lead_artist(artists, joined, lead):
    mpris = SpotifyMpris.__new__(SpotifyMpris)  # no DBus connection
    mpris._conn = FakeConn({"Metadata": ("a{sv}", {"xesam:artist": artists})})
    snap = mpris.snapshot()
    assert (snap.artist, snap.lead_artist) == (joined, lead)
