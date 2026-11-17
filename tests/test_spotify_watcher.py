# tests/test_spotify_watcher.py
"""SpotifyWatcher: the MPRIS connection + PropertiesChanged listener that the
Spotify and Home pages share, driven by a fake connection whose filter queues
the test feeds by hand. The listener thread is real."""
import queue
import threading
import time
from dataclasses import replace

import pytest

from pages.spotify import PlayerSnapshot, SpotifyWatcher

PLAYING = PlayerSnapshot(status="Playing", artist="Zombie Hyperdrive",
                         title="Gigawatt", art_url="https://art/1")


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


class Harness:
    def __init__(self, mpris):
        self.mpris = mpris
        self.changes = []  # (snapshot, art) per on_change call
        self.arts = []  # urls fetched
        self.watcher = SpotifyWatcher(self._on_change, connect=lambda: mpris,
                                      fetch_art=self._fetch_art)

    def _on_change(self, snap, art):
        self.changes.append((snap, art))

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
