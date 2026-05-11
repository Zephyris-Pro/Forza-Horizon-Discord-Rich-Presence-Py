use super::GameModule;

pub struct FH4Module;

impl GameModule for FH4Module {
    fn target_process_name(&self) -> &'static str {
        "ForzaHorizon4.exe"
    }

    fn discord_client_id(&self) -> &'static str {
        "1501483341164183562"
    }

    fn uwp_package_name(&self) -> &'static str {
        "Microsoft.SunriseBaseGame_8wekyb3d8bbwe"
    }

    fn game_name(&self) -> &'static str {
        "Forza Horizon 4"
    }

    fn logo_asset_key(&self) -> &'static str {
        "logo"
    }

    fn format_class(&self, class_id: i32) -> String {
        match class_id {
            0 => "D".into(),
            1 => "C".into(),
            2 => "B".into(),
            3 => "A".into(),
            4 => "S1".into(),
            5 => "S2".into(),
            6 => "X".into(),
            _ => "Unknown".into(),
        }
    }
}
