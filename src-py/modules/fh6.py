from .base import GameModule


def _fmt(class_id: int) -> str:
    return {0: "D", 1: "C", 2: "B", 3: "A", 4: "S1", 5: "S2", 6: "R", 7: "X"}.get(
        class_id, "Unknown"
    )


def FH6Module() -> GameModule:
    return GameModule(
        process_name="forzahorizon6.exe",
        discord_client_id="1501533820564934737",
        uwp_package_name="",
        game_name="Forza Horizon 6",
        logo_asset_key="logo",
        _format_class=_fmt,
    )
