# tests/test_hue_page.py
"""HuePage logic against a faked phue.Bridge."""
import pages.hue as hue_mod
from pages.hue import HuePage


class FakeGroup:
    def __init__(self, group_id, name):
        self.group_id = group_id
        self.name = name


class FakeBridge:
    def __init__(self, ip):
        self.ip = ip
        self.groups = [FakeGroup(1, "Living"), FakeGroup(2, "Bedroom")]
        self.scene_calls = []

    def get_group(self, group_id):
        return {"lights": []}

    def activate_scene(self, group_id, scene_id, transition_time=4):
        self.scene_calls.append((group_id, scene_id))


class BrokenBridge:
    def __init__(self, ip):
        raise OSError("bridge unreachable")


HUE_CFG = {
    "hue": {
        "bridge_ip": "10.0.0.2",
        "scenes": [
            {"name": "Relax", "group_id": 1, "scene_id": "abc",
             "icon": "scene_relax.png"},
            {"name": "Party", "group_id": 1, "scene_id": "def",
             "icon": "scene_party.png"},
        ],
    }
}


def test_init_does_not_connect(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", BrokenBridge)
    ctrl.config = HUE_CFG
    HuePage(ctrl)  # must not raise


def test_render_with_unreachable_bridge_shows_error(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", BrokenBridge)
    ctrl.config = HUE_CFG
    page = HuePage(ctrl)
    page.render()
    assert ctrl.images[8]["icon"] == "error.png"


def test_render_lists_rooms_from_bridge(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", FakeBridge)
    ctrl.config = HUE_CFG
    page = HuePage(ctrl)
    page.render()
    assert ctrl.images[8]["label"] == "Living"
    assert ctrl.images[9]["label"] == "Bedroom"


def test_render_lists_scenes_on_row_4(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", FakeBridge)
    ctrl.config = HUE_CFG
    page = HuePage(ctrl)
    page.render()
    assert ctrl.images[24]["icon"] == "scene_relax.png"
    assert ctrl.images[24]["label"] == "Relax"
    assert ctrl.images[25]["icon"] == "scene_party.png"


def test_scene_key_activates_scene(ctrl, monkeypatch):
    monkeypatch.setattr(hue_mod, "Bridge", FakeBridge)
    ctrl.config = HUE_CFG
    page = HuePage(ctrl)
    page.render()
    page.on_key(25)
    assert page.bridge.scene_calls == [(1, "def")]
