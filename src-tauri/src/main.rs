// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod database;
mod discord;
mod modules;
mod telemetry;

use std::sync::{Arc, Mutex};
use std::time::Duration;
use std::os::windows::process::CommandExt;
use sysinfo::System;
use tauri::{AppHandle, Manager, Emitter};
use tauri::tray::{TrayIconBuilder, MouseButton, MouseButtonState, TrayIconEvent};
use tauri::menu::{Menu, MenuItem};
use tokio::sync::broadcast;

use database::CarDatabase;
use discord::DiscordService;
use modules::{fh4::FH4Module, GameModule};
use telemetry::TelemetryServer;

struct AppState {
    db: Arc<Mutex<CarDatabase>>,
    game_module: Arc<dyn GameModule>,
}

#[tauri::command]
async fn fix_uwp_isolation(state: tauri::State<'_, AppState>) -> Result<String, String> {
    let package_name = state.game_module.uwp_package_name();
    
    // Command to exempt UWP app from loopback isolation.
    // Needs elevation. We use tauri-plugin-shell or std::process.
    // To ask for elevation on Windows without external crates, we can use powershell Start-Process -Verb RunAs
    let status = std::process::Command::new("powershell")
        .args(&[
            "-Command",
            &format!("Start-Process -FilePath 'CheckNetIsolation.exe' -ArgumentList 'LoopbackExempt -a -n={}' -Verb RunAs -WindowStyle Hidden", package_name)
        ])
        .status()
        .map_err(|e| e.to_string())?;

    if status.success() {
        Ok("Isolation fixed".into())
    } else {
        Err("Failed to execute command".into())
    }
}

#[tauri::command]
async fn check_db_updates(app: tauri::AppHandle) -> Result<String, String> {
    CarDatabase::check_for_updates(app).await
}

#[tauri::command]
async fn check_uwp_status(state: tauri::State<'_, AppState>) -> Result<bool, String> {
    let package_name = state.game_module.uwp_package_name().to_lowercase();
    if package_name.is_empty() {
        return Ok(true); // No UWP fix needed for this game
    }

    let output = std::process::Command::new("CheckNetIsolation")
        .arg("LoopbackExempt")
        .arg("-s")
        .creation_flags(0x08000000) // CREATE_NO_WINDOW
        .output()
        .map_err(|e: std::io::Error| e.to_string())?;

    let output_str = String::from_utf8_lossy(&output.stdout).to_lowercase();
    
    // If the package name is explicitly found in the output, it's exempt
    if output_str.contains(&package_name) {
        return Ok(true);
    }
    
    Ok(false)
}

#[tauri::command]
fn ui_ready() {
    // Frontend is ready to receive status updates
}

fn create_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let show_i = MenuItem::with_id(app, "show", "Settings", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_i, &quit_i])?;

    let _tray = TrayIconBuilder::new()
        .menu(&menu)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "quit" => {
                std::process::exit(0);
            }
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
        })
        .icon(app.default_window_icon().unwrap().clone())
        .build(app)?;

    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            create_tray(app)?;
            
            // Hide window on start to run in background
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.hide();
            }

            let app_handle = app.handle().clone();
            
            let db = Arc::new(Mutex::new(CarDatabase::new(&app_handle)));
            let game_module: Arc<dyn GameModule> = Arc::new(FH4Module);

            app.manage(AppState {
                db: db.clone(),
                game_module: game_module.clone(),
            });

            // Start background monitor task
            let module = game_module.clone();
            let app_handle_clone = app_handle.clone();
            
            tauri::async_runtime::spawn(async move {
                let mut sys = System::new_all();
                let server = Arc::new(TelemetryServer::new());
                let discord_service = Arc::new(DiscordService::new(module.discord_client_id()));
                
                let (tx, mut rx) = broadcast::channel(16);
                let mut is_game_running = false;

                // Handle telemetry data
                let db_clone = db.clone();
                let discord_clone = discord_service.clone();
                tauri::async_runtime::spawn(async move {
                    while let Ok(data) = rx.recv().await {
                        let db_lock = db_clone.lock().unwrap();
                        discord_clone.update_presence(&data, &db_lock);
                    }
                });

                loop {
                    sys.refresh_processes();
                    let process_name = module.target_process_name();
                    let mut found = false;

                    for process in sys.processes().values() {
                        if process.name() == process_name {
                            found = true;
                            break;
                        }
                    }

                    if found && !is_game_running {
                        // Game started
                        is_game_running = true;
                        println!("Game started: {}", process_name);
                        
                        let _ = discord_service.connect();
                        server.start(9909, tx.clone());

                        let _ = app_handle_clone.emit("status_update", serde_json::json!({
                            "status": "connected",
                            "game": module.game_name(),
                            "details": "Broadcasting presence..."
                        }));

                    } else if !found && is_game_running {
                        // Game stopped
                        is_game_running = false;
                        println!("Game stopped.");
                        
                        server.stop();
                        discord_service.disconnect();

                        let _ = app_handle_clone.emit("status_update", serde_json::json!({
                            "status": "disconnected",
                            "game": "",
                            "details": "Waiting for game..."
                        }));
                    }

                    tokio::time::sleep(Duration::from_secs(3)).await;
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| match event {
            tauri::WindowEvent::CloseRequested { api, .. } => {
                window.hide().unwrap();
                api.prevent_close();
            }
            _ => {}
        })
        .invoke_handler(tauri::generate_handler![
            fix_uwp_isolation,
            check_uwp_status,
            check_db_updates,
            ui_ready
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
