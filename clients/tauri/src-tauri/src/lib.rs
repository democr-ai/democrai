use serde_json::Value;
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::webview::{Cookie, PageLoadEvent};
use tauri::{AppHandle, Emitter, Manager, State};

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
#[cfg(unix)]
use std::os::unix::net::UnixStream;

#[cfg(unix)]
type IpcStream = UnixStream;

#[cfg(not(unix))]
type IpcStream = std::net::TcpStream;

struct IpcState {
    writer: Mutex<Option<IpcStream>>,
    jwt: Mutex<String>,
    session_key: String,
}

impl Default for IpcState {
    fn default() -> Self {
        Self {
            writer: Mutex::new(None),
            jwt: Mutex::new(load_desktop_jwt().unwrap_or_default()),
            session_key: generate_session_key(),
        }
    }
}

fn generate_session_key() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    format!("{:016x}{:08x}{:08x}", nanos, process::id(), 0)
}

fn home_dir() -> Option<PathBuf> {
    env::var_os("HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("USERPROFILE").map(PathBuf::from))
}

fn desktop_jwt_path() -> Option<PathBuf> {
    home_dir().map(|home| home.join(".democrai").join("auth_token"))
}

fn load_desktop_jwt() -> Option<String> {
    let path = desktop_jwt_path()?;
    let token = fs::read_to_string(path).ok()?.trim().to_string();
    if token.is_empty() {
        None
    } else {
        Some(token)
    }
}

fn save_desktop_jwt(token: &str) -> Result<(), String> {
    let path =
        desktop_jwt_path().ok_or_else(|| "Unable to resolve desktop JWT path".to_string())?;
    if token.is_empty() {
        match fs::remove_file(&path) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(format!("Unable to remove desktop JWT: {error}")),
        }
        return Ok(());
    }

    let dir = path
        .parent()
        .ok_or_else(|| "Unable to resolve desktop JWT directory".to_string())?;
    fs::create_dir_all(dir)
        .map_err(|error| format!("Unable to create desktop JWT directory: {error}"))?;
    #[cfg(unix)]
    {
        fs::set_permissions(dir, fs::Permissions::from_mode(0o700))
            .map_err(|error| format!("Unable to set desktop JWT directory permissions: {error}"))?;
    }

    fs::write(&path, token).map_err(|error| format!("Unable to write desktop JWT: {error}"))?;
    #[cfg(unix)]
    {
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600))
            .map_err(|error| format!("Unable to set desktop JWT permissions: {error}"))?;
    }
    Ok(())
}

fn set_state_jwt(state: &IpcState, token: &str) -> Result<(), String> {
    {
        let mut jwt = state
            .jwt
            .lock()
            .map_err(|_| "IPC JWT lock poisoned".to_string())?;
        if jwt.as_str() == token {
            return Ok(());
        }
        *jwt = token.to_string();
    }
    save_desktop_jwt(token)
}

fn configured_http_base_url() -> String {
    env::var("DEMOCRAI_TAURI_HTTP_BASE_URL")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "http://localhost:8000".to_string())
}

fn host_from_http_url(url: &str) -> Option<String> {
    let rest = url
        .strip_prefix("http://")
        .or_else(|| url.strip_prefix("https://"))?;
    let host_port = rest.split('/').next().unwrap_or_default();
    let host = host_port.rsplit('@').next().unwrap_or(host_port);
    let host = host.split(':').next().unwrap_or_default().trim();
    if host.is_empty() {
        None
    } else {
        Some(host.to_string())
    }
}

fn cookie_domain() -> String {
    env::var("DEMOCRAI_TAURI_COOKIE_DOMAIN")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .or_else(|| host_from_http_url(&configured_http_base_url()))
        .unwrap_or_else(|| "localhost".to_string())
}

fn auth_cookie_name() -> String {
    env::var("DEMOCRAI_TAURI_AUTH_COOKIE_NAME")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "session".to_string())
}

fn session_cookie_name() -> String {
    env::var("DEMOCRAI_TAURI_SESSION_COOKIE_NAME")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "democrai_sid".to_string())
}

fn build_cookie(name: String, value: String, domain: &str) -> Cookie<'static> {
    Cookie::build((name, value))
        .domain(domain.to_string())
        .path("/")
        .http_only(true)
        .build()
}

fn sync_webview_cookies(app: &AppHandle, state: &IpcState) -> Result<(), String> {
    let Some(window) = app.get_webview_window("main") else {
        return Ok(());
    };
    let domain = cookie_domain();
    window
        .set_cookie(build_cookie(
            session_cookie_name(),
            state.session_key.clone(),
            &domain,
        ))
        .map_err(|error| format!("Unable to set Tauri session cookie: {error}"))?;

    let token = state
        .jwt
        .lock()
        .map_err(|_| "IPC JWT lock poisoned".to_string())?
        .clone();
    if token.is_empty() {
        window
            .delete_cookie(build_cookie(auth_cookie_name(), String::new(), &domain))
            .map_err(|error| format!("Unable to clear Tauri auth cookie: {error}"))?;
    } else {
        window
            .set_cookie(build_cookie(auth_cookie_name(), token, &domain))
            .map_err(|error| format!("Unable to set Tauri auth cookie: {error}"))?;
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn configure_media_permissions(app: &AppHandle) -> Result<(), String> {
    let Some(window) = app.get_webview_window("main") else {
        return Ok(());
    };
    window
        .with_webview(|webview| {
            use webkit2gtk::glib::Cast;
            use webkit2gtk::PermissionRequestExt;
            use webkit2gtk::WebViewExt;

            webview
                .inner()
                .connect_permission_request(|_, request| {
                    if request
                        .clone()
                        .downcast::<webkit2gtk::UserMediaPermissionRequest>()
                        .is_ok()
                    {
                        request.allow();
                        return true;
                    }
                    false
                });
        })
        .map_err(|error| format!("Unable to configure Tauri media permissions: {error}"))?;
    Ok(())
}

#[cfg(not(target_os = "linux"))]
fn configure_media_permissions(_app: &AppHandle) -> Result<(), String> {
    Ok(())
}

fn update_jwt_from_payload(state: &IpcState, payload: &Value) -> Result<(), String> {
    let Some(jwt_value) = payload.get("jwt") else {
        return Ok(());
    };
    if let Some(token) = jwt_value.as_str() {
        set_state_jwt(state, token)?;
    }
    Ok(())
}

fn adapt_payload_for_ipc(payload: Value, state: &IpcState) -> Result<Value, String> {
    update_jwt_from_payload(state, &payload)?;

    let Value::Object(mut map) = payload else {
        return Ok(payload);
    };

    let has_jwt = map.get("jwt").is_some_and(|value| !value.is_null());
    if !has_jwt {
        let jwt = state
            .jwt
            .lock()
            .map_err(|_| "IPC JWT lock poisoned".to_string())?
            .clone();
        if jwt.is_empty() {
            map.remove("jwt");
        } else {
            map.insert("jwt".to_string(), Value::String(jwt));
        }
    }

    let has_session_key = map.get("session_key").is_some_and(|value| !value.is_null());
    if !has_session_key {
        map.insert(
            "session_key".to_string(),
            Value::String(state.session_key.clone()),
        );
    }

    Ok(Value::Object(map))
}

fn handle_inbound_jwt(app: &AppHandle, value: &Value) {
    let Some(token) = value.get("jwt").and_then(Value::as_str) else {
        return;
    };
    let state = app.state::<IpcState>();
    if let Err(error) = set_state_jwt(&state, token) {
        emit_ipc_error(app, error);
    }
    if let Err(error) = sync_webview_cookies(app, &state) {
        emit_ipc_error(app, error);
    }
}

fn ipc_endpoint(explicit: Option<String>) -> Result<String, String> {
    explicit
        .filter(|value| !value.trim().is_empty())
        .or_else(|| env::var("DEMOCRAI_IPC_ENDPOINT").ok())
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| "Missing IPC endpoint".to_string())
}

#[cfg(unix)]
fn connect_stream(endpoint: &str) -> Result<IpcStream, String> {
    let path = endpoint
        .strip_prefix("unix://")
        .or_else(|| endpoint.strip_prefix("unix:"))
        .unwrap_or(endpoint);
    UnixStream::connect(path)
        .map_err(|error| format!("Unable to connect to IPC endpoint '{endpoint}': {error}"))
}

#[cfg(not(unix))]
fn connect_stream(endpoint: &str) -> Result<IpcStream, String> {
    let target = endpoint
        .strip_prefix("tcp://")
        .ok_or_else(|| format!("Unsupported IPC endpoint for this platform: {endpoint}"))?;
    std::net::TcpStream::connect(target)
        .map_err(|error| format!("Unable to connect to IPC endpoint '{endpoint}': {error}"))
}

fn emit_ipc_error(app: &AppHandle, message: String) {
    let _ = app.emit("democrai-ipc-error", message);
}

#[tauri::command]
fn connect_ipc(
    app: AppHandle,
    state: State<'_, IpcState>,
    server_name: Option<String>,
) -> Result<(), String> {
    sync_webview_cookies(&app, &state)?;

    let already_connected = {
        let writer = state
            .writer
            .lock()
            .map_err(|_| "IPC writer lock poisoned".to_string())?;
        writer.is_some()
    };
    if already_connected {
        return Ok(());
    }

    let endpoint = ipc_endpoint(server_name)?;
    let stream = connect_stream(&endpoint)?;
    let reader = stream
        .try_clone()
        .map_err(|error| format!("Unable to clone IPC stream: {error}"))?;

    {
        let mut writer = state
            .writer
            .lock()
            .map_err(|_| "IPC writer lock poisoned".to_string())?;
        *writer = Some(stream);
    }

    std::thread::spawn(move || {
        let mut reader = BufReader::new(reader);
        let mut line = String::new();

        loop {
            line.clear();
            match reader.read_line(&mut line) {
                Ok(0) => {
                    let _ = app.emit("democrai-ipc-disconnected", ());
                    break;
                }
                Ok(_) => {
                    let trimmed = line.trim();
                    if trimmed.is_empty() {
                        continue;
                    }
                    match serde_json::from_str::<Value>(trimmed) {
                        Ok(value) => {
                            handle_inbound_jwt(&app, &value);
                            let _ = app.emit("democrai-ipc-message", value);
                        }
                        Err(error) => {
                            emit_ipc_error(&app, format!("Invalid IPC JSON: {error}"));
                        }
                    }
                }
                Err(error) => {
                    emit_ipc_error(&app, format!("IPC read failed: {error}"));
                    let _ = app.emit("democrai-ipc-disconnected", ());
                    break;
                }
            }
        }
    });

    Ok(())
}

#[tauri::command]
fn send_ipc(payload: Value, state: State<'_, IpcState>) -> Result<(), String> {
    let payload = adapt_payload_for_ipc(payload, &state)?;
    let mut writer = state
        .writer
        .lock()
        .map_err(|_| "IPC writer lock poisoned".to_string())?;
    let stream = writer
        .as_mut()
        .ok_or_else(|| "IPC stream is not connected".to_string())?;
    let mut data = serde_json::to_vec(&payload)
        .map_err(|error| format!("Unable to encode IPC payload: {error}"))?;
    data.push(b'\n');
    stream
        .write_all(&data)
        .map_err(|error| format!("IPC write failed: {error}"))?;
    stream
        .flush()
        .map_err(|error| format!("IPC flush failed: {error}"))?;
    Ok(())
}

#[tauri::command]
fn disconnect_ipc(state: State<'_, IpcState>) -> Result<(), String> {
    let mut writer = state
        .writer
        .lock()
        .map_err(|_| "IPC writer lock poisoned".to_string())?;
    *writer = None;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(IpcState::default())
        .setup(|app| {
            let state = app.state::<IpcState>();
            sync_webview_cookies(app.handle(), &state)?;
            configure_media_permissions(app.handle())?;
            Ok(())
        })
        .on_page_load(|webview, payload| {
            if matches!(payload.event(), PageLoadEvent::Started) {
                let state = webview.state::<IpcState>();
                if let Err(error) = sync_webview_cookies(webview.app_handle(), &state) {
                    emit_ipc_error(webview.app_handle(), error);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            connect_ipc,
            send_ipc,
            disconnect_ipc
        ])
        .run(tauri::generate_context!())
        .expect("error while running Democrai Tauri wrapper");
}
