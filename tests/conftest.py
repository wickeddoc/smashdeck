# tests/conftest.py
"""Shared fakes: a controller/deck pair that records rendering calls."""
import pytest


class FakeDeck:
    def __init__(self):
        self.brightness = None

    def key_count(self):
        return 32

    def set_brightness(self, value):
        self.brightness = value


class FakeController:
    """Stands in for DeckController; records every set_key_image call."""

    def __init__(self, config=None):
        self.config = config or {}
        self.deck = FakeDeck()
        self.images = {}  # key index -> kwargs of last render
        self.pushes = []  # key index of every set_key_image call, in order

    def set_key_image(self, key, icon_filename=None, label=None,
                      color=(0, 0, 0), highlight=None, pil_image=None):
        self.pushes.append(key)
        self.images[key] = {
            "icon": icon_filename,
            "label": label,
            "color": color,
            "highlight": highlight,
            "pil_image": pil_image,
        }

    def switch_page(self, name):
        self.switched_to = name


@pytest.fixture
def ctrl():
    return FakeController()
