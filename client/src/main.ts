/// <reference types="vite/client" />
// 宠物窗主入口：渲染 kaltsit Live2D + 上报角色包围盒给 Rust 做穿透判定 + WS 对话。
// 穿透判定改由 Rust 后台轮询全局鼠标（前端在穿透态收不到 mousemove，无法自判）。
import { invoke, isTauri } from "@tauri-apps/api/core";
import { startPet, modelBounds } from "./pet-render";

const MODEL_URL = "/skins/kaltsit/kaltsit.model3.json";

async function reportHitRegions(): Promise<void> {
  // 命中区域 = 角色包围盒 + 对话面板矩形；鼠标落在任一区域内则不穿透
  const rects: { x: number; y: number; w: number; h: number }[] = [];
  const b = modelBounds();
  if (b) rects.push(b);
  for (const id of ["dock", "chat"]) {
    const el = document.getElementById(id);
    if (!el || el.classList.contains("hidden")) continue;
    const r = el.getBoundingClientRect();
    rects.push({ x: r.x, y: r.y, w: r.width, h: r.height });
  }
  if (!isTauri()) return;
  await invoke("set_hit_regions", { rects });
}

async function main(): Promise<void> {
  // 先接对话与命中区域上报，保证即使 Live2D 加载失败，对话框仍可用、窗口仍可交互
  await setupChat();
  await reportHitRegions();
  setInterval(() => void reportHitRegions(), 500);

  // Live2D 独立加载；失败只影响形象，不拖垮对话，且错误可见
  const canvas = document.getElementById("stage") as HTMLCanvasElement;
  try {
    await startPet(canvas, MODEL_URL);
  } catch (err) {
    const replyEl = document.getElementById("reply");
    if (replyEl) replyEl.textContent = `形象加载失败：${String(err)}`;
  }
}

// 经 WS 连本地后端，验证流式对话。
async function setupChat(): Promise<void> {
  const replyEl = document.getElementById("reply") as HTMLDivElement;
  const statusEl = document.getElementById("status") as HTMLDivElement;
  const msgEl = document.getElementById("msg") as HTMLInputElement;
  const sendEl = document.getElementById("send") as HTMLButtonElement;
  const chatEl = document.getElementById("chat") as HTMLDivElement;
  const closeEl = document.getElementById("close-chat") as HTMLButtonElement;
  const toggleEl = document.getElementById("toggle-chat") as HTMLButtonElement;
  const hideEl = document.getElementById("hide-pet") as HTMLButtonElement;
  const setChatOpen = (open: boolean) => {
    chatEl.classList.toggle("hidden", !open);
    void reportHitRegions();
  };
  closeEl.addEventListener("click", () => setChatOpen(false));
  toggleEl.addEventListener("click", () => setChatOpen(chatEl.classList.contains("hidden")));
  hideEl.addEventListener("click", () => {
    invoke("set_pet_visible", { visible: false }).catch((err: unknown) => {
      replyEl.textContent = `隐藏桌宠失败：${String(err)}。恢复：从主窗点「唤出桌宠」，或重启客户端。`;
    });
  });
  if (import.meta.env.DEV) {
    const pet = window as Window & {
      __petDebug?: { chatOpen: () => boolean; setChatOpen: (open: boolean) => void };
    };
    pet.__petDebug = {
      chatOpen: () => !chatEl.classList.contains("hidden"),
      setChatOpen,
    };
  }
  window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!chatEl.classList.contains("hidden")) setChatOpen(false);
  });

  let info: { port: number; token: string };
  try {
    info = await invoke<{ port: number; token: string }>("backend_info");
  } catch (err) {
    replyEl.textContent = `还没有连上本地后端：${String(err)}。恢复：重启客户端。`;
    return;
  }

  const send = () => {
    const text = msgEl.value.trim();
    if (!text) return;
    msgEl.value = "";
    replyEl.textContent = "";
    statusEl.textContent = "凯尔希思考中…";
    const ws = new WebSocket(`ws://127.0.0.1:${info.port}/ws?token=${info.token}`);
    ws.onopen = () => ws.send(JSON.stringify({ type: "chat", text }));
    ws.onmessage = (ev) => {
      const d = JSON.parse(ev.data);
      if (d.type === "token") {
        // 工具调用期间的 status 提示在正文开始流入时清掉
        if (statusEl.textContent) statusEl.textContent = "";
        replyEl.textContent += d.data;
      } else if (d.type === "status") {
        statusEl.textContent = d.data; // 工具进度：在看今天的日程…
      } else if (d.type === "done") {
        statusEl.textContent = "";
        ws.close();
      } else if (d.type === "error") {
        statusEl.textContent = "";
        replyEl.textContent = `错误：${d.data}`;
      }
    };
    ws.onerror = () => {
      statusEl.textContent = "";
      replyEl.textContent = "连接后端失败。恢复：确认后端进程在运行";
    };
  };

  sendEl.addEventListener("click", send);
  msgEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });
}

void main();
