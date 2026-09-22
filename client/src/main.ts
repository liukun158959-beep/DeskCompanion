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
    // 命中角色像素，或落在 HTML UI（对话面板）上，都不穿透
    const overUI = (e.target as HTMLElement)?.closest("#chat") != null;
    const hit = overUI || alphaAt(e.clientX, e.clientY) > ALPHA_HIT;
    void setClickThrough(!hit);
  });

  // 窗口尺寸变化时重绘
  window.addEventListener("resize", () => {
    void renderPet(canvas, "/assets/idle.webp");
  });

  await setupChat();
}

// Spike B：经 WS 连本地 Python 后端，验证流式对话。
async function setupChat(): Promise<void> {
  const info = await invoke<{ port: number; token: string }>("backend_info");
  const replyEl = document.getElementById("reply") as HTMLDivElement;
  const msgEl = document.getElementById("msg") as HTMLInputElement;
  const sendEl = document.getElementById("send") as HTMLButtonElement;

  const send = () => {
    const text = msgEl.value.trim();
    if (!text) return;
    msgEl.value = "";
    replyEl.textContent = "";
    const ws = new WebSocket(`ws://127.0.0.1:${info.port}/ws?token=${info.token}`);
    ws.onopen = () => ws.send(JSON.stringify({ type: "chat", text }));
    ws.onmessage = (ev) => {
      const d = JSON.parse(ev.data);
      if (d.type === "token") replyEl.textContent += d.data;
      else if (d.type === "done") ws.close();
      else if (d.type === "error") replyEl.textContent = `错误：${d.data}`;
    };
    ws.onerror = () => {
      replyEl.textContent = "连接后端失败。恢复：确认后端进程在运行";
    };
  };

  sendEl.addEventListener("click", send);
  msgEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });
}

void main();
