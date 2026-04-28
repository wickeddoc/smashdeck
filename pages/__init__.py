# pages/__init__.py
from abc import ABC, abstractmethod


class BasePage(ABC):
    def __init__(self, controller):
        self.ctrl = controller

    @abstractmethod
    def render(self):
        """Draw all button icons for this page."""
        pass

    @abstractmethod
    def on_key(self, key: int):
        """Handle a key press."""
        pass

    def activate(self):
        """Called when this page becomes the active page."""
        pass

    def deactivate(self):
        """Called when this page is no longer the active page."""
        pass

    def clear(self):
        """Clear only the content area (keys 8-31), leaving nav bar intact."""
        for k in range(8, self.ctrl.deck.key_count()):
            self.ctrl.set_key_image(k, color=(0, 0, 0))
