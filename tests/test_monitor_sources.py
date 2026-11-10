# tests/test_monitor_sources.py
"""System metric sources against fake sysfs trees, canned command output and
monkeypatched psutil: no real sensors, GPU or network needed."""
from collections import namedtuple
from types import SimpleNamespace

import pytest

from pages.monitor import sources
from pages.monitor.sources import (
    GpuReading,
    Rate,
    SystemSampler,
    cpu_temp,
    default_route_interface,
    parse_nvidia_smi,
    read_hwmon_power,
    ssd_temp,
)

T = namedtuple("T", "label current")  # shape of psutil's shwtemp entries


def make_hwmon(root, index, name, sensors):
    """sensors: {"power1": ("label", microwatts)}"""
    d = root / f"hwmon{index}"
    d.mkdir()
    (d / "name").write_text(f"{name}\n")
    for prefix, (label, value) in sensors.items():
        (d / f"{prefix}_label").write_text(f"{label}\n")
        (d / f"{prefix}_input").write_text(f"{value}\n")


# --- read_hwmon_power

def test_hwmon_power_reads_labelled_sensor_in_watts(tmp_path):
    make_hwmon(tmp_path, 0, "nvme", {})
    make_hwmon(tmp_path, 1, "corsairpsu", {"power1": ("power total", 186000000),
                                           "power2": ("power 12v", 150000000)})
    assert read_hwmon_power(str(tmp_path), "corsairpsu", "power total") == 186.0


def test_hwmon_power_missing_driver_or_label_is_none(tmp_path):
    make_hwmon(tmp_path, 0, "zenpower", {"power1": ("RAPL_P_Package", 42164100)})
    assert read_hwmon_power(str(tmp_path), "corsairpsu", "power total") is None
    assert read_hwmon_power(str(tmp_path), "zenpower", "RAPL_P_Core") is None
    assert read_hwmon_power(str(tmp_path / "missing"), "zenpower", "RAPL_P_Package") is None


# --- cpu_temp / ssd_temp

def test_cpu_temp_prefers_zenpower_then_k10temp_then_coretemp():
    both = {"k10temp": [T("Tctl", 61.0)], "zenpower": [T("Tdie", 48.0), T("Tctl", 49.1)]}
    assert cpu_temp(both) == 49.1
    assert cpu_temp({"k10temp": [T("Tccd1", 40.0), T("Tctl", 61.0)]}) == 61.0
    assert cpu_temp({"coretemp": [T("Core 0", 50.0), T("Package id 0", 55.0)]}) == 55.0
    assert cpu_temp({"nvme": [T("Composite", 40.0)]}) is None


def test_ssd_temp_is_hottest_composite():
    temps = {"nvme": [T("Composite", 49.8), T("Sensor 1", 75.0), T("Composite", 60.9)]}
    assert ssd_temp(temps) == 60.9


def test_ssd_temp_without_composite_labels_uses_all_entries():
    assert ssd_temp({"nvme": [T("", 41.0), T("", 44.5)]}) == 44.5
    assert ssd_temp({}) is None


# --- default_route_interface

ROUTE = (
    "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
    "wlan0\t00000000\t0101A8C0\t0003\t0\t0\t600\t00000000\t0\t0\t0\n"
    "enp15s0u2\t00000000\t0101A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0\n"
    "eno1\t0000630A\t00000000\t0001\t0\t0\t50\t00FFFFFF\t0\t0\t0\n"
)


def test_default_route_interface_picks_lowest_metric_default():
    assert default_route_interface(ROUTE) == "enp15s0u2"


def test_default_route_interface_none_without_default_route():
    only_lan = ROUTE.splitlines()[0] + "\n" + ROUTE.splitlines()[3] + "\n"
    assert default_route_interface(only_lan) is None


# --- parse_nvidia_smi

def test_parse_nvidia_smi_first_gpu():
    assert parse_nvidia_smi("58, 4, 55.91, 4789, 32607\n") == GpuReading(58.0, 4.0, 55.91, 4789.0, 32607.0)


def test_parse_nvidia_smi_unsupported_fields_are_none():
    assert parse_nvidia_smi("58, 4, [N/A], 4789, 32607\n").power is None


def test_parse_nvidia_smi_empty_or_malformed_is_none():
    assert parse_nvidia_smi("") is None
    assert parse_nvidia_smi("58, 4\n") is None


# --- Rate

def stepping_clock(times):
    it = iter(times)
    return lambda: next(it)


def test_rate_first_update_is_none_then_bytes_per_second():
    rate = Rate()
    assert rate.update(1000, now=10.0) is None
    assert rate.update(2000, now=12.0) == 500.0
    assert rate.update(2600, now=13.0) == 600.0


def test_rate_counter_reset_is_none():
    rate = Rate()
    rate.update(5000, now=0.0)
    assert rate.update(100, now=2.0) is None
    assert rate.update(300, now=4.0) == 100.0


# --- SystemSampler with faked psutil

@pytest.fixture
def fake_psutil(monkeypatch):
    counters = {"disk": SimpleNamespace(read_bytes=0, write_bytes=0),
                "net": SimpleNamespace(bytes_recv=0, bytes_sent=0)}
    monkeypatch.setattr(sources.psutil, "sensors_temperatures",
                        lambda: {"zenpower": [T("Tctl", 51.1)],
                                 "nvme": [T("Composite", 60.9)]})
    monkeypatch.setattr(sources.psutil, "cpu_percent", lambda interval=None: 12.5)
    monkeypatch.setattr(sources.psutil, "virtual_memory", lambda: SimpleNamespace(percent=32.0))
    monkeypatch.setattr(sources.psutil, "disk_usage",
                        lambda path: SimpleNamespace(percent={"/": 52.4, "/data": 76.5}[path]))
    monkeypatch.setattr(sources.psutil, "disk_io_counters", lambda: counters["disk"])
    monkeypatch.setattr(sources.psutil, "net_io_counters",
                        lambda pernic=False: {"eth9": counters["net"]})
    return counters


def no_gpu():
    raise FileNotFoundError("nvidia-smi")


@pytest.fixture
def sampler(tmp_path, fake_psutil):
    make_hwmon(tmp_path, 0, "corsairpsu", {"power1": ("power total", 214000000)})
    route = tmp_path / "route"
    route.write_text(ROUTE.replace("enp15s0u2", "eth9"))
    return SystemSampler(
        disks=[{"name": "/", "path": "/"}, {"name": "Data", "path": "/data"}],
        hwmon_root=str(tmp_path),
        route_file=str(route),
        clock=stepping_clock([0.0, 2.0]),
        gpu_query=no_gpu,
    )


def test_sampler_fills_available_fields_and_isolates_failures(sampler):
    s = sampler.sample()
    assert s.cpu_temp == 51.1
    assert s.ssd_temp == 60.9
    assert s.pc_power == 214.0
    assert s.cpu_power is None  # no zenpower hwmon in the fake tree
    assert s.ram_percent == 32.0
    assert s.disks == [("/", 52.4), ("Data", 76.5)]
    assert (s.gpu_temp, s.gpu_load, s.gpu_power, s.vram_used_gb) == (None, None, None, None)
    assert s.pending is False


def test_sampler_rates_need_two_samples(sampler, fake_psutil):
    first = sampler.sample()
    assert (first.cpu_load, first.disk_read, first.net_down) == (None, None, None)

    fake_psutil["disk"].read_bytes, fake_psutil["disk"].write_bytes = 4_000_000, 1_000_000
    fake_psutil["net"].bytes_recv, fake_psutil["net"].bytes_sent = 2_500_000, 500_000
    second = sampler.sample()  # 2 s later on the stepping clock

    assert second.cpu_load == 12.5
    assert (second.disk_read, second.disk_write) == (2_000_000.0, 500_000.0)
    assert (second.net_down, second.net_up) == (1_250_000.0, 250_000.0)


def test_sampler_logs_a_failing_source_once(sampler, capsys):
    sampler.sample()
    sampler.sample()
    assert capsys.readouterr().out.count("source 'gpu' unavailable") == 1


def test_sampler_gpu_reading_converts_vram_to_gb(tmp_path, fake_psutil):
    s = SystemSampler(
        hwmon_root=str(tmp_path), route_file=str(tmp_path / "none"),
        gpu_query=lambda: GpuReading(58.0, 4.0, 55.9, 4608.0, 32768.0),
    ).sample()
    assert (s.gpu_temp, s.gpu_load, s.gpu_power) == (58.0, 4.0, 55.9)
    assert (s.vram_used_gb, s.vram_total_gb) == (4.5, 32.0)


def test_placeholder_sample_is_pending_and_keeps_disk_names():
    s = sources.SystemSample.placeholder(["/", "Fast"])
    assert s.pending is True
    assert s.disks == [("/", None), ("Fast", None)]
