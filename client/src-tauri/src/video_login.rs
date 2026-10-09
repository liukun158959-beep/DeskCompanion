//! Dedicated remote windows have persistent profiles and no access to local IPC.
use serde::Serialize;
use tauri::{AppHandle, Manager, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

fn platform_info(platform: &str) -> Result<(&'static str, &'static str), String> {
    match platform {
        "Bilibili" => Ok(("video-bilibili", "https://www.bilibili.com/")),
        "YouTube" => Ok(("video-youtube", "https://www.youtube.com/")),
        _ => Err("请选择 Bilibili 或 YouTube。".into()),
    }
}

fn allowed_domain(platform: &str, domain: &str) -> bool {
    let domain = domain.trim_start_matches('.');
    let roots: &[&str] = if platform == "Bilibili" {
        &["bilibili.com"]
    } else {
        &["youtube.com", "google.com"]
    };
    roots
        .iter()
        .any(|root| domain == *root || domain.ends_with(&format!(".{root}")))
}

fn login_window(
    app: &AppHandle,
    platform: &str,
    visible: bool,
    proxy: Option<String>,
) -> Result<WebviewWindow, String> {
    let (label, home) = platform_info(platform)?;
    if let Some(window) = app.get_webview_window(label) {
        return Ok(window);
    }
    let profile = app
        .path()
        .app_local_data_dir()
        .map_err(|_| "无法创建视频登录目录。")?
        .join(label);
    std::fs::create_dir_all(&profile).map_err(|_| "无法创建视频登录目录。")?;
    let target = platform.to_string();
    let popup_platform = platform.to_string();
    let popup_app = app.clone();
    let mut builder =
        WebviewWindowBuilder::new(app, label, WebviewUrl::External(Url::parse(home).unwrap()))
            .title(format!("知行 · {platform} 登录与视频浏览"))
            .inner_size(1080.0, 760.0)
            .visible(visible)
            .data_directory(profile)
            .on_navigation(move |url| {
                url.scheme() == "https"
                    && url.username().is_empty()
                    && url.password().is_none()
                    && url.port().is_none()
                    && allowed_domain(&target, url.host_str().unwrap_or(""))
            })
            .on_new_window(move |url, _| {
                // Platform target=_blank links continue in this same isolated window.
                if url.scheme() == "https"
                    && url.username().is_empty()
                    && url.password().is_none()
                    && url.port().is_none()
                    && allowed_domain(&popup_platform, url.host_str().unwrap_or(""))
                {
                    if let Some(window) = popup_app.get_webview_window(label) {
                        tauri::async_runtime::spawn(async move {
                            let _ = window.navigate(url);
                        });
                    }
                }
                tauri::webview::NewWindowResponse::Deny
            });
    if let Some(proxy) = proxy.filter(|s| !s.is_empty()) {
        let proxy = Url::parse(&proxy).map_err(|_| "视频代理地址不正确。")?;
        if !matches!(proxy.scheme(), "http" | "https")
            || proxy.host_str().is_none()
            || !proxy.username().is_empty()
            || proxy.password().is_some()
            || !matches!(proxy.path(), "" | "/")
            || proxy.query().is_some()
            || proxy.fragment().is_some()
        {
            return Err("视频代理地址不正确。".into());
        }
        builder = builder.proxy_url(proxy);
    }
    builder
        .build()
        .map_err(|_| "视频窗口创建失败，请重启知行后重试。".into())
}

#[tauri::command]
pub async fn open_video_login(
    app: AppHandle,
    platform: String,
    url: Option<String>,
    proxy: Option<String>,
) -> Result<(), String> {
    // WebView2 operations must run outside a synchronous command / UI thread.
    tauri::async_runtime::spawn_blocking(move || -> Result<(), String> {
        let window = login_window(&app, &platform, true, proxy)?;
        if let Some(url) = url.filter(|s| !s.trim().is_empty()) {
            let target = Url::parse(url.trim()).map_err(|_| "视频链接不正确。")?;
            // Only open matching platform video pages, never local or arbitrary URLs.
            let host = target.host_str().unwrap_or("");
            let valid = match platform.as_str() {
                "Bilibili" => {
                    ["www.bilibili.com", "bilibili.com", "m.bilibili.com"].contains(&host)
                        && target.path().starts_with("/video/")
                }
                "YouTube" => {
                    (["www.youtube.com", "youtube.com", "m.youtube.com"].contains(&host)
                        && (target.path() == "/watch"
                            || target.path().starts_with("/shorts/")
                            || target.path().starts_with("/live/")))
                        || host == "youtu.be"
                }
                _ => false,
            };
            if valid
                && target.scheme() == "https"
                && target.username().is_empty()
                && target.password().is_none()
                && target.port().is_none()
            {
                // youtu.be redirects to YouTube; use the canonical address for the navigation allowlist.
                let target = if host == "youtu.be" {
                    Url::parse(&format!(
                        "https://www.youtube.com/watch?v={}",
                        target.path().trim_matches('/')
                    ))
                    .unwrap()
                } else {
                    target
                };
                window.navigate(target).map_err(|_| "视频页面打开失败。")?;
            }
        }
        window.show().map_err(|_| "视频窗口显示失败。")?;
        window.set_focus().map_err(|_| "视频窗口显示失败。".into())
    })
    .await
    .map_err(|_| "视频窗口打开失败。")?
}

#[derive(Serialize)]
pub struct LoginCookie {
    domain: String,
    name: String,
    value: String,
    path: String,
    expires: i64,
    secure: bool,
    http_only: bool,
}

#[tauri::command]
pub async fn capture_video_login(
    app: AppHandle,
    platform: String,
) -> Result<Vec<LoginCookie>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let (label, _) = platform_info(&platform)?;
        let window = app
            .get_webview_window(label)
            .ok_or("请先打开视频登录窗口，完成登录后保持窗口打开。")?;
        let cookies = window
            .cookies()
            .map_err(|_| "读取视频窗口登录态失败，请重试。")?;
        Ok(cookies
            .into_iter()
            .filter(|c| allowed_domain(&platform, c.domain().unwrap_or("")))
            .map(|c| LoginCookie {
                domain: c.domain().unwrap_or("").into(),
                name: c.name().into(),
                value: c.value().into(),
                path: c.path().unwrap_or("/").into(),
                expires: c
                    .expires_datetime()
                    .map(|d| d.unix_timestamp().max(0))
                    .unwrap_or(0),
                secure: c.secure().unwrap_or(false),
                http_only: c.http_only().unwrap_or(false),
            })
            .collect())
    })
    .await
    .map_err(|_| "读取视频登录态失败。")?
}

#[tauri::command]
pub async fn clear_video_login_window(app: AppHandle, platform: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || -> Result<(), String> {
        let window = login_window(&app, &platform, false, None)?;
        // DeleteCookie is queued on the UI thread; the subsequent cookie read waits for completion.
        for cookie in window
            .cookies()
            .map_err(|_| "清除视频窗口登录态失败，请重试。")?
        {
            window
                .delete_cookie(cookie)
                .map_err(|_| "清除视频窗口登录态失败，请重试。")?;
        }
        if window
            .cookies()
            .map_err(|_| "核实视频登录态清除结果失败。")?
            .iter()
            .any(|c| {
                matches!(
                    c.name(),
                    "SESSDATA" | "SID" | "SAPISID" | "__Secure-3PAPISID" | "__Secure-1PAPISID"
                )
            })
        {
            return Err("视频窗口仍有登录信息，请重试清除。".into());
        }
        // The dedicated profile contains only this platform. Clear storage and cache as well.
        window
            .clear_all_browsing_data()
            .map_err(|_| "清除视频窗口登录态失败，请重试。")?;
        window.close().map_err(|_| "关闭视频窗口失败。".into())
    })
    .await
    .map_err(|_| "清除视频登录态失败。")?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn domains_are_platform_scoped() {
        assert!(allowed_domain("Bilibili", ".bilibili.com"));
        assert!(!allowed_domain("Bilibili", "bilibili.com.evil.test"));
        assert!(!allowed_domain("Bilibili", "google.com"));
        assert!(allowed_domain("YouTube", "accounts.google.com"));
        assert!(!allowed_domain("YouTube", "notgoogle.com"));
        assert!(platform_info("../../other").is_err());
    }
}
