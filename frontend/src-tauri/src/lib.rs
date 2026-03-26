use serde::Serialize;
use std::sync::Mutex;
use tauri::Manager;

#[derive(Clone, Serialize)]
struct BackendStatus {
    online: bool,
    version: String,
    message: String,
}

struct BackendProcess(Mutex<Option<std::process::Child>>);

impl Drop for BackendProcess {
    fn drop(&mut self) {
        if let Some(ref mut child) = *self.0.lock().unwrap() {
            println!("[tauri] Stopping backend (PID: {})...", child.id());
            let _ = child.kill();
            let _ = child.wait();
            println!("[tauri] Backend stopped.");
        }
    }
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! MoldGen backend ready.", name)
}

#[tauri::command]
fn get_app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[tauri::command]
async fn check_backend_health() -> Result<BackendStatus, String> {
    match reqwest::get("http://127.0.0.1:8000/api/v1/system/health").await {
        Ok(resp) => {
            let status_code = resp.status();
            if status_code.is_success() {
                if let Ok(json) = resp.json::<serde_json::Value>().await {
                    return Ok(BackendStatus {
                        online: true,
                        version: json["version"]
                            .as_str()
                            .unwrap_or("unknown")
                            .to_string(),
                        message: "Backend is online".to_string(),
                    });
                }
            }
            Ok(BackendStatus {
                online: false,
                version: String::new(),
                message: format!("Backend returned status: {}", status_code),
            })
        }
        Err(e) => Ok(BackendStatus {
            online: false,
            version: String::new(),
            message: format!("Cannot reach backend: {}", e),
        }),
    }
}

#[tauri::command]
async fn wait_for_backend(max_seconds: u64) -> Result<BackendStatus, String> {
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(max_seconds);
    loop {
        match reqwest::get("http://127.0.0.1:8000/api/v1/system/health").await {
            Ok(resp) if resp.status().is_success() => {
                if let Ok(json) = resp.json::<serde_json::Value>().await {
                    return Ok(BackendStatus {
                        online: true,
                        version: json["version"]
                            .as_str()
                            .unwrap_or("unknown")
                            .to_string(),
                        message: "Backend is online".to_string(),
                    });
                }
            }
            _ => {}
        }
        if std::time::Instant::now() >= deadline {
            return Ok(BackendStatus {
                online: false,
                version: String::new(),
                message: format!("Backend did not start within {} seconds", max_seconds),
            });
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
}

fn spawn_backend(app: &tauri::App) -> Option<std::process::Child> {
    let resource_dir = app.path().resource_dir().ok()?;

    let sidecar_name = if cfg!(target_os = "windows") {
        "moldgen-server.exe"
    } else {
        "moldgen-server"
    };

    let sidecar_path = resource_dir.join("binaries").join(sidecar_name);

    if sidecar_path.exists() {
        println!("[tauri] Launching backend sidecar: {:?}", sidecar_path);
        match std::process::Command::new(&sidecar_path)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
        {
            Ok(child) => {
                println!("[tauri] Backend started with PID: {}", child.id());
                return Some(child);
            }
            Err(e) => {
                eprintln!("[tauri] Failed to launch sidecar: {}", e);
            }
        }
    } else {
        println!(
            "[tauri] Sidecar not found at {:?}, trying Python fallback",
            sidecar_path
        );
    }

    for python in &["python", "python3"] {
        if std::process::Command::new(python)
            .arg("--version")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .is_ok()
        {
            println!("[tauri] Starting backend via {}", python);
            match std::process::Command::new(python)
                .args(["-m", "moldgen"])
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::piped())
                .spawn()
            {
                Ok(child) => {
                    println!("[tauri] Backend started via {}, PID: {}", python, child.id());
                    return Some(child);
                }
                Err(e) => {
                    eprintln!("[tauri] Failed to start via {}: {}", python, e);
                }
            }
        }
    }

    println!("[tauri] No backend launcher found — expecting manually-started backend");
    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            #[cfg(desktop)]
            {
                let handle = app.handle().clone();
                handle.plugin(tauri_plugin_updater::Builder::new().build())?;
            }

            let child = spawn_backend(app);
            if let Some(child) = child {
                let state: tauri::State<BackendProcess> = app.state();
                *state.0.lock().unwrap() = Some(child);
            }

            let window = app.get_webview_window("main").unwrap();
            window
                .set_title("MoldGen — AI 医学教具模具工作站")
                .ok();

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            greet,
            get_app_version,
            check_backend_health,
            wait_for_backend,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
