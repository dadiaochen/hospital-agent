export function createIdempotencyKey(prefix: "run" | "confirm"): string {
  const randomPart = globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `ui-${prefix}-${randomPart}`;
}
