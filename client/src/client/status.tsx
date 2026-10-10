import { Card, CardBody, CardHeader, CardTitle } from "reend-components";

// 状态卡只转述接口里已有的字段。没有的连接信息不编。

export type StatusKind = "feishu" | "github";

export type StatusView = {
  kind: StatusKind;
  title: string;
  state: "loading" | "ready" | "off" | "error";
  line: string;
};

const TITLES: Record<StatusKind, string> = {
  feishu: "飞书",
  github: "GitHub",
};

export const STATUS_KINDS: StatusKind[] = ["feishu", "github"];

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
    if (row.login_busy === true) {
      return { kind, title, state: "off", line: "正在等授权" };
    }
    return { kind, title, state: "off", line: text(row.hint) || text(row.error) || "未登录" };
  }
  if (kind === "github") {
    const login = text(row.login);
    const repos = Array.isArray(row.repos) ? row.repos.length : null;
    const line = login ? `已登录 ${login}` : "已登录";
    return { kind, title, state: "ready", line: repos === null ? line : `${line}，${repos} 个仓库` };
  }
  return { kind, title, state: "off", line: "未连接" };
}

export function StatusGrid(props: { cards: StatusView[]; onOpenFeishu?: () => void }) {
  if (props.cards.length === 0) return null;
  return (
    <div className="mt-6 grid gap-3 sm:grid-cols-2">
      {props.cards.map((card) => {
        const open = card.kind === "feishu" ? props.onOpenFeishu : undefined;
        const target = open ? "feishu" : undefined;
        return (
          <Card
            key={card.kind}
            data-status={card.kind}
            data-state={card.state}
            data-open={target}
            hoverable
            role={open ? "button" : undefined}
            tabIndex={open ? 0 : undefined}
            className={open ? "cursor-pointer text-left" : undefined}
            onClick={open || undefined}
            onKeyDown={
              open
                ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      open();
                    }
                  }
                : undefined
            }
          >
            <CardHeader>
              <CardTitle className="text-xs text-muted-foreground">{card.title}</CardTitle>
            </CardHeader>
            <CardBody>
              <div data-status-line className={`text-sm leading-6 ${card.state === "error" ? "text-destructive" : ""}`}>
                {card.line}
              </div>
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
}
