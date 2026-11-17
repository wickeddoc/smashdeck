# tests/test_artist_photos.py
"""ArtistPhotos: artist name -> MusicBrainz ID -> fanart.tv artist thumb,
cached on disk. HTTP is faked with trimmed real responses; the cache is a
tmp_path directory; time is a fake clock."""
import io
import json
import os
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from pages.artist_photos import ArtistPhotos

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
MBID = "056e4f3e-d505-4dad-8ec1-d04f521cbb56"
DAY = 24 * 60 * 60
RED, BLUE = (200, 30, 30), (30, 30, 200)


def fixture(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


def png(color, size=(1000, 1000)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


class FakeHttp:
    """Serves MusicBrainz, fanart.tv and image URLs; records every request."""

    def __init__(self):
        self.requests = []  # (url, headers)
        self.musicbrainz = fixture("musicbrainz_artist.json")
        self.fanart = fixture("fanart_music.json")
        self.images = {"daft-punk-21.jpg": png(BLUE), "daft-punk-22.jpg": png(RED)}
        self.fail = {}  # host -> exception to raise

    def __call__(self, url, headers):
        self.requests.append((url, headers))
        host = urlsplit(url).hostname
        if host in self.fail:
            raise self.fail[host]
        if host == "musicbrainz.org":
            return self.musicbrainz
        if host == "webservice.fanart.tv":
            if isinstance(self.fanart, Exception):
                raise self.fanart
            return self.fanart
        return self.images[url.rsplit("/", 1)[1]]

    def hosts(self):
        return [urlsplit(url).hostname for url, _ in self.requests]


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


def not_found():
    return urllib.error.HTTPError("https://webservice.fanart.tv/v3/music/x", 404,
                                  "Not Found", {}, None)


@pytest.fixture
def env(tmp_path):
    class Env:
        http = FakeHttp()
        clock = Clock()
        cache = tmp_path / "artists"

        def photos(self, **kwargs):
            kwargs.setdefault("api_key", "PROJECT")
            return ArtistPhotos(cache_dir=self.cache, http=self.http, clock=self.clock,
                                sleep=self.clock.sleep, **kwargs)
    return Env()


# --- config ---------------------------------------------------------------------

def test_off_without_the_config_section():
    assert ArtistPhotos.from_config({}) is None


def test_off_when_disabled():
    assert ArtistPhotos.from_config({"artist_art": {"enabled": False, "api_key": "k"}}) is None


def test_off_without_a_project_key_and_says_why(capsys):
    assert ArtistPhotos.from_config({"artist_art": {"client_key": "mine"}}) is None
    assert "api_key" in capsys.readouterr().out


def test_on_with_a_project_key(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    photos = ArtistPhotos.from_config({"artist_art": {"api_key": "k"}})
    assert photos is not None
    assert photos.cache_dir == tmp_path / "smashdeck" / "artists"


def test_cache_dir_can_be_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    photos = ArtistPhotos.from_config({"artist_art": {"api_key": "k", "cache_dir": "~/art"}})
    assert photos.cache_dir == tmp_path / "art"


# --- lookup -----------------------------------------------------------------------

def test_lookup_returns_the_most_liked_thumb_at_key_size(env):
    photo = env.photos().lookup("Daft Punk")
    assert photo.size == (144, 144)
    assert photo.getpixel((72, 72)) == RED  # likes 5 beats likes 2
    assert env.http.hosts() == ["musicbrainz.org", "webservice.fanart.tv", "assets.fanart.tv"]


def test_musicbrainz_is_asked_for_the_exact_artist_with_a_user_agent(env):
    env.photos().lookup('AC/DC "live"')
    url, headers = env.http.requests[0]
    query = parse_qs(urlsplit(url).query)
    assert query["query"] == ['artist:"AC/DC \\"live\\""']
    assert query["fmt"] == ["json"]
    assert headers["User-Agent"].startswith("SmashDeck/")


def test_fanart_gets_the_project_key_and_only_a_configured_personal_key(env):
    env.photos().lookup("Daft Punk")
    url, _ = env.http.requests[1]
    assert urlsplit(url).path == f"/v3/music/{MBID}"
    assert parse_qs(urlsplit(url).query) == {"api_key": ["PROJECT"]}

    env.http.requests.clear()
    env.photos(client_key="MINE").lookup("Daft Punk NFT")
    url, _ = env.http.requests[1]
    assert parse_qs(urlsplit(url).query) == {"api_key": ["PROJECT"], "client_key": ["MINE"]}


def test_artist_names_match_case_insensitively_and_by_alias(env):
    assert env.photos().lookup("daft punk") is not None
    assert env.photos().lookup("Duft Punk") is not None  # an alias of Daft Punk
    fanart_urls = [u for u, _ in env.http.requests if "webservice" in u]
    assert all(MBID in u for u in fanart_urls)


def test_no_exact_match_means_no_photo_rather_than_a_wrong_one(env):
    assert env.photos().lookup("Daft") is None
    assert env.http.hosts() == ["musicbrainz.org"]


def test_an_artist_without_thumbs_has_no_photo(env):
    env.http.fanart = json.dumps({"name": "Daft Punk", "artistbackground": []}).encode()
    assert env.photos().lookup("Daft Punk") is None


def test_musicbrainz_requests_are_spaced_a_second_apart(env):
    photos = env.photos()
    photos.lookup("Daft Punk")
    photos.lookup("Daft Punk NFT")
    assert env.clock.slept == [1.0]


# --- cache --------------------------------------------------------------------------

def test_unknown_artist_is_not_known(env):
    assert env.photos().known("Daft Punk") == (False, None)


def test_a_found_photo_is_kept_on_disk(env):
    env.photos().lookup("Daft Punk")
    env.http.requests.clear()
    known, photo = env.photos().known("Daft Punk")  # a fresh instance: from disk
    assert known
    assert photo.size == (144, 144)
    assert photo.getpixel((72, 72)) == RED
    assert env.http.requests == []


def test_a_found_photo_never_expires(env):
    env.photos().lookup("Daft Punk")
    env.clock.t += 365 * DAY
    assert env.photos().known("Daft Punk")[0]


def test_no_photo_is_remembered_for_a_week(env):
    env.photos().lookup("Daft")
    assert env.photos().known("Daft") == (True, None)
    env.clock.t += 7 * DAY - 1
    assert env.photos().known("Daft") == (True, None)
    env.clock.t += 1
    assert env.photos().known("Daft") == (False, None)


def test_after_a_week_only_fanart_is_asked_again(env):
    env.http.fanart = not_found()
    assert env.photos().lookup("Daft Punk") is None
    env.clock.t += 7 * DAY
    env.http.requests.clear()
    env.http.fanart = fixture("fanart_music.json")
    assert env.photos().lookup("Daft Punk") is not None
    assert env.http.hosts() == ["webservice.fanart.tv", "assets.fanart.tv"]


@pytest.mark.parametrize("host, error", [
    ("musicbrainz.org", urllib.error.URLError("timed out")),
    ("webservice.fanart.tv", urllib.error.HTTPError("u", 503, "Unavailable", {}, None)),
    ("assets.fanart.tv", OSError("connection reset")),
])
def test_network_trouble_is_retried_after_ten_minutes_not_a_week(env, host, error, capsys):
    env.http.fail[host] = error
    photos = env.photos()
    assert photos.lookup("Daft Punk") is None
    assert photos.known("Daft Punk") == (True, None)  # don't hammer a failing service
    env.clock.t += 10 * 60
    assert photos.known("Daft Punk") == (False, None)
    assert env.photos().known("Daft Punk") == (False, None)  # nothing written to disk
    out = capsys.readouterr().out
    assert "Daft Punk" in out
    assert host in out  # which service failed


def test_failures_never_log_the_api_keys(env, capsys):
    env.http.fail["webservice.fanart.tv"] = urllib.error.HTTPError(
        "https://webservice.fanart.tv/v3/music/x?api_key=PROJECT&client_key=MINE",
        500, "Server Error", {}, None)
    env.photos(client_key="MINE").lookup("Daft Punk")
    out = capsys.readouterr().out
    assert "PROJECT" not in out
    assert "MINE" not in out


def test_a_corrupt_cache_entry_is_looked_up_again(env):
    env.photos().lookup("Daft Punk")
    for name in os.listdir(env.cache):
        (env.cache / name).write_bytes(b"garbage")
    assert env.photos().known("Daft Punk") == (False, None)
    assert env.photos().lookup("Daft Punk") is not None
