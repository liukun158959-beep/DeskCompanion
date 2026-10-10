use tauri::{AppHandle, Emitter, Manager, Url, WebviewUrl};
use tauri::webview::{NewWindowResponse, PageLoadEvent, WebviewBuilder};
use std::sync::{Arc, atomic::{AtomicBool, Ordering}, Mutex};

const LABEL: &str = "side-browser";

#[derive(Clone, serde::Serialize)]
struct BrowserState { url: String, title: String, loading: bool }

#[derive(serde::Deserialize)]
pub struct Bounds { x: f64, y: f64, w: f64, h: f64 }

fn browser_url(raw: &str) -> Result<Url, String> {
    let url = Url::parse(&super::clean_http_url(raw)?) .map_err(|_| "网页地址无效。")?;
    let host = url.host_str().unwrap_or_default().trim_end_matches('.').to_ascii_lowercase();
    let local_ip = host.trim_matches(['[', ']']).parse::<std::net::IpAddr>().ok().is_some_and(|ip| {
        ip.is_loopback() || ip.is_unspecified() || matches!(ip, std::net::IpAddr::V6(v6) if v6.to_ipv4_mapped().is_some_and(|v4| v4.is_loopback() || v4.is_unspecified()))
    });
    if host == "localhost" || host.ends_with(".localhost") || local_ip {
        return Err("内置浏览器不打开本机服务地址。".into());
    }
    Ok(url)
}

#[tauri::command]
pub async fn open_side_browser(app: AppHandle, url: String) -> Result<(), String> {
    let url = browser_url(&url)?;
    if let Some(webview) = app.get_webview(LABEL) { return webview.navigate(url).map_err(|e| e.to_string()); }
    let main = app.get_window("main").ok_or("主窗口未就绪，请重启客户端。")?;
    let profile = app.path().app_local_data_dir().map_err(|e| e.to_string())?.join("side-browser-profile");
    std::fs::create_dir_all(&profile).map_err(|e| e.to_string())?;
    let nav_app = app.clone();
    let popup_app = app.clone();
    let load_app = app.clone();
    let title_app = app.clone();
    let loading = Arc::new(AtomicBool::new(true));
    let nav_loading = loading.clone();
    let load_loading = loading.clone();
    let document_title = Arc::new(Mutex::new(String::from("网页")));
    let load_title = document_title.clone();
    let builder = WebviewBuilder::new(LABEL, WebviewUrl::External(url))
        .data_directory(profile)
        .on_navigation(move |url| {
            if browser_url(url.as_str()).is_err() { return false; }
            nav_loading.store(true, Ordering::Relaxed);
            let _ = nav_app.emit_to("main", "side-browser-state", BrowserState { url: url.to_string(), title: "正在打开网页…".into(), loading: true });
            true
        })
        .on_new_window(move |url, _| {
            // 网站的新窗口请求也回到这个侧栏，不创建浮窗；远程页面始终无本地 IPC 权限。
            if browser_url(url.as_str()).is_ok() {
                let app = popup_app.clone();
                tauri::async_runtime::spawn(async move { if let Some(view) = app.get_webview(LABEL) { let _ = view.navigate(url); } });
            }
            NewWindowResponse::Deny
        })
        .on_page_load(move |_, payload| {
            let loading = matches!(payload.event(), PageLoadEvent::Started);
            load_loading.store(loading, Ordering::Relaxed);
            let title = load_title.lock().map(|t| t.clone()).unwrap_or_else(|_| "网页".into());
            let _ = load_app.emit_to("main", "side-browser-state", BrowserState { url: payload.url().to_string(), title, loading });
        })
        .on_document_title_changed(move |view, title| {
            if let Ok(mut current) = document_title.lock() { *current = title.clone(); }
            if let Ok(url) = view.url() { let _ = title_app.emit_to("main", "side-browser-state", BrowserState { url: url.to_string(), title, loading: loading.load(Ordering::Relaxed) }); }
        })
        .on_download(|_, event| !matches!(event, tauri::webview::DownloadEvent::Requested { .. }));
    let view = main.add_child(builder, tauri::LogicalPosition::new(0., 0.), tauri::LogicalSize::new(1., 1.)).map_err(|e| e.to_string())?;
    view.hide().map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn side_browser_layout(app: AppHandle, visible: bool, bounds: Option<Bounds>) -> Result<(), String> {
    let Some(view) = app.get_webview(LABEL) else { return Ok(()); };
    if !visible { return view.hide().map_err(|e| e.to_string()); }
    let b = bounds.ok_or("缺少侧栏位置。")?;
    if ![b.x, b.y, b.w, b.h].iter().all(|v| v.is_finite()) || b.x < 0. || b.y < 0. || b.w < 20. || b.h < 20. { return view.hide().map_err(|e| e.to_string()); }
    let window = app.get_window("main").ok_or("主窗口未就绪。")?;
    let size = window.inner_size().map_err(|e| e.to_string())?.to_logical::<f64>(window.scale_factor().map_err(|e| e.to_string())?);
    let width = b.w.min(size.width - b.x);
    let height = b.h.min(size.height - b.y);
    if width < 20. || height < 20. { return view.hide().map_err(|e| e.to_string()); }
    view.set_bounds(tauri::Rect { position: tauri::LogicalPosition::new(b.x, b.y).into(), size: tauri::LogicalSize::new(width, height).into() }).map_err(|e| e.to_string())?;
    view.show().map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn side_browser_action(app: AppHandle, action: String) -> Result<(), String> {
    let view = app.get_webview(LABEL).ok_or("网页尚未打开，请先输入网页地址。")?;
    if action == "close" { return view.close().map_err(|e| e.to_string()); }
    let script = match action.as_str() { "back" => "history.back()", "forward" => "history.forward()", "reload" => "location.reload()", "stop" => "window.stop()", _ => return Err("不支持的浏览器操作。".into()) };
    view.eval(script).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn browser_navigation_stays_remote_and_has_no_credentials() {
        assert!(browser_url("https://www.bilibili.com/video/BV1v9V5zSEHA").is_ok());
        for url in ["file:///C:/secret", "tauri://localhost", "javascript:alert(1)", "http://127.0.0.1:8000", "http://localhost:5180", "http://localhost.:5180", "http://foo.localhost", "http://[::1]", "http://[::ffff:127.0.0.1]", "http://[::]", "https://user:pass@example.org"] { assert!(browser_url(url).is_err(), "{url}"); }
    }
}
