import json
import queue
import subprocess
import threading
import webbrowser

import requests

from database import CarDatabase
from modules import ALL_MODULES
from telemetry import TelemetryServer


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.xuid: str = ""
        self.telemetry_port: int = 8001
        self.relay_targets: list[str] = []
        self.active_module = None
        self.telemetry_server: TelemetryServer | None = None
        self.telemetry_queue: queue.Queue | None = None
        self.session_active: bool = False


class Api:
    def __init__(self, db: CarDatabase, state: AppState, settings=None):
        self._db = db
        self._state = state
        self._settings = settings
        self._window = None
        self._ui_ready = False

    def get_settings(self) -> dict:
        return self._settings.get_all() if self._settings else {}

    def set_setting(self, key: str, value):
        if self._settings:
            self._settings.set(key, value)

    def set_window(self, window):
        self._window = window

    def emit(self, event_name: str, payload):
        if not self._window or not self._ui_ready:
            return
        js = (
            f"window.dispatchEvent(new CustomEvent("
            f"{json.dumps(event_name)}, "
            f"{{detail: {json.dumps(payload)}}}));"
        )
        try:
            self._window.evaluate_js(js)
        except Exception:
            pass

    def ui_ready(self):
        self._ui_ready = True
        with self._state.lock:
            module = self._state.active_module
        if module:
            self.emit(
                "status_update",
                {
                    "status": "connected",
                    "game": module.game_name,
                    "details": "Broadcasting presence...",
                },
            )
        else:
            self.emit(
                "status_update",
                {
                    "status": "disconnected",
                    "game": "",
                    "details": "Launch game to broadcast",
                },
            )

    def check_uwp_status(self) -> bool:
        try:
            result = subprocess.run(
                ["CheckNetIsolation", "LoopbackExempt", "-s"],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
            )
            output = result.stdout.lower()
            for m in ALL_MODULES:
                if m.uwp_package_name and m.uwp_package_name.lower() not in output:
                    return False
            return True
        except Exception:
            return False

    def fix_uwp_isolation(self) -> str:
        packages = [m.uwp_package_name for m in ALL_MODULES if m.uwp_package_name]
        if not packages:
            return "Nothing to fix"

        needs_uac = False
        for pkg in packages:
            r = subprocess.run(
                ["CheckNetIsolation", "LoopbackExempt", "-a", f"-n={pkg}"],
                capture_output=True,
                creationflags=0x08000000,
            )
            if r.returncode != 0:
                needs_uac = True
                break

        if not needs_uac:
            return "Isolation fixed directly"

        script = " & ".join(
            f"CheckNetIsolation LoopbackExempt -a -n={pkg}" for pkg in packages
        )
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                f"Start-Process -FilePath 'cmd.exe' -ArgumentList '/c {script}' "
                f"-Verb RunAs -Wait -WindowStyle Hidden",
            ],
            creationflags=0x08000000,
            check=True,
        )
        return "Isolation fixed via UAC"

    def check_db_updates(self) -> str:
        return self._db.check_for_updates()

    def update_xuid(self, xuid: str):
        with self._state.lock:
            self._state.xuid = xuid

    def update_telemetry_port(self, port: int):
        with self._state.lock:
            if self._state.telemetry_port == port:
                return
            self._state.telemetry_port = port
            if self._state.session_active and self._state.telemetry_server:
                self._state.telemetry_server.restart(
                    port,
                    self._state.telemetry_queue,
                    list(self._state.relay_targets),
                )

    def update_relay_ports(self, targets: list):
        addrs = [
            f"{t['ip']}:{t['port']}" for t in targets if t.get("ip") and t.get("port")
        ]
        with self._state.lock:
            self._state.relay_targets = addrs
            if self._state.session_active and self._state.telemetry_server:
                self._state.telemetry_server.restart(
                    self._state.telemetry_port,
                    self._state.telemetry_queue,
                    addrs,
                )

    def set_window_height(self, height: int):
        if self._window:
            try:
                self._window.resize(530, int(height))
            except Exception:
                pass

    def hide_window(self):
        if self._window:
            self._window.hide()

    def show_window(self):
        if self._window:
            self._window.show()

    def open_url(self, url: str):
        webbrowser.open(url)

    def report_car_name(self, car_id: int, car_name: str, game: str) -> str:
        self._db.add_car_locally(car_id, car_name)
        resp = requests.post(
            "https://forza-rpc-backend.vercel.app/api/report",
            json={"car_id": car_id, "car_name": car_name, "game": game},
            timeout=10,
        )
        if resp.ok:
            return "Report sent! Name saved locally."
        raise RuntimeError(f"Server returned: {resp.status_code}")
