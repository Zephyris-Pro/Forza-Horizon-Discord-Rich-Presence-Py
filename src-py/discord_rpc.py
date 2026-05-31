import time
from typing import Any

from telemetry import TelemetryData

try:
    from pypresence import Presence
except ImportError:
    Presence = None

_INVALID_XBL = {
    "connecting...",
    "disconnected",
    "connected (no activity)",
    "waiting for game...",
}


class DiscordRpc:
    def __init__(self):
        self._presence = None
        self._start_time = int(time.time())
        self._last_car: TelemetryData | None = None
        self._last_xbl: str | None = None

    def connect(self, client_id: str):
        if Presence is None:
            print("[Discord] pypresence not installed")
            return
        try:
            self._presence = Presence(client_id)
            self._presence.connect()
            self._start_time = int(time.time())
        except Exception as e:
            print(f"[Discord] Failed to connect: {e}")
            self._presence = None

    def disconnect(self):
        if self._presence:
            try:
                self._presence.clear()
                self._presence.close()
            except Exception:
                pass
            self._presence = None
        self._last_car = None
        self._last_xbl = None

    def update_presence(self, telemetry, db, module, xbl_state: str | None):
        if not self._presence:
            return
        payload = self._build_payload(telemetry, db, module, xbl_state)
        try:
            self._presence.update(
                details=payload["details"],
                state=payload["state"],
                large_image=payload["large_image"],
                large_text=payload.get("large_text"),
                small_image=payload.get("small_image"),
                small_text=payload.get("small_text"),
                start=self._start_time,
            )
        except Exception as e:
            print(f"[Discord] update failed: {e}")

    def _build_payload(
        self, telemetry, db, module, xbl_state: str | None
    ) -> dict[str, Any]:
        valid_xbl = _validate_xbl(xbl_state)
        if valid_xbl:
            self._last_xbl = valid_xbl
        effective_xbl = self._last_xbl

        if telemetry and telemetry.car_ordinal != 0:
            self._last_car = telemetry
        effective_tel = self._last_car

        fallback = None
        if effective_tel and not effective_xbl:
            fallback = {
                "Forza Horizon 4": "Exploring Great Britain",
                "Forza Horizon 5": "Exploring Mexico",
            }.get(module.game_name, "Exploring Japan")
        display_location = effective_xbl or fallback

        details: str | None = None
        state: str | None = None
        small_image: str | None = None
        small_text: str | None = None
        large_text: str | None = display_location

        if effective_tel:
            car_name = db.get_car_name(effective_tel.car_ordinal)
            is_unknown = car_name is None
            if is_unknown:
                car_name = f"Unknown Car ({effective_tel.car_ordinal})"

            display_name = car_name[:22] + "..." if len(car_name) > 25 else car_name
            class_str = module.format_class(effective_tel.car_class)

            if display_location:
                details = display_location
                if not is_unknown:
                    state = f"{display_name} | {class_str} ({effective_tel.car_pi})"
            else:
                if not is_unknown:
                    details = car_name
                    state = f"{class_str} ({effective_tel.car_pi})"

            if not is_unknown:
                small_image = f"class_{class_str.lower()}"
                small_text = f"{car_name} | {class_str} ({effective_tel.car_pi})"
        else:
            details = display_location

        return {
            "details": details,
            "state": state,
            "large_image": module.logo_asset_key,
            "large_text": large_text,
            "small_image": small_image,
            "small_text": small_text,
        }


def _validate_xbl(s: str | None) -> str | None:
    if not s:
        return None
    trimmed = s.strip()
    lower = trimmed.lower()
    if (
        lower in _INVALID_XBL
        or lower.startswith("error:")
        or lower.startswith("api error")
        or lower.startswith("network error")
    ):
        return None
    return trimmed
