/// <reference types="vite/client" />

// 分析按钮的对照表。只解析技能正文里的 maa-rules，不调用模型。

export type RuleSource = "rule" | "doc";

export type MaaRule = {
  id: string;
  match: "all" | "any";
  keywords: string[];
  source: RuleSource;
  text: string;
};

export type LogItem = {
  source?: string;
  kind?: string;
  time?: string;
  title?: string;
  text?: string;
};

export type AnalysisHit = {
  id: string;
  source: RuleSource;
  text: string;
};

export type Analysis =
  | { kind: "empty" }
  | { kind: "none" }
  | { kind: "hits"; hits: AnalysisHit[] }
  | { kind: "bad"; message: string };

const FENCE = /```maa-rules\s*([\s\S]*?)```/;

export function sourceLabel(source: RuleSource): string {
  return source === "doc" ? "文档原句" : "桌宠规则";
}

export function parseRules(body: string): MaaRule[] {
  const found = body.match(FENCE);
  if (!found) {
    throw new Error("技能里没有 maa-rules 对照表。恢复：检查 skills/maa-log-analysis/SKILL.md。");
  }
  let raw: unknown;
  try {
    raw = JSON.parse(found[1]);
  } catch (err) {
    throw new Error(`对照表不是合法 JSON：${String(err)}。恢复：检查 skills/maa-log-analysis/SKILL.md。`);
  }
  if (!Array.isArray(raw) || raw.length === 0) {
    throw new Error("对照表是空的。恢复：检查 skills/maa-log-analysis/SKILL.md。");
  }
  return raw.map((row, index) => readRule(row, index));
}

function readRule(row: unknown, index: number): MaaRule {
  if (!row || typeof row !== "object") {
    throw new Error(`对照表第 ${index + 1} 条不是对象。恢复：检查 skills/maa-log-analysis/SKILL.md。`);
  }
  const item = row as Record<string, unknown>;
  const id = typeof item.id === "string" ? item.id.trim() : "";
  const match = item.match === "all" || item.match === "any" ? item.match : "";
  const source = item.source === "rule" || item.source === "doc" ? item.source : "";
  const text = typeof item.text === "string" ? item.text.trim() : "";
  const keywords = Array.isArray(item.keywords)
    ? item.keywords.filter((word): word is string => typeof word === "string" && word.trim().length > 0)
    : [];
  if (!id || !match || !source || !text || keywords.length === 0) {
    throw new Error(`对照表第 ${index + 1} 条缺字段。恢复：检查 skills/maa-log-analysis/SKILL.md。`);
  }
  return { id, match, keywords, source, text };
}

function hit(rule: MaaRule, text: string): boolean {
  if (rule.match === "all") return rule.keywords.every((word) => text.includes(word));
  return rule.keywords.some((word) => text.includes(word));
}

// 按单条出错原文匹配。几条日志拼在一起不算命中。
export function matchRules(items: LogItem[], rules: MaaRule[]): Analysis {
  const segments = items
    .map((item) => `${item.title || ""}\n${item.text || ""}`.trim())
    .filter((text) => text.length > 0);
  if (segments.length === 0) return { kind: "empty" };
  const hits: AnalysisHit[] = [];
  const seen = new Set<string>();
  for (const rule of rules) {
    if (seen.has(rule.id)) continue;
    if (!segments.some((text) => hit(rule, text))) continue;
    seen.add(rule.id);
    hits.push({ id: rule.id, source: rule.source, text: rule.text });
  }
  if (hits.length === 0) return { kind: "none" };
  return { kind: "hits", hits };
}
