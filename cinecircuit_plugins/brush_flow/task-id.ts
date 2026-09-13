// Task keys identify configuration rows, not credentials or security tokens.
let sequence = 0;

export function newTaskId(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return `task-${uuid}`;
  sequence += 1;
  return `task-${Date.now().toString(36)}-${sequence.toString(36)}-${Math.random().toString(36).slice(2)}`;
}
