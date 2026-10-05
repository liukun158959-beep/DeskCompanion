// 四张状态卡只转述接口里已有的字段。没有的连接信息不编。

export type StatusKind = "feishu" | "github" | "maa" | "skland";

export type StatusView = {
  kind: StatusKind;
  title: string;
  state: "loading" | "ready" | "off" | "error";
  line: string;
};

const TITLES: Record<StatusKind, string> = {
  feishu: "飞书",
  github: "GitHub",
  maa: "MAA",
  skland: "森空岛",
};

export const STATUS_KINDS: StatusKind[] = ["feishu", "github", "maa", "skland"];

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function loadingStatuses(): StatusView[] {
  return STATUS_KINDS.map((kind) => ({
    kind,
    title: TITLES[kind],
    state: "loading",
    line: "读取中…",
  }));
}

export function statusError(kind: StatusKind, message: string): StatusView {
  return { kind, title: TITLES[kind], state: "error", line: message || "读取失败。" };
}

export function statusFromPayload(kind: StatusKind, data: unknown): StatusView {
  const title = TITLES[kind];
  if (!data || typeof data !== "object") {
    return { kind, title, state: "error", line: "返回不是对象。" };
  }
  const row = data as Record<string, unknown>;
  if (row.ok === false) {
    return { kind, title, state: "error", line: text(row.error) || text(row.hint) || "读取失败。" };
  }
  if (kind === "feishu") {
    if (row.logged_in === true) {
      const name = text(row.user_name);
      return { kind, title, state: "ready", line: name ? `已登录 ${name}` : "已登录" };
    }
    return { kind, title, state: "off", line: text(row.hint) || text(row.error) || "未登录" };
  }
  if (kind === "github") {
    const login = text(row.login);
    const repos = Array.isArray(row.repos) ? row.repos.length : null;
    const line = login ? `已登录 ${login}` : "已登录";
    return { kind, title, state: "ready", line: repos === null ? line : `${line}，${repos} 个仓库` };
  }
  if (kind === "maa") {
    return { kind, title, state: "ready", line: text(row.message) || text(row.status) || "已连接" };
  }
  if (row.has_token === false) {
    return { kind, title, state: "off", line: text(row.hint) || "未配置" };
  }
  if (row.synced === true && row.ap != null) {
    const max = row.ap_max;
    return {
      kind,
      title,
      state: "ready",
      line: max == null ? `理智 ${row.ap}` : `理智 ${row.ap}/${max}`,
    };
  }
  return { kind, title, state: "off", line: text(row.hint) || "未同步" };
}

export function StatusGrid(props: { cards: StatusView[] }) {
  if (props.cards.length === 0) return null;
  return (
    <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {props.cards.map((card) => (
        <article
          key={card.kind}
          data-status={card.kind}
          data-state={card.state}
          className="rounded-2xl bg-panel px-4 py-3"
        >
          <div className="text-xs text-muted">{card.title}</div>
          <div
            data-status-line
            className={`mt-1 text-sm leading-6 ${card.state === "error" ? "text-red-700 dark:text-red-300" : ""}`}
          >
            {card.line}
          </div>
        </article>
      ))}
    </div>
  );
}
