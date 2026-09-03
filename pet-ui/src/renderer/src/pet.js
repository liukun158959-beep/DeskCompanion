import * as PIXI from "pixi.js";
import { Live2DModel } from "pixi-live2d-display/cubism4";

window.PIXI = PIXI;

const PRIORITY_FORCE = 3;

let app = null;
let model = null;
let baseScale = 1;
let userScale = 1.5;
let viewW = 0;
let viewH = 0;
let busy = false;
let playingGroup = "Idle";

export function currentScale() {
  return userScale;
}

function waitFrames(n) {
  return new Promise((resolve) => {
    function step() {
      n -= 1;
      if (n <= 0) {
        resolve();
        return;
      }
      requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });
}

export async function startPet(canvas, modelUrl, scale) {
  if (!window.Live2DCubismCore) {
    throw new Error("Cubism Core 未加载。请确认 pet-ui 已 npm run build。");
  }
  userScale = scale;
  const wrap = canvas.parentElement;
  viewW = wrap.clientWidth;
  viewH = wrap.clientHeight;
  if (viewW <= 1 || viewH <= 1) {
    throw new Error(`画布尺寸无效 ${viewW}x${viewH}。`);
  }
  Live2DModel.registerTicker(PIXI.Ticker);
  app = new PIXI.Application({
    view: canvas,
    backgroundAlpha: 0,
    antialias: true,
    autoDensity: true,
    clearBeforeRender: true,
    preserveDrawingBuffer: true,
    resolution: window.devicePixelRatio || 1,
    width: viewW,
    height: viewH,
  });
  console.log(`加载 Live2D ${modelUrl}`);
  const loaded = Live2DModel.from(modelUrl, { autoInteract: false });
  const timed = new Promise((_, reject) => {
    setTimeout(() => reject(new Error("Live2D 模型加载超时。")), 12000);
  });
  model = await Promise.race([loaded, timed]);
  app.stage.addChild(model);
  await waitFrames(2);
  fitModel();
  bindMotionFinish();
  app.ticker.add(keepTalking);
  playMotion("Idle");
  console.log(
    `模型包围盒 ${model.width}x${model.height} scale=${model.scale.x} pos=${model.x},${model.y}`
  );
  return model;
}

function fitModel() {
  if (!app || !model) {
    return;
  }
  const srcW = model.internalModel.originalWidth;
  const srcH = model.internalModel.originalHeight;
  if (srcW <= 1 || srcH <= 1) {
    throw new Error(`Live2D 模型原始尺寸无效 ${srcW}x${srcH}。`);
  }
  baseScale = Math.min(viewW / srcW, viewH / srcH) * 0.92;
  applyScale();
  model.anchor.set(0.5, 1);
  model.x = viewW * 0.52;
  model.y = viewH * 0.98;
}

function applyScale() {
  const factor = userScale / 1.5;
  model.scale.set(baseScale * factor);
}

export function applyCanvasSize(width, height, scale) {
  viewW = width;
  viewH = height;
  if (scale) {
    userScale = scale;
  }
  if (!app) {
    return;
  }
  app.renderer.resize(viewW, viewH);
  if (model) {
    fitModel();
  }
}

export function setUserScale(scale) {
  userScale = scale;
  applyScale();
}

function resetToDefaults() {
  const core = model.internalModel.coreModel;
  const count = core.getParameterCount();
  for (let i = 0; i < count; i += 1) {
    core.setParameterValueByIndex(i, core.getParameterDefaultValue(i));
  }
}

function bindMotionFinish() {
  model.internalModel.motionManager.on("motionFinish", () => {
    if (playingGroup !== "Idle") {
      resetToDefaults();
    }
  });
}

function keepTalking() {
  if (!busy || !model) {
    return;
  }
  const state = model.internalModel.motionManager.state;
  if (state.currentGroup === "Talk" || state.reservedGroup === "Talk") {
    return;
  }
  playMotion("Talk");
}

export function playMotion(group) {
  if (!model) {
    throw new Error("模型还没加载完。");
  }
  playingGroup = group;
  model.motion(group, undefined, PRIORITY_FORCE);
}

export function setBusy(nextBusy) {
  if (!model) {
    return;
  }
  busy = Boolean(nextBusy);
  const core = model.internalModel.coreModel;
  core.setParameterValueById("Param4", busy ? 1 : 0);
  core.setParameterValueById("Param5", busy ? 1 : 0);
  if (busy) {
    playMotion("Talk");
    return;
  }
  model.internalModel.motionManager.stopAllMotions();
  resetToDefaults();
  playMotion("Idle");
}

const ALPHA_HIT = 16;
const PIXEL = new Uint8Array(4);

export function hitModel(clientX, clientY) {
  if (!model || !app) {
    return false;
  }
  const view = app.view;
  const rect = view.getBoundingClientRect();
  const cssX = clientX - rect.left;
  const cssY = clientY - rect.top;
  if (cssX < 0 || cssY < 0 || cssX >= rect.width || cssY >= rect.height) {
    return false;
  }
  const renderer = app.renderer;
  const gl = renderer.gl;
  if (!gl) {
    throw new Error("渲染器没有 WebGL，无法做像素命中。");
  }
  renderer.renderTexture.bind(null);
  const scaleX = view.width / rect.width;
  const scaleY = view.height / rect.height;
  const px = Math.min(view.width - 1, Math.max(0, Math.floor(cssX * scaleX)));
  const py = Math.min(view.height - 1, Math.max(0, Math.floor(cssY * scaleY)));
  gl.readPixels(px, view.height - 1 - py, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, PIXEL);
  return PIXEL[3] > ALPHA_HIT;
}

export function focusAt(clientX, clientY) {
  if (!model || !app) {
    return;
  }
  const rect = app.view.getBoundingClientRect();
  model.focus(clientX - rect.left, clientY - rect.top);
}
