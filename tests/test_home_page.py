# tests/test_home_page.py
from pages.home import HomePage


def test_render_shows_brightness_keys(ctrl):
    page = HomePage(ctrl)
    page.render()
    assert ctrl.images[8]["icon"] == "brightness_25.png"
    assert ctrl.images[11]["icon"] == "brightness_100.png"


def test_brightness_key_sets_deck_brightness(ctrl):
    page = HomePage(ctrl)
    page.on_key(10)
    assert ctrl.deck.brightness == 75


def test_other_keys_do_nothing(ctrl):
    page = HomePage(ctrl)
    page.on_key(20)
    assert ctrl.deck.brightness is None
