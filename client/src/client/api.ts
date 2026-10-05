import { invoke } from "@tauri-apps/api/core";

export type BackendInfo = { port: number; token: string };

export type ChatItem = { role: string; text: string; ts?: string };

export type SessionItem = {
  id: string;
  title: string;
  updated: string;
  count: number;
};

type RpcEnvelope<T> = { ok: boolean; result?: T; error?: string };

export async function backendInfo(): Promise<BackendInfo> {
  return invoke<BackendInfo>("backend_info");
}

function wsUrl(info: BackendInfo): string {
  return `ws://127.0.0.1:${info.port}/ws?token=${info.token}`;
}

export type StreamHandlers = {
  onToken: (piece: string) => void;
  onStatus: (text: string) => void;
  onDone: (answer: string) => void;
  onError: (message: string) => void;
};

export function streamChat(info: BackendInfo, text: string, handlers: StreamHandlers): void {
  const ws = new WebSocket(wsUrl(info));
  ws.onopen = () => ws.send(JSON.stringify({ type: "chat", text }));
  ws.onmessage = (ev) => {
    const msg = JSON.parse(String(ev.data)) as { type: string; data?: string };
    if (msg.type === "token") handlers.onToken(msg.data || "");
    else if (msg.type === "status") handlers.onStatus(msg.data || "");
    else if (msg.type === "done") {
      handlers.onDone(msg.data || "");
      ws.close();
    } else if (msg.type === "error") {
      handlers.onError(msg.data || "对话失败");
      ws.close();
    }
  };
  ws.onerror = () => handlers.onError("连不上本地后端。恢复：看桌宠日志后重启客户端");
}

export function rpc<T>(
  info: BackendInfo,
  method: string,
  args: Record<string, unknown> = {},
): Promise<T> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl(info));
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "rpc", id: method, method, args }));
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(String(ev.data)) as {
        type: string;
        result?: RpcEnvelope<T>;
        data?: string;
      };
      ws.close();
      if (msg.type === "rpc_result" && msg.result?.ok) {
        resolve(msg.result.result as T);
        return;
      }
      reject(new Error(msg.result?.error || msg.data || "RPC 失败"));
    };
    ws.onerror = () => reject(new Error("连不上本地后端。恢复：看桌宠日志后重启客户端"));
  });
}
