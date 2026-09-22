// Spike B：Rust 壳托管 Python 后端。
// 启动时 spawn python server.py，轮询 /health 就绪，退出时 kill 子进程。
// 同时保留 Spike A 的 set_click_through 命令。
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::Manager;

// 后端连接信息，注入前端
#[derive(Clone, serde::Serialize)]
struct BackendInfo {
    port: u16,
    token: String,
}

// 托管子进程句柄，退出时清理
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

// 选一个空闲端口：绑 127.0.0.1:0 让系统分配后立即释放
fn pick_free_port() -> u16 {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("无法分配端口");
    listener.local_addr().expect("读端口失败").port()
}

// 生成进程 token：用纳秒时间戳，spike 够用
fn gen_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("tok{nanos:x}")
}

// 轮询健康检查，最多等 ~10 秒
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

    // server.py 路径：spike 期用编译时 manifest 目录定位
    let server_py = format!("{}/../backend-spike/server.py", env!("CARGO_MANIFEST_DIR"));

    let child = Command::new("python")
        .arg(&server_py)
        .arg("--port")
        .arg(port.to_string())
        .arg("--token")
        .arg(&token)
        .spawn()
        .expect("启动 Python 后端失败。恢复：确认 python 在 PATH 且 server.py 存在");

    if !wait_healthy(port) {
        // 消除 fallback：起不来直接失败，不静默继续
        panic!("Python 后端健康检查超时。恢复：手动跑 python backend-spike/server.py 看报错");
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
            // App 退出时清理 Python 子进程，不留孤儿
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
