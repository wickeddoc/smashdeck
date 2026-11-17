# tests/test_home_page.py
"""HomePage: the overview (CPU/GPU temperature, weather, Spotify) and the
brightness column, with an injected sampler, weather fetch and Spotify
watcher. render_face is swapped for identity so each key's recorded "image"
is the face it would show; test_home_faces_render_* draw them for real."""
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest
from PIL import Image

from pages import home
from pages.faces import PictureFace
from pages.home import SPOTIFY_GREEN, HomePage
from pages.monitor.sources import SystemSample
from pages.monitor.tiles import GREEN, RED
from pages.monitor.weather import parse
from pages.monitor.weather_feed import WeatherFeed
from pages.spotify import PlayerSnapshot

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "openmeteo.json")
LOCATION = {"latitude": 49.63277, "longitude": 6.26459}
PLAYING = PlayerSnapshot(status="Playing", artist="Zombie Hyperdrive",
                         title="Gigawatt", art_url="https://art/1")
COVER = Image.new("RGB", (640, 640), (120, 40, 160))
PHOTO = Image.new("RGB", (144, 144), (90, 90, 90))
MUSIC_KEYS = {16, 17, 18}


class FakeSampler:
    def __init__(self):
        self.calls = 0
        self.resets = 0
        self.next = SystemSample(cpu_temp=54.0, gpu_temp=60.0)

    def reset(self):
        self.resets += 1

    def sample(self):
        self.calls += 1
        return self.next


class FakeFetch:
    def __init__(self):
        with open(FIXTURE) as f:
            self.weather = parse(json.load(f))
        self.calls = 0

    def __call__(self, lat, lon):
        self.calls += 1
        return self.weather


class FakeMpris:
    def __init__(self, watcher):
        self.watcher = watcher
        self.play_pauses = 0

    def play_pause(self):
        self.play_pauses += 1
        playing = self.watcher.snap.status == "Playing"
        self.watcher.snap = PlayerSnapshot(**{**vars(self.watcher.snap),
                                              "status": "Paused" if playing else "Playing"})


class FakeWatcher:
    """Stands in for SpotifyWatcher; push() plays the listener thread."""

    def __init__(self, on_change, artist_photos=None):
        self.on_change = on_change
        self.artist_photos = artist_photos
        self.snap = PlayerSnapshot()  # Spotify not running
        self.art = None
        self.artist_photo = None
        self.mpris = None
        self.starts = 0
        self.stops = 0
        self.fail = False

    def start(self):
        if self.fail:
            raise OSError("no session bus")
        self.starts += 1
        self.mpris = FakeMpris(self)
        return self.snap

    def stop(self):
        self.stops += 1
        self.mpris = None

    def snapshot(self):
        return self.snap

    def push(self, snap, art=None, photo=None):
        self.snap, self.art, self.artist_photo = snap, art, photo
        self.on_change(snap, art, photo)


@pytest.fixture(autouse=True)
def faces_as_images(monkeypatch):
    monkeypatch.setattr(home, "render_face", lambda face: face)


@pytest.fixture
def p(ctrl):
    ctrl.config = {"monitor": {"weather": LOCATION}}
    s = SimpleNamespace(ctrl=ctrl, sampler=FakeSampler(), fetch=FakeFetch(), watchers=[])
    s.weather = WeatherFeed.from_config(ctrl.config["monitor"], fetch=s.fetch,
                                        start_thread=lambda fn: fn())

    def watch(on_change, artist_photos=None):
        s.watchers.append(FakeWatcher(on_change, artist_photos))
        return s.watchers[-1]

    s.photos = object()  # an ArtistPhotos, as far as the page is concerned
    s.page = HomePage(ctrl, weather=s.weather, sampler=s.sampler, watch_spotify=watch,
                      artist_photos=s.photos)
    s.spotify = s.watchers[0]
    yield s
    s.page.deactivate()


def shown(ctrl, key):
    return ctrl.images[key]["pil_image"]


# --- brightness column -------------------------------------------------------

def test_brightness_keys_sit_under_restart(p):
    p.page.render()
    assert [(p.ctrl.images[k]["icon"], p.ctrl.images[k]["label"]) for k in (15, 23, 31)] == [
        ("brightness_33.png", "33%"), ("brightness_66.png", "66%"), ("brightness_100.png", "100%")]


@pytest.mark.parametrize("key, percent", [(15, 33), (23, 66), (31, 100)])
def test_brightness_key_sets_deck_brightness(p, key, percent):
    p.page.on_key(key)
    assert p.ctrl.deck.brightness == percent


def test_unused_keys_do_nothing(p):
    p.page.on_key(12)
    p.page.on_key(20)
    assert p.ctrl.deck.brightness is None
    assert not hasattr(p.ctrl, "switched_to")


# --- temperatures and weather -------------------------------------------------

def test_before_the_first_sample_temperatures_read_dash(p):
    p.page.render()
    assert (shown(p.ctrl, 8).label, shown(p.ctrl, 8).value) == ("CPU", "—")
    assert (shown(p.ctrl, 9).label, shown(p.ctrl, 9).value) == ("GPU", "—")


def test_tick_shows_cpu_and_gpu_temperature_and_the_weather(p):
    p.page.render()
    p.page.tick()
    assert (shown(p.ctrl, 8).label, shown(p.ctrl, 8).value) == ("CPU", "54°")
    assert (shown(p.ctrl, 9).label, shown(p.ctrl, 9).value) == ("GPU", "60°")
    assert shown(p.ctrl, 10).label == "Now"
    assert shown(p.ctrl, 10).value != "—"
    assert p.fetch.calls == 1


def test_tomorrows_weather_sits_next_to_the_current_weather(p):
    p.page.render()
    assert (shown(p.ctrl, 11).label, shown(p.ctrl, 11).value) == ("Tomorrow", "—")
    p.page.tick()
    tomorrow = p.fetch.weather.tomorrow
    assert shown(p.ctrl, 11).label == "Tomorrow"
    assert shown(p.ctrl, 11).value == f"{round(tomorrow.t_max)}° / {round(tomorrow.t_min)}°"
    assert shown(p.ctrl, 11).icon != ""


def test_temperatures_use_the_monitor_colours(p):
    p.sampler.next = SystemSample(cpu_temp=95.0, gpu_temp=60.0)
    p.page.render()
    p.page.tick()
    assert shown(p.ctrl, 8).color == RED
    assert shown(p.ctrl, 9).color == GREEN


def test_tick_redraws_only_changed_keys(p):
    p.page.render()
    p.page.tick()
    p.ctrl.pushes.clear()
    p.page.tick()
    assert p.ctrl.pushes == []
    p.sampler.next = SystemSample(cpu_temp=55.0, gpu_temp=60.0)
    p.page.tick()
    assert p.ctrl.pushes == [8]


def test_weather_is_shared_not_refetched(p):
    p.page.render()
    p.page.tick()
    p.weather.refresh_if_due()  # e.g. the Monitor page polling the same feed
    p.page.tick()
    assert p.fetch.calls == 1


@pytest.mark.parametrize("key", [8, 9, 10, 11])
def test_monitor_keys_open_the_monitor_page(p, key):
    p.page.on_key(key)
    assert p.ctrl.switched_to == "monitor"


# --- Spotify ------------------------------------------------------------------

def test_spotify_not_running_shows_play_and_blank_music_keys(p):
    p.page.activate()
    p.page.render()
    assert p.ctrl.images[16]["icon"] == "play.png"
    assert p.ctrl.images[16]["highlight"] is None
    for key in (17, 18):
        assert shown(p.ctrl, key) is None
        assert p.ctrl.images[key]["color"] == (0, 0, 0)


def test_playing_track_shows_pause_artist_and_album_art(p):
    p.spotify.snap, p.spotify.art = PLAYING, COVER
    p.page.activate()
    p.page.render()
    assert p.ctrl.images[16]["icon"] == "pause.png"
    assert p.ctrl.images[16]["highlight"] == SPOTIFY_GREEN
    assert shown(p.ctrl, 17) == PictureFace("Artist", "Zombie Hyperdrive", None)
    assert shown(p.ctrl, 18) == PictureFace("Song", "Gigawatt", COVER)


def test_a_track_change_redraws_only_the_music_keys(p):
    p.page.activate()
    p.page.render()
    p.page.tick()
    p.ctrl.pushes.clear()
    p.spotify.push(PLAYING)  # cover art not fetched yet
    assert set(p.ctrl.pushes) == MUSIC_KEYS
    assert shown(p.ctrl, 18) == PictureFace("Song", "Gigawatt", None)
    p.ctrl.pushes.clear()
    p.spotify.push(PLAYING, COVER)  # ...and now it is
    assert p.ctrl.pushes == [18]


def test_play_key_toggles_playback_and_redraws_at_once(p):
    p.spotify.snap = PLAYING
    p.page.activate()
    p.page.render()
    p.page.on_key(16)
    assert p.spotify.mpris.play_pauses == 1
    assert p.ctrl.images[16]["icon"] == "play.png"


def test_the_watcher_gets_the_artist_photos(p):
    assert p.spotify.artist_photos is p.photos


def test_artist_key_shows_the_artist_photo(p):
    p.spotify.snap, p.spotify.art, p.spotify.artist_photo = PLAYING, COVER, PHOTO
    p.page.activate()
    p.page.render()
    assert shown(p.ctrl, 17) == PictureFace("Artist", "Zombie Hyperdrive", PHOTO)


def test_an_arriving_artist_photo_redraws_only_the_artist_key(p):
    p.page.activate()
    p.page.render()
    p.spotify.push(PLAYING, COVER)
    p.ctrl.pushes.clear()
    p.spotify.push(PLAYING, COVER, PHOTO)
    assert p.ctrl.pushes == [17]


def test_works_with_the_real_spotify_watcher(ctrl):
    """The fakes above can't catch a callback signature mismatch; this can."""
    from pages.spotify import SpotifyWatcher
    from tests.test_spotify_watcher import FakeMpris, wait_until

    mpris = FakeMpris(PlayerSnapshot())  # nothing playing yet
    page = HomePage(ctrl, sampler=FakeSampler(), watch_spotify=lambda on_change, **kw:
                    SpotifyWatcher(on_change, connect=lambda: mpris,
                                   fetch_art=lambda url: COVER, **kw))
    try:
        page.activate()
        page.render()
        mpris.props_changed(**vars(PLAYING))  # only the callback can draw this
        assert wait_until(lambda: shown(ctrl, 18) == PictureFace("Song", "Gigawatt", COVER))
    finally:
        page.deactivate()


@pytest.mark.parametrize("key", [17, 18])
def test_artist_and_song_keys_open_the_spotify_page(p, key):
    p.page.on_key(key)
    assert p.ctrl.switched_to == "spotify"


def test_play_key_without_spotify_connection_does_nothing(p):
    p.page.render()
    p.page.on_key(16)  # never activated: no connection
    assert p.ctrl.images[16]["icon"] == "play.png"


def test_home_still_works_when_the_session_bus_is_unreachable(p, capsys):
    p.spotify.fail = True
    p.page.activate()  # must not raise: Home is the start page
    p.page.render()
    p.page.tick()
    assert p.ctrl.images[16]["icon"] == "play.png"
    assert shown(p.ctrl, 8).value == "54°"
    assert "Spotify unavailable" in capsys.readouterr().out


# --- lifecycle ------------------------------------------------------------------

def home_threads():
    return [t for t in threading.enumerate() if t.name == "home-poll"]


def test_activate_starts_polling_and_spotify_deactivate_stops_both(p):
    p.page.activate()
    assert len(home_threads()) == 1
    assert p.spotify.starts == 1
    assert p.sampler.resets == 1
    p.page.deactivate()
    assert home_threads() == []
    assert p.spotify.stops == 1


def test_poll_thread_redraws_the_temperatures(p, monkeypatch):
    monkeypatch.setattr(home, "POLL_SECONDS", 0.05)
    p.page.activate()
    p.page.render()
    p.sampler.next = SystemSample(cpu_temp=70.0, gpu_temp=60.0)
    end = time.monotonic() + 5
    while shown(p.ctrl, 8).value != "70°" and time.monotonic() < end:
        time.sleep(0.02)
    assert shown(p.ctrl, 8).value == "70°"


def test_nothing_is_drawn_after_deactivate(p):
    p.page.activate()
    p.page.render()
    p.page.deactivate()
    p.ctrl.pushes.clear()
    p.spotify.push(PLAYING, COVER)  # a listener callback racing the switch
    p.page.tick()
    assert p.ctrl.pushes == []


def test_render_redraws_everything_again(p):
    p.page.render()
    p.page.tick()
    p.ctrl.pushes.clear()
    p.page.render()  # e.g. the Home nav key pressed again
    assert {8, 9, 10, 11, 15, 16, 17, 18, 23, 31} <= set(p.ctrl.pushes)
