# pages/hue.py
from phue import Bridge
from pages import BasePage


class HuePage(BasePage):
    def __init__(self, controller):
        super().__init__(controller)
        hue_cfg = self.ctrl.config.get("hue", {})
        self.bridge = Bridge(hue_cfg.get("bridge_ip"))
        print(self.bridge.groups)
        self.rooms = [
            {"name": room.name, "group_id": room.group_id}
            for room in self.bridge.groups
        ]
        self.selected_room = None
        self.selected_light = None
        self._light_ids = []  # light IDs currently shown on row 3

    def render(self):
        self.clear()
        self._render_rooms()
        if self.selected_room is not None:
            self._render_lights()

    def _render_rooms(self):
        for i, room in enumerate(self.rooms[:8]):
            key = 8 + i
            highlight = (120, 60, 180) if i == self.selected_room else None
            self.ctrl.set_key_image(key, "hue.png", room["name"], highlight=highlight)

    def _render_lights(self):
        room = self.rooms[self.selected_room]
        group = self.bridge.get_group(room["group_id"])
        light_ids = [int(lid) for lid in group.get("lights", [])]
        self._light_ids = light_ids[:8]

        for i, lid in enumerate(self._light_ids):
            light = self.bridge.get_light(lid)
            is_on = light["state"]["on"]
            icon = "light_on.png" if is_on else "light_off.png"
            highlight = (255, 220, 50) if is_on else None
            name = light["name"][:10]
            self.ctrl.set_key_image(16 + i, icon, name, highlight=highlight)

    def on_key(self, key):
        # Row 2 (keys 8-15): room selection
        if 8 <= key <= 15:
            idx = key - 8
            if idx < len(self.rooms):
                self.selected_room = idx
                self.render()

        # Row 3 (keys 16-23): toggle light
        elif 16 <= key <= 23:
            idx = key - 16
            if idx < len(self._light_ids):
                lid = self._light_ids[idx]
                is_on = self.bridge.get_light(lid, "on")
                self.selected_light = lid
                print(self.selected_light)
                self.bridge.set_light(lid, "on", not is_on)
                self._render_lights()
