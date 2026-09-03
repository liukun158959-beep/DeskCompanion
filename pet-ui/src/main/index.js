import { app, BrowserWindow, Menu, ipcMain, screen, protocol } from "electron";
import { appendFileSync, existsSync } from "fs";
import { readFile } from "fs/promises";
import { createConnection } from "net";
import { basename, dirname, extname, join } from "path";

protocol.registerSchemesAsPrivileged([
  {
    scheme: "pet",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
    },
  },
]);

function argValue(name) {
  const prefix = `--${name}=`;
  const hit = process.argv.find((item) => item.startsWith(prefix));
  if (!hit) {
    throw new Error(`缺少启动参数 ${name}。`);
  }
  return hit.slice(prefix.length);
}

const BRIDGE = argValue("bridge");
const MODEL = argValue("model");
const MODEL_DIR = dirname(MODEL);
const START_X = Number(argValue("x"));
const START_Y = Number(argValue("y"));
const START_SCALE = Number(argValue("scale"));
const START_PIN_TEXT = argValue("pin");
if (START_PIN_TEXT !== "true" && START_PIN_TEXT !== "false") {
  throw new Error("pin 只能是 true 或 false。");
}
const START_PIN = START_PIN_TEXT === "true";
const START_CLICK_THROUGH_TEXT = argValue("click-through");
if (START_CLICK_THROUGH_TEXT !== "true" && START_CLICK_THROUGH_TEXT !== "false") {
  throw new Error("click-through 只能是 true 或 false。");
}
const START_CLICK_THROUGH = START_CLICK_THROUGH_TEXT === "true";
const LOG_PATH = join(__dirname, "../../electron.log");
const RENDERER_DIR = join(__dirname, "../renderer");

const BASE_PET_W = 400;
const BASE_PET_H = 500;
const BASE_BUBBLE_W = 320;
const BASE_SCALE = 1.5;
const PIN_LIFT_Y = 24;

let win = null;
let bubbleOpen = false;
let pinned = START_PIN;
let clickThrough = START_CLICK_THROUGH;
let lastIgnoreRequest = true;
let currentScale = START_SCALE;
let socket = null;
let buffer = "";
const pending = new Map();
let reqId = 1;

function elog(msg) {
  const line = `${new Date().toISOString()} ${msg}\n`;
  try {
    appendFileSync(LOG_PATH, line, "utf8");
  } catch {
    console.error(msg);
  }
}

function sendLine(obj) {
  if (!socket || socket.destroyed) {
    throw new Error("还没连上 Python 桥。");
  }
  socket.write(JSON.stringify(obj) + "\n", "utf8");
}

function emit(event, params) {
  sendLine({ v: 1, dir: "evt", event, params: params || {} });
}

function request(method, params, timeoutMs) {
  const id = String(reqId++);
  const waitMs = timeoutMs == null ? 15000 : timeoutMs;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      if (!pending.has(id)) {
        return;
      }
      pending.delete(id);
      reject(new Error("桥调用 " + method + " 超时。"));
    }, waitMs);
    pending.set(id, {
      resolve: (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      reject: (err) => {
        clearTimeout(timer);
        reject(err);
      },
    });
    sendLine({ v: 1, id, dir: "req", method, params: params || {} });
  });
}

function onLine(line) {
  const msg = JSON.parse(line);
  if (msg.dir === "res") {
    const wait = pending.get(String(msg.id));
    if (!wait) {
      throw new Error(`桥返回了未知 id ${msg.id}。`);
    }
    pending.delete(String(msg.id));
    if (!msg.ok) {
      wait.reject(new Error(msg.error || "桥调用失败。"));
      return;
    }
    wait.resolve(msg.result);
    return;
  }
  if (msg.dir === "evt") {
    if (!win) {
      return;
    }
    if (msg.event === "quit") {
      app.quit();
      return;
    }
    if (msg.event === "hide_pet") {
      win.hide();
      return;
    }
    if (msg.event === "show_pet") {
      win.show();
      return;
    }
    if (msg.event === "set_click_through") {
      const enabled = msg.params && msg.params.enabled;
      if (enabled !== true && enabled !== false) {
        elog("set_click_through 不是 true/false");
        return;
      }
      clickThrough = enabled;
      applyMouseIgnore();
      return;
    }
    win.webContents.send("bridge-event", msg);
    return;
  }
  throw new Error(`未知桥方向 ${msg.dir}。`);
}

function connectBridge() {
  const [host, portText] = BRIDGE.split(":");
  const port = Number(portText);
  return new Promise((resolve, reject) => {
    socket = createConnection({ host, port });
    socket.setEncoding("utf8");
    socket.on("connect", resolve);
    socket.on("data", (chunk) => {
      buffer += chunk;
      while (true) {
        const idx = buffer.indexOf("\n");
        if (idx < 0) {
          return;
        }
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (line) {
          onLine(line);
        }
      }
    });
    socket.on("error", (err) => {
      elog(`桥连接失败 ${err}`);
      reject(err);
      app.quit();
    });
    socket.on("close", () => {
      elog("桥断开");
      app.quit();
    });
  });
}

function nativeHwnd() {
  const buf = win.getNativeWindowHandle();
  return buf.readUInt32LE(0);
}

function mimeOf(filePath) {
  const ext = extname(filePath).toLowerCase();
  if (ext === ".html") {
    return "text/html; charset=utf-8";
  }
  if (ext === ".js" || ext === ".mjs") {
    return "text/javascript; charset=utf-8";
  }
  if (ext === ".css") {
    return "text/css; charset=utf-8";
  }
  if (ext === ".json") {
    return "application/json; charset=utf-8";
  }
  if (ext === ".png") {
    return "image/png";
  }
  if (ext === ".wasm") {
    return "application/wasm";
  }
  return "application/octet-stream";
}

function resolvePetPath(requestUrl) {
  const parsed = new URL(requestUrl);
  let rel = decodeURIComponent(parsed.pathname);
  if (rel.startsWith("/")) {
    rel = rel.slice(1);
  }
  if (!rel || rel.includes("..") || rel.includes("\\")) {
    throw new Error(`非法资源路径 ${rel || "(空)"}`);
  }
  if (rel.startsWith("ui/")) {
    return join(RENDERER_DIR, rel.slice(3));
  }
  if (rel.startsWith("model/")) {
    return join(MODEL_DIR, rel.slice(6));
  }
  throw new Error(`未知资源前缀 ${rel}`);
}

function registerModelProtocol() {
  protocol.handle("pet", async (request) => {
    try {
      const filePath = resolvePetPath(request.url);
      if (request.url.includes("/model/")) {
        elog(`模型资源 ${request.url}`);
      }
      if (!existsSync(filePath)) {
        elog(`资源不存在 ${request.url} -> ${filePath}`);
        return new Response("not found", { status: 404 });
      }
      const data = await readFile(filePath);
      return new Response(new Uint8Array(data.buffer, data.byteOffset, data.byteLength), {
        headers: {
          "content-type": mimeOf(filePath),
          "content-length": String(data.byteLength),
          "cache-control": "no-cache",
        },
      });
    } catch (err) {
      elog(`协议失败 ${request.url} ${err}`);
      return new Response(String(err), { status: 500 });
    }
  });
}

function layoutFor(scale) {
  const factor = Number(scale) / BASE_SCALE;
  return {
    scale: Number(scale),
    factor,
    petW: Math.round(BASE_PET_W * factor),
    petH: Math.round(BASE_PET_H * factor),
    bubbleW: Math.round(BASE_BUBBLE_W * factor),
  };
}

function clampCharacter(cx, cy) {
  const { petW, petH } = layoutFor(currentScale);
  const display = screen.getDisplayNearestPoint({ x: cx, y: cy });
  const work = display.workArea;
  const maxX = work.x + Math.max(0, work.width - petW);
  const maxY = work.y + Math.max(0, work.height - petH);
  return {
    x: Math.min(Math.max(cx, work.x), maxX),
    y: Math.min(Math.max(cy, work.y), maxY),
  };
}

function windowWidth() {
  const { petW, bubbleW } = layoutFor(currentScale);
  return petW + bubbleW;
}

function characterOrigin() {
  const [x, y] = win.getPosition();
  const { bubbleW } = layoutFor(currentScale);
  return {
    x: x + bubbleW,
    y,
  };
}

function applyWindowLayout(origin) {
  const { petW, petH, bubbleW } = layoutFor(currentScale);
  const placed = clampCharacter(origin.x, origin.y);
  win.setBounds({
    x: placed.x - bubbleW,
    y: placed.y,
    width: petW + bubbleW,
    height: petH,
  });
}

function applyBubble(open) {
  if (!win) {
    throw new Error("窗口还没建好，不能开关气泡。");
  }
  bubbleOpen = Boolean(open);
  emit(bubbleOpen ? "bubble_opened" : "bubble_closed", {});
}

function createWindow() {
  const lay = layoutFor(currentScale);
  let x = START_X;
  let y = START_Y;
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    const work = screen.getPrimaryDisplay().workArea;
    x = work.x + work.width - lay.petW;
    y = work.y + work.height - lay.petH;
  }
  ({ x, y } = clampCharacter(x, y));
  win = new BrowserWindow({
    width: lay.petW + lay.bubbleW,
    height: lay.petH,
    x: x - lay.bubbleW,
    y,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    hasShadow: false,
    skipTaskbar: true,
    resizable: false,
    useContentSize: true,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
    },
  });
  win.setAlwaysOnTop(true);
  win.setMenuBarVisibility(false);
  applyMouseIgnore();
  win.webContents.on("console-message", (_e, level, message) => {
    const text = String(message);
    if (text.includes("[CSM]")) {
      return;
    }
    if (
      level >= 2
      || text.includes("加载")
      || text.includes("模型")
      || text.includes("renderer boot")
      || text.includes("失败")
    ) {
      elog(`[renderer] ${text}`);
    }
  });
  win.webContents.on("did-finish-load", () => {
    elog(`页面加载完成 ${win.webContents.getURL()}`);
  });
  win.webContents.on("did-fail-load", (_e, code, desc, url) => {
    elog(`页面加载失败 ${code} ${desc} ${url}`);
    emit("fail", { error: `页面加载失败：${desc}` });
  });
  win.on("closed", () => {
    elog("窗口已关");
    win = null;
  });

  const modelUrl = `pet://local/model/${basename(MODEL)}`;
  const query = new URLSearchParams({
    model: modelUrl,
    scale: String(lay.scale),
    petW: String(lay.petW),
    petH: String(lay.petH),
    bubbleW: String(lay.bubbleW),
  });
  elog(`打开窗口 char=${x},${y} model=${MODEL}`);

  if (process.env.ELECTRON_RENDERER_URL) {
    win.loadURL(`${process.env.ELECTRON_RENDERER_URL}?${query}`);
  } else {
    win.loadURL(`pet://local/ui/index.html?${query}`);
  }
  if (pinned) {
    snapToCorner();
  }
}

function popupMenu() {
  request("maa_menu", {}, 800)
    .then((maa) => {
      showPetMenu(maa);
    })
    .catch((err) => {
      elog(`maa_menu ${err}`);
      showPetMenu({
        ok: false,
        options: [],
        message: String(err && err.message ? err.message : err),
      });
    });
}

function showPetMenu(maa) {
  const optionItems = (maa && maa.options ? maa.options : []).map((opt) => ({
    label: opt.label,
    type: "checkbox",
    checked: Boolean(opt.checked),
    click: (item) => {
      request("maa_set_option", { id: opt.id, checked: item.checked }).catch((err) => {
        elog(`maa_set_option ${err}`);
      });
    },
  }));
  const maaMenu = [
    ...optionItems,
    { type: "separator" },
    {
      label: "授权一次开游戏",
      click: () => {
        request("maa_authorize", {}).catch((err) => elog(`maa_authorize ${err}`));
      },
    },
    {
      label: "打开游戏",
      click: () => {
        request("maa_open_game", {}).catch((err) => elog(`maa_open_game ${err}`));
      },
    },
    {
      label: "开始清日常",
      click: () => {
        request("maa_start_daily", {}).catch((err) => elog(`maa_start_daily ${err}`));
      },
    },
    {
      label: "停止",
      click: () => {
        request("maa_stop", {}).catch((err) => elog(`maa_stop ${err}`));
      },
    },
  ];
  const menu = Menu.buildFromTemplate([
    { label: "打开看板", click: () => emit("open_board", {}) },
    { type: "separator" },
    { label: "明日方舟", submenu: maaMenu },
    { type: "separator" },
    { label: "待机", click: () => win.webContents.send("play-motion", "Idle") },
    { label: "疑问", click: () => win.webContents.send("play-motion", "Talk") },
    { label: "惊讶", click: () => win.webContents.send("play-motion", "Tap") },
    { label: "烦躁", click: () => win.webContents.send("play-motion", "Fail") },
    { label: "我的愿望", click: () => win.webContents.send("play-motion", "Wish") },
    { type: "separator" },
    { label: "大小 1x", click: () => setScale(1) },
    { label: "大小 1.5x", click: () => setScale(1.5) },
    { label: "大小 2x", click: () => setScale(2) },
    { type: "separator" },
    {
      label: "锁定右下角",
      type: "checkbox",
      checked: pinned,
      click: (item) => setPinned(item.checked),
    },
    {
      label: "点击穿透",
      type: "checkbox",
      checked: clickThrough,
      click: (item) => setClickThrough(item.checked),
    },
    { label: "隐藏", click: () => emit("hide_pet", {}) },
    { label: "退出", click: () => emit("quit", {}) },
  ]);
  menu.popup({ window: win });
}

function setScale(scale) {
  const origin = characterOrigin();
  currentScale = Number(scale);
  applyWindowLayout(origin);
  const lay = layoutFor(currentScale);
  win.webContents.send("set-layout", lay);
  emit("persist_scale", { scale: currentScale });
  persist();
}

function persist() {
  if (!win) {
    return;
  }
  const origin = characterOrigin();
  emit("persist", { x: origin.x, y: origin.y });
}

function snapToCorner() {
  if (!win) {
    return;
  }
  const { petW, petH, bubbleW } = layoutFor(currentScale);
  const origin = characterOrigin();
  const display = screen.getDisplayNearestPoint({ x: origin.x, y: origin.y });
  const work = display.workArea;
  const bounds = display.bounds;
  let x = work.x + work.width - petW;
  let y = bounds.y + bounds.height - petH - PIN_LIFT_Y;
  const maxX = work.x + Math.max(0, work.width - petW);
  const maxY = bounds.y + Math.max(0, bounds.height - petH);
  x = Math.min(Math.max(x, work.x), maxX);
  y = Math.min(Math.max(y, bounds.y), maxY);
  win.setBounds({
    x: x - bubbleW,
    y,
    width: petW + bubbleW,
    height: petH,
  });
}

function setPinned(next) {
  pinned = Boolean(next);
  if (pinned) {
    snapToCorner();
  }
  emit("persist_pin", { pin: pinned });
  persist();
}

function applyMouseIgnore() {
  if (!win) {
    return;
  }
  if (clickThrough || lastIgnoreRequest) {
    win.setIgnoreMouseEvents(true, { forward: true });
    return;
  }
  win.setIgnoreMouseEvents(false);
}

function setClickThrough(next) {
  clickThrough = Boolean(next);
  applyMouseIgnore();
  emit("persist_click_through", { click_through: clickThrough });
}

process.on("uncaughtException", (err) => {
  elog(`uncaughtException ${err && err.stack ? err.stack : err}`);
});

app.whenReady().then(async () => {
  elog(`argv ${process.argv.join(" ")}`);
  registerModelProtocol();
  await connectBridge();
  createWindow();
});

app.on("window-all-closed", () => {
  app.quit();
});

ipcMain.on("ignore-mouse", (_e, ignore) => {
  lastIgnoreRequest = Boolean(ignore);
  applyMouseIgnore();
});

ipcMain.on("drag-by", (_e, dx, dy) => {
  if (!win) {
    return;
  }
  const moveX = Number(dx);
  const moveY = Number(dy);
  if (!Number.isFinite(moveX) || !Number.isFinite(moveY)) {
    return;
  }
  const { petH } = layoutFor(currentScale);
  const [x, y] = win.getPosition();
  win.setBounds({
    x: Math.round(x + moveX),
    y: Math.round(y + moveY),
    width: windowWidth(),
    height: petH,
  });
});

ipcMain.on("drag-end", () => {
  if (pinned) {
    snapToCorner();
  }
  persist();
});

ipcMain.on("context-menu", () => {
  popupMenu();
});

ipcMain.on("open-board", () => {
  emit("open_board", {});
});

ipcMain.on("toggle-chat", () => {
  emit("toggle_chat", {});
});

ipcMain.handle("set-bubble", (_e, open) => {
  applyBubble(open);
});

ipcMain.on("model-ready", () => {
  const origin = characterOrigin();
  elog("模型就绪");
  emit("ready", { hwnd: nativeHwnd(), x: origin.x, y: origin.y, scale: START_SCALE });
  persist();
});

ipcMain.on("model-failed", (_e, message) => {
  elog(`模型失败 ${message}`);
  emit("fail", { error: String(message || "Live2D 模型加载失败。") });
});

ipcMain.handle("call", async (_e, method, params) => {
  return request(method, params);
});

ipcMain.on("set-scale", (_e, scale) => {
  setScale(Number(scale));
});
