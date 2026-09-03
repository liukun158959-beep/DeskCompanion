import "./style.css";
import { initBubble } from "./bubble.js";
import {
  startPet,
  playMotion,
  setBusy,
  hitModel,
  focusAt,
  currentScale,
  applyCanvasSize,
} from "./pet.js";

const params = new URLSearchParams(window.location.search);
const modelUrl = params.get("model");
const startScale = Number(params.get("scale") || "1.5");
const startLayout = {
  scale: startScale,
  factor: startScale / 1.5,
  petW: Number(params.get("petW") || "400"),
  petH: Number(params.get("petH") || "500"),
  bubbleW: Number(params.get("bubbleW") || "320"),
};

function applyCssLayout(lay) {
  const factor = lay.factor != null ? lay.factor : lay.scale / 1.5;
  document.documentElement.style.setProperty("--pet-w", lay.petW + "px");
  document.documentElement.style.setProperty("--bubble-w", lay.bubbleW + "px");
  document.documentElement.style.setProperty("--ui-scale", String(factor));
}

function layoutFor(scale) {
  const factor = scale / 1.5;
  return {
    scale,
    factor,
    petW: Math.round(400 * factor),
    petH: Math.round(500 * factor),
    bubbleW: Math.round(320 * factor),
  };
}

applyCssLayout(startLayout);
console.log(`renderer boot href=${window.location.href} model=${modelUrl}`);
if (!modelUrl) {
  throw new Error("缺少 model 参数。");
}

const bubble = initBubble();
const canvas = document.getElementById("live2d");
let dragging = false;
let moved = false;
let lastX = 0;
let lastY = 0;
let lastClickAt = 0;
let ignoringMouse = true;

function setIgnoreMouse(ignore) {
  if (ignore === ignoringMouse) {
    return;
  }
  ignoringMouse = ignore;
  window.petAPI.ignoreMouse(ignore);
}

window.addEventListener("pet-need-mouse", () => {
  setIgnoreMouse(false);
});

try {
  console.log("开始加载模型");
  await startPet(canvas, modelUrl, startScale);
  setIgnoreMouse(true);
  window.petAPI.modelReady();
  console.log("模型就绪已通知");
} catch (err) {
  const message = String(err && err.stack ? err.stack : err);
  console.error(`模型加载失败 ${message}`);
  window.petAPI.modelFailed(message);
  throw err;
}

window.petAPI.onPlayMotion((group) => playMotion(group));
window.petAPI.onSetLayout((lay) => {
  applyCssLayout(lay);
  applyCanvasSize(lay.petW, lay.petH, lay.scale);
});

window.petAPI.onBridge((msg) => {
  const p = msg.params || {};
  switch (msg.event) {
    case "show_chat":
      bubble.showChat();
      break;
    case "show_notice":
      bubble.showNotice();
      break;
    case "show_panel":
      bubble.showPanel(p.panel || "today");
      break;
    case "today_notice":
      bubble.todayNotice(p.text);
      break;
    case "maa_notice":
      bubble.maaNotice(p.text);
      break;
    case "hide_bubble":
      bubble.hideBubble();
      break;
    case "append_message":
      bubble.appendMessage(p.role, p.text);
      break;
    case "load_history":
      bubble.loadHistory(p.rows);
      break;
    case "begin_stream":
      bubble.beginStream();
      break;
    case "append_stream":
      bubble.appendStream(p.piece);
      break;
    case "set_stream_status":
      bubble.setStreamStatus(p.text);
      break;
    case "end_stream":
      bubble.endStream(p.text, p.role);
      break;
    case "set_busy":
      bubble.setBusy(p.busy);
      setBusy(Boolean(p.busy));
      break;
    case "play_motion":
      playMotion(p.group);
      break;
    case "hide_window":
      document.body.style.opacity = "0";
      break;
    case "show_window":
      document.body.style.opacity = "1";
      break;
    default:
      break;
  }
});

window.petAPI.call("load_history", {}).then((rows) => {
  if (rows) {
    bubble.loadHistory(rows);
  }
});

function updateIgnore(ev) {
  const onBubble = bubble.hitBubble(ev.clientX, ev.clientY);
  const onModel = hitModel(ev.clientX, ev.clientY);
  setIgnoreMouse(!(onBubble || onModel || dragging));
}

document.addEventListener("mousemove", (ev) => {
  focusAt(ev.clientX, ev.clientY);
  if (dragging) {
    const dx = ev.screenX - lastX;
    const dy = ev.screenY - lastY;
    if (Math.abs(dx) + Math.abs(dy) > 6) {
      moved = true;
    }
    window.petAPI.dragBy(dx, dy);
    lastX = ev.screenX;
    lastY = ev.screenY;
  }
  updateIgnore(ev);
});

document.addEventListener("mouseleave", () => {
  if (!dragging) {
    setIgnoreMouse(true);
  }
});

canvas.addEventListener("pointerdown", (ev) => {
  if (ev.button === 2) {
    ev.preventDefault();
    openPetMenu(ev.clientX, ev.clientY);
    return;
  }
  if (ev.button !== 0) {
    return;
  }
  if (!hitModel(ev.clientX, ev.clientY)) {
    return;
  }
  dragging = true;
  moved = false;
  lastX = ev.screenX;
  lastY = ev.screenY;
});

window.addEventListener("pointerup", (ev) => {
  if (!dragging) {
    return;
  }
  dragging = false;
  window.petAPI.dragEnd();
  if (moved) {
    return;
  }
  const now = Date.now();
  if (now - lastClickAt < 400) {
    lastClickAt = 0;
    window.petAPI.openBoard();
    return;
  }
  lastClickAt = now;
  if (bubble.isOpen()) {
    void bubble.hideBubble();
    return;
  }
  void bubble.showPanel("today");
});

let lastMenuAt = 0;

function openPetMenu(clientX, clientY) {
  const onBubble = bubble.hitBubble(clientX, clientY);
  const onModel = hitModel(clientX, clientY);
  if (!onBubble && !onModel) {
    return;
  }
  const now = Date.now();
  if (now - lastMenuAt < 400) {
    return;
  }
  lastMenuAt = now;
  window.petAPI.contextMenu();
}

canvas.addEventListener("contextmenu", (ev) => {
  ev.preventDefault();
  openPetMenu(ev.clientX, ev.clientY);
});

document.addEventListener("contextmenu", (ev) => {
  if (ev.target === canvas) {
    return;
  }
  ev.preventDefault();
  openPetMenu(ev.clientX, ev.clientY);
});

window.addEventListener("wheel", (ev) => {
  if (!hitModel(ev.clientX, ev.clientY)) {
    return;
  }
  const cur = currentScale();
  const next = ev.deltaY < 0
    ? (cur < 1.5 ? 1.5 : 2)
    : (cur > 1.5 ? 1.5 : 1);
  if (next === cur) {
    return;
  }
  const lay = layoutFor(next);
  applyCssLayout(lay);
  applyCanvasSize(lay.petW, lay.petH, next);
  window.petAPI.persistScale(next);
});
