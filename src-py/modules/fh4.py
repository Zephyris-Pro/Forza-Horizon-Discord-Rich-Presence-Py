from .base import GameModule
from ._common import fmt_standard_classes


def FH4Module() -> GameModule:
    return GameModule(
        process_name="forzahorizon4.exe",
        discord_client_id="1501483341164183562",
        uwp_package_name="Microsoft.SunriseBaseGame_8wekyb3d8bbwe",
        game_name="Forza Horizon 4",
        logo_asset_key="logo",
        _format_class=fmt_standard_classes,
    )
