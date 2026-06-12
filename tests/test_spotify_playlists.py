# tests/test_spotify_playlists.py
"""SpotifyPage playlist rendering and OpenUri dispatch, no DBus needed."""
from pages.spotify import SpotifyPage

SPOTIFY_CFG = {
    "spotify": {
        "playlists": [
            {"name": "Chill", "uri": "spotify:playlist:xxxxx"},
            {"name": "Work", "uri": "spotify:playlist:yyyyy"},
        ]
    }
}


class FakeMpris:
    def __init__(self):
        self.opened = []

    def open_uri(self, uri):
        self.opened.append(uri)


def test_render_shows_playlists_on_row_4(ctrl):
    ctrl.config = SPOTIFY_CFG
    page = SpotifyPage(ctrl)
    page.render()  # _mpris is None -> default snapshot; playlists still render
    assert ctrl.images[24]["icon"] == "playlist_1.png"
    assert ctrl.images[24]["label"] == "Chill"
    assert ctrl.images[25]["icon"] == "playlist_2.png"
    assert ctrl.images[25]["label"] == "Work"


def test_playlist_key_calls_open_uri(ctrl):
    ctrl.config = SPOTIFY_CFG
    page = SpotifyPage(ctrl)
    fake = FakeMpris()
    page._mpris = fake
    page.on_key(25)
    assert fake.opened == ["spotify:playlist:yyyyy"]


def test_no_playlists_configured_renders_nothing_on_24(ctrl):
    ctrl.config = {"spotify": {}}
    page = SpotifyPage(ctrl)
    page.render()
    # clear() paints it black; no playlist icon must overwrite it
    assert ctrl.images[24]["icon"] is None
