from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class GameModule:
    process_name: str
    discord_client_id: str
    uwp_package_name: str
    game_name: str
    logo_asset_key: str
    _format_class: Callable[[int], str]

    def format_class(self, class_id: int) -> str:
        return self._format_class(class_id)
