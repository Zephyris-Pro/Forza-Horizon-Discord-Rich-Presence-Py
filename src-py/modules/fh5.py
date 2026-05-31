from .base import GameModule
from ._common import fmt_standard_classes


def FH5Module() -> GameModule:
    return GameModule(
        process_name="ForzaHorizon5.exe",
        discord_client_id="1501532618989113434",
        uwp_package_name="Microsoft.624F8B84B80_8wekyb3d8bbwe",
        game_name="Forza Horizon 5",
        logo_asset_key="logo",
        _format_class=fmt_standard_classes,
    )
