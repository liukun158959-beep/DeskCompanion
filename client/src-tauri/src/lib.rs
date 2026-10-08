// 宠物窗 Rust 壳：托管 Python 后端 + 全局鼠标轮询做点击穿透。
// 穿透关键：ignore_cursor_events 会让整窗收不到 mousemove，前端无法自判，
// 必须由 Rust 后台线程轮询全局鼠标坐标，落在角色/面板区域外才穿透。
use std::process::{Child, Command};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::{Emitter, Manager, PhysicalPosition};

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
struct DragLock(std::sync::Arc<AtomicBool>);

#[tauri::command]
fn set_hit_regions(regions: tauri::State<HitRegions>, rects: Vec<Rect>) {
    if let Ok(mut guard) = regions.0.lock() {
        *guard = rects;
    }
}

#[tauri::command]
async fn backend_info(info: tauri::State<'_, BackendInfo>) -> Result<BackendInfo, String> {
    let backend = info.inner().clone();
    let port = backend.port;
    // 窗口先打开并显示启动页，健康检查在后台等待，不阻塞 UI 线程。
    let healthy = tauri::async_runtime::spawn_blocking(move || wait_healthy(port))
        .await
        .map_err(|err| format!("助手启动检查失败：{err}。请查看启动终端。"))?;
    if !healthy {
        return Err("本地助手未能启动。请查看启动终端，确认 Python 与 Atlas 已安装，再重新启动客户端。".into());
    }
    Ok(backend)
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

// 拖动中禁止穿透，否则窗口一动，松手事件会丢。
#[tauri::command]
fn set_drag_lock(lock: tauri::State<DragLock>, locked: bool) {
    lock.0.store(locked, Ordering::Relaxed);
}

#[tauri::command]
fn nudge_pet(app: tauri::AppHandle, dx: f64, dy: f64) -> Result<(), String> {
    let window = app
        .get_webview_window("pet")
        .ok_or("找不到桌宠窗口。恢复：重启客户端。")?;
    let scale = window.scale_factor().map_err(|err| err.to_string())?;
    let pos = window.outer_position().map_err(|err| err.to_string())?;
    let nx = pos.x + (dx * scale).round() as i32;
    let ny = pos.y + (dy * scale).round() as i32;
    window
        .set_position(tauri::PhysicalPosition::new(nx, ny))
        .map_err(|err| err.to_string())
}

#[tauri::command]
fn show_main(app: tauri::AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or("找不到主窗口。恢复：重启客户端。")?;
    window.unminimize().map_err(|err| err.to_string())?;
    window.show().map_err(|err| err.to_string())?;
    window.set_focus().map_err(|err| err.to_string())?;
    Ok(())
}

#[tauri::command]
fn open_today(app: tauri::AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or("找不到主窗口。恢复：重启客户端。")?;
    window.emit("open-today", true).map_err(|err| err.to_string())?;
    Ok(())
}

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}

/// 只打开 http/https。走 ShellExecute，不经过 cmd，避免链接里的符号被当成命令。
#[tauri::command]
fn open_link(url: String) -> Result<(), String> {
    let url = clean_http_url(&url)?;
    #[cfg(windows)]
    {
        let op = wide("open");
        let file = wide(&url);
        let code = unsafe {
            ShellExecuteW(
                std::ptr::null_mut(),
                op.as_ptr(),
                file.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                1,
            )
        };
        if code <= 32 {
            return Err(format!("打不开链接（{code}）。恢复：复制地址到浏览器打开。"));
        }
        return Ok(());
    }
    #[cfg(not(windows))]
    {
        let _ = url;
        Err("只在 Windows 上打开链接。".into())
    }
}

fn clean_http_url(raw: &str) -> Result<String, String> {
    let url = raw.trim();
    if url.len() > 2000 {
        return Err("链接太长。恢复：复制地址到浏览器打开。".into());
    }
    if url.chars().any(|ch| ch.is_whitespace()) {
        return Err("链接里不能有空白。".into());
    }
    let lower = url.to_ascii_lowercase();
    if !(lower.starts_with("https://") || lower.starts_with("http://")) {
        return Err("只打开 http 或 https 链接。".into());
    }
    let rest = url.split_once("://").map(|(_, rest)| rest).unwrap_or("");
    let host = rest.split(['/', '?', '#']).next().unwrap_or("");
    if host.is_empty() || host.contains('@') {
        return Err("这个地址不能打开。恢复：复制到浏览器。".into());
    }
    Ok(url.to_string())
}

#[cfg(windows)]
fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(std::iter::once(0)).collect()
}

#[cfg(windows)]
#[link(name = "shell32")]
extern "system" {
    fn ShellExecuteW(
        hwnd: *mut std::ffi::c_void,
        lp_operation: *const u16,
        lp_file: *const u16,
        lp_parameters: *const u16,
        lp_directory: *const u16,
        n_show_cmd: i32,
    ) -> isize;
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
fn start_cursor_poll(
    window: tauri::WebviewWindow,
    regions: std::sync::Arc<Mutex<Vec<Rect>>>,
    drag_lock: std::sync::Arc<AtomicBool>,
) {
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
            let ignore = !drag_lock.load(Ordering::Relaxed) && !inside;
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

    let regions = std::sync::Arc::new(Mutex::new(Vec::<Rect>::new()));
    let regions_for_state = regions.clone();
    let drag_lock_for_state = std::sync::Arc::new(AtomicBool::new(false));
    let drag_lock_for_poll = drag_lock_for_state.clone();

    tauri::Builder::default()
        .manage(BackendInfo { port, token })
        .manage(BackendProcess(Mutex::new(Some(child))))
        .manage(HitRegions(regions_for_state))
        .manage(DragLock(drag_lock_for_state))
        .setup(move |app| {
            if let Some(win) = app.get_webview_window("pet") {
                let _ = win.set_always_on_top(true);
                start_cursor_poll(win, regions.clone(), drag_lock_for_poll.clone());
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            set_hit_regions,
            backend_info,
            set_pet_visible,
            set_drag_lock,
            nudge_pet,
            show_main,
            open_today,
            open_link,
            quit_app
        ])
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
