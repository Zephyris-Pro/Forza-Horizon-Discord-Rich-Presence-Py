import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "src-py"))

import logging
import threading

import webview
import pystray
from PIL import Image

from api import Api, AppState
from database import CarDatabase
from game_monitor import monitor_loop
from settings import SettingsStore

CARS_JSON = os.path.join(BASE_DIR, "assets", "cars.json")
APPDATA_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "ForzaRPC"
)
SETTINGS_PATH = os.path.join(APPDATA_DIR, "settings.json")
ICON_PATH = os.path.join(BASE_DIR, "assets", "icon.ico")
HTML_PATH = os.path.join(BASE_DIR, "src", "index.html")


def _setup_logging():
    """Logge tout en DEBUG vers la console, en réduisant le bruit des libs tierces."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("comtypes", "urllib3", "PIL", "asyncio", "webview", "pystray"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main():
    _setup_logging()
    logging.getLogger("forzarpc").info("ForzaRPC starting (debug logging enabled)")
    db = CarDatabase(CARS_JSON, APPDATA_DIR)
    state = AppState()
    settings = SettingsStore(SETTINGS_PATH)
    api = Api(db, state, settings)

    window = webview.create_window(
        "Forza Rich Presence",
        url=HTML_PATH,
        js_api=api,
        width=530,
        height=365,
        resizable=False,
        min_size=(530, 395),
    )
    api.set_window(window)

    def on_closing():
        window.hide()
        return False

    window.events.closing += on_closing

    def stop_app(icon=None):
        if icon:
            icon.stop()
        with state.lock:
            if state.telemetry_server:
                state.telemetry_server.stop()
        os._exit(0)

    image = Image.open(ICON_PATH)
    menu = pystray.Menu(
        pystray.MenuItem("Settings", lambda icon, item: window.show()),
        pystray.MenuItem("Quit", lambda icon, item: stop_app(icon)),
    )
    tray = pystray.Icon("ForzaRPC", image, "Forza Rich Presence", menu)
    threading.Thread(target=tray.run, daemon=True).start()

    threading.Thread(
        target=monitor_loop,
        args=(state, db, api),
        daemon=True,
    ).start()

    storage_path = os.path.join(APPDATA_DIR, "webview")
    os.makedirs(storage_path, exist_ok=True)
    webview.start(
        debug=False, private_mode=False, storage_path=storage_path, icon=ICON_PATH
    )


if __name__ == "__main__":
    main()
