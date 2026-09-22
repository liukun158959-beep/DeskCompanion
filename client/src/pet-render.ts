// Spike A 渲染层：先用一张咕嘎静态帧验证透明窗与穿透，Live2D 阶段再替换。
// 关键：保留一份离屏像素数据，供 hit-test 读取某点的 alpha。

let offscreen: HTMLCanvasElement | null = null;
let offCtx: CanvasRenderingContext2D | null = null;
let drawW = 0;
let drawH = 0;
let offsetX = 0;
let offsetY = 0;

// 把咕嘎帧画到主 canvas，居中等比缩放；同时画进离屏 canvas 供 alpha 读取。
export async function renderPet(canvas: HTMLCanvasElement, imgUrl: string): Promise<void> {
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("无法获取 2d 上下文");

  const img = await loadImage(imgUrl);
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  canvas.width = vw;
  canvas.height = vh;

  // 等比缩放到窗口 80% 高度，底部对齐
  const scale = Math.min((vh * 0.9) / img.height, (vw * 0.9) / img.width);
  drawW = img.width * scale;
  drawH = img.height * scale;
  offsetX = (vw - drawW) / 2;
  offsetY = vh - drawH;

  ctx.clearRect(0, 0, vw, vh);
  ctx.drawImage(img, offsetX, offsetY, drawW, drawH);

  offscreen = document.createElement("canvas");
  offscreen.width = vw;
  offscreen.height = vh;
  offCtx = offscreen.getContext("2d", { willReadFrequently: true });
  offCtx!.drawImage(img, offsetX, offsetY, drawW, drawH);
}

// 读取某屏幕坐标处的 alpha（0-255）。角色不透明区域 alpha 高。
export function alphaAt(x: number, y: number): number {
  if (!offCtx) return 0;
  if (x < 0 || y < 0 || x >= offscreen!.width || y >= offscreen!.height) return 0;
  const px = offCtx.getImageData(x, y, 1, 1).data;
  return px[3];
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`加载形象失败: ${url}`));
    img.src = url;
  });
}
