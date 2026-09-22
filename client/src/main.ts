// Spike A 主入口：渲染咕嘎帧 + 动态点击穿透。
// 穿透核心：鼠标移动时读该点 alpha，落在角色身上则关闭穿透（可交互），
// 落在透明区则开启穿透（鼠标穿到桌面下层）。
import { invoke } from "@tauri-apps/api/core";
import { renderPet, alphaAt } from "./pet-render";

const ALPHA_HIT = 10; // alpha 阈值：高于此算命中角色
let lastIgnore: boolean | null = null;

async function setClickThrough(ignore: boolean): Promise<void> {
  // 去抖：状态不变不重复调用命令
  if (ignore === lastIgnore) return;
  lastIgnore = ignore;
  await invoke("set_click_through", { ignore });
}

async function main(): Promise<void> {
  const canvas = document.getElementById("stage") as HTMLCanvasElement;
  // spike 素材：由 tauri 静态目录提供的咕嘎 idle 帧
  await renderPet(canvas, "/assets/idle.webp");

  // 初始：整窗穿透，等鼠标移到角色上再放开
  await setClickThrough(true);

  window.addEventListener("mousemove", (e) => {
    const hit = alphaAt(e.clientX, e.clientY) > ALPHA_HIT;
    void setClickThrough(!hit);
  });

  // 窗口尺寸变化时重绘
  window.addEventListener("resize", () => {
    void renderPet(canvas, "/assets/idle.webp");
  });
}

void main();
