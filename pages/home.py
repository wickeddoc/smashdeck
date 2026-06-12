# pages/home.py
from pages import BasePage

BRIGHTNESS_KEYS = {8: 25, 9: 50, 10: 75, 11: 100}


class HomePage(BasePage):
    def render(self):
        self.clear()
        for key, pct in BRIGHTNESS_KEYS.items():
            self.ctrl.set_key_image(key, f"brightness_{pct}.png", f"{pct}%")

    def on_key(self, key):
        pct = BRIGHTNESS_KEYS.get(key)
        if pct is not None:
            self.ctrl.deck.set_brightness(pct)
