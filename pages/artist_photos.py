# pages/artist_photos.py
"""Artist photos from fanart.tv, cached on disk (optional feature).

fanart.tv indexes music by MusicBrainz ID, so a lookup is: artist name ->
MusicBrainz artist search (no key; an exact name or alias match only, as no
photo beats a wrong one) -> fanart.tv's square "artistthumb" with the most
likes -> scaled to key size and cached as ``<key>.png`` next to a
``<key>.json`` entry. A found photo is kept until the cache is deleted; "no
photo" is remembered for a week; network trouble is retried after ten
minutes, in memory only.

known() is cheap (memory or disk, no network); lookup() does the HTTP calls
and blocks, so callers run it off the page threads (see SpotifyWatcher).
One instance is shared by the Home and Spotify pages.

Config, under ``spotify:`` in config.yaml::

    artist_art:
      enabled: true          # default when the section exists
      api_key: "..."         # fanart.tv project key (required)
      client_key: "..."      # fanart.tv personal key (optional: newer images)
      cache_dir: "~/.cache/smashdeck/artists"   # optional
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

from PIL import Image, ImageOps

from pages.monitor.tiles import SIZE

MUSICBRAINZ = "https://musicbrainz.org/ws/2/artist/"
FANART = "https://webservice.fanart.tv/v3/music/"
USER_AGENT = "SmashDeck/1.0 ( Stream Deck controller )"
MUSICBRAINZ_INTERVAL = 1.0  # s; MusicBrainz allows one request per second
NOT_FOUND_TTL = 7 * 24 * 60 * 60  # s to remember "no photo"
RETRY_AFTER = 10 * 60  # s after network trouble
TIMEOUT = 10  # s per HTTP request


def _http_get(url: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return Path(base) / "smashdeck" / "artists"


def _entry_key(artist: str) -> str:
    return hashlib.sha1(artist.strip().casefold().encode()).hexdigest()[:16]


def _phrase(text: str) -> str:
    """A Lucene phrase query term for MusicBrainz search."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _likes(thumb: dict) -> int:
    try:
        return int(thumb.get("likes") or 0)
    except ValueError:
        return 0


class ArtistPhotos:
    def __init__(self, api_key: str, client_key: str | None = None, cache_dir=None,
                 http=_http_get, clock=time.time, sleep=time.sleep):
        self._api_key = api_key
        self._client_key = client_key
        self.cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()
        self._http = http
        self._clock = clock
        self._sleep = sleep
        self._memory = {}  # entry key -> (photo or None, valid until or None)
        self._lock = threading.Lock()  # guards _memory
        self._lookup_lock = threading.Lock()  # one lookup at a time
        self._musicbrainz_ready = 0.0  # clock() of the next allowed request

    @classmethod
    def from_config(cls, spotify_cfg, **kwargs) -> ArtistPhotos | None:
        """None (feature off) unless ``artist_art`` exists, isn't disabled
        and has an ``api_key``."""
        cfg = (spotify_cfg or {}).get("artist_art")
        if not cfg or not cfg.get("enabled", True):
            return None
        if not cfg.get("api_key"):
            print("spotify: artist_art needs a fanart.tv api_key (project key); "
                  "artist photos are off")
            return None
        cache_dir = cfg.get("cache_dir")
        return cls(cfg["api_key"], client_key=cfg.get("client_key") or None,
                   cache_dir=os.path.expanduser(cache_dir) if cache_dir else None, **kwargs)

    # --- public ---

    def known(self, artist: str):
        """(True, photo or None) when the cache has an answer, else
        (False, None) and lookup() is needed. Never touches the network."""
        key = _entry_key(artist)
        with self._lock:
            hit = self._memory.get(key)
        if hit is not None:
            photo, until = hit
            if until is None or self._clock() < until:
                return True, photo
        entry = self._read_entry(key)
        if entry is None:
            return False, None
        if entry.get("photo"):
            try:
                with Image.open(self.cache_dir / f"{key}.png") as img:
                    photo = img.convert("RGB")
            except (OSError, ValueError):
                return False, None
            self._remember(key, photo, None)
            return True, photo
        until = entry.get("checked", 0) + NOT_FOUND_TTL
        if self._clock() < until:
            self._remember(key, None, until)
            return True, None
        return False, None

    def lookup(self, artist: str):
        """The artist's photo or None, fetching and caching it if needed.
        Blocks on the network: never call it from a page or key thread."""
        key = _entry_key(artist)
        with self._lookup_lock:
            known, photo = self.known(artist)
            if known:  # e.g. another watcher's lookup just finished
                return photo
            mbid = (self._read_entry(key) or {}).get("mbid")
            try:
                mbid = mbid or self._musicbrainz_id(artist)
                photo = self._fanart_photo(mbid) if mbid else None
            except Exception as e:  # network or service trouble: retry later
                # repr of urllib errors carries no URL, so no API key leaks
                print(f"artist photos: lookup for {artist!r} failed: {e!r}")
                self._remember(key, None, self._clock() + RETRY_AFTER)
                return None
            self._store(key, artist, mbid, photo)
            return photo

    # --- network ---

    def _get(self, url: str) -> bytes:
        return self._http(url, {"User-Agent": USER_AGENT})

    def _musicbrainz_id(self, artist: str) -> str | None:
        wait = self._musicbrainz_ready - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._musicbrainz_ready = self._clock() + MUSICBRAINZ_INTERVAL
        query = urlencode({"query": f"artist:{_phrase(artist)}", "fmt": "json", "limit": 10})
        found = json.loads(self._get(f"{MUSICBRAINZ}?{query}"))
        wanted = artist.strip().casefold()
        candidates = sorted(found.get("artists") or [], key=lambda a: -(a.get("score") or 0))
        for candidate in candidates:
            names = [candidate.get("name") or ""]
            names += [alias.get("name") or "" for alias in candidate.get("aliases") or []]
            if any(name.strip().casefold() == wanted for name in names):
                return candidate.get("id")
        return None

    def _fanart_photo(self, mbid: str):
        keys = {"api_key": self._api_key}
        if self._client_key:
            keys["client_key"] = self._client_key
        try:
            art = json.loads(self._get(f"{FANART}{mbid}?{urlencode(keys)}"))
        except urllib.error.HTTPError as e:
            if e.code == 404:  # fanart.tv has nothing for this artist
                return None
            raise
        thumbs = [t for t in art.get("artistthumb") or [] if t.get("url")]
        if not thumbs:
            return None
        best = max(thumbs, key=_likes)  # first of equals: fanart.tv's order
        with Image.open(io.BytesIO(self._get(best["url"]))) as img:
            return ImageOps.fit(img.convert("RGB"), (SIZE, SIZE))

    # --- cache ---

    def _remember(self, key, photo, until):
        with self._lock:
            self._memory[key] = (photo, until)

    def _read_entry(self, key: str) -> dict | None:
        try:
            with open(self.cache_dir / f"{key}.json") as f:
                entry = json.load(f)
        except (OSError, ValueError):
            return None
        return entry if isinstance(entry, dict) else None

    def _store(self, key, artist, mbid, photo):
        now = self._clock()
        self._remember(key, photo, None if photo is not None else now + NOT_FOUND_TTL)
        entry = {"artist": artist, "mbid": mbid, "photo": photo is not None, "checked": now}
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            if photo is not None:
                self._write(key, ".png", lambda f: photo.save(f, "PNG"))
            self._write(key, ".json", lambda f: f.write(json.dumps(entry).encode()))
        except OSError as e:  # e.g. read-only home: still works from memory
            print(f"artist photos: can't write the cache in {self.cache_dir}: {e!r}")

    def _write(self, key, suffix, write):
        """Write atomically, so a crash never leaves a half-written entry."""
        final = self.cache_dir / f"{key}{suffix}"
        tmp = final.with_name(f"{final.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with open(tmp, "wb") as f:
            write(f)
        os.replace(tmp, final)
