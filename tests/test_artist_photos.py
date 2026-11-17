# tests/test_artist_photos.py
"""ArtistPhotos: artist name -> MusicBrainz ID -> fanart.tv artist thumb,
cached on disk. HTTP is faked with trimmed real responses; the cache is a
tmp_path directory; time is a fake clock."""
import io
import json
import os
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from pages import artist_photos as ap
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
        self.flaky = {}  # host -> exceptions to raise first, one per request

    def __call__(self, url, headers):
        self.requests.append((url, headers))
        host = urlsplit(url).hostname
        if host in self.fail:
            raise self.fail[host]
        if self.flaky.get(host):
            raise self.flaky[host].pop(0)
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


# --- hardening: fetch only what fanart.tv and MusicBrainz should serve ----------


def thumbs(*entries):
    return json.dumps({"name": "Daft Punk", "artistthumb": list(entries)}).encode()


@pytest.mark.parametrize("url", [
    "http://assets.fanart.tv/fanart/daft-punk-22.jpg",  # not https
    "https://192.168.1.1/daft-punk-22.jpg",  # the LAN
    "file:///etc/passwd",
    "https://fanart.tv.evil.example/daft-punk-22.jpg",  # look-alike hosts
    "https://evilfanart.tv/daft-punk-22.jpg",
])
def test_image_urls_outside_fanart_tv_are_never_fetched(env, url):
    env.http.fanart = thumbs({"url": url, "likes": "9"})
    assert env.photos().lookup("Daft Punk") is None
    assert env.http.hosts() == ["musicbrainz.org", "webservice.fanart.tv"]


def test_a_bad_thumb_url_does_not_hide_a_good_one(env):
    env.http.fanart = thumbs(
        {"url": "https://192.168.1.1/daft-punk-22.jpg", "likes": "9"},
        {"url": "https://assets.fanart.tv/fanart/daft-punk-21.jpg", "likes": "1"})
    assert env.photos().lookup("Daft Punk").getpixel((72, 72)) == BLUE


def test_images_on_any_fanart_tv_host_are_fine(env):
    # fanart.tv has changed its image URLs before (late 2025)
    env.http.fanart = thumbs({"url": "https://images.fanart.tv/music/daft-punk-22.jpg"})
    assert env.photos().lookup("Daft Punk") is not None


def test_an_image_too_large_to_decode_safely_is_refused(env, monkeypatch):
    monkeypatch.setattr(ap, "MAX_IMAGE_PIXELS", 999 * 999)  # the fake thumbs are 1000²
    assert env.photos().lookup("Daft Punk") is None


def test_musicbrainz_ids_that_are_not_ids_are_never_sent_to_fanart(env):
    found = json.loads(env.http.musicbrainz)
    found["artists"][0]["id"] = "../../v3/movies/x?"
    env.http.musicbrainz = json.dumps(found).encode()
    assert env.photos().lookup("Daft Punk") is None
    assert env.http.hosts() == ["musicbrainz.org"]


def test_a_tampered_id_in_the_cache_is_not_used(env):
    env.http.fanart = not_found()
    env.photos().lookup("Daft Punk")  # caches the MusicBrainz ID
    (entry,) = env.cache.glob("*.json")
    data = json.loads(entry.read_text())
    data["mbid"] = "../../v3/movies/x?"
    entry.write_text(json.dumps(data))
    env.clock.t += 7 * DAY
    env.http.requests.clear()
    env.photos().lookup("Daft Punk")
    assert env.http.hosts()[0] == "musicbrainz.org"  # asked again, not trusted
    assert all("movies" not in url for url, _ in env.http.requests)


class FakeResponse:
    def __init__(self, size):
        self.size = size

    def read(self, amount=-1):
        return b"x" * (self.size if amount < 0 else min(amount, self.size))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, size):
        self.size = size
        self.opened = []

    def open(self, req, timeout):
        self.opened.append(req.full_url)
        return FakeResponse(self.size)


def test_responses_over_10_mb_are_refused(monkeypatch):
    monkeypatch.setattr(ap, "_OPENER", FakeOpener(ap.MAX_RESPONSE + 1))
    with pytest.raises(ValueError):
        ap._http_get("https://assets.fanart.tv/x.jpg", {})
    monkeypatch.setattr(ap, "_OPENER", FakeOpener(100))
    assert len(ap._http_get("https://assets.fanart.tv/x.jpg", {})) == 100


@pytest.mark.parametrize("url", ["http://musicbrainz.org/ws/2/artist/", "file:///etc/passwd",
                                 "https://192.168.1.1/", "https://example.com/x.jpg"])
def test_requests_only_go_to_musicbrainz_and_fanart_over_https(monkeypatch, url):
    opener = FakeOpener(10)
    monkeypatch.setattr(ap, "_OPENER", opener)
    with pytest.raises(ValueError):
        ap._http_get(url, {})
    assert opener.opened == []


@pytest.mark.parametrize("target, allowed", [
    ("https://assets.fanart.tv/fanart/x.jpg", True),
    ("https://musicbrainz.org/ws/2/artist/?query=x", True),
    ("http://assets.fanart.tv/fanart/x.jpg", False),
    ("http://192.168.1.1/", False),
    ("https://example.com/", False),
])
def test_redirects_may_not_leave_musicbrainz_or_fanart(target, allowed):
    handler = ap._AllowlistRedirects()
    req = urllib.request.Request("https://assets.fanart.tv/fanart/a.jpg")
    if allowed:
        assert handler.redirect_request(req, None, 302, "Found", {}, target) is not None
    else:
        with pytest.raises(urllib.error.HTTPError):
            handler.redirect_request(req, None, 302, "Found", {}, target)


# --- a busy service (MusicBrainz answers 503 "currently busy" under load) ----

def busy(retry_after="1"):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://musicbrainz.org/ws/2/artist/", 503,
                                  "Service Temporarily Unavailable", headers, None)


def test_a_busy_service_is_asked_again_after_its_retry_after(env):
    env.http.flaky["musicbrainz.org"] = [busy(), busy()]
    assert env.photos().lookup("Daft Punk") is not None
    assert env.http.hosts()[:3] == ["musicbrainz.org"] * 3
    assert env.clock.slept == [1.0, 1.0]


def test_a_service_busy_three_times_is_left_for_ten_minutes(env):
    env.http.flaky["musicbrainz.org"] = [busy(), busy(), busy()]
    photos = env.photos()
    assert photos.lookup("Daft Punk") is None
    assert env.http.hosts() == ["musicbrainz.org"] * 3
    assert photos.known("Daft Punk") == (True, None)


@pytest.mark.parametrize("retry_after, waited", [(None, 1.0), ("120", 5.0), ("soon", 1.0)])
def test_the_wait_before_asking_again_is_short(env, retry_after, waited):
    env.http.flaky["webservice.fanart.tv"] = [busy(retry_after)]
    assert env.photos().lookup("Daft Punk") is not None
    assert env.clock.slept == [waited]


def test_other_errors_are_not_retried(env):
    env.http.flaky["musicbrainz.org"] = [urllib.error.URLError("timed out")]
    assert env.photos().lookup("Daft Punk") is None
    assert env.http.hosts() == ["musicbrainz.org"]
