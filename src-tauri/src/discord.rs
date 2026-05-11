use discord_rich_presence::{activity, DiscordIpc, DiscordIpcClient};
use std::sync::Mutex;
use crate::telemetry::TelemetryData;
use crate::database::CarDatabase;
use crate::modules::GameModule;

pub struct DiscordService {
    client: Mutex<Option<DiscordIpcClient>>,
    client_id: String,
    start_time: i64,
}

impl DiscordService {
    pub fn new(client_id: &str) -> Self {
        let start_time = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;

        Self {
            client: Mutex::new(None),
            client_id: client_id.to_string(),
            start_time,
        }
    }

    pub fn connect(&self) -> Result<(), Box<dyn std::error::Error>> {
        let mut client = DiscordIpcClient::new(&self.client_id)?;
        client.connect()?;
        
        let mut lock = self.client.lock().unwrap();
        *lock = Some(client);
        
        Ok(())
    }

    pub fn disconnect(&self) {
        let mut lock = self.client.lock().unwrap();
        if let Some(mut client) = lock.take() {
            let _ = client.clear_activity();
            let _ = client.close();
        }
    }

    pub fn update_presence(&self, data: &TelemetryData, db: &CarDatabase, module: &dyn GameModule, xbl_state: Option<&str>) {
        let mut lock = self.client.lock().unwrap();
        if let Some(client) = lock.as_mut() {
            let car_name = db.get_car_name(data.car_ordinal);
            let display_name = if car_name.chars().count() > 25 {
                let truncated: String = car_name.chars().take(22).collect();
                format!("{}...", truncated)
            } else {
                car_name.clone()
            };

            let class_str = module.format_class(data.car_class);
            // let telemetry_str = format!("{} | {:.0} km/h | Class {} ({})", car_name, data.speed_kmh.abs(), class_str, data.car_pi);
            let telemetry_str = format!("{} | {} ({})", display_name, class_str, data.car_pi);

            let mut details_str = String::new(); // Top line
            let mut state_str = String::new();   // Bottom line

            if let Some(xbl) = xbl_state {
                // OpenXBL goes to the top
                details_str = xbl.to_string();
                
                if data.is_race_on != 0 {
                    // Telemetry goes to the bottom
                    state_str = telemetry_str;
                }
            } else {
                // No OpenXBL fallback
                if data.is_race_on != 0 {
                    details_str = car_name.clone();
                    // state_str = format!("{:.0} km/h | Class {} ({})", data.speed_kmh.abs(), class_str, data.car_pi);
                    state_str = format!("{} ({})", class_str, data.car_pi);
                }
                // If is_race_on == 0, we leave both empty (no "In Menus")
            }

            let class_key = format!("class_{}", class_str.to_lowercase());
            let hover_text = format!("{} | {} ({})", car_name, class_str, data.car_pi);

            let mut payload = activity::Activity::new()
                .timestamps(activity::Timestamps::new().start(self.start_time));

            if !details_str.is_empty() {
                payload = payload.details(&details_str);
            }
            
            if !state_str.is_empty() {
                payload = payload.state(&state_str);
            }

            // Assets logic
            if data.is_race_on == 0 {
                payload = payload.assets(activity::Assets::new().large_image("menu_icon"));
            } else {
                let mut assets = activity::Assets::new()
                    .large_image(module.logo_asset_key())
                    .small_image(&class_key)
                    .small_text(&hover_text);
                
                if let Some(xbl) = xbl_state {
                    assets = assets.large_text(xbl);
                }
                
                payload = payload.assets(assets);
            }

            let _ = client.set_activity(payload);
        }
    }
}
