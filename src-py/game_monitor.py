import logging
import os
import queue
import threading
import time

from api import Api, AppState
from discord_rpc import DiscordRpc
from modules import ALL_MODULES
from telemetry import TelemetryServer
from xbox_presence import (
    XboxStatusReader,
    list_processes,
    get_process_image_path,
)

# We need to poll the Xbox presence API at a reasonable interval (not too fast to avoid rate limits, not too slow to keep presence updated).
PRESENCE_POLL_INTERVAL = 20

logger = logging.getLogger("forzarpc.monitor")


def _module_for_process(name, modules, *, exact=False):
    """Module dont le process_name matche `name`, ou None. Fonction pure."""
    n = (name or "").lower()
    if not n:
        return None
    for module in modules:
        target = module.process_name.lower()
        if (n == target) if exact else (target in n or n in target):
            return module
    return None


def _find_active_module(modules):
    procs = list_processes()
    for name, _pid in procs:
        module = _module_for_process(name, modules)
        if module:
            return module
    for _name, pid in procs:
        path = get_process_image_path(pid)
        if path:
            module = _module_for_process(os.path.basename(path), modules, exact=True)
            if module:
                return module
    return None


def _presence_poller(xbl_state: list, stop: threading.Event, module, api: Api):
    reader = XboxStatusReader(module.game_name)
    last_poll = 0.0

    while not stop.is_set():
        stop.wait(timeout=1.0)
        if stop.is_set():
            break

        if time.monotonic() - last_poll < PRESENCE_POLL_INTERVAL:
            continue
        last_poll = time.monotonic()

        try:
            xbl_state[0] = reader.poll()
            logger.debug("Presence poll -> %r", xbl_state[0])
        except Exception as e:
            xbl_state[0] = f"Error: {e}"
            logger.debug("Presence poll failed: %s", e)

        with api._state.lock:
            active = api._state.active_module
        if active:
            api.emit(
                "status_update",
                {
                    "status": "connected",
                    "game": active.game_name,
                    "details": "Broadcasting presence...",
                    "presence": xbl_state[0] or "Waiting for presence...",
                },
            )

    reader.close()


def _discord_updater(
    discord: DiscordRpc,
    data_queue: queue.Queue,
    db,
    module,
    xbl_state: list,
    stop: threading.Event,
    api: Api,
):
    last_tel = None

    while not stop.is_set():
        try:
            tel = data_queue.get(timeout=1.5)
            last_tel = tel
        except queue.Empty:
            pass

        if stop.is_set():
            break

        with api._state.lock:
            xbl = xbl_state[0]

        discord.update_presence(last_tel, db, module, xbl)

        if last_tel and last_tel.car_ordinal != 0:
            if db.get_car_name(last_tel.car_ordinal) is None:
                api.emit(
                    "unknown_car",
                    {
                        "id": last_tel.car_ordinal,
                        "class": module.format_class(last_tel.car_class),
                        "pi": last_tel.car_pi,
                    },
                )
            else:
                api.emit("unknown_car", None)


def monitor_loop(state: AppState, db, api: Api):
    is_running = False
    stop_event: threading.Event | None = None
    discord: DiscordRpc | None = None
    xbl_state = [None]

    while True:
        module = _find_active_module(ALL_MODULES)

        if module and not is_running:
            logger.info("Game detected: %s", module.game_name)
            is_running = True
            stop_event = threading.Event()
            xbl_state[0] = None

            data_queue: queue.Queue = queue.Queue(maxsize=16)
            tel_server = TelemetryServer()

            with state.lock:
                state.active_module = module
                state.telemetry_queue = data_queue
                state.telemetry_server = tel_server
                state.session_active = True
                port = state.telemetry_port
                relay = list(state.relay_targets)

            tel_server.start(port, data_queue, relay)

            discord = DiscordRpc()
            discord.connect(module.discord_client_id)

            api.emit(
                "status_update",
                {
                    "status": "connected",
                    "game": module.game_name,
                    "details": "Broadcasting presence...",
                    "presence": "Connecting...",
                },
            )

            threading.Thread(
                target=_presence_poller,
                args=(xbl_state, stop_event, module, api),
                daemon=True,
            ).start()

            threading.Thread(
                target=_discord_updater,
                args=(discord, data_queue, db, module, xbl_state, stop_event, api),
                daemon=True,
            ).start()

        elif not module and is_running:
            logger.info("Game session ended")
            is_running = False
            if stop_event:
                stop_event.set()
                stop_event = None

            with state.lock:
                state.active_module = None
                state.session_active = False
                if state.telemetry_server:
                    state.telemetry_server.stop()
                    state.telemetry_server = None
                state.telemetry_queue = None

            if discord:
                discord.disconnect()
                discord = None

            api.emit("unknown_car", None)
            api.emit(
                "status_update",
                {
                    "status": "disconnected",
                    "game": "",
                    "details": "Launch game to broadcast",
                },
            )

        time.sleep(3)
