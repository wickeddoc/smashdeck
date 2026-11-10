# pages/monitor/sources.py
"""System metric sources: psutil, sysfs hwmon and nvidia-smi.

Every reading is optional. A missing sensor, driver or binary yields None for
that field only, so the page shows "n/a" for one key instead of failing.
"""
from __future__ import annotations

import os
import subprocess
import time
import traceback
from dataclasses import dataclass, field

import psutil

CPU_TEMP_SENSORS = (("zenpower", "Tctl"), ("k10temp", "Tctl"), ("coretemp", "Package id 0"))
CPU_POWER_SENSOR = ("zenpower", "RAPL_P_Package")
PC_POWER_SENSOR = ("corsairpsu", "power total")
NVIDIA_QUERY = "temperature.gpu,utilization.gpu,power.draw,memory.used,memory.total"


@dataclass
class SystemSample:
    """One poll's readings; None means unavailable (or no rate yet)."""

    cpu_temp: float | None = None  # °C
    cpu_load: float | None = None  # %
    cpu_power: float | None = None  # W
    gpu_temp: float | None = None
    gpu_load: float | None = None
    gpu_power: float | None = None
    vram_used_gb: float | None = None
    vram_total_gb: float | None = None
    pc_power: float | None = None
    ram_percent: float | None = None
    disks: list[tuple[str, float | None]] = field(default_factory=list)  # (name, % full)
    ssd_temp: float | None = None
    disk_read: float | None = None  # bytes/s
    disk_write: float | None = None
    net_down: float | None = None
    net_up: float | None = None
    pending: bool = False  # True before the first real sample

    @classmethod
    def placeholder(cls, disk_names) -> SystemSample:
        """Shown before the first real sample: every key reads "—"."""
        return cls(disks=[(name, None) for name in disk_names], pending=True)


@dataclass(frozen=True)
class GpuReading:
    temp: float | None
    load: float | None
    power: float | None
    mem_used_mib: float | None
    mem_total_mib: float | None


def read_hwmon_power(root: str, driver: str, label: str) -> float | None:
    """Watts from the hwmon power sensor `label` of driver `driver`, or None."""
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return None
    for entry in entries:
        base = os.path.join(root, entry)
        try:
            with open(os.path.join(base, "name")) as f:
                if f.read().strip() != driver:
                    continue
            for fname in sorted(os.listdir(base)):
                if not (fname.startswith("power") and fname.endswith("_label")):
                    continue
                with open(os.path.join(base, fname)) as f:
                    if f.read().strip() != label:
                        continue
                with open(os.path.join(base, fname[: -len("_label")] + "_input")) as f:
                    return int(f.read().strip()) / 1e6  # µW -> W
        except (OSError, ValueError):
            continue
    return None


def cpu_temp(temps: dict) -> float | None:
    """CPU temperature from psutil.sensors_temperatures() output."""
    for driver, label in CPU_TEMP_SENSORS:
        for entry in temps.get(driver, []):
            if entry.label == label:
                return entry.current
    return None


def ssd_temp(temps: dict) -> float | None:
    """Hottest NVMe 'Composite' reading (any NVMe reading if none is labelled)."""
    entries = temps.get("nvme", [])
    values = [e.current for e in entries if e.label == "Composite"] or [e.current for e in entries]
    return max(values) if values else None


def default_route_interface(route_text: str) -> str | None:
    """Interface of the lowest-metric default route in /proc/net/route text."""
    best = None
    for line in route_text.splitlines()[1:]:
        cols = line.split()
        if len(cols) < 7 or cols[1] != "00000000":
            continue
        metric = int(cols[6])
        if best is None or metric < best[0]:
            best = (metric, cols[0])
    return best[1] if best else None


def parse_nvidia_smi(stdout: str) -> GpuReading | None:
    """First GPU's line of `nvidia-smi --format=csv,noheader,nounits` output."""
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    values = []
    for raw in lines[0].split(","):
        try:
            values.append(float(raw.strip()))
        except ValueError:  # "[N/A]", "[Not Supported]"
            values.append(None)
    if len(values) != 5:
        return None
    return GpuReading(*values)


def query_nvidia_smi(timeout: float = 2.0) -> GpuReading | None:
    out = subprocess.run(
        ["nvidia-smi", f"--query-gpu={NVIDIA_QUERY}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=timeout, check=True,
    ).stdout
    return parse_nvidia_smi(out)


class Rate:
    """Turns a cumulative counter into a per-second rate."""

    def __init__(self):
        self._last: tuple[float, float] | None = None  # (time, counter)

    def update(self, counter: float, now: float) -> float | None:
        last, self._last = self._last, (now, counter)
        if last is None or counter < last[1] or now <= last[0]:
            return None
        return (counter - last[1]) / (now - last[0])


class SystemSampler:
    def __init__(self, disks=(), net_interface=None, hwmon_root="/sys/class/hwmon",
                 route_file="/proc/net/route", clock=time.monotonic,
                 gpu_query=query_nvidia_smi):
        self.disks = [(d["name"], d["path"]) for d in disks][:2]
        self.net_interface = net_interface
        self.hwmon_root = hwmon_root
        self.route_file = route_file
        self.gpu_query = gpu_query
        self._clock = clock
        self._rates = {name: Rate() for name in ("read", "write", "down", "up")}
        self._iface: str | None = None
        self._cpu_primed = False
        self._failed: set[str] = set()

    def _try(self, name, fn, default=None):
        try:
            return fn()
        except Exception:
            if name not in self._failed:  # log once per source, not every tick
                self._failed.add(name)
                print(f"monitor: source '{name}' unavailable:")
                traceback.print_exc()
            return default

    def _cpu_load(self):
        value = psutil.cpu_percent(interval=None)
        if not self._cpu_primed:  # the first call has no reference interval
            self._cpu_primed = True
            return None
        return value

    def _net_counters(self):
        iface = self.net_interface
        if iface is None:
            with open(self.route_file) as f:
                iface = default_route_interface(f.read())
        if iface != self._iface:  # interface changed: old counters don't apply
            self._iface = iface
            self._rates["down"], self._rates["up"] = Rate(), Rate()
        if iface is None:
            return None
        return psutil.net_io_counters(pernic=True).get(iface)

    def sample(self) -> SystemSample:
        now = self._clock()
        s = SystemSample()

        temps = self._try("sensors", psutil.sensors_temperatures) or {}
        s.cpu_temp = cpu_temp(temps)
        s.ssd_temp = ssd_temp(temps)
        s.cpu_load = self._try("cpu_load", self._cpu_load)
        s.cpu_power = self._try("cpu_power", lambda: read_hwmon_power(self.hwmon_root, *CPU_POWER_SENSOR))
        s.pc_power = self._try("pc_power", lambda: read_hwmon_power(self.hwmon_root, *PC_POWER_SENSOR))

        gpu = self._try("gpu", self.gpu_query)
        if gpu is not None:
            s.gpu_temp, s.gpu_load, s.gpu_power = gpu.temp, gpu.load, gpu.power
            if gpu.mem_used_mib is not None:
                s.vram_used_gb = gpu.mem_used_mib / 1024
            if gpu.mem_total_mib is not None:
                s.vram_total_gb = gpu.mem_total_mib / 1024

        s.ram_percent = self._try("ram", lambda: psutil.virtual_memory().percent)
        s.disks = [
            (name, self._try(f"disk {path}", lambda p=path: psutil.disk_usage(p).percent))
            for name, path in self.disks
        ]

        io = self._try("disk_io", psutil.disk_io_counters)
        if io is not None:
            s.disk_read = self._rates["read"].update(io.read_bytes, now)
            s.disk_write = self._rates["write"].update(io.write_bytes, now)

        nic = self._try("net", self._net_counters)
        if nic is not None:
            s.net_down = self._rates["down"].update(nic.bytes_recv, now)
            s.net_up = self._rates["up"].update(nic.bytes_sent, now)
        return s
