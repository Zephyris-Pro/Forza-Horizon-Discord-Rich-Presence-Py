import json
import os
import requests


class CarDatabase:
    UPDATE_URL = (
        "https://raw.githubusercontent.com/1Stalk/"
        "Forza-Horizon-Discord-Rich-Presence/main/src-tauri/cars.json"
    )

    def __init__(self, cars_json_path: str, appdata_dir: str):
        self._cars_json_path = cars_json_path
        self._appdata_dir = appdata_dir
        self._cars: dict[int, str] = {}
        self.reload()

    def reload(self):
        self._cars.clear()
        self._load_file(self._cars_json_path)
        self._load_file(os.path.join(self._appdata_dir, "cars_local.json"))
        self._load_file(os.path.join(self._appdata_dir, "cars_update.json"))

    def _load_file(self, path: str):
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                try:
                    self._cars[int(k)] = v
                except ValueError:
                    pass
        except Exception:
            pass

    def get_car_name(self, car_id: int) -> str | None:
        return self._cars.get(car_id)

    def add_car_locally(self, car_id: int, name: str):
        self._cars[car_id] = name
        os.makedirs(self._appdata_dir, exist_ok=True)
        local_path = os.path.join(self._appdata_dir, "cars_local.json")
        existing = {}
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing[str(car_id)] = name
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

    def check_for_updates(self) -> str:
        response = requests.get(self.UPDATE_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid database format")
        os.makedirs(self._appdata_dir, exist_ok=True)
        update_path = os.path.join(self._appdata_dir, "cars_update.json")
        with open(update_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.reload()
        return "Database successfully updated!"
