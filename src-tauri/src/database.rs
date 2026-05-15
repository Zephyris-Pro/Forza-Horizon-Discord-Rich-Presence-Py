use std::collections::HashMap;
use std::fs;

use tauri::AppHandle;
use tauri::Manager;

pub struct CarDatabase {
    cars: HashMap<i32, String>,
}

impl CarDatabase {
    pub fn new(app_handle: &AppHandle) -> Self {
        let mut db = CarDatabase {
            cars: HashMap::new(),
        };
        db.load(app_handle);
        db
    }

    pub fn load(&mut self, app_handle: &AppHandle) {
        // 1. Load embedded database
        let embedded_json = include_bytes!("../cars.json");
        if let Ok(embedded_cars) = serde_json::from_slice::<HashMap<String, String>>(embedded_json) {
            for (k, v) in embedded_cars {
                if let Ok(id) = k.parse::<i32>() {
                    self.cars.insert(id, v);
                }
            }
        }

        // 2. Try to load update from AppData
        if let Some(app_dir) = app_handle.path().app_data_dir().ok() {
            let update_file = app_dir.join("cars_update.json");
            if update_file.exists() {
                if let Ok(update_data) = fs::read_to_string(update_file) {
                    if let Ok(updated_cars) = serde_json::from_str::<HashMap<String, String>>(&update_data) {
                        for (k, v) in updated_cars {
                            if let Ok(id) = k.parse::<i32>() {
                                self.cars.insert(id, v);
                            }
                        }
                    }
                }
            }
        }
    }

    pub fn get_car_name(&self, id: i32) -> String {
        self.cars.get(&id).cloned().unwrap_or_else(|| format!("Unknown Car ({})", id))
    }

    pub fn get_car_name_opt(&self, id: i32) -> Option<String> {
        self.cars.get(&id).cloned()
    }

    pub fn add_car_locally(&mut self, app_handle: &AppHandle, id: i32, name: String) -> Result<(), String> {
        self.cars.insert(id, name.clone());
        
        if let Some(app_dir) = app_handle.path().app_data_dir().ok() {
            let _ = fs::create_dir_all(&app_dir);
            let update_file = app_dir.join("cars_update.json");
            
            // Read existing update or start new
            let mut custom_map = if update_file.exists() {
                let data = fs::read_to_string(&update_file).unwrap_or_default();
                serde_json::from_str::<HashMap<String, String>>(&data).unwrap_or_default()
            } else {
                HashMap::new()
            };
            
            custom_map.insert(id.to_string(), name);
            
            if let Ok(json) = serde_json::to_string_pretty(&custom_map) {
                fs::write(update_file, json).map_err(|e| e.to_string())?;
            }
        }
        Ok(())
    }

    pub async fn check_for_updates(app_handle: AppHandle) -> Result<String, String> {
        // In a real scenario, this would fetch from a GitHub releases page or ForzaDB API.
        // For demonstration, we simulate an API call.
        
        let client = reqwest::Client::new();
        // Replace with actual URL when ready. For now, we simulate success if offline or fail gracefully.
        let target_url = "https://raw.githubusercontent.com/1Stalk/Forza-Horizon-Discord-Rich-Presence/main/src-tauri/cars.json"; 
        
        match client.get(target_url).send().await {
            Ok(response) => {
                let status = response.status();
                if status.is_success() {
                    if let Ok(json_text) = response.text().await {
                        // Validate JSON
                        if serde_json::from_str::<HashMap<String, String>>(&json_text).is_ok() {
                            if let Some(app_dir) = app_handle.path().app_data_dir().ok() {
                                let _ = fs::create_dir_all(&app_dir);
                                let update_file = app_dir.join("cars_update.json");
                                if fs::write(update_file, json_text).is_ok() {
                                    return Ok("Database successfully updated!".to_string());
                                }
                            }
                        } else {
                            return Err("Invalid database format".into());
                        }
                    }
                } else if status.as_u16() == 404 {
                    return Err("Update source not found (Check URL)".into());
                }
                Err(format!("Server returned error: {}", status))
            },
            Err(e) => {
                Err(format!("Network error: {}", e))
            }
        }
    }
}
