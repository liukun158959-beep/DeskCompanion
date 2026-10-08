function report(state: "loading" | "ready" | "error", message?: string): void {
  window.dispatchEvent(new CustomEvent("desk-startup", { detail: { state, message } }));
}

export function startupStatus(message: string): void {
  report("loading", message);
}

export function startupReady(): void {
  // 等待 React 把就绪后的主界面提交到屏幕，再开始淡出。
  requestAnimationFrame(() => report("ready"));
}

export function startupFailed(error: unknown): void {
  report("error", error instanceof Error ? error.message : String(error));
}
