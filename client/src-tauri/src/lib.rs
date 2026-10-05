// Rust 壳托管 Python 后端（desk_companion.local_api），退出时清理子进程。
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::Manager;

#[derive(Clone, serde::Serialize)]
struct BackendInfo {
    port: u16,
    token: String,
}

struct BackendProcess(Mutex<Option<Child>>);

#[tauri::command]
fn set_click_through(window: tauri::Window, ignore: bool) -> Result<(), String> {
    window
        .set_ignore_cursor_events(ignore)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn backend_info(info: tauri::State<BackendInfo>) -> BackendInfo {
    info.inner().clone()
}

fn pick_free_port() -> u16 {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("无法分配端口");
    listener.local_addr().expect("读端口失败").port()
}

fn gen_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("tok{nanos:x}")
}

fn wait_healthy(port: u16) -> bool {
    let url = format!("http://127.0.0.1:{port}/health");
    for _ in 0..50 {
        if let Ok(resp) = ureq::get(&url).timeout(Duration::from_millis(500)).call() {
            if resp.status() == 200 {
                return true;
            }
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port = pick_free_port();
    let token = gen_token();
    let server_dir = format!("{}/..", env!("CARGO_MANIFEST_DIR"));

    // 拉起真实后端：desk_companion.local_api.server（不再是 spike 回显）
    let child = Command::new("python")
        .args(["-m", "desk_companion.local_api.server", "--port"])
        .arg(port.to_string())
        .arg("--token")
        .arg(&token)
        .current_dir(format!("{server_dir}/.."))
        .spawn()
        .expect("启动 Python 后端失败。恢复：确认 python 在 PATH 且已 pip install -e 本项目");

    if !wait_healthy(port) {
        panic!("Python 后端健康检查超时。恢复：手动跑 python -m desk_companion.local_api.server 看报错");
    }

    tauri::Builder::default()
        .manage(BackendInfo { port, token })
        .manage(BackendProcess(Mutex::new(Some(child))))
        .setup(|app| {
            if let Some(win) = app.get_webview_window("pet") {
                let _ = win.set_always_on_top(true);
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![set_click_through, backend_info])
        .build(tauri::generate_context!())
        .expect("构建 Tauri 应用失败")
        .run(|app, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app.try_state::<BackendProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
