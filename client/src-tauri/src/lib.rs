// Spike A：Rust 壳。暴露 set_click_through 命令，动态切换窗口鼠标穿透。
use tauri::Manager;

#[tauri::command]
fn set_click_through(window: tauri::Window, ignore: bool) -> Result<(), String> {
    window
        .set_ignore_cursor_events(ignore)
        .map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            // 确保 pet 窗口存在并置顶
            if let Some(win) = app.get_webview_window("pet") {
                let _ = win.set_always_on_top(true);
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![set_click_through])
        .run(tauri::generate_context!())
        .expect("启动 Tauri 应用失败");
}
