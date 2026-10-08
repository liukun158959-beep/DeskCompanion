/** Core 脚本加载前检查 HTTP 响应，让错误能定位到实际文件。 */
export async function loadCubismCore(url: string, filePath: string): Promise<void> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`读取 Cubism Core 失败（HTTP ${response.status}）。文件：${filePath}`);
    const source = await response.text();
    if (!source.trim() || /^\s*</.test(source) || !source.includes("Live2DCubismCore")) {
      throw new Error(`Cubism Core 文件内容无效，请使用完整的 live2dcubismcore.js。文件：${filePath}`);
    }
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw new Error(`读取 Cubism Core 超时。文件：${filePath}`);
    if (err instanceof TypeError) throw new Error(`连接不到形象素材服务，请重启客户端。文件：${filePath}`);
    throw err;
  } finally { clearTimeout(timeout); }
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    const timer = setTimeout(() => fail("加载超时"), 15000);
    function cleanup() { clearTimeout(timer); script.onload = null; script.onerror = null; }
    function fail(reason: string) {
      cleanup(); script.remove();
      reject(new Error(`Cubism Core ${reason}。文件：${filePath}`));
    }
    script.src = url;
    script.crossOrigin = "anonymous";
    script.onload = () => {
      const core = (window as Window & { Live2DCubismCore?: { Version?: { csmGetVersion?: unknown } } }).Live2DCubismCore;
      if (typeof core?.Version?.csmGetVersion !== "function") { fail("未能初始化，请检查文件是否损坏或版本是否正确"); return; }
      cleanup(); resolve();
    };
    script.onerror = () => fail("脚本加载失败，请检查素材服务和文件类型");
    document.head.appendChild(script);
  });
}

export function petErrorText(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return `形象加载失败：${message.replace(/。+$/, "")}。\n请在主窗口的使用引导中查看素材位置。`;
}
