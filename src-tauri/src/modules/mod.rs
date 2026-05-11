pub mod fh4;
pub mod fh5;

pub trait GameModule: Send + Sync {
    fn target_process_name(&self) -> &'static str;
    fn discord_client_id(&self) -> &'static str;
    fn uwp_package_name(&self) -> &'static str;
    fn game_name(&self) -> &'static str;
    fn logo_asset_key(&self) -> &'static str;
    fn format_class(&self, class_id: i32) -> String;
}
