# tests/test_spotify_page.py
"""SpotifyPage's artist key (15): the artist photo when there is one,
otherwise the green name key; and the page against the real watcher."""
from PIL import Image

from pages.spotify import PlayerSnapshot, SpotifyPage, SpotifyWatcher
from tests.test_spotify_watcher import FakeMpris, wait_until

PLAYING = PlayerSnapshot(status="Playing", artist="Zombie Hyperdrive",
                         lead_artist="Zombie Hyperdrive", title="Gigawatt",
                         art_url="https://art/1")
PHOTO = Image.new("RGB", (144, 144), (90, 90, 90))


class StaticWatcher:
    def __init__(self, snap=PLAYING, photo=None):
        self.snap, self.art, self.artist_photo = snap, None, photo

    def snapshot(self):
        return self.snap


def test_artist_key_shows_the_artist_photo(ctrl):
    SpotifyPage(ctrl, watcher=StaticWatcher(photo=PHOTO)).render()
    key = ctrl.images[15]
    assert key["label"] is None
    assert key["pil_image"].size == (144, 144)
    assert key["pil_image"].getpixel((72, 60)) == (90, 90, 90)  # photo above the strip


def test_without_a_photo_the_artist_key_is_the_green_name_key(ctrl):
    SpotifyPage(ctrl, watcher=StaticWatcher()).render()
    assert ctrl.images[15]["label"] == "Zombie Hyperd"[:12]
    assert ctrl.images[15]["color"] == (30, 215, 96)
    assert ctrl.images[15]["pil_image"] is None


def test_no_artist_no_artist_key(ctrl):
    SpotifyPage(ctrl, watcher=StaticWatcher(snap=PlayerSnapshot())).render()
    assert ctrl.images[15]["label"] is None  # left as clear() painted it
    assert ctrl.images[15]["pil_image"] is None


def test_the_page_hands_its_artist_photos_to_its_watcher(ctrl):
    photos = object()
    page = SpotifyPage(ctrl, artist_photos=photos)
    assert page.artist_photos is photos
    assert page._watcher._photos is photos


def test_works_with_the_real_spotify_watcher(ctrl):
    """A fake watcher can't catch a callback signature mismatch; this can."""
    cover = Image.new("RGB", (640, 640), (120, 40, 160))
    mpris = FakeMpris(PlayerSnapshot())  # nothing playing yet
    page = SpotifyPage(ctrl, watcher=SpotifyWatcher(
        lambda *a: page._on_change(*a), connect=lambda: mpris, fetch_art=lambda url: cover))
    try:
        page.activate()
        mpris.props_changed(**vars(PLAYING))  # only the callback can draw this
        assert wait_until(lambda: ctrl.images.get(31, {}).get("pil_image") is cover)
    finally:
        page.deactivate()
