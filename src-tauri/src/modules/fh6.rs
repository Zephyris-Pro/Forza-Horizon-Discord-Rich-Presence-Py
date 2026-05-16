use super::GameModule;

pub struct FH6Module;

impl GameModule for FH6Module {
    fn target_process_name(&self) -> &'static str {
        "forzahorizon6.exe"
    }

    fn discord_client_id(&self) -> &'static str {
        "1501533820564934737"
    }

    fn uwp_package_name(&self) -> &'static str {
        ""
    }

    fn game_name(&self) -> &'static str {
        "Forza Horizon 6"
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
            6 => "R".into(),
            7 => "X".into(),
            _ => "Unknown".into(),
        }
    }
}
