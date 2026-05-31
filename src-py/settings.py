import json
import os
import threading


class SettingsStore:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict = self._load()

    def _load(self) -> dict:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get_all(self) -> dict:
        with self._lock:
            return dict(self._data)

    def set(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = value
            self._save()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
