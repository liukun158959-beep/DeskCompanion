// 宠物窗 Rust 壳：托管 Python 后端 + 全局鼠标轮询做点击穿透。
// 穿透关键：ignore_cursor_events 会让整窗收不到 mousemove，前端无法自判，
// 必须由 Rust 后台线程轮询全局鼠标坐标，落在角色/面板区域外才穿透。
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::{Manager, PhysicalPosition};

#[derive(Clone, serde::Serialize)]
struct BackendInfo {
    port: u16,
    token: String,
}

#[derive(Clone, serde::Deserialize)]
struct Rect {
    x: f64,
    y: f64,
    w: f64,
    h: f64,
}

struct BackendProcess(Mutex<Option<Child>>);
struct HitRegions(std::sync::Arc<Mutex<Vec<Rect>>>);

#[tauri::command]
fn set_hit_regions(regions: tauri::State<HitRegions>, rects: Vec<Rect>) {
    if let Ok(mut guard) = regions.0.lock() {
        *guard = rects;
    }
}

#[tauri::command]
fn backend_info(info: tauri::State<BackendInfo>) -> BackendInfo {
    info.inner().clone()
}

// 隐藏只是把宠物窗收起，主窗还在，可再唤出。不要关整个进程。
#[tauri::command]
fn set_pet_visible(app: tauri::AppHandle, visible: bool) -> Result<(), String> {
    let window = app
        .get_webview_window("pet")
        .ok_or("找不到桌宠窗口。恢复：重启客户端。")?;
    if visible {
        window.show().map_err(|err| err.to_string())?;
        window.set_focus().map_err(|err| err.to_string())?;
    } else {
        window.hide().map_err(|err| err.to_string())?;
    }
    Ok(())
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

// 后台轮询：全局鼠标落在任一命中区域内 -> 可交互；否则穿透。
fn start_cursor_poll(window: tauri::WebviewWindow, regions: std::sync::Arc<Mutex<Vec<Rect>>>) {
    std::thread::spawn(move || {
        let mut last_ignore: Option<bool> = None;
        loop {
            std::thread::sleep(Duration::from_millis(30));
            let scale = window.scale_factor().unwrap_or(1.0);
            let cursor: PhysicalPosition<f64> = match window.cursor_position() {
                Ok(p) => p,
                Err(_) => continue,
            };
            let origin: PhysicalPosition<i32> = match window.outer_position() {
                Ok(p) => p,
                Err(_) => continue,
            };
            // 全局物理坐标 -> 窗口相对逻辑坐标
            let rx = (cursor.x - origin.x as f64) / scale;
            let ry = (cursor.y - origin.y as f64) / scale;
            let inside = regions
                .lock()
                .map(|rs| rs.iter().any(|r| rx >= r.x && rx <= r.x + r.w && ry >= r.y && ry <= r.y + r.h))
                .unwrap_or(false);
            let ignore = !inside;
            if last_ignore != Some(ignore) {
                last_ignore = Some(ignore);
                let _ = window.set_ignore_cursor_events(ignore);
            }
        }
    });
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

    let regions = std::sync::Arc::new(Mutex::new(Vec::<Rect>::new()));
    let regions_for_state = regions.clone();

    tauri::Builder::default()
        .manage(BackendInfo { port, token })
        .manage(BackendProcess(Mutex::new(Some(child))))
        .manage(HitRegions(regions_for_state))
        .setup(move |app| {
            if let Some(win) = app.get_webview_window("pet") {
                let _ = win.set_always_on_top(false);
                start_cursor_poll(win, regions.clone());
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![set_hit_regions, backend_info, set_pet_visible])
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
