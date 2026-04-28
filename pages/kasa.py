# pages/kasa.py
import asyncio
from kasa import SmartPlug
from pages import BasePage


class KasaPage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        kasa_cfg = self.ctrl.config.get("kasa", {})
        self.devices = kasa_cfg.get("devices", [])
        self._plugs = [SmartPlug(d["host"]) for d in self.devices]

    def _run(self, coro):
        return asyncio.run(coro)

    async def _update_all(self):
        for plug in self._plugs:
            await plug.update()

    def render(self):
        self.clear()
        self._run(self._update_all())
        for i, (dev, plug) in enumerate(zip(self.devices[:8], self._plugs[:8])):
            icon = "power_on.png" if plug.is_on else "power_off.png"
            highlight = (60, 180, 120) if plug.is_on else None
            self.ctrl.set_key_image(8 + i, icon, dev["name"], highlight=highlight)

    def on_key(self, key):
        if 8 <= key <= 15:
            idx = key - 8
            if idx < len(self._plugs):
                plug = self._plugs[idx]
                if plug.is_on:
                    self._run(plug.turn_off())
                else:
                    self._run(plug.turn_on())
                self.render()
