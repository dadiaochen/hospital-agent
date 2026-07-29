const relationshipLabels: Record<string, string> = {
  self: "本人",
  father: "父亲",
  mother: "母亲",
};

const statusLabels: Record<string, string> = {
  draft: "待确认",
  confirmed: "已确认（仅本地）",
  rejected: "已拒绝",
  completed: "已完成",
  needs_confirmation: "待用户确认",
  needs_clarification: "需要补充信息",
  blocked: "已拦截",
  running: "运行中",
  waiting_confirmation: "等待确认",
  failed: "失败",
  active: "有效",
  expired: "已过期",
};

export function formatRelationship(value: string): string {
  return relationshipLabels[value] ?? value;
}

export function formatStatus(value: string): string {
  return statusLabels[value] ?? value;
}

export function formatDate(value: string | null): string {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export function formatDateTime(value: string | null): string {
  if (!value) return "未结束";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function describeRecord(record: Record<string, unknown>): string {
  const pairs = Object.entries(record)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .slice(0, 5)
    .map(([key, value]) => `${key}: ${String(value)}`);
  return pairs.length > 0 ? pairs.join("；") : "无结构化内容";
}
