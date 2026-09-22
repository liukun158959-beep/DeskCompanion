// 桌面入口：委托 lib.rs 的 run()
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    desk_companion_client_lib::run()
}
