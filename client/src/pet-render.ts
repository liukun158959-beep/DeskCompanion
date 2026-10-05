// 宠物渲染：kaltsit Live2D（迁移自 pet-ui/src/renderer/src/pet.js，改写为 TS）。
// 弃用 guga 静态帧。对外暴露 modelBounds() 供 Rust 穿透 hit-test。
import * as PIXI from "pixi.js";
import { Live2DModel, MotionPriority } from "pixi-live2d-display/cubism4";

(window as unknown as { PIXI: typeof PIXI }).PIXI = PIXI;

let app: PIXI.Application | null = null;
let model: Live2DModel | null = null;
let lastMotion = "";

const HEADROOM = 72;

function waitFrames(n: number): Promise<void> {
  return new Promise((resolve) => {
    const step = () => {
      n -= 1;
      if (n <= 0) resolve();
      else requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

export async function startPet(canvas: HTMLCanvasElement, modelUrl: string): Promise<void> {
  if (!(window as unknown as { Live2DCubismCore?: unknown }).Live2DCubismCore) {
    throw new Error("Cubism Core 未加载。确认 public/Core/live2dcubismcore.js 存在。");
  }
  const wrap = canvas.parentElement!;
  const viewW = wrap.clientWidth;
  const viewH = wrap.clientHeight;
  if (viewW <= 1 || viewH <= 1) throw new Error(`画布尺寸无效 ${viewW}x${viewH}`);

  Live2DModel.registerTicker(PIXI.Ticker);
  app = new PIXI.Application({
    view: canvas,
    backgroundAlpha: 0,
    antialias: true,
    autoDensity: true,
    resolution: window.devicePixelRatio || 1,
    width: viewW,
    height: viewH,
  });

  model = await Live2DModel.from(modelUrl, { autoInteract: false });
  app.stage.addChild(model);
  await waitFrames(2);

  const srcW = model.internalModel.originalWidth;
  const srcH = model.internalModel.originalHeight;
  const fitH = Math.max(1, viewH - HEADROOM);
  const baseScale = Math.min(viewW / srcW, fitH / srcH);
  model.scale.set(baseScale);
  model.anchor.set(0.5, 1);
  model.x = viewW * 0.5;
  model.y = viewH - 4;
  await playMotion("Idle");
}

export function currentMotion(): string {
  return lastMotion;
}

// 待机用低优先级，点一下的 Tap 能盖过它。播不出来就抛，不假装在动。
export async function playMotion(group: string): Promise<void> {
  if (!model) {
    throw new Error("形象还没加载。恢复：确认 public/Core 和 public/skins/kaltsit 都在。");
  }
  const priority = group === "Idle" ? MotionPriority.IDLE : MotionPriority.NORMAL;
  const ok = await model.motion(group, undefined, priority);
  const playing = model.internalModel.motionManager.state.currentPriority;
  if (!ok && !(group === "Idle" && playing === MotionPriority.IDLE)) {
    throw new Error(`动作「${group}」没有播出来。恢复：检查模型里的 ${group} 动作组。`);
  }
  lastMotion = group;
}

// 角色渲染包围盒（CSS 逻辑像素，窗口相对坐标），供 Rust 穿透判定。
export function modelBounds(): { x: number; y: number; w: number; h: number } | null {
  if (!model) return null;
  const b = model.getBounds();
  return { x: b.x, y: b.y, w: b.width, h: b.height };
}
