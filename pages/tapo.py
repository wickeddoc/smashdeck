# pages/tapo.py
import asyncio
from tapo import ApiClient
from pages import BasePage


class TapoPage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        tapo_cfg = self.ctrl.config.get("tapo", {})
        self._email = tapo_cfg.get("email")
        self._password = tapo_cfg.get("password")
        self.devices = tapo_cfg.get("devices", [])
        self._clients = []  # populated on first render
        self._device_on = []  # cached on/off state per device

    def _run(self, coro):
        return asyncio.run(coro)

    async def _connect_all(self):
        client = ApiClient(self._email, self._password)
        self._clients = []
        for dev in self.devices:
            device = await client.p100(dev["host"])
            self._clients.append(device)

    async def _update_all(self):
        if not self._clients:
            await self._connect_all()
        states = []
        for device in self._clients:
            info = await device.get_device_info()
            states.append(info.device_on)
        return states

    def render(self):
        self.clear()
        self._device_on = self._run(self._update_all())
        for i, (dev, is_on) in enumerate(zip(self.devices[:8], self._device_on[:8])):
            icon = "power_on.png" if is_on else "power_off.png"
            highlight = (50, 130, 220) if is_on else None
            self.ctrl.set_key_image(8 + i, icon, dev["name"], highlight=highlight)

    def on_key(self, key):
        if 8 <= key <= 15:
            idx = key - 8
            if idx < len(self._clients):
                device = self._clients[idx]
                if self._device_on[idx]:
                    self._run(device.off())
                else:
                    self._run(device.on())
                self.render()
