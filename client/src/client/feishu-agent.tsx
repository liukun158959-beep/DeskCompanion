import { useEffect, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { Button } from "reend-components";
import { rpc, type BackendInfo } from "./api";

export type FeishuAgentStatus = {
  ok: boolean; enabled: boolean; connected: boolean; state: string;
  error: string; diagnostic: string; last_reply: string;
  binding: { app_id?: string; app_name?: string; owner_name?: string; owner_id?: string };
};

const STATES: Record<string, string> = {
  stopped: "未接入", connecting: "正在连接", connected: "已接入", reconnecting: "正在重连", error: "接入未成功",
};

export function FeishuAgentPane({ info, debug = false }: { info: BackendInfo | null; debug?: boolean }) {
  const [snap, setSnap] = useState<FeishuAgentStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!info || debug) return;
    let active = true;
    const refresh = async () => {
      try {
        const value = await rpc<FeishuAgentStatus>(info, "load_feishu_agent");
        if (active) setSnap(value);
      } catch (err) { if (active) setError(String(err)); }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, [info, debug]);

  async function change(start: boolean) {
    if (!info || debug || busy) return;
    setBusy(true); setError("");
    try {
      const value = await rpc<FeishuAgentStatus>(info, start ? "start_feishu_agent" : "stop_feishu_agent");
      if (!value.ok) throw new Error(value.error || "飞书接入未成功。");
      setSnap(value);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  const working = snap?.state === "connected" || snap?.state === "connecting" || snap?.state === "reconnecting";
  return <section className="mt-10 max-w-2xl rounded-xl border border-border p-5" aria-label="飞书桌宠 Agent">
    <h2 className="text-base font-semibold">在飞书使用桌宠 Agent</h2>
    <p className="mt-2 text-sm leading-6 text-muted-foreground">
      接入本机飞书 CLI 已配置的应用。接入后，你可以在飞书私聊机器人，使用桌宠的模型、技能、知识库和工具。
      仅接受绑定的登录用户；桌宠需要保持运行，聊天历史与桌面当前对话分开保存。
    </p>
    <p className="mt-4 text-sm" data-feishu-agent-state>{STATES[snap?.state || "stopped"] || "读取状态中"}</p>
    {snap?.binding?.app_id ? <p className="mt-2 text-sm text-muted-foreground">
      应用：{snap.binding.app_name || snap.binding.app_id}<br />
      允许私聊：{snap.binding.owner_name || snap.binding.owner_id}
    </p> : null}
    {error || snap?.error ? <p role="alert" className="mt-3 whitespace-pre-wrap text-sm text-destructive">{error || snap?.error}</p> : null}
    {snap?.diagnostic ? <p className="mt-2 text-sm text-muted-foreground">{snap.diagnostic}</p> : null}
    {snap?.last_reply ? <p className="mt-2 text-xs text-muted-foreground">最近回复：{snap.last_reply}</p> : null}
    <div className="mt-4 flex gap-3">
      <Button type="button" variant="primary" size="sm" disabled={busy || working || !info || debug} onClick={() => void change(true)}>
        {snap?.state === "error" ? "重新接入" : "接入飞书"}
      </Button>
      <Button type="button" variant="secondary" size="sm" disabled={busy || (!working && !snap?.enabled) || !info || debug} onClick={() => void change(false)}>停止接入</Button>
    </div>
    <p className="mt-4 text-xs leading-6 text-muted-foreground">
      在应用后台开启机器人能力，选择长连接订阅「接收消息」事件，并开通接收单聊消息、以应用身份发送消息权限后发布。
      私聊发送 /help 查看指令，/new 开新对话，/skills 查看技能，/kb 提问知识库。
    </p>
    <button type="button" className="mt-2 text-xs underline" onClick={() => {
      const url = "https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case";
      if (isTauri()) void invoke("open_link", { url }); else window.open(url, "_blank", "noopener");
    }}>查看飞书官方长连接开发文档</button>
  </section>;
}
